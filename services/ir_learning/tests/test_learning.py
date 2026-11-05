"""Synthetic, offline regressions; never connect to MQTT or physical hardware."""
import copy
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from services.ir_learning.model import LearningSession, STATE_FIELDS
from services.ir_learning.transport import CaptureCollector, strict_json


BOOT = "node02-1234abcd"
SESSION = "a" * 32
MODULUS = 2**32


def state(**changes):
    result = dict.fromkeys(STATE_FIELDS)
    result.update(power=True, mode=1, temp_c=24, fan=1, swingv=0)
    result.update(changes)
    return result


def capture(decoded=None, *, protocol="KELVINATOR", bits=128, rawlen=280):
    return {
        "boot_id": BOOT, "protocol": protocol, "bits": bits,
        "state": decoded, "rawlen": rawlen, "overflow": False,
        "truncated": False,
        "timings_us": [2] + [500 + 2 * index for index in range(1, rawlen)],
    }


class FakeTransport:
    def __init__(self):
        self.armed = []
        self.cancelled = []

    def arm(self, session_id, seconds):
        self.armed.append((session_id, seconds))

    def cancel(self, session_id):
        self.cancelled.append(session_id)


class OfflineTestCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        for target in ("socket.create_connection", "socket.socket"):
            guard = patch(target, side_effect=AssertionError("network_forbidden"))
            guard.start()
            self.addCleanup(guard.stop)


