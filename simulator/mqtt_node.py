#!/usr/bin/env python3
"""Synthetic MQTT node. Offline JSONL by default; never represents measurements."""

import argparse
import json
import math
import os
import random
import re
import sys
import threading
import time
import uuid


NODE_PATTERN = re.compile(r"node[0-9]{2,3}\Z")


def make_sample(node_id, boot_id, sequence, rng, uptime=0):
    """Build one synthetic v1 record; no synchronized sensor clock is claimed."""
    return {
        "schema_version": "1.0",
        "node_id": node_id,
        "boot_id": boot_id,
        "timestamp": None,
        "sequence": sequence,
        "simulated": True,
        "temperature": round(rng.uniform(22, 28), 2),
        "humidity": round(rng.uniform(40, 65), 2),
        "light": round(rng.uniform(0.2, 0.8), 3),
        "rssi": rng.randint(-75, -40),
        "uptime": uptime,
        "sensor_status": dict.fromkeys(("temperature", "humidity", "light"), "ok"),
    }


def connect_mqtt(node_id):
    """Optional local-only transport; import paho only when explicitly requested."""
    import paho.mqtt.client as mqtt

    host = os.environ.get("MQTT_HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("This non-TLS demo only permits a loopback broker")
    username = os.environ.get("MQTT_USERNAME")
    password = os.environ.get("MQTT_PASSWORD")
    if not username or not password or password == "REPLACE_WITH_LOCAL_PASSWORD":
        raise ValueError("Set private MQTT_USERNAME and MQTT_PASSWORD environment values")
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"xiaoxi-{node_id}",
        clean_session=True,
        protocol=mqtt.MQTTv311,
    )
    client.username_pw_set(username, password)
    status_topic = f"xiaoxi/dorm/{node_id}/status"
    offline = json.dumps({"schema_version": "1.0", "node_id": node_id, "state": "offline"})
    client.will_set(status_topic, offline, qos=1, retain=True)
    ready = threading.Event()
    accepted = []

    def on_connect(_client, _userdata, _flags, reason_code, _properties):
        accepted.append(not reason_code.is_failure)
        ready.set()

    client.on_connect = on_connect
    client.connect(host, int(os.environ.get("MQTT_PORT", "1883")), keepalive=30)
    client.loop_start()
    if not ready.wait(10) or not accepted[-1]:
        client.disconnect()
        client.loop_stop()
        raise RuntimeError("MQTT connection timed out or was rejected")
    return client, status_topic, offline


def send(client, topic, payload, qos, retain):
    result = client.publish(topic, payload, qos=qos, retain=retain)
    result.wait_for_publish(timeout=5)
    if not result.is_published():
        raise RuntimeError("MQTT publish timed out; delivery is not confirmed")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--node-id", default=os.environ.get("MQTT_NODE_ID", "node90"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--publish", action="store_true", help="Send to a local authenticated broker")
    args = parser.parse_args(argv)
    if not NODE_PATTERN.fullmatch(args.node_id):
        parser.error("node ID must match node[0-9]{2,3}")
    if not 1 <= args.count <= 4294967296:
        parser.error("count must be in 1..4294967296")
    if not math.isfinite(args.interval) or args.interval <= 0:
        parser.error("interval must be a finite positive number")
    rng = random.Random(args.seed)
    boot_id = f"sim-{uuid.uuid4().hex}"
    client = None
    try:
        if args.publish:
            client, status_topic, offline = connect_mqtt(args.node_id)
            online = json.dumps({"schema_version": "1.0", "node_id": args.node_id, "state": "online"})
            send(client, status_topic, online, qos=1, retain=True)
        started = time.monotonic()
        for sequence in range(args.count):
            uptime = int(time.monotonic() - started) if args.publish else int(sequence * args.interval)
            payload = json.dumps(
                make_sample(args.node_id, boot_id, sequence, rng, uptime),
                ensure_ascii=False,
                allow_nan=False,
            )
            if client:
                send(client, f"xiaoxi/dorm/{args.node_id}/telemetry", payload, qos=0, retain=False)
            print(payload, flush=True)
            if client and sequence < args.count - 1:
                time.sleep(args.interval)
    finally:
        if client:
            try:
                send(client, status_topic, offline, qos=1, retain=True)
            finally:
                client.disconnect()
                client.loop_stop()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ImportError, ValueError, OSError, RuntimeError) as exc:
        print(f"Simulator error: {exc}", file=sys.stderr)
        sys.exit(1)
