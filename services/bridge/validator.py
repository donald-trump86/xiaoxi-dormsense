#!/usr/bin/env python3
"""Private node01 validator. Import is offline; only main reads runtime config.

Run one worker. The state directory must already exist, be owned by the process,
and have mode 0700. Keep both sequence.json and sequence.json.lock across restarts;
do not delete damaged state to reset anti-replay protection. A missing lock is
recreated from valid state during quiescent recovery (no other writer running).
Never unlink/replace a lock while writers run: flock protects the stable inode.
Missing state with a surviving lock fails closed. A previously initialized Gate also refuses loss of both files.
A NEW process cannot distinguish total durable loss from first use: operators
MUST NOT replace the state volume with an empty directory or delete both files;
restore trusted high-water state before restart, never guess an empty baseline.
MQTT5 retainAsPublished preserves publisher RETAIN even for live deliveries;
this private consumer choice leaves UNO MQTT3.1.1 and v1 payload/topics intact.
MQTT sessions are recreated after close-first abort to discard pending packets.
A single unfinished public publish Info is allowed, not a payload retry buffer.
The 5s monotonic send budget is soft: checks run around each blocking loop;
OS/TLS buffers and scheduling can exceed it. This is NOT a hard deadline or
complete source-age guarantee. Sequence persistence may deliberately lose data.
"""

import argparse
import fcntl
import json
import logging
import os
from pathlib import Path
import re
import socket
import stat
import sys
import tempfile
import threading
import time
from types import SimpleNamespace

# Keep check_repository.ROOT tied to its original file, never rewrite its ROOT.
REPOSITORY = Path(__file__).resolve().parents[2]
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))
from scripts import check_repository


LOGGER = logging.getLogger("validator")
RAW_TELEMETRY = "xiaoxi/dorm/node01/telemetry"
RAW_STATUS = "xiaoxi/dorm/node01/status"
VALIDATED_TELEMETRY = "xiaoxi/validated/node01/telemetry"
VALIDATED_STATUS = "xiaoxi/validated/node01/status"
MAX_UINT32 = 4294967295
READY_TIMEOUT_SECONDS = 10.0
SEND_BUDGET_SECONDS = 5.0
LOCK_MARKER = b"sequence-gate-v1\n"
BOOT_PATTERN = re.compile(r"node01-([0-9a-f]{8})")


class Rejected(ValueError):
    """Only a fixed reason code; never include payload or nested exception text."""


def _reject_constant(_value):
    raise Rejected("NONFINITE")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Rejected("DUPLICATE_KEYS")
        result[key] = value
    return result


