"""Apply the XiaoXi patch only to its exact approved pinned upstream sources.

Standard library only. Validate all inputs and all result hashes before writing
any target. This is a build/isolated-test helper, never a live-container updater.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


SOURCE_PATHS = (
    "hermes_cli/web_routers/audio.py",
    "tools/tts_tool.py",
    "tools/tts_tool_providers.py",
    "tools/transcription_local.py",
    "web/src/components/ChatSidebar.tsx",
    "web/src/pages/ChatPage.tsx",
    "hermes_cli/banner.py",
    "hermes_cli/cli_render.py",
    "hermes_cli/dashboard_auth/login_page.py",
    "ui-tui/src/components/branding.tsx",
    "ui-tui/src/theme.ts",
    "ui-tui/src/app/useMainApp.ts",
    "ui-tui/src/app/uiStore.ts",
    "web/src/App.tsx",
    "web/src/components/SidebarFooter.tsx",
    "web/index.html",
)
BASE_IMAGE = (
    "nousresearch/hermes-agent@sha256:"
    "39c4ac5a8eaecddc525cd680eb4bda1143f2b12e8f21e2d63c2d5d471a8390c8"
)
HUNK = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@\n")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patched_sources(patch: bytes, originals: dict[str, bytes]) -> dict[str, bytes]:
    """Render strict unified hunks in memory; reject fuzz, offset, and extra files."""
    lines = patch.decode("utf-8").splitlines(keepends=True)
    results = {}
    index = 0
    while index < len(lines):
        header = lines[index]
        if not header.startswith("--- a/") or not header.endswith("\n"):
            raise ValueError("Invalid patch file header")
        relative = header[len("--- a/"):-1]
        if relative not in originals or relative in results:
            raise ValueError("Unexpected or repeated patch target")
        index += 1
        if index >= len(lines) or lines[index] != f"+++ b/{relative}\n":
            raise ValueError("Patch target headers disagree")
        index += 1
        original = originals[relative].decode("utf-8").splitlines(keepends=True)
        output = []
        cursor = 0
        hunks = 0
        while index < len(lines) and lines[index].startswith("@@ "):
            match = HUNK.fullmatch(lines[index])
            if match is None:
                raise ValueError("Invalid hunk header")
            old_start, old_count, new_start, new_count = (
                int(value) if value is not None else 1 for value in match.groups()
            )
            start = max(old_start - 1, 0)
            if not cursor <= start <= len(original):
                raise ValueError("Hunk position is outside source")
            output.extend(original[cursor:start])
            if len(output) != max(new_start - 1, 0):
                raise ValueError("Hunk result position disagrees")
            cursor = start
            consumed = added = 0
            index += 1
            while consumed < old_count or added < new_count:
                if index >= len(lines) or lines[index][:1] not in (" ", "+", "-"):
                    raise ValueError("Incomplete hunk")
                marker, content = lines[index][0], lines[index][1:]
                if marker in (" ", "-"):
                    if cursor >= len(original) or original[cursor] != content:
                        raise ValueError("Hunk context disagrees with source")
                    cursor += 1
                    consumed += 1
                if marker in (" ", "+"):
                    output.append(content)
                    added += 1
                if consumed > old_count or added > new_count:
                    raise ValueError("Hunk line counts disagree")
                index += 1
            hunks += 1
        if not hunks:
            raise ValueError("Patch file has no hunks")
        output.extend(original[cursor:])
        results[relative] = "".join(output).encode("utf-8")
    if set(results) != set(SOURCE_PATHS):
        raise ValueError("Patch must cover exactly the approved source files")
    return results


def apply_patch(root: Path, manifest_path: Path, patch_path: Path, *, check: bool = False) -> dict:
    """Verify complete pre/post images; write only after every check succeeds."""
    root = root.resolve(strict=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("base_image") != BASE_IMAGE:
        raise ValueError("Unsupported patch baseline")
    rows = manifest.get("files", [])
    if len(rows) != len(SOURCE_PATHS) or {row["path"] for row in rows} != set(SOURCE_PATHS):
        raise ValueError("Manifest must name exactly the approved source files")
    patch = patch_path.read_bytes()
    if sha256(patch) != manifest.get("patch_sha256"):
        raise ValueError("Patch SHA-256 mismatch")
    originals = {}
    targets = {}
    for row in rows:
        relative = row["path"]
        target = root / relative
        if target.resolve(strict=True) != target or not target.is_file():
            raise ValueError("Source path must be a regular non-symlink file")
        original = target.read_bytes()
        if sha256(original) != row["before_sha256"]:
            raise ValueError(f"Pristine source SHA-256 mismatch: {relative}")
        originals[relative], targets[relative] = original, target
    results = patched_sources(patch, originals)
    for row in rows:
        if sha256(results[row["path"]]) != row["after_sha256"]:
            raise ValueError(f"Result source SHA-256 mismatch: {row['path']}")
    if not check:
        for relative in SOURCE_PATHS:
            targets[relative].write_bytes(results[relative])
    return {"verified_files": len(results), "written": not check}


def main() -> int:
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/opt/hermes"))
    parser.add_argument("--manifest", type=Path, default=base / "patches/manifest.json")
    parser.add_argument("--patch", type=Path, default=base / "patches/hermes.patch")
    parser.add_argument("--check", action="store_true", help="Validate without writing")
    args = parser.parse_args()
    try:
        report = apply_patch(args.root, args.manifest, args.patch, check=args.check)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Patch rejected: {error}\n")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
