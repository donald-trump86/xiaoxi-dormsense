"""The default simulator path must be offline and truthfully labelled."""

import json
import random
import subprocess
import sys
import unittest

from scripts.check_repository import ROOT, validate_telemetry
from simulator.mqtt_node import make_sample


class OfflineSimulatorTests(unittest.TestCase):
    def run_node(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "simulator/mqtt_node.py"), *args],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )

    def test_default_offline_batch(self):
        result = self.run_node("--count", "3", "--node-id", "node90")
        self.assertEqual(result.returncode, 0, result.stderr)
        samples = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(samples), 3)
        self.assertEqual([s["sequence"] for s in samples], [0, 1, 2])
        self.assertEqual(len({s["boot_id"] for s in samples}), 1)
        for sample in samples:
            validate_telemetry(sample)
            self.assertTrue(sample["simulated"])
            self.assertIsNone(sample["timestamp"])

    def test_seed_reproduces_values(self):
        first = make_sample("node90", "test-boot", 0, random.Random(42))
        second = make_sample("node90", "test-boot", 0, random.Random(42))
        self.assertEqual(first, second)

    def test_new_process_has_new_boot_id(self):
        first = json.loads(self.run_node("--count", "1").stdout)
        second = json.loads(self.run_node("--count", "1").stdout)
        self.assertNotEqual(first["boot_id"], second["boot_id"])

    def test_invalid_arguments_fail(self):
        for args in (
            ("--count", "0"), ("--node-id", "person-name"),
            ("--interval", "0"), ("--interval", "nan"),
        ):
            with self.subTest(args=args):
                result = self.run_node(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
