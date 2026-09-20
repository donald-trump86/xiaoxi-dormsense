"""Validate examples and rejection behavior against the documented contract."""

from copy import deepcopy
import unittest

from jsonschema import ValidationError

from scripts.check_repository import ROOT, load_json, validate_telemetry


class TelemetryContractTests(unittest.TestCase):
    def setUp(self):
        self.sample = load_json(ROOT / "data/samples/telemetry.simulated.json")

    def test_sample_valid(self):
        validate_telemetry(self.sample, "xiaoxi/dorm/node90/telemetry")

    def test_absent_sensors_are_null(self):
        for field in ("temperature", "humidity", "light"):
            self.sample[field] = None
            self.sample["sensor_status"][field] = "missing"
        validate_telemetry(self.sample)

    def test_synchronized_utc_time(self):
        self.sample["timestamp"] = "2026-01-01T00:00:00Z"
        validate_telemetry(self.sample)

    def test_invalid_fields_rejected(self):
        cases = {
            "schema_version": "2.0", "node_id": "room/person",
            "sequence": -1, "boot_id": "", "humidity": 101,
            "light": 100, "simulated": "true", "rssi": 10,
            "timestamp": "2026-02-30T00:00:00Z",
        }
        for key, value in cases.items():
            with self.subTest(key=key):
                changed = deepcopy(self.sample)
                changed[key] = value
                with self.assertRaises(ValidationError):
                    validate_telemetry(changed)

    def test_unversioned_or_unknown_fields_rejected(self):
        del self.sample["schema_version"]
        with self.assertRaises(ValidationError):
            validate_telemetry(self.sample)
        self.sample["schema_version"] = "1.0"
        self.sample["secret"] = "not-a-real-secret"
        with self.assertRaises(ValidationError):
            validate_telemetry(self.sample)

    def test_unsynchronized_non_utc_time_rejected(self):
        for stamp in ("2026-01-01T08:00:00+08:00", 0, "yesterday"):
            self.sample["timestamp"] = stamp
            with self.subTest(stamp=stamp), self.assertRaises(ValidationError):
                validate_telemetry(self.sample)

    def test_cross_field_consistency(self):
        self.sample["sensor_status"]["temperature"] = "error"
        with self.assertRaises(ValueError):
            validate_telemetry(self.sample)
        self.sample["temperature"] = None
        validate_telemetry(self.sample)
        self.sample["sensor_status"]["temperature"] = "ok"
        with self.assertRaises(ValueError):
            validate_telemetry(self.sample)

    def test_topic_node_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            validate_telemetry(self.sample, "xiaoxi/dorm/node01/telemetry")

    def test_non_finite_numbers_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            self.sample["temperature"] = value
            with self.assertRaises(ValueError):
                validate_telemetry(self.sample)


if __name__ == "__main__":
    unittest.main()
