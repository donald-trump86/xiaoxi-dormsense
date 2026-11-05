"""Synthetic, offline checks for bounded HA archive summaries; no real data."""
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
from itertools import repeat
import json
from pathlib import Path
import sys
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "environment.py"
SPEC = importlib.util.spec_from_file_location("environment_summary", MODULE_PATH)
environment = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = environment
SPEC.loader.exec_module(environment)
summarize_history = environment.summarize_history

NOW = datetime(2026, 6, 2, 12, tzinfo=timezone.utc)
ENTITIES = {
    name: "sensor.xiaoxi_node01_" + name
    for name in ("temperature", "humidity", "light")
}


def row(value="20", *, channel="temperature", age=10, sequence=1,
        boot="node01-00000001", written_age=None, **attributes):
    received = NOW - timedelta(seconds=age)
    attrs = {
        "simulated": False,
        "boot_id": boot,
        "sequence": sequence,
        "received_at": received.isoformat(),
        "unit_of_measurement": {
            "temperature": "°C", "humidity": "%", "light": None,
        }[channel],
    }
    attrs.update(attributes)
    written = received if written_age is None else NOW - timedelta(
        seconds=written_age
    )
    return {
        "entity_id": ENTITIES[channel], "state": value,
        "attributes": attrs, "last_updated_ts": written.timestamp(),
    }


def channel(rows, name="temperature"):
    return summarize_history(rows, now=NOW)["channels"][name]


