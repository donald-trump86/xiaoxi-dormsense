"""Reject dependency regressions while exposing the pinned base's known conflict."""
from __future__ import annotations

import argparse
import importlib
import importlib.metadata as metadata
import json
from pathlib import Path
import re
import subprocess
import sys


BASE_IMAGE = (
    "nousresearch/hermes-agent@sha256:"
    "39c4ac5a8eaecddc525cd680eb4bda1143f2b12e8f21e2d63c2d5d471a8390c8"
)
KNOWN_CONFLICT = (
    "The package `msal` requires `cryptography>=2.5,<49`, "
    "but `50.0.0` is installed"
)
BASE_VERSIONS = {"msal": "1.36.0", "cryptography": "50.0.0"}
CLEAN_ENV = {
    "PATH": "/opt/hermes/.venv/bin:/usr/local/bin:/usr/bin:/bin",
    "HOME": "/tmp",
    "TMPDIR": "/tmp",
    "LANG": "C.UTF-8",
}


def parse_check(stdout: str, stderr: str, returncode: int) -> list[str]:
    """Parse the pinned uv format; unknown output or a failed checker is fatal."""
    if returncode not in (0, 1):
        raise ValueError(f"Dependency checker failed with exit {returncode}")
    conflicts = []
    declared_count = None
    for line in (stdout + "\n" + stderr).splitlines():
        line = line.strip()
        if not line or re.fullmatch(r"Checked \d+ packages? in \S+", line):
            continue
        count = re.fullmatch(r"Found (\d+) incompatibilit(?:y|ies)", line)
        if count:
            if declared_count is not None:
                raise ValueError("Duplicate dependency-check summary")
            declared_count = int(count.group(1))
        elif line.startswith("The package `"):
            conflicts.append(line)
        elif line != "All installed packages are compatible":
            raise ValueError(f"Unexpected dependency-check output: {line}")
    if returncode == 1 and (not conflicts or declared_count != len(conflicts)):
        raise ValueError("Incomplete dependency-conflict diagnostics")
    if returncode == 0 and (conflicts or declared_count not in (None, 0)):
        raise ValueError("Inconsistent dependency-check result")
    return sorted(conflicts)


def capture_snapshot() -> dict:
    result = subprocess.run(
        [
            "/usr/local/bin/uv", "pip", "check", "--no-config",
            "--python", sys.executable,
        ],
        env=CLEAN_ENV,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    snapshot = {
        "schema_version": 1,
        "base_image": BASE_IMAGE,
        "conflicts": parse_check(result.stdout, result.stderr, result.returncode),
        "baseline_packages": {name: metadata.version(name) for name in BASE_VERSIONS},
    }
    validate_baseline(snapshot)
    return snapshot


def validate_baseline(snapshot: dict) -> None:
    expected = {
        "schema_version": 1,
        "base_image": BASE_IMAGE,
        "conflicts": [KNOWN_CONFLICT],
        "baseline_packages": BASE_VERSIONS,
    }
    if snapshot != expected:
        raise ValueError("Dependency conflicts or baseline package versions changed")


def compare_snapshots(before: dict, after: dict) -> None:
    validate_baseline(before)
    validate_baseline(after)
    if before != after:
        raise ValueError("Voice installation changed the dependency conflict baseline")


def verify_voice_lock(lock_path: Path) -> int:
    rows = re.findall(
        r"^([a-z][a-z0-9-]+)==([^\s]+)",
        lock_path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if len(rows) != 35 or len(dict(rows)) != 35:
        raise ValueError("Expected the complete 35-package voice lock")
    for name, expected in rows:
        if metadata.version(name) != expected:
            raise ValueError(f"Installed voice dependency differs from lock: {name}")
    for module in ("edge_tts", "faster_whisper", "ctranslate2", "zhconv"):
        importlib.import_module(module)
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--record", type=Path)
    mode.add_argument("--compare", type=Path)
    args = parser.parse_args()
    current = capture_snapshot()
    if args.record:
        args.record.write_text(json.dumps(current, sort_keys=True) + "\n", encoding="utf-8")
        print("Recorded known upstream conflict: " + KNOWN_CONFLICT)
    else:
        before = json.loads(args.compare.read_text(encoding="utf-8"))
        compare_snapshots(before, current)
        count = verify_voice_lock(Path(__file__).with_name("requirements-voice.lock"))
        print("Unchanged upstream conflict: " + KNOWN_CONFLICT)
        print(f"All {count} voice lock versions and four library imports passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, metadata.PackageNotFoundError, subprocess.SubprocessError) as error:
        print(f"Dependency verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
