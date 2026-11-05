"""Offline guard tests with synthetic six-file source trees; no Hermes imports."""
import difflib
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from apply_patch import BASE_IMAGE, SOURCE_PATHS, apply_patch


class PatchGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="xiaoxi-patch-guard-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "sources"
        self.patch_path = self.base / "patch.diff"
        self.manifest_path = self.base / "manifest.json"
        diff = []
        rows = []
        self.before = {}
        self.after = {}
        for index, relative in enumerate(SOURCE_PATHS):
            before, after = f"original-{index}\n", f"result-{index}\n"
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(before, encoding="utf-8")
            self.before[relative], self.after[relative] = before.encode(), after.encode()
            diff.extend(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True), fromfile="a/" + relative, tofile="b/" + relative))
            rows.append({"path": relative, "before_sha256": self.digest(before.encode()), "after_sha256": self.digest(after.encode())})
        patch = "".join(diff).encode()
        self.patch_path.write_bytes(patch)
        self.manifest = {"schema_version": 1, "base_image": BASE_IMAGE, "patch_sha256": self.digest(patch), "files": rows}
        self.save_manifest()

    @staticmethod
    def digest(data):
        return hashlib.sha256(data).hexdigest()

    def save_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def contents(self):
        return {relative: (self.root / relative).read_bytes() for relative in SOURCE_PATHS}

    def apply(self, **kwargs):
        return apply_patch(self.root, self.manifest_path, self.patch_path, **kwargs)

    def test_check_then_apply_verifies_all_six_exact_results(self):
        self.assertEqual(self.apply(check=True), {"verified_files": 6, "written": False})
        self.assertEqual(self.contents(), self.before)
        self.assertEqual(self.apply(), {"verified_files": 6, "written": True})
        self.assertEqual(self.contents(), self.after)

    def test_changed_last_source_rejects_before_any_target_write(self):
        (self.root / SOURCE_PATHS[-1]).write_bytes(b"unexpected source\n")
        snapshot = self.contents()
        with self.assertRaisesRegex(ValueError, "Pristine source SHA-256 mismatch"):
            self.apply()
        self.assertEqual(self.contents(), snapshot)

    def test_altered_patch_rejects_before_any_target_write(self):
        self.patch_path.write_bytes(self.patch_path.read_bytes() + b"unexpected\n")
        with self.assertRaisesRegex(ValueError, "Patch SHA-256 mismatch"):
            self.apply()
        self.assertEqual(self.contents(), self.before)

    def test_wrong_result_hash_rejects_before_any_target_write(self):
        self.manifest["files"][-1]["after_sha256"] = "0" * 64
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "Result source SHA-256 mismatch"):
            self.apply()
        self.assertEqual(self.contents(), self.before)

    def test_valid_patch_hash_cannot_hide_wrong_hunk_context(self):
        patch = self.patch_path.read_bytes().replace(b"-original-0\n", b"-different-0\n", 1)
        self.patch_path.write_bytes(patch)
        self.manifest["patch_sha256"] = self.digest(patch)
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "Hunk context disagrees"):
            self.apply()
        self.assertEqual(self.contents(), self.before)

    def test_source_symlink_rejects_without_writing_its_destination(self):
        target = self.root / SOURCE_PATHS[-1]
        external = self.base / "external.txt"
        external.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(external)
        with self.assertRaisesRegex(ValueError, "non-symlink"):
            self.apply()
        self.assertEqual(external.read_bytes(), self.before[SOURCE_PATHS[-1]])
        self.assertEqual(self.contents(), self.before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
