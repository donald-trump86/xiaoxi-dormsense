"""Small synthetic SQLite fixtures; no access to the actual HA database."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from analytics.src import recorder_report as report

NOW = datetime(2026, 11, 5, 1, 0, tzinfo=timezone.utc)


class RecorderReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "history.sqlite"
        self.db = sqlite3.connect(self.path)
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE states_meta (metadata_id INTEGER PRIMARY KEY, entity_id TEXT);
            CREATE TABLE state_attributes (attributes_id INTEGER PRIMARY KEY, shared_attrs TEXT);
            CREATE TABLE states (state_id INTEGER PRIMARY KEY, state TEXT,
              attributes_id INTEGER, metadata_id INTEGER, last_updated_ts REAL);
        """)
        for i, entity in enumerate((*report.ENTITIES, "sensor.unrelated"), 1):
            self.db.execute("INSERT INTO states_meta VALUES (?,?)", (i, entity))

    def add(self, entity=1, age=10, encoded=None):
        if encoded is None:
            encoded = json.dumps({"simulated": False, "sequence": 1,
                                  "private_unused_field": "MUST_NOT_LEAVE_ADAPTER"})
        attr = self.db.execute("INSERT INTO state_attributes(shared_attrs) VALUES (?)", (encoded,)).lastrowid
        self.db.execute("INSERT INTO states(state,attributes_id,metadata_id,last_updated_ts) VALUES (?,?,?,?)",
                        ("23.1", attr, entity, NOW.timestamp() - age))
        self.db.commit()

    def test_scoped_window_projection_and_database_unchanged(self):
        self.add(age=10)
        self.add(entity=2, age=86400)
        self.add(entity=3, age=86401)
        self.add(entity=1, age=-1)
        self.add(entity=4, age=10)
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        rows = report.read_recorder_history(self.path, now=NOW)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["entity_id"], report.ENTITIES[1])
        self.assertEqual(rows[1]["entity_id"], report.ENTITIES[0])
        self.assertNotIn("MUST_NOT_LEAVE_ADAPTER", json.dumps(rows))
        self.assertEqual(set(rows[1]["attributes"]), {"simulated", "sequence"})
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)

    def test_window_is_86400_seconds_across_daylight_saving(self):
        from zoneinfo import ZoneInfo
        self.add()
        for now, age, expected in (
            (datetime(2026, 3, 8, 12, tzinfo=ZoneInfo("America/New_York")), 23.5 * 3600, 1),
            (datetime(2026, 11, 1, 12, tzinfo=ZoneInfo("America/New_York")), 24.5 * 3600, 0),
        ):
            with self.subTest(now=now):
                self.db.execute("UPDATE states SET last_updated_ts=?", (now.timestamp() - age,))
                self.db.commit()
                self.assertEqual(len(report.read_recorder_history(self.path, now=now)), expected)

    def test_malformed_attributes_remain_invalid_reset_markers(self):
        for value in ("not json", '{"sequence":1,"sequence":2}', '{"value":NaN}', "[]", "x" * 17000):
            self.add(encoded=value)
        rows = report.read_recorder_history(self.path, now=NOW)
        self.assertTrue(all(row["attributes"] is None for row in rows))
        self.assertEqual(len(rows), 5)

    def test_row_limit_fails_without_partial_report(self):
        self.add(); self.add()
        with patch.object(report, "MAX_ROWS", 1):
            with self.assertRaisesRegex(ValueError, "history_row_limit"):
                report.read_recorder_history(self.path, now=NOW)

    def test_symlink_and_naive_now_are_rejected(self):
        alias = self.path.parent / "link.sqlite"
        alias.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError, "regular_database_required"):
            report.read_recorder_history(alias, now=NOW)
        with self.assertRaisesRegex(ValueError, "aware_now_required"):
            report.read_recorder_history(self.path, now=NOW.replace(tzinfo=None))


if __name__ == "__main__":
    unittest.main()
