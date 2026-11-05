#!/usr/bin/env python3
"""Offline integrity check of four explicitly provisioned Whisper files; no download."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat

MANIFEST = Path(__file__).resolve().parents[1] / "deploy/examples/whisper-base.manifest.json"
REQUIRED = {"config.json", "model.bin", "tokenizer.json", "vocabulary.txt"}


def verify_model(directory: Path, manifest: dict) -> dict:
    """Verify local file bytes, not model compatibility, transcription or provenance of old caches."""
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("MODEL_DIRECTORY")
    if manifest.get("format_version") != 1:
        raise ValueError("MANIFEST_VERSION")
    revision = manifest.get("revision")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("MANIFEST_REVISION")
    rows = manifest.get("files")
    if not isinstance(rows, list) or len(rows) != len(REQUIRED):
        raise ValueError("MANIFEST_FILES")
    validated = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("MANIFEST_FILES")
        name, size = row.get("path"), row.get("size")
        if not isinstance(name, str) or name not in REQUIRED or name in seen:
            raise ValueError("MANIFEST_PATH")
        seen.add(name)
        if type(size) is not int or size <= 0:
            raise ValueError("MANIFEST_SIZE")
        if set(row) == {"path", "size", "sha256"}:
            algorithm, length = "sha256", 64
        elif set(row) == {"path", "size", "git_blob_sha1"}:
            algorithm, length = "git_blob_sha1", 40
        else:
            raise ValueError("MANIFEST_HASH")
        expected = row[algorithm]
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{%d}" % length, expected):
            raise ValueError("MANIFEST_HASH")
        validated.append((name, size, algorithm, expected))
    for name, size, algorithm, expected in validated:
        path = directory / name
        try:
            info = path.lstat()
        except FileNotFoundError:
            raise ValueError("MODEL_FILE_MISSING:" + name) from None
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("MODEL_FILE_NOT_REGULAR:" + name)
        if info.st_size != size:
            raise ValueError("MODEL_SIZE:" + name)
        digest = hashlib.sha256() if algorithm == "sha256" else hashlib.sha1()
        if algorithm == "git_blob_sha1":
            digest.update(f"blob {size}\0".encode("ascii"))
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != expected:
            raise ValueError("MODEL_HASH:" + name)
    return {"verified_files": len(validated), "repository": manifest.get("repository"), "revision": revision}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        result = verify_model(args.directory, manifest)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Model verification failed: {error}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
