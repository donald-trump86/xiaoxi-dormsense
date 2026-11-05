#!/usr/bin/env python3
"""Read only three HA recorder entities in a bounded day; emit summaries, not rows."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
import time

ENTITIES = tuple("sensor." + "xiaoxi_" + "node01_" + channel
                 for channel in ("temperature", "humidity", "light"))
MAX_ROWS = 100_000
MAX_ATTRIBUTES_BYTES = 16_384
ATTRIBUTE_KEYS = {"node_id", "boot_id", "sequence", "simulated", "received_at",
                  "unit_of_measurement"}


def _reject_constant(value):
    raise ValueError("nonfinite_json")


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def read_recorder_history(database: Path, *, now: datetime) -> list[dict]:
    """Snapshot the fixed entities via read-only SQLite, limited to [now-24h, now]."""
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("aware_now_required")
    database = Path(database)
    if database.is_symlink() or not database.is_file():
        raise ValueError("regular_database_required")
    uri = database.resolve(strict=True).as_uri() + "?mode=ro"
    end = now.timestamp()
    start = end - 86_400
    deadline = time.monotonic() + 5
    connection = sqlite3.connect(uri, uri=True, timeout=1, isolation_level=None)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA busy_timeout=1000")
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        connection.execute("BEGIN")
        cursor = connection.execute(
            "SELECT m.entity_id,s.state,a.shared_attrs,s.last_updated_ts "
            "FROM states AS s JOIN states_meta AS m ON m.metadata_id=s.metadata_id "
            "LEFT JOIN state_attributes AS a ON a.attributes_id=s.attributes_id "
            "WHERE m.entity_id IN (?,?,?) AND s.last_updated_ts>=? "
            "AND s.last_updated_ts<=? ORDER BY s.last_updated_ts,s.state_id LIMIT ?",
            (*ENTITIES, start, end, MAX_ROWS + 1),
        )
        rows = []
        for entity_id, state, encoded, written in cursor:
            if len(rows) >= MAX_ROWS:
                raise ValueError("history_row_limit")
            attributes = None
            if isinstance(encoded, str) and len(encoded.encode("utf-8")) <= MAX_ATTRIBUTES_BYTES:
                try:
                    decoded = json.loads(encoded, parse_constant=_reject_constant,
                                         object_pairs_hook=_unique_pairs)
                    if isinstance(decoded, dict):
                        attributes = {key: decoded[key] for key in ATTRIBUTE_KEYS if key in decoded}
                except (ValueError, RecursionError, UnicodeError):
                    pass
            rows.append({"entity_id": entity_id, "state": state,
                         "attributes": attributes, "last_updated_ts": written})
        return rows
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    args = parser.parse_args()
    try:
        if __package__:
            from .environment import summarize_history
        else:
            from environment import summarize_history
        now = datetime.now(timezone.utc)
        result = summarize_history(read_recorder_history(args.database, now=now), now=now)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
        return 0
    except (OSError, ValueError, sqlite3.Error, OverflowError):
        print("history_report_failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
