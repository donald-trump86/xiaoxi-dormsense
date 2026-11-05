"""Apply and test the formal patch in an ephemeral pinned-image fixture.

Reads only the approved upstream sources and public installed TypeScript
compiler. No production container, runtime config, model, network, or audio API.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid


ROOT = Path(__file__).resolve().parents[1]
IMAGE = (
    "nousresearch/hermes-agent@sha256:"
    "39c4ac5a8eaecddc525cd680eb4bda1143f2b12e8f21e2d63c2d5d471a8390c8"
)
INPUTS = (
    "apply_patch.py",
    "check_voice_dependencies.py",
    "tests/test_dependency_baseline.py",
    "patches/hermes.patch",
    "patches/manifest.json",
    "tests/test_voice_patch.py",
    "tests/test_transcription_normalization.py",
    "tests/test_patch_guard.py",
    "tests/test_voice_playback.cjs",
    "tests/test_chat_continuation.cjs",
)
FIXTURE_PROGRAM = r'''
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

payload = json.load(sys.stdin)
base = Path(tempfile.mkdtemp(prefix="xiaoxi-hermes-offline-", dir="/tmp"))
for relative, text in payload["files"].items():
    target = base / relative
    if not target.resolve().is_relative_to(base):
        raise SystemExit("Invalid test input path")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
sys.path.insert(0, str(base))
from apply_patch import SOURCE_PATHS, apply_patch
sources = base / "sources"
for relative in SOURCE_PATHS:
    original = Path("/opt/hermes") / relative
    if original.resolve() != original:
        raise SystemExit("Unexpected pristine source symlink")
    target = sources / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(original.read_bytes())
manifest = base / "patches/manifest.json"
patch = base / "patches/hermes.patch"
print(json.dumps(apply_patch(sources, manifest, patch, check=True)), flush=True)
print(json.dumps(apply_patch(sources, manifest, patch)), flush=True)
for relative in SOURCE_PATHS:
    if relative.endswith(".py"):
        compile((sources / relative).read_text(encoding="utf-8"), relative, "exec")
print("Python compilation passed for all patched Python modules", flush=True)
if not payload["frontend_only"]:
    suite = unittest.defaultTestLoader.discover(str(base / "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
sidebar = (sources / "web/src/components/ChatSidebar.tsx").read_text(encoding="utf-8")
page = (sources / "web/src/pages/ChatPage.tsx").read_text(encoding="utf-8")
for name in ("test_voice_playback.cjs", "test_chat_continuation.cjs"):
    tests = (base / "tests" / name).read_text(encoding="utf-8")
    script = "globalThis.__sidebarSource = " + json.dumps(sidebar) + ";\n"
    script += "globalThis.__chatPageSource = " + json.dumps(page) + ";\n" + tests
    result = subprocess.run(["node", "-"], input=script, text=True, cwd="/opt/hermes/web", timeout=30, check=False)
    if result.returncode:
        raise SystemExit(result.returncode)
raise SystemExit(0)
'''


def main(*, frontend_only: bool = False) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-only", action="store_true", default=frontend_only)
    args = parser.parse_args()
    payload = {
        "files": {relative: (ROOT / relative).read_text(encoding="utf-8") for relative in INPUTS},
        "frontend_only": args.frontend_only,
    }
    name = "xiaoxi-hermes-offline-" + uuid.uuid4().hex
    command = [
        "docker", "run", "--rm", "--interactive", "--pull=never", "--name", name,
        "--network=none", "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--pids-limit=128", "--memory=512m",
        "--user=65534:65534", "--tmpfs=/tmp:rw,nosuid,nodev,size=128m,mode=1777",
        "--entrypoint=python", IMAGE, "-B", "-S", "-c", FIXTURE_PROGRAM,
    ]
    try:
        result = subprocess.run(command, input=json.dumps(payload), text=True, timeout=90, check=False)
    except subprocess.TimeoutExpired:
        # This exact unique name belongs to the fixture started immediately above.
        subprocess.run(["docker", "rm", "--force", name], timeout=10, check=False)
        print("Offline fixture timed out and was removed", file=sys.stderr)
        return 1
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
