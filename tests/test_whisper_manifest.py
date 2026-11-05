"""Synthetic tiny files; these tests do not read/download/load real model weights."""
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest

from scripts.verify_whisper_model import verify_model


class WhisperManifestTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.manifest = {"format_version": 1, "repository": "synthetic-fixture", "revision": "a" * 40, "files": []}
        for name in ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt"):
            content = ("synthetic-only:" + name).encode()
            (self.root / name).write_bytes(content)
            row = {"path": name, "size": len(content)}
            if name == "model.bin":
                row["sha256"] = hashlib.sha256(content).hexdigest()
            else:
                row["git_blob_sha1"] = hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()
            self.manifest["files"].append(row)

    def test_verifies_git_blob_and_weight_sha256_with_bounded_reads(self):
        result = verify_model(self.root, self.manifest)
        self.assertEqual(result["verified_files"], 4)
        self.assertEqual(result["revision"], "a" * 40)

    def test_rejects_same_size_corruption_and_wrong_size(self):
        target = self.root / "model.bin"
        original = target.read_bytes()
        target.write_bytes(b"x" * len(original))
        with self.assertRaisesRegex(ValueError, "MODEL_HASH:model.bin"):
            verify_model(self.root, self.manifest)
        target.write_bytes(b"x")
        with self.assertRaisesRegex(ValueError, "MODEL_SIZE:model.bin"):
            verify_model(self.root, self.manifest)

    def test_rejects_missing_file(self):
        # A separate empty fixture avoids deleting an existing user/model file.
        with tempfile.TemporaryDirectory() as missing:
            with self.assertRaisesRegex(ValueError, "MODEL_FILE_MISSING"):
                verify_model(Path(missing), self.manifest)

    def test_rejects_duplicate_and_traversing_manifest_before_file_reads(self):
        for replacement in ("../outside", "config.json"):
            invalid = deepcopy(self.manifest)
            invalid["files"][1]["path"] = replacement
            with self.subTest(path=replacement), self.assertRaisesRegex(ValueError, "MANIFEST_PATH"):
                verify_model(self.root, invalid)

    def test_rejects_symlinks_and_git_hash_without_blob_header(self):
        with tempfile.TemporaryDirectory() as linked:
            linked = Path(linked)
            for row in self.manifest["files"]:
                (linked / row["path"]).symlink_to(self.root / row["path"])
            with self.assertRaisesRegex(ValueError, "MODEL_FILE_NOT_REGULAR"):
                verify_model(linked, self.manifest)
        invalid = deepcopy(self.manifest)
        raw = (self.root / "config.json").read_bytes()
        invalid["files"][0]["git_blob_sha1"] = hashlib.sha1(raw).hexdigest()
        with self.assertRaisesRegex(ValueError, "MODEL_HASH:config.json"):
            verify_model(self.root, invalid)


if __name__ == "__main__":
    unittest.main()
