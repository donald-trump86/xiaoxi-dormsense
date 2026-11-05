"""Offline synthetic fixtures only: NEVER publish these as real telemetry."""

import concurrent.futures
import importlib
import json
import multiprocessing
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import validator


TELEMETRY = "xiaoxi/dorm/node01/telemetry"
STATUS = "xiaoxi/dorm/node01/status"


def fixture(sequence=0, boot_id="node01-00000001"):
    # False is a validation boundary fixture, not a measurement or Broker input.
    return {
        "schema_version": "1.0", "node_id": "node01", "boot_id": boot_id,
        "timestamp": None, "sequence": sequence, "simulated": False,
        "temperature": 24.5, "humidity": 55.0, "light": None,
        "sensor_status": {
            "temperature": "ok", "humidity": "ok", "light": "missing",
        },
    }


def encoded(payload):
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def suback_codes(*identifiers):
    from paho.mqtt.packettypes import PacketTypes
    from paho.mqtt.reasoncodes import ReasonCode
    return [ReasonCode(PacketTypes.SUBACK, identifier=value) for value in identifiers]


def process_accept(path):
    return validator.SequenceGate(Path(path)).accept(fixture(7))


class FakeInfo:
    """Only the public MQTTMessageInfo surface; deliberately no payload."""

    def __init__(self, published=False, rc=0):
        self.published = published
        self.rc = rc

    def is_published(self):
        return self.published


class FakeSocket:
    def __init__(self, events):
        self.events = events
        self.closed = False

    def shutdown(self, how):
        self.events.append("shutdown")

    def close(self):
        self.events.append("close")
        self.closed = True