class LearningSessionTests(OfflineTestCase):
    def setUp(self):
        super().setUp()
        private = tempfile.TemporaryDirectory(prefix="xiaoxi-ir-model-tests-")
        self.addCleanup(private.cleanup)
        self.directory = Path(private.name) / "profiles"
        self.transport = FakeTransport()
        self.session = LearningSession(self.directory, self.transport)

    def deliver(self, sample):
        session_id, seconds = self.transport.armed[-1]
        self.assertEqual(seconds, 45)
        return self.session.receive(session_id, sample)

    def baseline(self, decoded=None):
        self.assertEqual(self.session.start()["status"], "ready")
        self.assertTrue(self.deliver(capture(state() if decoded is None else decoded)))
        self.assertEqual(self.session.public()["status"], "captured")

    def test_expiry_requires_new_baseline_before_comparing_next_key(self):
        self.baseline()
        self.session.next("temp_up")
        self.session.expire(self.transport.armed[-1][0])
        with self.assertRaisesRegex(ValueError, "baseline_required"):
            self.session.next("fan")
        self.session.next("baseline")
        self.deliver(capture(state(temp_c=26)))
        self.assertEqual(self.session.next("fan")["status"], "ready")

    def test_lost_arm_ack_requires_new_baseline(self):
        self.baseline()
        with patch.object(self.transport, "arm", side_effect=ValueError("node_response_timeout")):
            with self.assertRaisesRegex(ValueError, "receiver_not_ready"):
                self.session.next("temp_up")
        with self.assertRaisesRegex(ValueError, "baseline_required"):
            self.session.next("fan")
        self.assertEqual(self.session.public()["record_count"], 1)
        self.assertEqual(self.session.next("baseline")["status"], "ready")

    def test_stale_skip_does_not_clear_newer_window(self):
        self.baseline()
        self.session.next("fan")
        active = self.session.data["capture"].copy()
        with self.assertRaisesRegex(ValueError, "button_mismatch"):
            self.session.skip(button="temp_up")
        self.assertEqual(self.session.data["capture"], active)
        self.assertEqual(self.transport.cancelled, [])
        self.assertEqual(self.session.public()["status"], "ready")
        self.assertEqual(self.session.public()["record_count"], 1)

    def test_restart_requires_baseline_without_losing_saved_records(self):
        self.baseline()
        resumed = LearningSession(self.directory, FakeTransport())
        self.assertEqual(resumed.public()["record_count"], 1)
        with self.assertRaisesRegex(ValueError, "baseline_required"):
            resumed.next("temp_up")

    def test_skip_and_cancel_release_model_lock_before_transport_callback(self):
        import threading
        self.baseline()
        def cancel_with_callback(_):
            completed = threading.Event()
            worker = threading.Thread(target=lambda: (self.session.public(), completed.set()), daemon=True)
            worker.start()
            worker.join(.5)
            self.assertTrue(completed.is_set(), "callback blocked on model lock")
        self.transport.cancel = cancel_with_callback
        self.session.next("fan")
        self.session.skip()
        with self.assertRaisesRegex(ValueError, "baseline_required"):
            self.session.next("fan")
        self.session.next("baseline")
        self.session.cancel()
        self.assertEqual(self.session.public()["status"], "cancelled")

    def test_baseline_then_temp_up_preserves_evidence_without_ac_claim(self):
        self.baseline()
        self.session.next("temp_up")
        self.assertTrue(self.deliver(capture(state(temp_c=25))))
        public = self.session.public()
        self.assertEqual(public["record_count"], 2)
        self.assertEqual(public["changes"], {"temp_c": {"before": 24, "after": 25}})
        self.assertEqual(public["validation"]["basis"], "library_state_transition")
        record = self.session.data["records"][-1]
        self.assertTrue(record["semantics_verified"])
        self.assertFalse(record["appliance_response_verified"])
        self.assertEqual(record["capture"]["timings_us"], capture()["timings_us"])
        self.assertNotIn("timings_us", json.dumps(public))

    def test_wrong_known_key_updates_next_before_state_but_is_not_bound(self):
        self.baseline()
        self.session.next("temp_up")
        self.assertTrue(self.deliver(capture(state(fan=2))))
        public = self.session.public()
        self.assertEqual(public["status"], "rejected")
        self.assertEqual(public["record_count"], 1)
        self.assertEqual(public["validation"]["basis"], "no_expected_change")
        self.assertEqual(public["changes"], {"fan": {"before": 1, "after": 2}})
        with self.assertRaisesRegex(ValueError, "manual_confirmation_not_applicable"):
            self.session.confirm("温度增加", True)
        self.session.next("temp_up")
        self.deliver(capture(state(temp_c=25, fan=2)))
        record = self.session.data["records"][-1]
        self.assertEqual(record["before"]["state"]["fan"], 2)
        self.assertEqual(record["changes"], {"temp_c": {"before": 24, "after": 25}})
        self.assertEqual(self.session.public()["record_count"], 2)

    def test_wrong_temperature_direction_is_rejected(self):
        self.baseline()
        self.session.next("temp_up")
        self.deliver(capture(state(temp_c=23)))
        public = self.session.public()
        self.assertEqual(public["status"], "rejected")
        self.assertEqual(public["record_count"], 1)
        self.assertEqual(public["validation"]["basis"], "wrong_temperature_direction")
        self.session.next("temp_down")
        self.deliver(capture(state(temp_c=22)))
        self.assertEqual(self.session.public()["changes"], {
            "temp_c": {"before": 23, "after": 22},
        })

    def test_unknown_requires_explicit_label_and_stays_unverified(self):
        self.session.start()
        self.deliver(capture(protocol="UNKNOWN", bits=0))
        public = self.session.public()
        self.assertEqual(public["status"], "needs_confirmation")
        self.assertEqual(public["record_count"], 0)
        self.assertEqual(public["validation"]["basis"], "manual_label_unverified")
        with self.assertRaisesRegex(ValueError, "explicit_label_confirmation_required"):
            self.session.confirm("当前基线", False)
        self.session.confirm("当前基线", True)
        record = self.session.data["records"][0]
        self.assertEqual(record["label"], "当前基线")
        self.assertEqual(record["semantic_source"], "user_report_unverified")
        self.assertFalse(record["semantics_verified"])
        self.assertFalse(record["appliance_response_verified"])
        self.assertIsNone(record["capture"]["state"])
        self.assertIsNone(record["capture"]["nominal_carrier_khz"])

    def test_unsupported_null_does_not_become_false_or_a_verified_change(self):
        self.baseline(state(light=None))
        self.session.next("light")
        self.deliver(capture(state(light=None)))
        public = self.session.public()
        self.assertEqual(public["status"], "needs_confirmation")
        self.assertIsNone(public["observed"]["light"])
        self.assertNotIn("light", public["changes"])
        self.assertEqual(public["record_count"], 1)
        self.session.confirm("屏显键", True)
        self.assertFalse(self.session.data["records"][-1]["semantics_verified"])

    def test_partial_gree_keeps_full_waveform_and_reports_warning(self):
        self.session.start()
        sample = capture(state(), protocol="GREE", bits=64)
        self.deliver(sample)
        public = self.session.public()
        self.assertEqual(public["observed"]["coverage"], "partial_protocol")
        self.assertTrue(public["validation"]["warnings"])
        self.assertIn("GREE", " ".join(public["validation"]["warnings"]))
        record = self.session.data["records"][0]
        self.assertEqual(record["capture"]["timings_us"], sample["timings_us"])
        self.assertEqual(len(record["capture"]["timings_us"]), 280)
        self.assertFalse(record["appliance_response_verified"])

    def test_short_140_frame_is_rejected_and_requires_new_baseline(self):
        self.baseline()
        self.session.next("temp_up")
        self.assertFalse(self.deliver(capture(state(temp_c=25), rawlen=140)))
        public = self.session.public()
        self.assertEqual(public["status"], "rejected")
        self.assertEqual(public["record_count"], 1)
        self.assertEqual(public["validation"]["basis"], "unexpected_frame_length")
        with self.assertRaisesRegex(ValueError, "baseline_required"):
            self.session.next("temp_up")
        self.session.next("baseline")
        self.deliver(capture(state(temp_c=25)))
        self.session.next("temp_up")
        self.deliver(capture(state(temp_c=26)))
        self.assertEqual(self.session.public()["status"], "captured")

    def test_recording_the_same_key_twice_retains_both_transitions(self):
        self.baseline()
        for temperature in (25, 26):
            self.session.next("temp_up")
            self.deliver(capture(state(temp_c=temperature)))
        records = self.session.data["records"]
        self.assertEqual([item["button"] for item in records], [
            "baseline", "temp_up", "temp_up",
        ])
        self.assertEqual(len({item["record_id"] for item in records}), 3)
        self.assertEqual([item["changes"]["temp_c"] for item in records[1:]], [
            {"before": 24, "after": 25}, {"before": 25, "after": 26},
        ])

    def test_restart_keeps_records_expires_window_and_uses_private_modes(self):
        self.baseline()
        self.session.next("temp_up")
        self.deliver(capture(state(temp_c=25)))
        records = copy.deepcopy(self.session.data["records"])
        profile_id = self.session.public()["profile_id"]
        self.session.next("mode")
        restarted_transport = FakeTransport()
        restarted = LearningSession(self.directory, restarted_transport)
        self.assertEqual(restarted.public()["status"], "expired")
        self.assertEqual(restarted.public()["profile_id"], profile_id)
        self.assertEqual(restarted.data["records"], records)
        self.assertIsNone(restarted.data["capture"])
        self.assertEqual(restarted_transport.armed, [])
        self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode), 0o700)
        files = list(self.directory.iterdir())
        self.assertEqual({path.name for path in files}, {
            "active.json", profile_id + ".json",
        })
        for path in files:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        stored = json.loads((self.directory / (profile_id + ".json")).read_text())
        self.assertEqual(stored["records"], records)
        self.assertEqual(stored["status"], "expired")

    def test_stale_session_capture_is_ignored_without_consuming_window(self):
        self.session.start()
        self.assertFalse(self.session.receive("b" * 32, capture(state())))
        self.assertEqual(self.session.public()["status"], "ready")
        self.assertEqual(self.session.public()["record_count"], 0)
        self.assertTrue(self.deliver(capture(state())))


