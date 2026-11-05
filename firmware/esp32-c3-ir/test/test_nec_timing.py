"""Synthetic offline checks; never connect to a node or emit infrared."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
from io import BytesIO, StringIO
import json
from pathlib import Path
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "nec_timing.py"
SPEC = importlib.util.spec_from_file_location("nec_timing", MODULE_PATH)
nec_timing = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(nec_timing)

BOOT = "node02-00000001"
CAPTURE = 4294967294
# Literal wire order, independent of the analyzer's reference generator.
BITS = "01011010000000101010010101011010"


def ideal_timings():
    timings = [2, 8960, 4480]
    for bit in BITS:
        timings.extend((560, 1680 if bit == "1" else 560))
    return timings + [560]


def events_for(timings=None, *, rawlen=None, overflow=0, limit=160):
    timings = ideal_timings() if timings is None else timings
    rawlen = len(timings) if rawlen is None else rawlen
    kept = min(rawlen, limit)
    events = []
    for offset in range(0, kept, 16):
        times = timings[offset:offset + 16]
        detail = (
            f"raw_timing capture={CAPTURE} rawlen={rawlen} kept={kept} "
            f"truncated={int(rawlen > kept)} overflow={overflow} "
            f"offset={offset} count={len(times)} unit=us "
            f"times={','.join(map(str, times))}"
        )
        events.append({
            "schema_version": "1.0", "node_id": "node02", "boot_id": BOOT,
            "event_type": "ir_raw_timing", "simulated": False,
            "sequence": (CAPTURE + offset // 16) % (2 ** 32), "detail": detail,
        })
    return events


def assemble(events):
    return nec_timing.assemble_capture(
        events, boot_id=BOOT, capture_sequence=CAPTURE
    )


class CaptureAssemblyTests(unittest.TestCase):
    def test_complete_out_of_order_and_uint32_sequence_wrap(self):
        events = events_for()
        self.assertEqual([event["sequence"] for event in events],
                         [4294967294, 4294967295, 0, 1, 2])
        events.insert(1, {"event_type": "ir_remote_captured"})
        capture = assemble(reversed(events))
        self.assertEqual(capture["timings_us"], ideal_timings())
        self.assertEqual(capture["rawlen"], 68)
        self.assertEqual(capture["kept"], 68)
        self.assertFalse(capture["overflow"])
        self.assertFalse(capture["truncated"])

    def test_new_300_and_historical_160_caps_remain_unambiguous(self):
        for limit in (160, 300):
            timings = [2] + [560] * (limit - 1)
            capture = assemble(events_for(timings, rawlen=65535, limit=limit))
            self.assertEqual(capture["kept"], limit)
            self.assertEqual(capture["timings_us"], timings)
            self.assertTrue(capture["truncated"])
        full = assemble(events_for([2] + [560] * 279, limit=300))
        self.assertEqual(full["kept"], 280)
        self.assertFalse(full["truncated"])

    def test_foreign_boot_and_capture_are_not_combined(self):
        foreign_boot = dict(events_for()[0], boot_id="node02-00000002")
        foreign_capture = dict(events_for()[0], sequence=10)
        foreign_capture["detail"] = foreign_capture["detail"].replace(
            f"capture={CAPTURE}", "capture=10"
        )
        result = assemble([foreign_boot, foreign_capture] + events_for())
        self.assertEqual(result["timings_us"], ideal_timings())

    def test_missing_first_middle_or_last_chunk_fails(self):
        for index in (0, 2, 4):
            events = events_for()
            del events[index]
            with self.subTest(index=index), self.assertRaisesRegex(
                    ValueError, "incomplete"):
                assemble(events)

    def test_duplicate_and_conflicting_chunks_fail(self):
        events = events_for()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            assemble(events + [dict(events[0])])
        conflicting = dict(events[0])
        conflicting["detail"] = conflicting["detail"].replace(
            "times=2,8960", "times=2,8962"
        )
        with self.assertRaisesRegex(ValueError, "conflicting"):
            assemble(events + [conflicting])

    def test_envelope_metadata_is_strict(self):
        changes = (
            ("schema_version", "1"), ("node_id", "node01"),
            ("boot_id", "node02-invalid"), ("simulated", True),
            ("simulated", 0), ("sequence", True), ("sequence", -1),
            ("sequence", 2 ** 32), ("sequence", CAPTURE - 1),
            ("detail", None),
        )
        for key, value in changes:
            events = events_for()
            events[0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                assemble(events)

    def test_detail_format_and_bounds_are_strict(self):
        mutations = (
            ("capture=4294967294", "capture=4294967296"),
            ("rawlen=68", "rawlen=65536"),
            ("rawlen=68", "rawlen=0"),
            ("kept=68", "kept=161"),
            ("kept=68", "kept=67"),
            ("truncated=0", "truncated=1"),
            ("overflow=0", "overflow=2"),
            ("offset=0", "offset=1"),
            ("offset=0", "offset=160"),
            ("count=16", "count=0"),
            ("count=16", "count=17"),
            ("count=16", "count=15"),
            ("unit=us", "unit=ticks"),
            ("times=2,8960", "times=-2,8960"),
            ("times=2,8960", "times=2,131071"),
            ("times=2,8960", "times=2,８９６０"),
            ("times=2,8960", "times=2, 8960"),
        )
        for old, new in mutations:
            events = events_for()
            events[0]["detail"] = events[0]["detail"].replace(old, new)
            with self.subTest(new=new), self.assertRaises(ValueError):
                assemble(events)
        for suffix in ("\n", " ", ","):
            events = events_for()
            events[0]["detail"] += suffix
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                assemble(events)

    def test_inconsistent_flags_and_metadata_fail(self):
        for old, new in (("overflow=0", "overflow=1"),
                         ("rawlen=68 kept=68", "rawlen=69 kept=69")):
            events = events_for()
            events[1]["detail"] = events[1]["detail"].replace(old, new)
            with self.subTest(new=new), self.assertRaisesRegex(
                    ValueError, "metadata"):
                assemble(events)

    def test_collection_and_argument_bounds(self):
        with self.assertRaisesRegex(ValueError, "too many"):
            assemble([{"event_type": "other"}] * 257)
        with self.assertRaises(ValueError):
            assemble(events_for([560] * 160, rawlen=65536))
        for boot, sequence in (("bad", 0), (BOOT, -1), (BOOT, 2 ** 32),
                               (BOOT, True), (BOOT, "10")):
            with self.subTest(boot=boot, sequence=sequence):
                with self.assertRaises(ValueError):
                    nec_timing.assemble_capture(
                        [], boot_id=boot, capture_sequence=sequence
                    )
        for bad in (None, "events", {}, [None]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                assemble(bad)

    def test_overflow_truncation_and_storage_limit_are_preserved(self):
        capture = assemble(events_for(overflow=1))
        self.assertTrue(capture["overflow"])
        capture = assemble(events_for([560] * 160, rawlen=65535))
        self.assertEqual(capture["rawlen"], 65535)
        self.assertTrue(capture["truncated"])
        self.assertEqual(len(capture["timings_us"]), 160)
        timings = ideal_timings()
        timings[10] = 131070
        capture = assemble(events_for(timings))
        self.assertEqual(capture["saturated_indices"], [10])
        report = nec_timing.analyze_nec(capture["timings_us"])
        self.assertFalse(report["matches_expected_timing"])
        self.assertEqual(report["storage_limit_indices"], [10])
        self.assertTrue(any("optical" in item for item in report["conclusions"]))


class NecTimingTests(unittest.TestCase):
    def test_ideal_fixed_value_and_exact_reference(self):
        report = nec_timing.analyze_nec(ideal_timings())
        self.assertTrue(report["matches_expected_timing"])
        self.assertEqual(report["expected"]["bits_msb_first"], BITS)
        self.assertEqual(report["expected"]["value_hex"], "0x5A02A55A")
        self.assertEqual(report["expected"]["timings_us"], ideal_timings())
        self.assertEqual(report["expected"]["frame_us"], 64400)
        self.assertEqual(report["expected"]["min_gap_us"], 22400)
        self.assertEqual(report["expected"]["nominal_send_gap_us"], 43680)
        self.assertEqual(report["observed_bits_by_space"], BITS)
        self.assertEqual(report["space_value_hex"], "0x5A02A55A")
        self.assertEqual(report["mismatches"], [])
        self.assertEqual(report["pulse_groups"]["data_marks"]["median_ratio"], 1)

    def test_skip_synthetic_sentinel_for_pulse_matching(self):
        timings = ideal_timings()
        for value in (100000, 3):
            timings[0] = value
            report = nec_timing.analyze_nec(timings)
            with self.subTest(value=value):
                self.assertTrue(report["matches_expected_timing"])
                self.assertFalse(report["sentinel_matches_library"])
                self.assertEqual(report["mismatches"], [])

    def test_bit_order_and_payload_difference_are_reported(self):
        # This value is bit-palindromic within three bytes, but 0x02 is not.
        timings = [2, 8960, 4480]
        reversed_per_byte = "01011010010000001010010101011010"
        for bit in reversed_per_byte:
            timings.extend((560, 1680 if bit == "1" else 560))
        timings.append(560)
        report = nec_timing.analyze_nec(timings)
        self.assertFalse(report["matches_expected_timing"])
        self.assertEqual(report["observed_bits_by_space"], reversed_per_byte)
        self.assertEqual(report["space_value_hex"], "0x5A40A55A")
        self.assertEqual(len(report["mismatches"]), 2)

    def test_default_tolerance_and_mark_excess_windows(self):
        windows = nec_timing.analyze_nec(ideal_timings())["windows_us"]
        self.assertEqual(windows, {
            "header_mark": [6758, 11262], "header_space": [3322, 5538],
            "bit_mark": [458, 762], "zero_space": [382, 638],
            "one_space": [1222, 2038],
        })
        for index, key in ((1, "header_mark"), (2, "header_space"),
                           (3, "bit_mark"), (4, "zero_space"),
                           (6, "one_space"), (67, "bit_mark")):
            for value in windows[key]:
                timings = ideal_timings()
                timings[index] = value
                with self.subTest(index=index, value=value):
                    self.assertTrue(nec_timing.analyze_nec(timings)[
                        "matches_expected_timing"])
            for value in (windows[key][0] - 2, windows[key][1] + 2):
                timings = ideal_timings()
                timings[index] = value
                with self.subTest(index=index, value=value):
                    self.assertFalse(nec_timing.analyze_nec(timings)[
                        "matches_expected_timing"])

    def test_lengths_scaling_zero_and_odd_values_are_not_proof_of_nec(self):
        for timings in ([], ideal_timings()[:-1], ideal_timings() + [22400],
                        [value * 2 for value in ideal_timings()]):
            with self.subTest(length=len(timings)):
                self.assertFalse(nec_timing.analyze_nec(timings)[
                    "matches_expected_timing"])
        timings = ideal_timings()
        timings[3] = 0
        report = nec_timing.analyze_nec(timings)
        self.assertEqual(report["mismatches"][0]["index"], 3)
        timings[3] = 561
        report = nec_timing.analyze_nec(timings)
        self.assertEqual(report["non_tick_aligned_indices"], [3])
        self.assertFalse(report["matches_expected_timing"])

    def test_analysis_input_bounds(self):
        for bad in (None, (2, 8960), [True], [-1], [131071], [1.0], [2] * 301):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                nec_timing.analyze_nec(bad)


class CliTests(unittest.TestCase):
    def test_json_report_keeps_loss_flags_separate_from_timing_match(self):
        for overflow in (0, 1):
            payload = json.dumps(events_for(overflow=overflow)).encode("utf-8")
            output = StringIO()
            with patch.object(Path, "open", return_value=BytesIO(payload)):
                with redirect_stdout(output):
                    status = nec_timing.main([
                        "synthetic.json", "--boot-id", BOOT,
                        "--capture-sequence", str(CAPTURE),
                    ])
            report = json.loads(output.getvalue())
            self.assertEqual(status, 0)
            self.assertTrue(report["nec_comparison"]["matches_expected_timing"])
            self.assertEqual(report["capture_without_loss_flags"], not overflow)
            self.assertEqual(report["capture"]["overflow"], bool(overflow))

    def test_cli_rejects_incomplete_and_oversized_evidence(self):
        payloads = (
            json.dumps(events_for()[:-1]).encode("utf-8"),
            b" " * (1024 * 1024 + 1),
            b"not JSON",
        )
        for payload in payloads:
            with patch.object(Path, "open", return_value=BytesIO(payload)):
                with redirect_stderr(StringIO()):
                    with self.assertRaises(SystemExit) as error:
                        nec_timing.main([
                            "synthetic.json", "--boot-id", BOOT,
                            "--capture-sequence", str(CAPTURE),
                        ])
            self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