class DecoderTests(unittest.TestCase):
    def assert_rejected(self, raw, topic=TELEMETRY, decoder=None):
        with self.assertRaises(ValueError) as caught:
            (decoder or validator.decode_telemetry)(raw, topic)
        self.assertRegex(str(caught.exception), r"^[A-Z0-9_]+$")
        self.assertNotIn("secret-fixture", str(caught.exception))

    def test_valid_schema_and_semantics_reused_with_repository_root(self):
        payload = fixture()
        from scripts import check_repository
        self.assertEqual(check_repository.ROOT, Path(__file__).resolve().parents[3])
        with patch.object(check_repository, "validate_telemetry", wraps=check_repository.validate_telemetry) as validate:
            self.assertEqual(validator.decode_telemetry(encoded(payload), TELEMETRY), payload)
        validate.assert_called_once_with(payload, TELEMETRY)

    def test_invalid_encoding_json_and_top_level(self):
        for raw in (b"\xff", b"{secret-fixture", b"[]", b"null", b"true", b'"secret-fixture"', b"{}{}"):
            with self.subTest(raw=raw):
                self.assert_rejected(raw)

    def test_size_boundary_counts_bytes(self):
        raw = encoded(fixture())
        self.assertEqual(validator.decode_telemetry(raw + b" " * (1024 - len(raw)), TELEMETRY), fixture())
        self.assert_rejected(raw + b" " * (1025 - len(raw)))

    def test_duplicate_keys_at_any_depth(self):
        for raw in (
            b'{"schema_version":"1.0","schema_version":"1.0"}',
            encoded(fixture()).replace(b'"temperature":"ok"', b'"temperature":"ok","temperature":"ok"'),
        ):
            self.assert_rejected(raw)

    def test_nonfinite_and_overflow_rejected(self):
        for number in (b"NaN", b"Infinity", b"-Infinity", b"1e999", b"9" * 400):
            self.assert_rejected(encoded(fixture()).replace(b"24.5", number))

    def test_contract_rejects_bad_fields_and_semantics(self):
        changes = (
            {"schema_version": "2.0"}, {"node_id": "node90"},
            {"extra": "secret-fixture"}, {"simulated": True},
            {"simulated": 0}, {"temperature": True}, {"humidity": 101},
            {"humidity": -1}, {"light": 2}, {"rssi": -128},
            {"uptime": -1}, {"timestamp": "2026-99-99T00:00:00Z"},
            {"timestamp": "2026-01-01T00:00:00+00:00"},
            {"sensor_status": {"temperature": "error"}},
            {"temperature": None}, {"sequence": -1},
            {"sequence": 4294967296}, {"sequence": True},
            {"sensor_status": {"unknown": "ok"}},
        )
        for change in changes:
            with self.subTest(change=change):
                self.assert_rejected(encoded(fixture() | change))
        for field in fixture().keys() - {"sensor_status"}:
            payload = fixture()
            del payload[field]
            self.assert_rejected(encoded(payload))
        for topic in (STATUS, "xiaoxi/dorm/node90/telemetry", TELEMETRY + "/", "xiaoxi/validated/node01/telemetry"):
            self.assert_rejected(encoded(fixture()), topic)

    def test_null_error_missing_and_no_sensor_status_are_valid(self):
        payload = fixture() | {"temperature": None, "sensor_status": {"temperature": "error"}}
        self.assertEqual(validator.decode_telemetry(encoded(payload), TELEMETRY), payload)
        payload.pop("sensor_status")
        self.assertEqual(validator.decode_telemetry(encoded(payload), TELEMETRY), payload)

    def test_boot_count_format_and_reserved_values(self):
        for boot in ("node01-00000000", "node01-0000000A", "node90-00000001", "node01-1", "node01-000000001", "node01-00000001\n"):
            self.assert_rejected(encoded(fixture(boot_id=boot)))
        for boot in ("node01-fffffffe", "node01-ffffffff"):
            payload = fixture(boot_id=boot)
            self.assertEqual(validator.decode_telemetry(encoded(payload), TELEMETRY), payload)

    def test_status_exact_protocol(self):
        for state in ("online", "offline"):
            payload = {"schema_version": "1.0", "node_id": "node01", "state": state}
            self.assertEqual(validator.decode_status(encoded(payload), STATUS), payload)
        good = {"schema_version": "1.0", "node_id": "node01", "state": "online"}
        for change in ({"extra": 1}, {"state": "unknown"}, {"state": True}, {"node_id": "node90"}, {"schema_version": "2.0"}):
            self.assert_rejected(encoded(good | change), STATUS, validator.decode_status)
        for field in good:
            bad = dict(good)
            del bad[field]
            self.assert_rejected(encoded(bad), STATUS, validator.decode_status)
        for raw in (b"\xff", b"NaN", b"[]", b'{"state":"online","state":"offline"}', encoded(good) + b" " * 1024):
            self.assert_rejected(raw, STATUS, validator.decode_status)
        self.assert_rejected(encoded(good), TELEMETRY, validator.decode_status)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "sequence.json"
        self.gate = validator.SequenceGate(self.path)

    def tearDown(self):
        self.directory.cleanup()

    def test_monotonic_sequence_boot_and_restart(self):
        self.assertTrue(self.gate.accept(fixture(5)))
        self.assertFalse(self.gate.accept(fixture(5)))
        self.assertFalse(self.gate.accept(fixture(4)))
        self.assertTrue(self.gate.accept(fixture(6)))
        self.assertTrue(self.gate.accept(fixture(0, "node01-00000002")))
        self.assertFalse(self.gate.accept(fixture(100, "node01-00000001")))
        restarted = validator.SequenceGate(self.path)
        self.assertFalse(restarted.accept(fixture(0, "node01-00000002")))
        self.assertTrue(restarted.accept(fixture(1, "node01-00000002")))
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.path.with_name(self.path.name + ".lock").stat().st_mode), 0o600)

    def test_final_valid_boot_segment_cannot_be_followed_by_old_segment(self):
        self.assertTrue(self.gate.accept(fixture(9, "node01-fffffffe")))
        self.assertTrue(self.gate.accept(fixture(0, "node01-ffffffff")))
        self.assertFalse(self.gate.accept(fixture(10, "node01-fffffffe")))
        self.assertTrue(validator.SequenceGate(self.path).accept(fixture(1, "node01-ffffffff")))

    def test_directory_fsync_failure_after_replace_consumes_but_does_not_accept(self):
        self.assertTrue(self.gate.accept(fixture(1)))
        real_fsync = validator.os.fsync

        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("secret-fixture")
            return real_fsync(fd)

        with patch.object(validator.os, "fsync", side_effect=fail_directory):
            self.assertFalse(self.gate.accept(fixture(2)))
        self.assertFalse(validator.SequenceGate(self.path).accept(fixture(2)))
        self.assertTrue(self.gate.accept(fixture(3)))

    def test_corrupt_lock_and_nonprivate_directory_fail_closed(self):
        self.assertTrue(self.gate.accept(fixture()))
        lock = self.path.with_name(self.path.name + ".lock")
        lock.write_bytes(b"secret-fixture")
        self.assertFalse(self.gate.accept(fixture(1)))
        lock.write_bytes(validator.LOCK_MARKER)
        self.path.parent.chmod(0o755)
        try:
            self.assertFalse(self.gate.accept(fixture(1)))
        finally:
            self.path.parent.chmod(0o700)

    def test_bad_format_type_and_ranges_never_write(self):
        for payload in ({}, None, fixture(-1), fixture(True), fixture(1.0), fixture(4294967296), fixture(boot_id="bad"), fixture(boot_id="node01-00000000")):
            with self.subTest(payload=payload):
                self.assertFalse(self.gate.accept(payload))
        self.assertFalse(self.path.exists())

    def test_corrupt_existing_state_fails_closed(self):
        for raw in (b"", b"{}", b"null", b"not json secret-fixture", b'{"boot_count":1,"sequence":3,"sequence":0}', b'{"boot_count":0,"sequence":0}', b'{"boot_count":1,"sequence":true}', b'{"boot_count":1,"sequence":-1}', b'{"boot_count":1,"sequence":0,"extra":1}'):
            with self.subTest(raw=raw):
                self.path.write_bytes(raw)
                self.path.chmod(0o600)
                self.assertFalse(validator.SequenceGate(self.path).accept(fixture(99)))
                self.assertEqual(self.path.read_bytes(), raw)

    def test_lost_state_or_lock_does_not_reset_known_gate(self):
        self.assertTrue(self.gate.accept(fixture(5)))
        self.path.unlink()
        self.assertFalse(self.gate.accept(fixture(0)))
        self.assertFalse(validator.SequenceGate(self.path).accept(fixture(0)))

    def test_missing_lock_with_intact_state_does_not_reset_high_water(self):
        self.assertTrue(self.gate.accept(fixture(5)))
        self.path.with_name(self.path.name + ".lock").unlink()
        restarted = validator.SequenceGate(self.path)
        self.assertFalse(restarted.accept(fixture(5)))
        self.assertTrue(restarted.accept(fixture(6)))

    def test_same_gate_latches_after_both_files_lost(self):
        self.assertTrue(self.gate.accept(fixture(5)))
        self.path.unlink()
        self.path.with_name(self.path.name + ".lock").unlink()
        self.assertFalse(self.gate.accept(fixture(0)))
        self.assertFalse(self.gate.accept(fixture(6)))
        self.assertFalse(self.path.exists())

    def test_total_durable_loss_is_undetectable_to_a_new_gate(self):
        # Operator MUST NOT restart with an empty replacement volume. Without
        # external authority a new process cannot distinguish this from first use.
        self.assertTrue(self.gate.accept(fixture(5)))
        self.path.unlink()
        self.path.with_name(self.path.name + ".lock").unlink()
        self.assertTrue(validator.SequenceGate(self.path).accept(fixture(0)))

    def test_read_replace_and_fsync_failures_cannot_accept(self):
        self.assertTrue(self.gate.accept(fixture(1)))
        original = self.path.read_bytes()
        with patch.object(validator, "_read_state", side_effect=OSError("secret-fixture")):
            self.assertFalse(self.gate.accept(fixture(2)))
        with patch.object(validator.os, "replace", side_effect=OSError("secret-fixture")):
            self.assertFalse(self.gate.accept(fixture(2)))
        self.assertEqual(self.path.read_bytes(), original)
        with patch.object(validator.os, "fsync", side_effect=OSError("secret-fixture")):
            self.assertFalse(self.gate.accept(fixture(2)))
        self.assertEqual(list(self.path.parent.glob(".sequence.json.*")), [])
        self.assertTrue(self.gate.accept(fixture(2)))

    def test_failed_first_write_leaves_closed_initialization(self):
        with patch.object(validator.os, "replace", side_effect=OSError("fixture")):
            self.assertFalse(self.gate.accept(fixture()))
        self.assertFalse(validator.SequenceGate(self.path).accept(fixture()))

    def test_symlink_or_public_state_rejected(self):
        target = self.path.parent / "target"
        target.write_bytes(b"fixture-unchanged")
        self.path.symlink_to(target)
        self.assertFalse(self.gate.accept(fixture()))
        self.assertEqual(target.read_bytes(), b"fixture-unchanged")
        self.path.unlink()
        self.path.write_bytes(b'{"boot_count":1,"sequence":0}')
        self.path.chmod(0o644)
        self.assertFalse(self.gate.accept(fixture(1)))

    def test_many_instances_same_sample_accept_exactly_once(self):
        gates = [validator.SequenceGate(self.path) for _ in range(16)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            results = list(executor.map(lambda gate: gate.accept(fixture(7)), gates))
        self.assertEqual(sum(results), 1)
        self.assertFalse(validator.SequenceGate(self.path).accept(fixture(7)))


    def test_separate_processes_same_sample_accept_exactly_once(self):
        with concurrent.futures.ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("spawn")) as executor:
            results = list(executor.map(process_accept, [str(self.path)] * 8))
        self.assertEqual(sum(results), 1)
        self.assertFalse(validator.SequenceGate(self.path).accept(fixture(7)))


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.client.is_connected.return_value = True
        self.client.publish.return_value = FakeInfo(published=True)
        self.client.socket.return_value = None
        self.client.subscribe.return_value = (0, 42)
        self.gate = Mock()
        self.gate.accept.return_value = True
        self.relay = validator.Relay(self.gate)
        self.relay.attach(self.client)
        self.relay.on_connect(self.client, None, None, 0, None)
        self.relay.on_subscribe(self.client, None, 42, suback_codes(0, 1), None)
        self.client.reset_mock()

    def message(self, topic, payload, retained=False):
        self.relay.on_message(self.client, None, SimpleNamespace(topic=topic, payload=encoded(payload), retain=retained))

    def test_waits_for_matching_success_suback_before_forwarding(self):
        self.relay.attach(self.client)
        self.relay.on_connect(self.client, None, None, 0, None)
        self.assertTrue(self.relay.connected)
        self.assertFalse(self.relay.ready)
        self.message(TELEMETRY, fixture())
        self.gate.accept.assert_not_called()
        self.client.publish.assert_not_called()
        self.relay.on_subscribe(self.client, None, 42, suback_codes(0, 1), None)
        self.assertTrue(self.relay.ready)
        self.message(TELEMETRY, fixture())
        self.gate.accept.assert_called_once()
        self.client.publish.assert_called_once()
        self.client.disconnect.assert_not_called()

    def test_preack_retained_status_keeps_only_latest_state_and_flushes_once(self):
        self.relay.attach(self.client)
        self.relay.on_connect(self.client, None, None, 0, None)
        self.message(STATUS, {"schema_version": "1.0", "node_id": "node01", "state": "offline"}, True)
        self.assertEqual(self.relay._pending_status, b"offline")
        self.message(STATUS, {"schema_version": "1.0", "node_id": "node01", "state": "online"}, True)
        self.assertEqual(self.relay._pending_status, b"online")
        self.client.publish.assert_not_called()
        self.relay.on_subscribe(self.client, None, 42, suback_codes(0, 1), None)
        self.client.publish.assert_called_once()
        args, kwargs = self.client.publish.call_args
        self.assertEqual(args[0], "xiaoxi/validated/node01/status")
        self.assertEqual(json.loads(args[1]), {"schema_version": "1.0", "node_id": "node01", "state": "online"})
        self.assertEqual(kwargs, {"qos": 1, "retain": True})
        self.assertIsNone(self.relay._pending_status)
        self.gate.accept.assert_not_called()

    def test_preack_telemetry_never_buffered_or_replayed(self):
        self.relay.attach(self.client)
        self.relay.on_connect(self.client, None, None, 0, None)
        self.message(TELEMETRY, fixture(), False)
        self.message(TELEMETRY, fixture(1), True)
        self.assertIsNone(self.relay._pending_status)
        self.relay.on_subscribe(self.client, None, 42, suback_codes(0, 1), None)
        self.client.publish.assert_not_called()
        self.gate.accept.assert_not_called()

    def test_preack_bad_status_topic_schema_and_nonretained_never_cached(self):
        self.relay.attach(self.client)
        self.relay.on_connect(self.client, None, None, 0, None)
        valid = {"schema_version": "1.0", "node_id": "node01", "state": "online"}
        cases = [
            (STATUS, b"online", True), (STATUS, b"offline", True),
            (STATUS, b"\xff", True), (STATUS, encoded({"state": "online"}), True),
            (STATUS, encoded(valid | {"schema_version": "2.0"}), True),
            (STATUS, encoded(valid | {"node_id": "node02"}), True),
            (STATUS, encoded(valid | {"state": "unknown"}), True),
            (STATUS, encoded(valid | {"extra": "secret-fixture"}), True),
            ("xiaoxi/dorm/node02/status", encoded(valid), True),
            (STATUS, encoded(valid), False),
        ]
        for topic, raw, retain in cases:
            with self.subTest(topic=topic, raw=raw, retain=retain):
                self.relay.on_message(self.client, None, SimpleNamespace(topic=topic, payload=raw, retain=retain))
                self.assertIsNone(self.relay._pending_status)
        self.relay.on_subscribe(self.client, None, 42, suback_codes(0, 1), None)
        self.client.publish.assert_not_called()
        self.gate.accept.assert_not_called()

    def test_preack_status_cleared_on_reject_bad_mid_timeout_or_disconnect(self):
        for event in ("reject", "bad_mid", "timeout", "disconnect"):
            with self.subTest(event=event):
                self.client.reset_mock()
                self.relay.attach(self.client)
                self.relay.on_connect(self.client, None, None, 0, None)
                self.message(STATUS, {"schema_version": "1.0", "node_id": "node01", "state": "offline"}, True)
                self.assertEqual(self.relay._pending_status, b"offline")
                if event == "reject":
                    self.relay.on_subscribe(self.client, None, 42, suback_codes(0, 128), None)
                elif event == "bad_mid":
                    self.relay.on_subscribe(self.client, None, 99, suback_codes(0, 1), None)
                elif event == "timeout":
                    self.relay._fail_subscription(self.client, "READY_TIMEOUT")
                else:
                    self.relay.on_disconnect(self.client, None, None, 1, None)
                self.assertIsNone(self.relay._pending_status)
                self.relay.on_subscribe(self.client, None, 42, suback_codes(0, 1), None)
                self.client.publish.assert_not_called()
                self.relay.attach(self.client)
                self.relay.on_connect(self.client, None, None, 0, None)
                self.relay.on_subscribe(self.client, None, 42, suback_codes(0, 1), None)
                self.client.publish.assert_not_called()

    def test_subscribe_send_failure_disconnects_without_forwarding(self):
        for result in ((4, None), (0, None), (0, True)):
            self.client.reset_mock()
            self.gate.reset_mock()
            self.relay.attach(self.client)
            self.client.subscribe.return_value = result
            with self.assertLogs("validator", level="WARNING") as caught:
                self.relay.on_connect(self.client, None, None, 0, None)
            self.assertIn("SUBSCRIBE_FAILED", " ".join(caught.output))
            self.assertFalse(self.relay.ready)
            self.assertTrue(self.relay.failed)
            self.client.disconnect.assert_called_once()
            self.message(TELEMETRY, fixture())
            self.gate.accept.assert_not_called()
            self.client.publish.assert_not_called()

    def test_suback_denial_or_bad_count_disconnects_without_forwarding(self):
        for codes in (suback_codes(0, 128), suback_codes(128, 1), suback_codes(0), [], [0, 1]):
            self.client.reset_mock()
            self.gate.reset_mock()
            self.relay.attach(self.client)
            self.relay.on_connect(self.client, None, None, 0, None)
            with self.assertLogs("validator", level="WARNING") as caught:
                self.relay.on_subscribe(self.client, None, 42, codes, None)
            self.assertRegex(" ".join(caught.output), r"SUBACK_(REJECT|INVALID)")
            self.assertFalse(self.relay.ready)
            self.assertTrue(self.relay.failed)
            self.client.disconnect.assert_called_once()
            self.message(TELEMETRY, fixture())
            self.gate.accept.assert_not_called()
            self.client.publish.assert_not_called()

    def test_unexpected_suback_mid_fails_closed_even_if_success_codes(self):
        self.relay.attach(self.client)
        self.relay.on_connect(self.client, None, None, 0, None)
        with self.assertLogs("validator", level="WARNING") as caught:
            self.relay.on_subscribe(self.client, None, 99, suback_codes(0, 1), None)
        self.assertIn("SUBACK_MID", " ".join(caught.output))
        self.client.disconnect.assert_called_once()
        self.assertFalse(self.relay.ready)
        self.relay.on_subscribe(self.client, None, 42, suback_codes(0, 1), None)
        self.assertFalse(self.relay.ready)
        self.message(TELEMETRY, fixture())
        self.gate.accept.assert_not_called()
        self.client.publish.assert_not_called()

    def test_forward_topics_and_flags(self):
        payload = fixture()
        self.message(TELEMETRY, payload)
        self.gate.accept.assert_called_once_with(payload)
        args, kwargs = self.client.publish.call_args
        self.assertEqual(args[0], "xiaoxi/validated/node01/telemetry")
        self.assertEqual(json.loads(args[1]), payload)
        self.assertEqual(kwargs, {"qos": 0, "retain": False})
        self.client.reset_mock()
        status = {"schema_version": "1.0", "node_id": "node01", "state": "offline"}
        self.message(STATUS, status, True)
        args, kwargs = self.client.publish.call_args
        self.assertEqual(args[0], "xiaoxi/validated/node01/status")
        self.assertEqual(json.loads(args[1]), status)
        self.assertTrue(kwargs["retain"])
        self.assertEqual(self.gate.accept.call_count, 1)

    def test_retained_telemetry_and_bad_status_do_not_touch_gate(self):
        # Same RETAIN rejection for live MQTT5 RAP publications and snapshots.
        self.message(TELEMETRY, fixture(), True)
        self.relay.on_disconnect(self.client, None, None, 1, None)
        self.relay.on_connect(self.client, None, None, 0, None)
        self.relay.on_subscribe(self.client, None, 42, suback_codes(0, 1), None)
        self.message(TELEMETRY, fixture(1), True)
        self.message(STATUS, {"state": "online"}, True)
        self.message(TELEMETRY, fixture() | {"simulated": True})
        self.gate.accept.assert_not_called()
        self.client.publish.assert_not_called()

    def test_failed_gate_never_publishes(self):
        self.gate.accept.return_value = False
        self.message(TELEMETRY, fixture())
        self.client.publish.assert_not_called()

    def test_disconnect_drops_input_reconnect_only_resubscribes(self):
        self.relay.on_disconnect(self.client, None, None, 1, None)
        self.message(TELEMETRY, fixture())
        self.message(STATUS, {"schema_version": "1.0", "node_id": "node01", "state": "online"})
        self.gate.accept.assert_not_called()
        self.client.publish.assert_not_called()
        self.relay.on_connect(self.client, None, None, 0, None)
        self.client.subscribe.assert_called_once()
        subscriptions = self.client.subscribe.call_args.args[0]
        self.assertEqual([topic for topic, _ in subscriptions], [TELEMETRY, STATUS])
        for (_topic, options), qos in zip(subscriptions, (0, 1)):
            self.assertEqual(options.QoS, qos)
            self.assertTrue(options.retainAsPublished)
            self.assertEqual(options.retainHandling, 0)
            self.assertEqual(options.pack()[0] & 8, 8)
        self.client.publish.assert_not_called()

    def test_publish_failure_not_retried_and_fixed_log_only(self):
        self.client.publish.side_effect = OSError("secret-fixture payload")
        with self.assertLogs("validator", level="WARNING") as caught:
            self.message(TELEMETRY, fixture())
        self.assertNotIn("secret-fixture", " ".join(caught.output))
        self.relay.on_disconnect(self.client, None, None, 1, None)
        self.relay.on_connect(self.client, None, None, 0, None)
        self.assertEqual(self.client.publish.call_count, 1)

    def _install_socket_fixture(self, client):
        events = []
        sock = FakeSocket(events)
        client.socket.return_value = sock

        def disconnect():
            events.append("disconnect")
            if not sock.closed:
                events.append("FLUSH_OLD_DATA")

        client.disconnect.side_effect = disconnect
        return sock, events

    def test_unfinished_info_is_normal_then_completed_before_next_input(self):
        info = FakeInfo()
        self.client.publish.return_value = info
        self.message(TELEMETRY, fixture())
        self.assertIs(self.relay._pending_info, info)
        self.assertFalse(self.relay.failed)
        self.client.disconnect.assert_not_called()
        info.published = True
        self.message(TELEMETRY, fixture(1))
        self.assertEqual(self.client.publish.call_count, 2)
        self.assertEqual(self.gate.accept.call_count, 2)
        self.assertIsNone(self.relay._pending_info)
        self.client.disconnect.assert_not_called()

    def test_unfinished_second_input_aborts_without_second_gate_or_queue(self):
        for first_topic, second_topic in ((TELEMETRY, TELEMETRY), (TELEMETRY, STATUS), (STATUS, TELEMETRY)):
            with self.subTest(first=first_topic, second=second_topic):
                self.setUp()
                sock, events = self._install_socket_fixture(self.client)
                self.client.publish.return_value = FakeInfo()
                status = {"schema_version": "1.0", "node_id": "node01", "state": "online"}
                self.message(first_topic, fixture() if first_topic == TELEMETRY else status)
                second = fixture(1) if second_topic == TELEMETRY else status
                self.message(second_topic, second)
                self.assertEqual(self.client.publish.call_count, 1)
                self.assertEqual(self.gate.accept.call_count, int(first_topic == TELEMETRY))
                self.assertTrue(self.relay.failed)
                self.assertIsNone(self.relay._pending_info)
                self.assertTrue(sock.closed)
                self.assertEqual(events, ["shutdown", "close", "disconnect"])

    def test_publish_nonzero_rc_or_exception_is_fatal_and_closes_first(self):
        for failure in (4, 15, "exception", "rejected_exception", "info_exception"):
            with self.subTest(failure=failure):
                self.setUp()
                sock, events = self._install_socket_fixture(self.client)
                if failure == "exception":
                    self.client.publish.side_effect = OSError("secret-fixture")
                elif failure == "rejected_exception":
                    self.client.publish.side_effect = validator.Rejected("CONTRACT")
                elif failure == "info_exception":
                    info = Mock(rc=0)
                    info.is_published.side_effect = RuntimeError("secret-fixture")
                    self.client.publish.return_value = info
                else:
                    self.client.publish.return_value = FakeInfo(rc=failure)
                with self.assertLogs("validator", level="WARNING") as caught:
                    self.message(TELEMETRY, fixture())
                self.assertNotIn("secret-fixture", " ".join(caught.output))
                self.assertTrue(self.relay.failed)
                self.assertFalse(self.relay.ready)
                self.assertIsNone(self.relay._pending_info)
                self.assertTrue(sock.closed)
                self.assertEqual(events, ["shutdown", "close", "disconnect"])
                self.message(TELEMETRY, fixture(1))
                self.assertEqual(self.gate.accept.call_count, 1)
                self.client.publish.assert_called_once()

    def test_disconnect_clears_unfinished_info(self):
        self.client.publish.return_value = FakeInfo()
        self.message(TELEMETRY, fixture())
        self.assertIsNotNone(self.relay._pending_info)
        self.relay.on_disconnect(self.client, None, None, 1, None)
        self.assertIsNone(self.relay._pending_info)
        self.assertIsNone(self.relay._send_deadline)
        self.message(TELEMETRY, fixture(1))
        self.client.publish.assert_called_once()

    def test_run_delayed_publish_completes_in_next_loop_without_abort(self):
        clients, events_list = [], []
        cancelled, now = [False], [0.0]
        stop = Mock()
        stop.is_set.side_effect = lambda: cancelled[0]
        config = {"host": "fixture.invalid", "port": 8883, "state_path": "/fixture/sequence.json"}
        gate = Mock()
        gate.accept.return_value = True

        def factory(_config, relay):
            client = Mock()
            client.subscribe.return_value = (0, 42)
            info = FakeInfo()
            client.publish.return_value = info
            _sock, events = self._install_socket_fixture(client)
            events_list.append(events)
            relay.attach(client)
            clients.append(client)

            def loop(timeout):
                if client.loop.call_count == 1:
                    relay.on_connect(client, None, None, 0, None)
                    relay.on_subscribe(client, None, 42, suback_codes(0, 1), None)
                    relay.on_message(client, None, SimpleNamespace(topic=TELEMETRY, payload=encoded(fixture()), retain=False))
                    client.disconnect.assert_not_called()
                else:
                    now[0] = 0.5
                    info.published = True
                    cancelled[0] = True
                return 0

            client.loop.side_effect = loop
            return client

        with patch.object(validator, "make_client", side_effect=factory), patch.object(validator, "SequenceGate", return_value=gate), patch("time.monotonic", side_effect=lambda: now[0]), patch.object(validator.LOGGER, "warning") as warning:
            validator.run(config, stop)
        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0].loop.call_count, 2)
        clients[0].publish.assert_called_once()
        gate.accept.assert_called_once()
        self.assertEqual(events_list[0], ["shutdown", "close", "disconnect"])
        stop.wait.assert_not_called()
        warning.assert_not_called()

    def test_run_five_second_pending_budget_aborts_before_next_loop_and_backs_off(self):
        clients, events_list, relays = [], [], []
        cancelled, now, between_loops = [False], [0.0], [False]
        stop = Mock()
        config = {"host": "fixture.invalid", "port": 8883, "state_path": "/fixture/sequence.json"}
        gate = Mock()
        gate.accept.return_value = True

        def is_set():
            if between_loops[0]:
                now[0] += 1.0
                between_loops[0] = False
            return cancelled[0]

        def wait(delay):
            if len(clients) == 3:
                cancelled[0] = True

        stop.is_set.side_effect = is_set
        stop.wait.side_effect = wait

        def factory(_config, relay):
            client = Mock()
            client.subscribe.return_value = (0, 42)
            client.publish.return_value = FakeInfo()
            _sock, events = self._install_socket_fixture(client)
            events_list.append(events)
            relay.attach(client)
            clients.append(client)
            relays.append(relay)

            def loop(timeout):
                if client.loop.call_count > 1:
                    raise OSError("fixture bound: expired client was looped")
                relay.on_connect(client, None, None, 0, None)
                relay.on_subscribe(client, None, 42, suback_codes(0, 1), None)
                relay.on_message(client, None, SimpleNamespace(topic=TELEMETRY, payload=encoded(fixture()), retain=False))
                now[0] += 4.0  # post-loop check is within the five-second budget
                between_loops[0] = True  # expire between loops, before next write
                return 0

            client.loop.side_effect = loop
            return client

        with patch.object(validator, "make_client", side_effect=factory), patch.object(validator, "SequenceGate", return_value=gate), patch("time.monotonic", side_effect=lambda: now[0]), self.assertLogs("validator", level="WARNING") as caught:
            validator.run(config, stop)
        self.assertEqual(len(clients), 3)
        self.assertEqual([call.args[0] for call in stop.wait.call_args_list], [1, 2, 4])
        self.assertEqual(sum("PUBLISH_TIMEOUT" in entry for entry in caught.output), 3)
        self.assertEqual(gate.accept.call_count, 3)
        for client, events, relay in zip(clients, events_list, relays):
            client.loop.assert_called_once_with(timeout=1.0)
            client.publish.assert_called_once()
            client.reconnect.assert_not_called()
            self.assertNotIn("FLUSH_OLD_DATA", events)
            self.assertEqual(events[:3], ["shutdown", "close", "disconnect"])
            self.assertIsNone(relay._pending_info)

    def test_run_shutdown_with_unfinished_publish_closes_before_disconnect(self):
        clients, events_list, relays = [], [], []
        cancelled = [False]
        stop = Mock()
        stop.is_set.side_effect = lambda: cancelled[0]
        config = {"host": "fixture.invalid", "port": 8883, "state_path": "/fixture/sequence.json"}
        gate = Mock()
        gate.accept.return_value = True

        def factory(_config, relay):
            client = Mock()
            client.subscribe.return_value = (0, 42)
            client.publish.return_value = FakeInfo()
            _sock, events = self._install_socket_fixture(client)
            events_list.append(events)
            relay.attach(client)
            clients.append(client)
            relays.append(relay)

            def loop(timeout):
                relay.on_connect(client, None, None, 0, None)
                relay.on_subscribe(client, None, 42, suback_codes(0, 1), None)
                relay.on_message(client, None, SimpleNamespace(topic=TELEMETRY, payload=encoded(fixture()), retain=False))
                cancelled[0] = True
                return 0

            client.loop.side_effect = loop
            return client

        with patch.object(validator, "make_client", side_effect=factory), patch.object(validator, "SequenceGate", return_value=gate), patch("time.monotonic", return_value=0.0):
            validator.run(config, stop)
        self.assertEqual(len(clients), 1)
        clients[0].loop.assert_called_once()
        self.assertEqual(events_list[0], ["shutdown", "close", "disconnect"])
        self.assertIsNone(relays[0]._pending_info)
        stop.wait.assert_not_called()

    def test_abort_never_disconnects_without_proven_socket_close(self):
        for failure in ("socket", "close", "shutdown"):
            with self.subTest(failure=failure):
                self.setUp()
                sock, events = self._install_socket_fixture(self.client)
                if failure == "socket":
                    self.client.socket.side_effect = OSError("secret-fixture")
                elif failure == "close":
                    sock.close = Mock(side_effect=OSError("secret-fixture"))
                else:
                    sock.shutdown = Mock(side_effect=OSError("already disconnected"))
                with patch.object(validator.LOGGER, "warning") as warning:
                    validator.abort_client(self.client)
                self.assertNotIn("secret-fixture", str(warning.call_args_list))
                if failure == "shutdown":
                    self.assertEqual(events, ["close", "disconnect"])
                    self.assertTrue(sock.closed)
                else:
                    self.client.disconnect.assert_not_called()
                    self.assertFalse(sock.closed)
                self.assertNotIn("FLUSH_OLD_DATA", events)

    def test_import_does_not_read_runtime_or_make_network_client(self):
        with patch("pathlib.Path.read_text", side_effect=AssertionError("runtime read")), patch("socket.socket", side_effect=AssertionError("network")):
            importlib.reload(validator)

    def test_network_disconnected_check_does_not_advance_gate(self):
        self.client.is_connected.return_value = False
        self.message(TELEMETRY, fixture())
        self.gate.accept.assert_not_called()
        self.client.publish.assert_not_called()

    def test_failed_connack_does_not_subscribe(self):
        self.relay.on_connect(self.client, None, None, 5, None)
        self.client.subscribe.assert_not_called()
        self.assertFalse(self.relay.connected)

    def test_run_discards_clients_and_caps_backoff_without_network(self):
        clients = []
        stop = Mock()
        attempts = 10
        stop.is_set.side_effect = sum(([False, False] for _ in range(attempts)), []) + [True]
        config = {"host": "fixture.invalid", "port": 8883, "state_path": "/fixture/sequence.json"}

        def factory(_config, relay):
            client = Mock()
            client.connect.side_effect = OSError("secret-fixture")
            relay.attach(client)
            clients.append(client)
            return client

        with patch.object(validator, "make_client", side_effect=factory), self.assertLogs("validator", level="WARNING") as caught:
            validator.run(config, stop)
        self.assertEqual(len(clients), attempts)
        self.assertEqual([call.args[0] for call in stop.wait.call_args_list], [1, 2, 4, 8, 16, 32, 60, 60, 60, 60])
        for client in clients:
            client.disconnect.assert_called_once()
            client.publish.assert_not_called()
        self.assertNotIn("secret-fixture", " ".join(caught.output))

    def test_run_subscription_failure_rebuilds_client_with_backoff(self):
        clients = []
        stop = Mock()
        stop.is_set.side_effect = [False, False, False] * 3 + [True]
        config = {"host": "fixture.invalid", "port": 8883, "state_path": "/fixture/sequence.json"}

        def factory(_config, relay):
            client = Mock()
            client.subscribe.return_value = (4, None)
            relay.attach(client)

            def loop(timeout):
                relay.on_connect(client, None, None, 0, None)
                return 0

            client.loop.side_effect = loop
            clients.append(client)
            return client

        with patch.object(validator, "make_client", side_effect=factory), self.assertLogs("validator", level="WARNING"):
            validator.run(config, stop)
        self.assertEqual(len(clients), 3)
        self.assertEqual([call.args[0] for call in stop.wait.call_args_list], [1, 2, 4])
        for client in clients:
            client.loop.assert_called_once()
            client.publish.assert_not_called()
            client.reconnect.assert_not_called()
            self.assertGreaterEqual(client.disconnect.call_count, 1)

    def _assert_missing_ack_timeout(self, receive_connack):
        clients = []
        now = [0.0]
        cancelled = [False]
        stop = Mock()
        stop.is_set.side_effect = lambda: cancelled[0]
        config = {"host": "fixture.invalid", "port": 8883, "state_path": "/fixture/sequence.json"}

        def wait(delay):
            if len(clients) == 3:
                cancelled[0] = True

        stop.wait.side_effect = wait

        def factory(_config, relay):
            client = Mock()
            client.subscribe.return_value = (0, 42)
            relay.attach(client)
            clients.append(client)
            calls = [0]

            def loop(timeout):
                calls[0] += 1
                now[0] += 9 if calls[0] == 1 else 1
                if receive_connack and calls[0] == 1:
                    relay.on_connect(client, None, None, 0, None)
                    relay.on_message(client, None, SimpleNamespace(
                        topic=STATUS, retain=True,
                        payload=encoded({"schema_version": "1.0", "node_id": "node01", "state": "online"}),
                    ))
                # Bound the regression test itself even without implementation.
                if sum(item.loop.call_count for item in clients) > 6:
                    cancelled[0] = True
                return 0

            client.loop.side_effect = loop
            return client

        with patch.object(validator, "make_client", side_effect=factory), patch("time.monotonic", side_effect=lambda: now[0]), self.assertLogs("validator", level="WARNING") as caught:
            validator.run(config, stop)
        self.assertEqual(len(clients), 3)
        self.assertEqual([call.args[0] for call in stop.wait.call_args_list], [1, 2, 4])
        self.assertEqual(sum("READY_TIMEOUT" in entry for entry in caught.output), 3)
        for client in clients:
            self.assertEqual(client.loop.call_count, 2)
            self.assertGreaterEqual(client.disconnect.call_count, 1)
            client.publish.assert_not_called()
            client.reconnect.assert_not_called()

    def test_run_missing_suback_times_out_and_backoff_does_not_reset(self):
        self._assert_missing_ack_timeout(receive_connack=True)

    def test_run_missing_connack_times_out_even_when_loop_stays_successful(self):
        self._assert_missing_ack_timeout(receive_connack=False)

    def test_handshake_callbacks_reject_exact_or_late_deadline(self):
        status = {"schema_version": "1.0", "node_id": "node01", "state": "online"}
        for at in (10.0, 11.0):
            for stage in ("connack", "suback", "message"):
                with self.subTest(at=at, stage=stage):
                    self.setUp()
                    self.relay.attach(self.client)
                    self.relay.begin_handshake(10.0)  # explicit standalone cutoff
                    sock, events = self._install_socket_fixture(self.client)
                    now = [9.0]
                    with patch("time.monotonic", side_effect=lambda: now[0]), patch.object(validator.LOGGER, "warning") as warning:
                        if stage != "connack":
                            self.relay.on_connect(self.client, None, None, 0, None)
                            self.message(STATUS, status, True)
                            self.assertEqual(self.relay._pending_status, b"online")
                        now[0] = at
                        if stage == "connack":
                            self.relay.on_connect(self.client, None, None, 0, None)
                            self.client.subscribe.assert_not_called()
                        elif stage == "suback":
                            self.relay.on_subscribe(self.client, None, 42, suback_codes(0, 1), None)
                        else:
                            self.message(STATUS, status, True)
                        self.message(TELEMETRY, fixture())
                        self.relay.on_subscribe(self.client, None, 42, suback_codes(0, 1), None)
                    self.gate.accept.assert_not_called()
                    self.client.publish.assert_not_called()
                    self.assertTrue(self.relay.failed)
                    self.assertFalse(self.relay.ready)
                    self.assertIsNone(self.relay._pending_status)
                    self.assertIsNone(self.relay._ready_deadline)
                    warning.assert_called_once_with("%s", "READY_TIMEOUT")
                    self.assertTrue(sock.closed)
                    self.assertEqual(events, ["shutdown", "close", "disconnect"])

    def test_handshake_callback_crossing_cutoff_before_effect_is_rejected(self):
        status = {"schema_version": "1.0", "node_id": "node01", "state": "online"}
        for stage in ("connack", "suback", "message"):
            with self.subTest(stage=stage):
                self.setUp()
                self.relay.attach(self.client)
                self.relay.begin_handshake(10.0)
                _sock, events = self._install_socket_fixture(self.client)
                if stage != "connack":
                    with patch("time.monotonic", return_value=9.0):
                        self.relay.on_connect(self.client, None, None, 0, None)
                        self.message(STATUS, status, True)
                with patch("time.monotonic", side_effect=[9.0, 10.0]), patch.object(validator.LOGGER, "warning") as warning:
                    if stage == "connack":
                        self.relay.on_connect(self.client, None, None, 0, None)
                    elif stage == "suback":
                        self.relay.on_subscribe(self.client, None, 42, suback_codes(0, 1), None)
                    else:
                        self.message(STATUS, status, True)
                if stage == "connack":
                    self.client.subscribe.assert_not_called()
                self.client.publish.assert_not_called()
                self.gate.accept.assert_not_called()
                self.assertIsNone(self.relay._pending_status)
                self.assertTrue(self.relay.failed)
                warning.assert_called_once_with("%s", "READY_TIMEOUT")
                self.assertEqual(events, ["shutdown", "close", "disconnect"])

    def test_successful_standalone_handshake_clears_cutoff_and_keeps_forwarding(self):
        self.relay.attach(self.client)
        self.relay.begin_handshake(10.0)
        self.relay.on_disconnect(self.client, None, None, 0, None)
        self.assertEqual(self.relay._ready_deadline, 10.0)  # pre-ACK disconnect cannot disable it
        now = [9.0]
        status = {"schema_version": "1.0", "node_id": "node01", "state": "offline"}
        with patch("time.monotonic", side_effect=lambda: now[0]), patch.object(validator.LOGGER, "warning") as warning:
            self.relay.on_connect(self.client, None, None, 0, None)
            self.assertEqual(self.relay._ready_deadline, 10.0)  # CONNACK cannot renew
            self.message(STATUS, status, True)
            now[0] = 9.999
            self.relay.on_subscribe(self.client, None, 42, suback_codes(0, 1), None)
            self.assertTrue(self.relay.ready)
            self.assertIsNone(self.relay._ready_deadline)
            now[0] = 100000.0
            self.message(TELEMETRY, fixture())
        self.assertEqual(self.client.publish.call_count, 2)
        self.gate.accept.assert_called_once()
        self.client.disconnect.assert_not_called()
        warning.assert_not_called()

    def test_run_in_loop_late_ack_never_flushes_or_advances_gate_and_backs_off(self):
        for stage in ("connack", "suback"):
            for at in (10.0, 11.0):
                with self.subTest(stage=stage, at=at):
                    clients, events_list = [], []
                    cancelled, now = [False], [0.0]
                    stop = Mock()
                    stop.is_set.side_effect = lambda: cancelled[0]
                    config = {"host": "fixture.invalid", "port": 8883, "state_path": "/fixture/sequence.json"}
                    gate = Mock()
                    gate.accept.return_value = True
                    status = {"schema_version": "1.0", "node_id": "node01", "state": "online"}

                    def wait(delay):
                        if len(clients) == 3:
                            cancelled[0] = True

                    stop.wait.side_effect = wait

                    def factory(_config, relay):
                        client = Mock()
                        client.subscribe.return_value = (0, 42)
                        client.publish.return_value = FakeInfo(published=True)
                        _sock, events = self._install_socket_fixture(client)
                        events_list.append(events)
                        relay.attach(client)
                        clients.append(client)
                        base = now[0]

                        def loop(timeout):
                            if client.loop.call_count > 1:
                                raise OSError("fixture bound: late ready bypass")
                            now[0] = base + 9.0
                            if stage == "suback":
                                relay.on_connect(client, None, None, 0, None)
                                relay.on_message(client, None, SimpleNamespace(topic=STATUS, payload=encoded(status), retain=True))
                                self.assertEqual(relay._pending_status, b"online")
                            now[0] = base + at
                            if stage == "connack":
                                relay.on_connect(client, None, None, 0, None)
                            relay.on_subscribe(client, None, 42, suback_codes(0, 1), None)
                            relay.on_message(client, None, SimpleNamespace(topic=TELEMETRY, payload=encoded(fixture()), retain=False))
                            relay.on_message(client, None, SimpleNamespace(topic=STATUS, payload=encoded(status), retain=True))
                            return 0

                        client.loop.side_effect = loop
                        return client

                    with patch.object(validator, "make_client", side_effect=factory), patch.object(validator, "SequenceGate", return_value=gate), patch("time.monotonic", side_effect=lambda: now[0]), self.assertLogs("validator", level="WARNING") as caught:
                        validator.run(config, stop)
                    self.assertEqual(len(clients), 3)
                    gate.accept.assert_not_called()
                    self.assertEqual([call.args[0] for call in stop.wait.call_args_list], [1, 2, 4])
                    self.assertEqual(sum("READY_TIMEOUT" in entry for entry in caught.output), 3)
                    for client, events in zip(clients, events_list):
                        client.loop.assert_called_once_with(timeout=1.0)
                        client.publish.assert_not_called()
                        client.reconnect.assert_not_called()
                        self.assertEqual(events[:3], ["shutdown", "close", "disconnect"])
                        self.assertNotIn("FLUSH_OLD_DATA", events)
                        if stage == "connack":
                            client.subscribe.assert_not_called()

    def test_run_successful_ack_disables_handshake_deadline(self):
        now = [0.0]
        cancelled = [False]
        clients = []
        stop = Mock()
        stop.is_set.side_effect = lambda: cancelled[0]
        config = {"host": "fixture.invalid", "port": 8883, "state_path": "/fixture/sequence.json"}

        def factory(_config, relay):
            client = Mock()
            client.subscribe.return_value = (0, 42)
            relay.attach(client)
            clients.append(client)
            calls = [0]

            def loop(timeout):
                calls[0] += 1
                if calls[0] == 1:
                    now[0] = 1.0
                    relay.on_connect(client, None, None, 0, None)
                    relay.on_subscribe(client, None, 42, suback_codes(0, 1), None)
                else:
                    now[0] = 1000.0 * calls[0]
                if calls[0] == 3:
                    cancelled[0] = True
                return 0

            client.loop.side_effect = loop
            return client

        with patch.object(validator, "make_client", side_effect=factory), patch("time.monotonic", side_effect=lambda: now[0]), patch.object(validator.LOGGER, "warning") as warning:
            validator.run(config, stop)
        self.assertEqual(len(clients), 1)
        self.assertEqual(clients[0].loop.call_count, 3)
        clients[0].disconnect.assert_called_once()  # shutdown only, not timeout
        stop.wait.assert_not_called()
        warning.assert_not_called()

    def test_run_lost_connection_replaces_old_queued_client(self):
        clients = []
        config = {"host": "fixture.invalid", "port": 8883, "state_path": "/fixture/sequence.json"}
        stop = Mock()
        stop.is_set.side_effect = [False, False, False, False, False, False, True]

        def factory(_config, relay):
            client = Mock()
            client.loop.return_value = 7
            relay.attach(client)
            clients.append(client)
            return client

        with patch.object(validator, "make_client", side_effect=factory):
            validator.run(config, stop)
        self.assertEqual(len(clients), 2)
        self.assertIsNot(clients[0], clients[1])
        for client in clients:
            client.loop.assert_called_once_with(timeout=1.0)
            client.connect.assert_called_once_with("fixture.invalid", 8883, keepalive=30, clean_start=True)
            client.publish.assert_not_called()
            client.reconnect.assert_not_called()
            client.disconnect.assert_called_once()

    def test_paho_configuration_v2_tls_and_bounded_reconnect(self):
        from paho.mqtt import client as mqtt
        config = {
            "host": "fixture.invalid", "port": 8883, "username": "xiaoxi_validator",
            "password": "fixture-only", "ca_file": "/fixture/ca.crt",
            "state_path": "/fixture/sequence.json",
        }
        with patch.object(mqtt, "Client", return_value=self.client) as factory:
            validator.make_client(config, self.relay)
        self.assertEqual(factory.call_args.kwargs["callback_api_version"], mqtt.CallbackAPIVersion.VERSION2)
        self.assertNotIn("clean_session", factory.call_args.kwargs)
        self.assertEqual(factory.call_args.kwargs["protocol"], mqtt.MQTTv5)
        self.client.username_pw_set.assert_called_once_with("xiaoxi_validator", "fixture-only")
        self.client.tls_set.assert_called_once_with(ca_certs="/fixture/ca.crt")
        self.client.tls_insecure_set.assert_not_called()
        self.client.reconnect_delay_set.assert_called_once_with(min_delay=1, max_delay=60)
        self.client.max_inflight_messages_set.assert_called_once_with(1)
        self.client.max_queued_messages_set.assert_called_once_with(1)
        self.assertFalse(factory.call_args.kwargs["reconnect_on_failure"])
        self.assertEqual(self.client.connect_timeout, 10)


class MainTests(unittest.TestCase):
    def test_main_configuration_is_private_deferred_and_exact(self):
        config = {
            "host": "fixture.invalid", "port": 8883, "username": "xiaoxi_validator",
            "password": "secret-fixture", "ca_file": "/fixture/ca.crt",
            "state_path": "/fixture/sequence.json",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture-config.json"
            path.write_bytes(encoded(config))
            path.chmod(0o600)
            with patch.object(sys, "argv", ["validator", "--config", str(path)]), patch.object(validator, "run") as run:
                self.assertEqual(validator.main(), 0)
                run.assert_called_once_with(config)
                path.chmod(0o644)
                run.reset_mock()
                with self.assertLogs("validator", level="WARNING") as caught:
                    self.assertEqual(validator.main(), 1)
                run.assert_not_called()
                self.assertNotIn("secret-fixture", " ".join(caught.output))
                path.chmod(0o600)
                for change in ({"extra": "secret-fixture"}, {"port": True}, {"username": "xiaoxi_node01"}, {"ca_file": "relative-ca.crt"}, {"state_path": "relative-state.json"}):
                    path.write_bytes(encoded(config | change))
                    with self.assertLogs("validator", level="WARNING"):
                        self.assertEqual(validator.main(), 1)
                    run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
