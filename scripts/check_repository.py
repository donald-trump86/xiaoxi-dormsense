#!/usr/bin/env python3
"""Offline checks: local Markdown paths, JSON/Schema, YAML syntax, synthetic sample."""

import json
import math
import os
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

import yaml
from jsonschema import Draft202012Validator, FormatChecker, SchemaError, ValidationError


ROOT = Path(__file__).resolve().parents[1]
IGNORED_DIRS = {
    ".git", ".venv", "venv", "__pycache__", ".pio", "node_modules",
    "runtime", "raw", "experiments-private", ".ipynb_checkpoints",
}
LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^\s)]+)(?:\s+\"[^\"]*\")?\)")


class HomeAssistantLoader(yaml.SafeLoader):
    """Parse the one HA include tag used here without reading/expanding its target."""


HomeAssistantLoader.add_constructor(
    "!include", lambda loader, node: loader.construct_scalar(node)
)


def repository_files():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS)
        for name in sorted(files):
            path = Path(base) / name
            if path.suffix in {".md", ".json", ".yaml", ".yml"}:
                yield path


def reject_constant(value):
    raise ValueError(f"Non-standard JSON constant: {value}")


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)


def telemetry_validator():
    schema = load_json(ROOT / "schemas/telemetry.schema.json")
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_telemetry(payload, topic=None):
    """Schema plus cross-field rules; receiver implementations must do both."""
    telemetry_validator().validate(payload)
    for field in ("temperature", "humidity", "light"):
        value = payload[field]
        if value is not None and not math.isfinite(value):
            raise ValueError(f"{field}: non-finite value")
        status = payload.get("sensor_status", {}).get(field)
        if status == "ok" and value is None:
            raise ValueError(f"{field}: ok requires a number")
        if status in {"missing", "error"} and value is not None:
            raise ValueError(f"{field}: {status} requires null")
    if topic is not None and topic != f"xiaoxi/dorm/{payload['node_id']}/telemetry":
        raise ValueError("Topic/payload node mismatch or invalid topic")


def check_markdown(path, text):
    errors = []
    for target in LINK_PATTERN.findall(text):
        target = target.strip("<>")
        parts = urlsplit(target)
        if parts.scheme or parts.netloc or not parts.path:
            continue
        destination = (path.parent / unquote(parts.path)).resolve()
        if not destination.is_relative_to(ROOT) or not destination.exists():
            errors.append(f"{path.relative_to(ROOT)}: broken local link {target}")
    return errors


def main():
    errors = []
    counts = {"markdown": 0, "json": 0, "yaml": 0}
    for path in repository_files():
        try:
            text = path.read_text(encoding="utf-8")
            if path.suffix == ".md":
                counts["markdown"] += 1
                errors.extend(check_markdown(path, text))
            elif path.suffix == ".json":
                counts["json"] += 1
                load_json(path)
            else:
                counts["yaml"] += 1
                yaml.load(text, Loader=HomeAssistantLoader)
        except (ValueError, yaml.YAMLError) as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
    try:
        sample = load_json(ROOT / "data/samples/telemetry.simulated.json")
        validate_telemetry(sample, "xiaoxi/dorm/node90/telemetry")
        if sample["simulated"] is not True:
            errors.append("Tracked sample must be explicitly synthetic")
    except (ValueError, OSError, ValidationError, SchemaError) as exc:
        errors.append(f"Telemetry sample/schema: {exc}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"PASS: {counts}; local paths, schema/sample and YAML syntax checked")
    print("Not checked: external URLs/anchors, HA runtime, Docker services or real hardware")
    return 0


if __name__ == "__main__":
    sys.exit(main())
