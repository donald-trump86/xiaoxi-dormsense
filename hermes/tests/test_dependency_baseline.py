"""Offline checks that the known upstream conflict cannot hide a new regression."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from check_voice_dependencies import (
    BASE_IMAGE,
    BASE_VERSIONS,
    KNOWN_CONFLICT,
    compare_snapshots,
    parse_check,
    validate_baseline,
    verify_voice_lock,
)


def baseline():
    return {
        "schema_version": 1,
        "base_image": BASE_IMAGE,
        "conflicts": [KNOWN_CONFLICT],
        "baseline_packages": dict(BASE_VERSIONS),
    }


class DependencyBaselineTests(unittest.TestCase):
    def test_exact_existing_conflict_is_accepted_independent_of_timing(self):
        output = "Checked 144 packages in 28ms\nFound 1 incompatibility\n" + KNOWN_CONFLICT
        self.assertEqual(parse_check("", output, 1), [KNOWN_CONFLICT])
        compare_snapshots(baseline(), copy.deepcopy(baseline()))

    def test_added_conflict_is_rejected(self):
        after = baseline()
        after["conflicts"].append("The package `new` requires `missing`, but it is not installed")
        with self.assertRaises(ValueError):
            compare_snapshots(baseline(), after)

    def test_changed_baseline_package_is_rejected(self):
        after = baseline()
        after["baseline_packages"]["cryptography"] = "48.0.0"
        with self.assertRaises(ValueError):
            compare_snapshots(baseline(), after)

    def test_missing_or_unknown_diagnostics_cannot_pass(self):
        for output in (
            "Found 2 incompatibilities\n" + KNOWN_CONFLICT,
            "Found 1 incompatibility\n",
            "warning: dependency inspection failed\n",
        ):
            with self.subTest(output=output), self.assertRaises(ValueError):
                parse_check("", output, 1)
        with self.assertRaises(ValueError):
            validate_baseline({**baseline(), "conflicts": []})

    def test_checker_failure_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_check("", "could not inspect environment", 2)

    def test_missing_transitive_version_fails_before_importing_libraries(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / "voice.lock"
            lock.write_text("".join(f"voice-dep{i}==1.0\n" for i in range(35)))
            with patch("check_voice_dependencies.metadata.version", return_value="0.9"), patch(
                "check_voice_dependencies.importlib.import_module"
            ) as imports:
                with self.assertRaisesRegex(ValueError, "differs from lock"):
                    verify_voice_lock(lock)
                imports.assert_not_called()


if __name__ == "__main__":
    unittest.main()