def event(sequence, event_type, detail, *, boot_id=BOOT):
    return {
        "schema_version": "1.0", "node_id": "node02", "simulated": False,
        "boot_id": boot_id, "sequence": sequence % MODULUS,
        "event_type": event_type,
        "detail": json.dumps(detail) if isinstance(detail, dict) else detail,
    }


def learning_event(kind, number, *, session_id=SESSION):
    detail = {"kind": kind, "capture": number, "session_id": session_id}
    if kind == "capture":
        detail.update(protocol="KELVINATOR", bits=128, state=state())
    sequence = number - 1 if kind == "capture" else number + 18
    return event(sequence, "ir_learning", detail)


def timing_event(number, offset, *, rawlen=280, boot_id=BOOT):
    kept = min(rawlen, 300)
    count = min(16, kept - offset)
    times = [2 if offset + index == 0 else 500 + 2 * (offset + index)
             for index in range(count)]
    detail = (
        f"raw_timing capture={number} rawlen={rawlen} kept={kept} "
        f"truncated={int(rawlen > kept)} overflow=0 offset={offset} "
        f"count={count} unit=us times=" + ",".join(map(str, times))
    )
    return event(number + offset // 16, "ir_raw_timing", detail, boot_id=boot_id)


class CaptureCollectorTests(OfflineTestCase):
    def started(self, number=41):
        collector = CaptureCollector(SESSION, BOOT)
        self.assertIsNone(collector.feed(learning_event("capture", number)))
        return collector

    def test_all_parts_reassemble_across_uint32_wrap(self):
        for number in (41, 0, MODULUS - 2):
            with self.subTest(capture=number):
                collector = self.started(number)
                for offset in reversed(range(0, 280, 16)):
                    self.assertIsNone(collector.feed(timing_event(number, offset)))
                result = collector.feed(learning_event("complete", number))
                self.assertEqual(result["capture_sequence"], number)
                self.assertEqual(result["boot_id"], BOOT)
                self.assertEqual(result["timings_us"], capture()["timings_us"])
                self.assertEqual(result["rawlen"], 280)
                self.assertFalse(result["overflow"])
                self.assertFalse(result["truncated"])

    def test_missing_first_middle_or_all_parts_fail_closed(self):
        for missing in (0, 16, "all"):
            with self.subTest(missing=missing):
                collector = self.started()
                for offset in range(0, 280, 16):
                    if missing != "all" and offset != missing:
                        collector.feed(timing_event(41, offset))
                with self.assertRaisesRegex(ValueError, "missing_capture_parts"):
                    collector.feed(learning_event("complete", 41))

    def test_duplicate_part_is_rejected(self):
        collector = self.started()
        first = timing_event(41, 0)
        collector.feed(first)
        with self.assertRaisesRegex(ValueError, "invalid_or_duplicate_timing_part"):
            collector.feed(first)

    def test_conflicting_part_metadata_is_rejected(self):
        collector = self.started()
        collector.feed(timing_event(41, 0))
        with self.assertRaisesRegex(ValueError, "inconsistent_timing_parts"):
            collector.feed(timing_event(41, 16, rawlen=282))

    def test_wrong_boot_cannot_fill_part_gap(self):
        collector = self.started()
        with self.assertRaisesRegex(ValueError, "invalid_capture_envelope"):
            collector.feed(timing_event(41, 0, boot_id="node02-87654321"))
        self.assertEqual(collector.parts, {})

    def test_foreign_session_and_capture_cannot_fill_part_gap(self):
        collector = self.started()
        original = copy.deepcopy(collector.metadata)
        for kind in ("capture", "complete"):
            self.assertIsNone(collector.feed(learning_event(
                kind, 41, session_id="b" * 32,
            )))
        self.assertEqual(collector.metadata, original)
        for offset in range(0, 280, 16):
            self.assertIsNone(collector.feed(timing_event(99, offset)))
        self.assertEqual(collector.parts, {})
        with self.assertRaisesRegex(ValueError, "missing_capture_parts"):
            collector.feed(learning_event("complete", 41))

    def test_wrong_part_sequence_is_rejected(self):
        collector = self.started()
        part = timing_event(41, 0)
        part["sequence"] += 1
        with self.assertRaisesRegex(ValueError, "invalid_or_duplicate_timing_part"):
            collector.feed(part)

    def test_ambiguous_json_metadata_is_rejected(self):
        for detail in ('{"capture":1,"capture":2}', '{"bits":NaN}'):
            with self.subTest(detail=detail), self.assertRaises(ValueError):
                strict_json(detail)


if __name__ == "__main__":
    unittest.main()