def _decode_object(raw: bytes) -> dict:
    if not isinstance(raw, bytes):
        raise Rejected("INPUT_TYPE")
    if len(raw) > 1024:
        raise Rejected("SIZE")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeError:
        raise Rejected("UTF8") from None
    try:
        payload = json.loads(
            text, object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except Rejected:
        raise
    except (ValueError, OverflowError, RecursionError):
        raise Rejected("JSON") from None
    if not isinstance(payload, dict):
        raise Rejected("OBJECT")
    return payload


def _segment(payload: dict) -> tuple[int, int]:
    if not isinstance(payload, dict):
        raise Rejected("SEGMENT")
    boot_id = payload.get("boot_id")
    match = BOOT_PATTERN.fullmatch(boot_id) if isinstance(boot_id, str) else None
    count = int(match.group(1), 16) if match else 0
    sequence = payload.get("sequence")
    if not 1 <= count <= MAX_UINT32:
        raise Rejected("BOOT_ID")
    if type(sequence) is not int or not 0 <= sequence <= MAX_UINT32:
        raise Rejected("SEQUENCE_TYPE")
    return count, sequence


def decode_telemetry(raw: bytes, topic: str) -> dict:
    """Full repository schema AND semantics, then the private node01 boundary."""
    if topic != RAW_TELEMETRY:
        raise Rejected("TOPIC")
    payload = _decode_object(raw)
    try:
        check_repository.validate_telemetry(payload, topic)
    except Exception:
        # Schema exceptions embed instance values. Never pass them to logging.
        raise Rejected("CONTRACT") from None
    if payload.get("node_id") != "node01" or payload.get("simulated") is not False:
        raise Rejected("SOURCE")
    _segment(payload)
    return payload


def decode_status(raw: bytes, topic: str) -> dict:
    """Status is exactly the v1 protocol's three fields; no telemetry schema."""
    if topic != RAW_STATUS:
        raise Rejected("TOPIC")
    payload = _decode_object(raw)
    if (
        set(payload) != {"schema_version", "node_id", "state"}
        or payload["schema_version"] != "1.0"
        or payload["node_id"] != "node01"
        or payload["state"] not in ("online", "offline")
    ):
        raise Rejected("STATUS")
    return payload


def _private_file(fd: int) -> None:
    info = os.fstat(fd)
    if (
        not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
    ):
        raise Rejected("STATE_PERMISSIONS")


def _read_state(path: Path) -> tuple[int, int]:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        _private_file(fd)
        with os.fdopen(fd, "rb", closefd=False) as stream:
            payload = _decode_object(stream.read(1025))
    finally:
        os.close(fd)
    if set(payload) != {"boot_count", "sequence"}:
        raise Rejected("STATE_INVALID")
    count, sequence = payload["boot_count"], payload["sequence"]
    if (
        type(count) is not int or not 1 <= count <= MAX_UINT32
        or type(sequence) is not int or not 0 <= sequence <= MAX_UINT32
    ):
        raise Rejected("STATE_INVALID")
    return count, sequence


class SequenceGate:
    """Linearize read/compare/fsync/replace across instances with a stable lock.

    Single worker is the runtime contract. Independent Gate instances still
    cannot accept a replay: each takes flock and reloads durable high-water state.
    A durable lock marker also distinguishes pristine startup from lost state.
    """

    def __init__(self, state_path: Path):
        self.path = Path(state_path).absolute()
        self.lock_path = self.path.with_name(self.path.name + ".lock")
        self._thread_lock = threading.Lock()
        self._observed_state = False

    def accept(self, payload: dict) -> bool:
        try:
            candidate = _segment(payload)
            with self._thread_lock:
                return self._accept_locked(candidate)
        except Rejected as exc:
            LOGGER.warning("%s", str(exc))
        except Exception:
            LOGGER.warning("STATE_IO")
        return False

    def _accept_locked(self, candidate: tuple[int, int]) -> bool:
        dir_fd = os.open(
            self.path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        lock_fd = None
        try:
            info = os.fstat(dir_fd)
            if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise Rejected("STATE_DIRECTORY")
            try:
                lock_fd = os.open(
                    self.lock_path,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                )
                created = True
            except FileExistsError:
                lock_fd = os.open(self.lock_path, os.O_RDWR | os.O_NOFOLLOW)
                created = False
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            _private_file(lock_fd)
            if created:
                with os.fdopen(lock_fd, "wb", closefd=False) as stream:
                    stream.write(LOCK_MARKER)
                    stream.flush()
                    os.fsync(lock_fd)
                os.fsync(dir_fd)
            elif os.read(lock_fd, len(LOCK_MARKER) + 1) != LOCK_MARKER:
                raise Rejected("STATE_LOCK")
            try:
                previous = _read_state(self.path)
            except FileNotFoundError:
                if not created or self._observed_state:
                    raise Rejected("STATE_MISSING") from None
                previous = None
            if previous is not None:
                self._observed_state = True
            if previous is not None and candidate <= previous:
                # Tuple ordering permits a higher boot count with sequence zero.
                return False
            # Latch before write: a partial initialization may lose samples, but
            # deleting its durable evidence cannot reset this existing instance.
            self._observed_state = True
            self._persist(candidate, dir_fd)
            return True
        finally:
            if lock_fd is not None:
                os.close(lock_fd)  # releases flock; NEVER unlink the stable lock
            os.close(dir_fd)

    def _persist(self, candidate: tuple[int, int], dir_fd: int) -> None:
        count, sequence = candidate
        data = json.dumps(
            {"boot_count": count, "sequence": sequence},
            separators=(",", ":"),
        ).encode("ascii")
        fd, name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", dir=self.path.parent,
        )
        temporary = Path(name)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as stream:
                fd = None
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            # mkstemp is in the checked private state directory; no cross-FS move.
            os.replace(temporary, self.path)
            os.fsync(dir_fd)
        finally:
            if fd is not None:
                os.close(fd)
            if temporary.parent == self.path.parent:
                temporary.unlink(missing_ok=True)


def abort_client(client) -> None:
    """Close public TLS/socket first; disconnect must never flush an old outbox."""
    try:
        sock = client.socket()
    except Exception:
        LOGGER.warning("SOCKET_ABORT_FAILED")
        return  # Cannot prove closure: do NOT risk disconnect's implicit write.
    if sock is not None:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass  # Already disconnected is normal; close is still mandatory.
        try:
            sock.close()
        except Exception:
            LOGGER.warning("SOCKET_ABORT_FAILED")
            return
    try:
        client.disconnect()
    except Exception:
        LOGGER.warning("DISCONNECT_FAILED")


class Relay:
    """No telemetry cache/retries; one validated 6/7-byte pre-SUBACK state."""

    def __init__(self, gate: SequenceGate):
        self.gate = gate
        self.connected = False
        self.ready = False
        self.failed = False
        self._subscribe_mid = None
        self._pending_status = None
        self._pending_info = None
        self._send_deadline = None
        self._has_published = False
        self._ready_deadline = None

    def attach(self, client) -> None:
        self.connected = False
        self.ready = False
        self.failed = False
        self._subscribe_mid = None
        self._pending_status = None
        self._pending_info = None
        self._send_deadline = None
        self._has_published = False
        self._ready_deadline = None
        client.on_connect = self.on_connect
        client.on_disconnect = self.on_disconnect
        client.on_subscribe = self.on_subscribe
        client.on_message = self.on_message

    def begin_handshake(self, deadline: float) -> None:
        """Inject the single CONNACK+SUBACK cutoff before connect, never renew it."""
        self._ready_deadline = deadline

    def check_ready(self, client) -> bool:
        """Run and callbacks must check the SAME cutoff before readiness effects."""
        if self.failed:
            return False
        if (
            not self.ready and self._ready_deadline is not None
            and time.monotonic() >= self._ready_deadline
        ):
            self._fail_subscription(client, "READY_TIMEOUT")
            return False
        return True

    def _fail_subscription(self, client, code: str) -> None:
        self.connected = False
        self.ready = False
        self.failed = True
        self._subscribe_mid = None
        self._pending_status = None
        self._pending_info = None
        self._send_deadline = None
        self._ready_deadline = None
        LOGGER.warning("%s", code)
        abort_client(client)

    def check_pending(self, client) -> bool:
        """Single-worker soft budget; never wait_for_publish or loop an old client."""
        if self.failed:
            return False
        if self._pending_info is None:
            return True
        try:
            if self._pending_info.is_published():
                self._pending_info = None
                self._send_deadline = None
                self._has_published = True
                return True
            if time.monotonic() >= self._send_deadline:
                self._fail_subscription(client, "PUBLISH_TIMEOUT")
                return False
        except Exception:
            self._fail_subscription(client, "PUBLISH_FAILED")
            return False
        return True

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if not self.check_ready(client):
            return
        self.connected = reason_code == 0
        self.ready = False
        self._subscribe_mid = None
        self._pending_status = None
        self._pending_info = None
        self._send_deadline = None
        self._has_published = False
        if not self.connected:
            self._fail_subscription(client, "CONNECT_REJECT")
            return
        from paho.mqtt.subscribeoptions import SubscribeOptions

        try:
            # MQTT3.1.1 clears RETAIN on live delivery; v5 RAP prevents that
            # blind spot while also delivering retained startup snapshots.
            if not self.check_ready(client):
                return
            rc, mid = client.subscribe([
                (RAW_TELEMETRY, SubscribeOptions(qos=0, retainAsPublished=True)),
                (RAW_STATUS, SubscribeOptions(qos=1, retainAsPublished=True)),
            ])
            if rc != 0 or type(mid) is not int or not 1 <= mid <= 65535:
                self._fail_subscription(client, "SUBSCRIBE_FAILED")
                return
            self._subscribe_mid = mid
        except Exception:
            self._fail_subscription(client, "SUBSCRIBE_FAILED")

    def on_subscribe(self, client, userdata, mid, reason_code_list, properties):
        if not self.connected or not self.check_ready(client):
            return
        if self._subscribe_mid is None or mid != self._subscribe_mid:
            self._fail_subscription(client, "SUBACK_MID")
            return
        try:
            if not isinstance(reason_code_list, list) or len(reason_code_list) != 2:
                raise ValueError
            failures = [reason.is_failure for reason in reason_code_list]
            if any(type(value) is not bool for value in failures):
                raise ValueError
        except Exception:
            self._fail_subscription(client, "SUBACK_INVALID")
            return
        if any(failures):
            self._fail_subscription(client, "SUBACK_REJECT")
            return
        if not self.check_ready(client):
            return
        snapshot = self._pending_status
        self._subscribe_mid = None
        self._pending_status = None
        self._ready_deadline = None  # Timely SUBACK ends this handshake permanently.
        self.ready = True
        if snapshot is not None:
            # Reconstruct canonical wire JSON; reuse validation/forwarding and
            # never retain a MQTTMessage, arbitrary raw body, topic or telemetry.
            raw = json.dumps({
                "schema_version": "1.0", "node_id": "node01",
                "state": snapshot.decode("ascii"),
            }, separators=(",", ":")).encode("ascii")
            self.on_message(client, None, SimpleNamespace(
                topic=RAW_STATUS, payload=raw, retain=True,
            ))

    def on_disconnect(
        self, client, userdata, disconnect_flags, reason_code, properties,
    ):
        self.connected = False
        self.ready = False
        self._subscribe_mid = None
        self._pending_status = None
        self._pending_info = None
        self._send_deadline = None
        self._has_published = False
        # An unfinished handshake keeps its original cutoff until this attempt ends.

    def on_message(self, client, userdata, message):
        if not self.connected or self.failed or not client.is_connected():
            return
        if not self.check_ready(client):
            return
        if not self.ready:
            if (
                self._subscribe_mid is not None
                and message.topic == RAW_STATUS and message.retain is True
            ):
                try:
                    payload = decode_status(message.payload, message.topic)
                    if not self.check_ready(client):
                        return
                    self._pending_status = payload["state"].encode("ascii")
                except Rejected as exc:
                    LOGGER.warning("%s", str(exc))
            return
        if not self.check_pending(client):
            return
        if self._pending_info is not None:
            self._fail_subscription(client, "PUBLISH_BUSY")
            return  # Drop second input BEFORE decoding or advancing the Gate.
        try:
            if message.topic == RAW_TELEMETRY:
                if message.retain:
                    raise Rejected("RETAINED_TELEMETRY")
                payload = decode_telemetry(message.payload, message.topic)
                if not self.gate.accept(payload):
                    raise Rejected("GATE_REJECT")
                topic, retained, qos = VALIDATED_TELEMETRY, False, 0
            elif message.topic == RAW_STATUS:
                payload = decode_status(message.payload, message.topic)
                topic, retained, qos = VALIDATED_STATUS, True, 1
            else:
                raise Rejected("TOPIC")
        except Rejected as exc:
            LOGGER.warning("%s", str(exc))
            return
        except Exception:
            self._fail_subscription(client, "PUBLISH_FAILED")
            return
        try:
            # Persistence precedes publish: crashes or network races may lose a
            # sample, but it cannot be reused to create fresh HA reception time.
            deadline = time.monotonic() + SEND_BUDGET_SECONDS
            info = client.publish(
                topic,
                json.dumps(payload, separators=(",", ":"), allow_nan=False),
                qos=qos, retain=retained,
            )
            if info.rc != 0:
                self._fail_subscription(client, "PUBLISH_FAILED")
                return
            self._pending_info = info
            self._send_deadline = deadline
            # False here is normal inside paho callbacks: loop_write comes later.
            self.check_pending(client)
        except Exception:
            self._fail_subscription(client, "PUBLISH_FAILED")


def make_client(config: dict, relay: Relay):
    """Called only at runtime; paho import, credentials and CA are deferred."""
    from paho.mqtt import client as mqtt

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="xiaoxi-node01-validator",
        protocol=mqtt.MQTTv5, reconnect_on_failure=False,
    )
    client.username_pw_set(config["username"], config["password"])
    client.tls_set(ca_certs=config["ca_file"])
    client.connect_timeout = 10
    client.reconnect_delay_set(min_delay=1, max_delay=60)
    client.max_inflight_messages_set(1)
    client.max_queued_messages_set(1)
    relay.attach(client)
    return client