class EnvironmentSummaryTests(unittest.TestCase):
    def test_empty_archive_and_explicit_method_limits(self):
        result = summarize_history([], now=NOW)
        self.assertEqual(result["window"]["seconds"], 86400)
        self.assertEqual(set(result["channels"]), set(ENTITIES))
        self.assertFalse(result["method"]["calibrated"])
        self.assertFalse(result["method"]["accuracy_validated"])
        self.assertFalse(result["method"]["trend_forecast"])
        self.assertIn("algorithmic", result["method"]["variance_interpretation"])
        for item in result["channels"].values():
            self.assertEqual(item["count"], 0)
            self.assertIsNone(item["mean"])
            self.assertIsNone(item["latest_observation"])
            self.assertIsNone(item["current_estimate"])
        json.dumps(result, allow_nan=False)

    def test_now_requires_a_valid_timezone(self):
        for invalid in (None, "now", True, datetime(2026, 6, 2)):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    summarize_history([], now=invalid)
        offset_now = NOW.astimezone(timezone(timedelta(hours=8)))
        self.assertEqual(summarize_history([], now=offset_now),
                         summarize_history([], now=NOW))

    def test_fixed_entities_statistics_and_no_private_attribute_output(self):
        rows = [row("20", age=20), row("22", sequence=2),
                row("50", channel="humidity"), row("0.3", channel="light")]
        rows[0]["attributes"]["private_field"] = "must_not_escape"
        rows.append({"entity_id": "sensor.private_other", "state": "secret"})
        before = copy.deepcopy(rows)
        result = summarize_history(rows, now=NOW)
        self.assertEqual(rows, before)
        item = result["channels"]["temperature"]
        self.assertEqual((item["count"], item["min"], item["max"], item["mean"]),
                         (2, 20, 22, 21))
        self.assertEqual(item["latest_observation"]["kind"],
                         "archived_observation")
        self.assertEqual(item["first_valid_received_at"],
                         rows[0]["attributes"]["received_at"])
        self.assertEqual(item["last_valid_received_at"],
                         rows[1]["attributes"]["received_at"])
        self.assertEqual(result["channels"]["humidity"]["unit"], "%")
        self.assertIsNone(result["channels"]["light"]["unit"])
        encoded = json.dumps(result, allow_nan=False)
        self.assertNotIn("private_other", encoded)
        self.assertNotIn("must_not_escape", encoded)
        self.assertNotIn("node_id", encoded)
        self.assertEqual(result["input"]["ignored_rows"], 1)

    def test_window_boundaries_and_future_received_time(self):
        rows = [row(age=86400), row(age=86400.01, sequence=2),
                row(age=-1, sequence=3, written_age=0),
                row(age=0, sequence=4)]
        item = channel(rows)
        self.assertEqual(item["count"], 2)
        self.assertEqual(sum(item["rejected_reasons"].values()), 2)
        self.assertEqual(item["current_status"], "fresh")
        future_write = row(age=0, written_age=-1, sequence=5)
        self.assertIsNone(channel(rows + [future_write])["current_estimate"])

    def test_write_time_and_received_time_must_agree(self):
        for received_age, written_age, accepted in (
                (10, 12, True), (10, 12.001, False),
                (40, 5, True), (40.001, 5, False)):
            with self.subTest(received_age=received_age, written_age=written_age):
                item = channel([row(age=received_age, written_age=written_age)])
                self.assertEqual(item["count"], int(accepted))
        for stamp in (True, float("nan"), float("inf"), None, "0"):
            bad = row()
            bad["last_updated_ts"] = stamp
            self.assertEqual(channel([bad])["count"], 0)
        invalid = row()
        invalid["last_updated_ts"] = None
        self.assertIsNone(channel([invalid, row(sequence=2)])["current_estimate"])

    def test_simulated_boot_and_sequence_metadata_are_checked(self):
        invalid_attrs = [
            {"simulated": True}, {"simulated": 0}, {"simulated": None},
            {"boot_id": "node02-00000001"}, {"boot_id": "node90-00000001"},
            {"boot_id": "node01-0000000A"}, {"boot_id": "node01-1"},
            {"boot_id": None}, {"sequence": True}, {"sequence": -1},
            {"sequence": 4294967296}, {"sequence": 1.0},
            {"node_id": "node02"}, {"node_id": None},
        ]
        for attrs in invalid_attrs:
            with self.subTest(attrs=attrs):
                self.assertEqual(channel([row(**attrs)])["count"], 0)
        for key in ("simulated", "boot_id", "sequence", "received_at"):
            sample = row()
            del sample["attributes"][key]
            self.assertEqual(channel([sample])["count"], 0)
        self.assertEqual(channel([row(sequence=0)])["count"], 1)
        self.assertEqual(channel([row(sequence=4294967295)])["count"], 1)

    def test_received_time_is_aware_iso_and_not_invented(self):
        for stamp in ("2026-06-02T11:59:50", "not_a_time", 1, None):
            self.assertEqual(channel([row(received_at=stamp)])["count"], 0)
        received = (NOW - timedelta(seconds=10)).astimezone(
            timezone(timedelta(hours=8))
        ).isoformat()
        self.assertEqual(channel([row(received_at=received)])["count"], 1)

    def test_numeric_states_units_ranges_and_nonfinite_values(self):
        for name, low, high in (("temperature", -40, 125),
                                ("humidity", 0, 100), ("light", 0, 1)):
            for value in (str(low), str(high)):
                self.assertEqual(
                    channel([row(value, channel=name)], name)["count"], 1
                )
            for value in (str(low - 0.1), str(high + 0.1), "nan", "inf",
                          "-inf", "true", "", None, True, 23.0):
                with self.subTest(channel=name, value=value):
                    item = channel([row(value, channel=name)], name)
                    self.assertEqual(item["count"], 0)
            invalid_unit = "lux" if name == "light" else "wrong"
            invalid = row(channel=name, unit_of_measurement=invalid_unit)
            self.assertEqual(channel([invalid], name)["count"], 0)
        missing = row()
        del missing["attributes"]["unit_of_measurement"]
        self.assertEqual(channel([missing])["count"], 0)
        light_missing = row("0.5", channel="light")
        del light_missing["attributes"]["unit_of_measurement"]
        self.assertEqual(channel([light_missing], "light")["count"], 1)

    def test_reordered_rows_are_processed_by_ha_write_time(self):
        rows = [row("20", age=30, sequence=1),
                row("21", age=20, sequence=2), row("22", sequence=3)]
        self.assertEqual(channel(rows), channel(list(reversed(rows))))

    def test_duplicate_and_descending_sequences_cannot_update_filter_twice(self):
        rows = [row("20", age=20, sequence=2),
                row("100", age=10, sequence=2),
                row("110", age=5, sequence=1)]
        item = channel(rows)
        self.assertEqual(item["count"], 1)
        self.assertEqual(item["max"], 20)
        self.assertEqual(item["rejected_reasons"]["duplicate_sequence"], 1)
        self.assertEqual(item["rejected_reasons"]["sequence_regression"], 1)
        self.assertIsNone(item["current_estimate"])
        rows.append(row("22", age=0, sequence=3))
        self.assertEqual(channel(rows)["count"], 2)

    def test_received_timestamp_regression_on_later_ha_write_is_rejected(self):
        rows = [row("20", age=20, sequence=1),
                row("99", age=21, written_age=10, sequence=2)]
        item = channel(rows)
        self.assertEqual(item["count"], 1)
        self.assertEqual(item["rejected_reasons"]["received_time_regression"], 1)
        self.assertIsNone(item["current_estimate"])

    def test_boot_change_resets_and_retired_boot_cannot_reappear(self):
        rows = [row("20", age=20),
                row("30", sequence=0, boot="node01-00000002")]
        item = channel(rows)
        self.assertEqual(item["reset_count"], 1)
        self.assertEqual(item["current_estimate"]["value"], 30)
        rows.append(row("100", age=0, sequence=2))
        item = channel(rows)
        self.assertEqual(item["count"], 2)
        self.assertEqual(item["rejected_reasons"]["retired_boot"], 1)
        self.assertIsNone(item["current_estimate"])

    def test_unavailable_with_retained_metadata_is_a_reset_marker(self):
        valid = row("20", age=20)
        offline = copy.deepcopy(valid)
        offline.update(state="unavailable", last_updated_ts=NOW.timestamp() - 15)
        item = channel([valid, offline])
        self.assertEqual(item["count"], 1)
        self.assertEqual(item["reset_count"], 1)
        self.assertFalse(item["latest_ha_state_healthy"])
        self.assertIsNone(item["current_estimate"])
        item = channel([valid, offline, row("30", sequence=2)])
        self.assertEqual(item["count"], 2)
        self.assertEqual(item["current_estimate"]["value"], 30)
        self.assertEqual(item["reset_count"], 1)

    def test_other_invalid_states_also_reset_filter(self):
        for invalid in ("unknown", "None", "nan", True):
            rows = [row("20", age=20), row(invalid, age=15, sequence=2),
                    row("30", sequence=3)]
            item = channel(rows)
            self.assertEqual(item["count"], 2)
            self.assertEqual(item["reset_count"], 1)
            self.assertEqual(item["current_estimate"]["value"], 30)

    def test_long_gap_resets_but_exact_35_second_gap_is_continuous(self):
        item = channel([row("20", age=50), row("30", sequence=2)])
        self.assertEqual(item["gap_count"], 1)
        self.assertEqual(item["reset_count"], 1)
        self.assertEqual(item["current_estimate"]["value"], 30)
        item = channel([row("20", age=45), row("30", sequence=2)])
        self.assertEqual(item["gap_count"], 0)
        self.assertLess(item["current_estimate"]["value"], 30)

    def test_exact_35_seconds_old_is_stale_and_archive_stays_available(self):
        item = channel([row(age=35)])
        self.assertEqual(item["count"], 1)
        self.assertEqual(item["current_status"], "stale")
        self.assertIsNone(item["current_estimate"])
        self.assertEqual(item["latest_observation"]["value"], 20)
        self.assertIsNotNone(channel([row(age=34.999)])["current_estimate"])

    def test_scalar_kalman_uses_actual_dt_and_explicit_defaults(self):
        item = channel([row("20", age=20), row("22", sequence=2)])
        predicted_p = 0.04 + 0.0001 * 10
        gain = predicted_p / (predicted_p + 0.04)
        self.assertAlmostEqual(item["current_estimate"]["value"], 20 + gain * 2)
        self.assertAlmostEqual(item["current_estimate"]["algorithmic_variance"],
                               (1 - gain) * predicted_p)
        self.assertEqual(item["filter_defaults"],
                         {"q_per_second": 0.0001, "r": 0.04, "initial_p": 0.04})
        result = summarize_history([], now=NOW)
        humidity = result["channels"]["humidity"]["filter_defaults"]
        light = result["channels"]["light"]["filter_defaults"]
        self.assertEqual(humidity["r"], 0.25)
        self.assertEqual(light["q_per_second"], 1e-6)

    def test_input_is_bounded_before_processing(self):
        with self.assertRaisesRegex(ValueError, "too_many_rows"):
            summarize_history(repeat({}, 100001), now=NOW)
        for invalid in (None, True, 123):
            with self.assertRaisesRegex(ValueError, "invalid_rows"):
                summarize_history(invalid, now=NOW)
        result = summarize_history(
            [None, {"entity_id": "sensor.unrelated"}], now=NOW
        )
        self.assertEqual(result["input"]["ignored_rows"], 2)


if __name__ == "__main__":
    unittest.main()
