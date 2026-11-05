"""Fixed node02 TLS transport. The chat-facing surface can only arm/cancel learning."""
import json
import re
import ssl
import threading
import time
import uuid

PREFIX = "xiaoxi/dorm/node02"
BOOT = re.compile(r"node02-[0-9a-f]{8}")
PART = re.compile(r"raw_timing capture=([0-9]{1,10}) rawlen=([0-9]{1,5}) kept=([0-9]{1,3}) truncated=([01]) overflow=([01]) offset=([0-9]{1,3}) count=([0-9]{1,2}) unit=us times=([0-9]{1,6}(?:,[0-9]{1,6}){0,15})", re.ASCII)


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result
    def reject(value):
        raise ValueError("nonfinite_json")
    return json.loads(raw, object_pairs_hook=unique, parse_constant=reject)


class CaptureCollector:
    def __init__(self, session_id, boot_id):
        self.session_id, self.boot_id = session_id, boot_id
        self.metadata = None
        self.parts = {}

    def feed(self, event):
        if (event.get("schema_version") != "1.0" or event.get("node_id") != "node02"
                or event.get("simulated") is not False or event.get("boot_id") != self.boot_id
                or type(event.get("sequence")) is not int or not 0 <= event["sequence"] < 2**32):
            raise ValueError("invalid_capture_envelope")
        if event["event_type"] == "ir_learning":
            detail = strict_json(event["detail"])
            if not isinstance(detail, dict) or detail.get("session_id") != self.session_id:
                return None
            if detail.get("kind") == "capture":
                capture = detail.get("capture")
                if (self.metadata is not None or type(capture) is not int or not 0 <= capture < 2**32
                        or capture != (event["sequence"] + 1) % 2**32):
                    raise ValueError("invalid_capture_start")
                self.metadata = detail
            elif detail.get("kind") == "complete":
                if not self.metadata or detail.get("capture") != self.metadata["capture"]:
                    raise ValueError("capture_not_started")
                if not self.parts or 0 not in self.parts:
                    raise ValueError("missing_capture_parts")
                first = self.parts[0]
                rawlen, kept, truncated, overflow = first[:4]
                if (set(self.parts) != set(range(0, kept, 16))
                        or event["sequence"] != (self.metadata["capture"] + (kept + 15) // 16) % 2**32):
                    raise ValueError("missing_capture_parts")
                return {"boot_id": self.boot_id, "capture_sequence": self.metadata["capture"],
                        "rawlen": rawlen, "kept": kept, "truncated": bool(truncated), "overflow": bool(overflow),
                        "timings_us": [duration for offset in sorted(self.parts) for duration in self.parts[offset][4]],
                        "protocol": self.metadata.get("protocol"), "bits": self.metadata.get("bits"),
                        "state": self.metadata.get("state")}
            return None
        if event["event_type"] != "ir_raw_timing" or not self.metadata:
            return None
        match = PART.fullmatch(event.get("detail", ""))
        if not match:
            raise ValueError("invalid_timing_part")
        capture, rawlen, kept, truncated, overflow, offset, count = map(int, match.groups()[:7])
        if capture != self.metadata["capture"]:
            return None
        times = list(map(int, match.group(8).split(",")))
        if (not 1 <= rawlen <= 65535 or kept != min(rawlen, 300) or truncated != int(rawlen > kept)
                or offset % 16 or not 0 <= offset < kept or count != min(16, kept - offset)
                or count != len(times) or any(not 0 < value <= 131070 or value % 2 for value in times)
                or event["sequence"] != (capture + offset // 16) % 2**32 or offset in self.parts):
            raise ValueError("invalid_or_duplicate_timing_part")
        metadata = (rawlen, kept, truncated, overflow)
        if self.parts and metadata != next(iter(self.parts.values()))[:4]:
            raise ValueError("inconsistent_timing_parts")
        self.parts[offset] = (*metadata, times)
        return None


class LearningTransport:
    def __init__(self, config):
        import paho.mqtt.client as mqtt
        self.mqtt = mqtt
        self.condition = threading.Condition()
        self.connected = self.subscribed = self.online = False
        self.responses = {}
        self.collector = None
        self.active_until = None
        self.on_capture = lambda session, capture: None
        self.on_expire = lambda session, reason: None
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id="ir-learning-" + uuid.uuid4().hex[:12],
                                  protocol=mqtt.MQTTv311, clean_session=True,
                                  reconnect_on_failure=True)
        self.client.connect_timeout = 4
        context = ssl.create_default_context(cafile=config["ca_file"])
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.client.tls_set_context(context)
        self.client.tls_insecure_set(False)
        self.client.username_pw_set(config["mqtt_username"], config["mqtt_password"])
        self.host = config["mqtt_host"]
        self.client.on_connect = self._connected
        self.client.on_subscribe = self._subscribed
        self.client.on_disconnect = self._disconnected
        self.client.on_message = self._message
        self.client.reconnect_delay_set(1, 30)
        self.stop = threading.Event()

    def start(self):
        self.client.connect_async(self.host, 8883, 30)
        self.client.loop_start()
        self.watchdog = threading.Thread(target=self._watchdog, daemon=True)
        self.watchdog.start()

    def close(self):
        self.stop.set()
        self.client.disconnect()
        self.client.loop_stop()
        self.watchdog.join(timeout=2)

    def _connected(self, client, userdata, flags, reason, properties):
        with self.condition:
            self.connected = not reason.is_failure
            self.subscribed = self.online = False
            if self.connected:
                client.subscribe([(PREFIX + "/status", 0), (PREFIX + "/event", 0)])
            self.condition.notify_all()

    def _subscribed(self, client, userdata, mid, reasons, properties):
        with self.condition:
            self.subscribed = len(reasons) == 2 and all(not reason.is_failure for reason in reasons)
            self.condition.notify_all()

    def _disconnected(self, client, userdata, flags, reason, properties):
        session = None
        with self.condition:
            self.connected = self.subscribed = self.online = False
            if self.collector:
                session = self.collector.session_id
            self.collector = self.active_until = None
            self.condition.notify_all()
        if session:
            self.on_expire(session, "connection_lost")

    def _message(self, client, userdata, message):
        if len(message.payload) > 2048:
            return
        try:
            event = strict_json(message.payload)
            if not isinstance(event, dict) or event.get("node_id") != "node02" or event.get("schema_version") != "1.0":
                return
            if message.topic == PREFIX + "/status":
                with self.condition:
                    self.online = event.get("state") == "online"
                    self.condition.notify_all()
                return
            if (message.topic != PREFIX + "/event" or message.retain or event.get("simulated") is not False
                    or not isinstance(event.get("boot_id"), str) or not BOOT.fullmatch(event["boot_id"])
                    or not isinstance(event.get("detail"), str) or len(event["detail"]) > 512):
                return
            completed = expired = None
            with self.condition:
                if event.get("event_type") == "ir_learning":
                    detail = strict_json(event["detail"])
                    if not isinstance(detail, dict):
                        return
                    command_id = detail.get("command_id")
                    if command_id in self.responses:
                        self.responses[command_id] = (event, detail)
                    if (self.collector and detail.get("session_id") == self.collector.session_id
                            and detail.get("kind") in {"expired", "cancelled"}):
                        expired = self.collector.session_id
                        self.collector = self.active_until = None
                if self.collector and event.get("event_type") in {"ir_learning", "ir_raw_timing"}:
                    try:
                        capture = self.collector.feed(event)
                    except (ValueError, KeyError, TypeError):
                        expired = self.collector.session_id
                        self.collector = self.active_until = None
                    else:
                        if capture:
                            completed = (self.collector.session_id, capture)
                            self.collector = self.active_until = None
                self.condition.notify_all()
            if completed:
                self.on_capture(*completed)
            if expired:
                self.on_expire(expired, "incomplete_or_expired_capture")
        except (ValueError, KeyError, TypeError, UnicodeDecodeError):
            return

    def _wait(self, predicate, timeout=2):
        deadline = time.monotonic() + timeout
        with self.condition:
            while not predicate():
                if not self.connected:
                    raise ValueError("mqtt_not_connected")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError("node_response_timeout")
                self.condition.wait(min(remaining, .2))

    def _exchange(self, action, fields, expected):
        command_id = uuid.uuid4().hex
        payload = {"schema_version": "1.0", "node_id": "node02", "command_id": command_id,
                   "action": action, "ttl_seconds": 10, **fields}
        with self.condition:
            if not (self.connected and self.subscribed and self.online):
                raise ValueError("receiver_not_ready")
            self.responses[command_id] = None
        try:
            result = self.client.publish(PREFIX + "/command", json.dumps(payload, separators=(",", ":")), qos=0, retain=False)
            if result.rc != self.mqtt.MQTT_ERR_SUCCESS:
                raise ValueError("publish_failed_no_retry")
            self._wait(lambda: self.responses.get(command_id) is not None)
            event, detail = self.responses[command_id]
            if detail.get("kind") != expected:
                raise ValueError("unexpected_node_reply")
            return event, detail
        finally:
            with self.condition:
                self.responses.pop(command_id, None)

    def status(self):
        event, detail = self._exchange("ir_status", {}, "status")
        if (detail.get("version") != "learn1" or type(detail.get("uptime_ms")) is not int
                or not 0 <= detail["uptime_ms"] < 2**32):
            raise ValueError("learning_firmware_required")
        return event["boot_id"], detail["uptime_ms"]

    def arm(self, session_id, seconds):
        boot, uptime = self.status()
        with self.condition:
            self.collector = CaptureCollector(session_id, boot)
            self.active_until = time.monotonic() + seconds + 4
        try:
            self._exchange("ir_learn_start", {"boot_id": boot, "deadline_ms": (uptime + 8000) % 2**32,
                           "session_id": session_id, "window_seconds": seconds}, "ready")
        except Exception:
            with self.condition:
                self.collector = self.active_until = None
            raise

    def cancel(self, session_id):
        # Clear host collection immediately; never block the model lock on a callback.
        with self.condition:
            self.collector = self.active_until = None
        try:
            boot, uptime = self.status()
            self._exchange("ir_learn_cancel", {"boot_id": boot, "deadline_ms": (uptime + 8000) % 2**32,
                           "session_id": session_id}, "cancelled")
        except ValueError:
            pass  # No capture is accepted after local cancellation, even if offline.

    def _watchdog(self):
        while not self.stop.wait(.5):
            session = None
            with self.condition:
                if self.collector and self.active_until and time.monotonic() >= self.active_until:
                    session = self.collector.session_id
                    self.collector = self.active_until = None
            if session:
                self.on_expire(session, "capture_timeout")