def run(config: dict, stop: threading.Event | None = None) -> None:
    """New client on EVERY connection attempt; never reconnect an old outbox."""
    stop = stop if stop is not None else threading.Event()
    relay = Relay(SequenceGate(Path(config["state_path"])))
    delay = 1
    while not stop.is_set():
        client = None
        try:
            client = make_client(config, relay)
            # One deadline spans CONNACK and SUBACK; CONNACK never renews it.
            relay.begin_handshake(time.monotonic() + READY_TIMEOUT_SECONDS)
            client.connect(
                config["host"], config["port"], keepalive=30, clean_start=True,
            )
            while not stop.is_set():
                if not relay.check_pending(client):
                    break
                if not relay.check_ready(client):
                    break
                if client.loop(timeout=1.0) != 0 or relay.failed:
                    break
                if not relay.check_pending(client):
                    break
                if not relay.check_ready(client):
                    break
                # ACK readiness alone does not prove a blocked publish drained.
                if relay.ready and relay._has_published:
                    delay = 1
        except Exception:
            LOGGER.warning("CONNECTION_FAILED")
        finally:
            relay.connected = False
            relay.ready = False
            relay._subscribe_mid = None
            relay._pending_status = None
            relay._pending_info = None
            relay._send_deadline = None
            relay._ready_deadline = None
            if client is not None:
                abort_client(client)
        if not stop.is_set():
            stop.wait(delay)
            delay = min(delay * 2, 60)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", required=True, type=Path,
        help="private 0600 JSON runtime configuration",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    try:
        fd = os.open(args.config, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            _private_file(fd)
            with os.fdopen(fd, "rb", closefd=False) as stream:
                config = _decode_object(stream.read(1025))
        finally:
            os.close(fd)
        keys = {"host", "port", "username", "password", "ca_file", "state_path"}
        if (
            set(config) != keys or type(config["port"]) is not int
            or not 1 <= config["port"] <= 65535
            or config["username"] != "xiaoxi_validator"
            or any(
                not isinstance(config[key], str) or not config[key]
                for key in keys - {"port"}
            )
            or not Path(config["ca_file"]).is_absolute()
            or not Path(config["state_path"]).is_absolute()
        ):
            raise Rejected("CONFIG")
        run(config)
    except KeyboardInterrupt:
        return 0
    except Exception:
        LOGGER.warning("RUNTIME_FAILED")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
