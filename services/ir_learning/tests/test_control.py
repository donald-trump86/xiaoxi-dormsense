"""Control checks use only private temporary files and an in-memory fake node."""
import copy
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from services.ir_learning import control, replay
from services.ir_learning.model import LearningSession, STATE_FIELDS
from services.ir_learning.tests.test_replay import FakeTransport, private_json, sample


PROFILE = "a" * 32
OLD_PROFILE = "d" * 32
RECORD = "b" * 32
COMMAND = "c" * 32


class ControlTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="xiaoxi-ir-control-tests-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / "state"
        self.directory.mkdir(mode=0o700)
        self.config_path = self.root / "config.json"
        private_json(self.config_path, {
            "state_dir": str(self.directory), "expected_rawlen": 280,
            "mqtt_host": "offline.invalid", "mqtt_username": "offline-test",
            "mqtt_password": "FAKE_CONFIG_SECRET_DO_NOT_REFLECT",
        })
        self.session = SimpleNamespace(
            directory=self.directory, expected_rawlen=280,
            lock=threading.RLock(), data=None, transport=Mock(),
        )
        self.control = control.IRControl(self.session, self.config_path)
        self.transport = FakeTransport()
        self.factory = Mock(return_value=self.transport)
        guard = patch.object(replay, "LearningTransport", self.factory)
        guard.start()
        self.addCleanup(guard.stop)
        for target in ("socket.socket", "socket.create_connection"):
            guard = patch(target, side_effect=AssertionError("network_forbidden"))
            guard.start()
            self.addCleanup(guard.stop)

    def profile(self, profile_id=PROFILE, *, active=True, records=None):
        if records is None:
            records = [{
                "record_id": RECORD, "button": "power", "label": "开关",
                "recorded_at": "2026-11-06T01:00:00+00:00",
                "semantics_verified": True, "capture": sample(),
                "before": {"secret": "FAKE_BEFORE_SECRET_DO_NOT_REFLECT"},
                "secret": "FAKE_RECORD_SECRET_DO_NOT_REFLECT",
            }]
        value = {"schema_version": "1.0", "profile_id": profile_id,
                 "records": records, "secret": "FAKE_PROFILE_SECRET_DO_NOT_REFLECT"}
        private_json(self.directory / (profile_id + ".json"), value)
        if active:
            private_json(self.directory / "active.json", {"profile_id": profile_id})
            self.session.data = {"profile_id": profile_id, "capture": None,
                                 "status": "captured"}
        return value

    def save(self, value):
        private_json(self.directory / (value["profile_id"] + ".json"), value)

    def send(self, **kwargs):
        return self.control.send(PROFILE, RECORD, COMMAND,
                                 confirm_once=kwargs.pop("confirm_once", True),
                                 **kwargs)

    def assert_zero_mqtt(self):
        self.factory.assert_not_called()
        self.session.transport.assert_not_called()
        self.assertEqual(self.session.transport.mock_calls, [])
        self.assertEqual(self.transport.publications, [])
        self.assertEqual(self.transport.status_calls, 0)

    def test_empty_catalog_succeeds_without_config_mqtt_or_writes(self):
        self.config_path.unlink()
        result = self.control.catalog()
        self.assertTrue(result["ok"])
        self.assertEqual(result["profiles"], [])
        self.assertEqual(result["commands"], [])
        self.assertNotIn("profile_id", result)
        self.assertNotIn("active_profile_id", result)
        self.assertRegex(result["command_id"], r"^[0-9a-f]{32}$")
        self.assertNotEqual(result["command_id"], self.control.catalog()["command_id"])
        self.assertEqual(list(self.directory.iterdir()), [])
        self.assert_zero_mqtt()

    def test_catalog_uses_active_and_explicit_old_profile_without_mutation(self):
        self.profile()
        old = self.profile(OLD_PROFILE, active=False)
        old["records"][0]["capture"]["state"]["power"] = False
        self.save(old)
        original = {path.name: path.read_bytes() for path in self.directory.iterdir()}
        result = self.control.catalog()
        self.assertEqual(result["profile_id"], PROFILE)
        self.assertEqual(result["active_profile_id"], PROFILE)
        self.assertEqual({entry["profile_id"] for entry in result["profiles"]},
                         {PROFILE, OLD_PROFILE})
        self.assertEqual(sum(entry["active"] for entry in result["profiles"]), 1)
        selected = self.control.catalog(OLD_PROFILE)
        self.assertEqual(selected["profile_id"], OLD_PROFILE)
        self.assertEqual(selected["active_profile_id"], PROFILE)
        self.assertIs(selected["commands"][0]["state"]["power"], False)
        self.assertEqual(original,
                         {path.name: path.read_bytes() for path in self.directory.iterdir()})
        self.assert_zero_mqtt()

    def test_profiles_are_visible_without_active_index_but_not_implicitly_selected(self):
        self.profile(OLD_PROFILE, active=False)
        result = self.control.catalog()
        self.assertTrue(result["ok"])
        self.assertEqual(result["commands"], [])
        self.assertEqual(result["profiles"], [{"profile_id": OLD_PROFILE,
                                               "record_count": 1, "active": False}])
        self.assertTrue(self.control.catalog(OLD_PROFILE)["commands"][0]["replayable"])
        self.assert_zero_mqtt()

    def test_empty_active_profile_is_valid_and_old_records_remain_selectable(self):
        self.profile(records=[])
        self.profile(OLD_PROFILE, active=False)
        result = self.control.catalog()
        self.assertTrue(result["ok"])
        self.assertEqual(result["profile_id"], PROFILE)
        self.assertEqual(result["commands"], [])
        self.assertEqual(len(self.control.catalog(OLD_PROFILE)["commands"]), 1)
        self.assert_zero_mqtt()

    def test_catalog_projects_only_bounded_metadata_and_decoded_fields(self):
        profile = self.profile()
        profile["records"][0]["label"] = "label\n" + "x" * 1000
        self.save(profile)
        result = self.control.catalog()
        self.assertTrue(result["ok"])
        self.assertLessEqual(len(result["commands"][0]["label"]), 80)
        self.assertNotIn("\n", result["commands"][0]["label"])
        self.assertEqual(set(result), {"ok", "profile_id", "active_profile_id",
                                      "profiles", "commands", "command_id"})
        command = result["commands"][0]
        self.assertEqual(set(command), {
            "profile_id", "record_id", "button", "label", "recorded_at",
            "state", "protocol", "bits", "coverage", "semantics_verified", "replayable",
        })
        self.assertLessEqual(set(command["state"]), STATE_FIELDS)
        self.assertIs(command["state"]["power"], True)
        self.assertNotIn("light", command["state"])
        self.assertEqual(command["coverage"], "full_protocol")
        for forbidden in ("timings_us", "capture", "before", "secret", "mqtt_", str(self.root)):
            self.assertNotIn(forbidden, json.dumps(result))
        self.assert_zero_mqtt()

    def test_unknown_state_stays_unknown_and_cannot_replay(self):
        profile = self.profile()
        capture = profile["records"][0]["capture"]
        capture.update(protocol="UNKNOWN", bits=0, state=None,
                       nominal_carrier_khz=38, coverage="full_protocol")
        self.save(profile)
        command = self.control.catalog()["commands"][0]
        self.assertIsNone(command["state"])
        self.assertEqual(command["coverage"], "unknown")
        self.assertFalse(command["replayable"])
        self.assertEqual(command["unavailable_reason"], "invalid_replay_capture")
        result = self.send()
        self.assertEqual(result["error"], "invalid_replay_capture")
        self.assertFalse((self.directory / ("replay-" + COMMAND + ".json")).exists())
        self.assert_zero_mqtt()

    def test_replayability_matches_existing_waveform_guards(self):
        cases = []
        for key in ("overflow", "truncated"):
            capture = sample()
            capture[key] = True
            cases.append(capture)
        for length in (140, 279, 300, 302):
            cases.append(sample(length))
        for index, duration in ((0, 4), (1, 501), (1, 0), (1, 65536), (1, True)):
            capture = sample()
            capture["timings_us"][index] = duration
            cases.append(capture)
        capture = sample()
        capture["timings_us"][1:] = [4000] * 279
        cases.append(capture)
        capture = sample()
        capture.update(protocol="SAMSUNG")
        cases.append(capture)
        for capture in cases:
            with self.subTest(length=capture["rawlen"], timings=capture["timings_us"][:2]):
                profile = self.profile()
                profile["records"][0]["capture"] = capture
                self.save(profile)
                command = self.control.catalog()["commands"][0]
                self.assertFalse(command["replayable"])
                self.assertEqual(command["unavailable_reason"], "invalid_replay_capture")
        self.assert_zero_mqtt()

    def test_exactly_one_second_and_expected_300_entry_profile_are_replayable(self):
        profile = self.profile()
        profile["records"][0]["capture"]["timings_us"] = [2] + [3584] * 278 + [3648]
        self.save(profile)
        self.assertTrue(self.control.catalog()["commands"][0]["replayable"])
        self.session.expected_rawlen = 300
        profile["records"][0]["capture"] = sample(300)
        self.save(profile)
        self.assertTrue(self.control.catalog()["commands"][0]["replayable"])
        self.assert_zero_mqtt()

    def test_private_modes_links_and_ownership_fail_closed(self):
        self.profile()
        profile_path = self.directory / (PROFILE + ".json")
        index = self.directory / "active.json"
        for path, mode in ((profile_path, 0o644), (index, 0o644), (self.directory, 0o755)):
            with self.subTest(path=path.name):
                path.chmod(mode)
                self.assertFalse(self.control.catalog()["ok"])
                path.chmod(0o700 if path == self.directory else 0o600)
        linked = "e" * 32
        (self.directory / (linked + ".json")).symlink_to(profile_path)
        self.assertFalse(self.control.catalog(linked)["ok"])
        with patch.object(replay.os, "geteuid", return_value=os.geteuid() + 1):
            self.assertFalse(self.control.catalog()["ok"])
        self.assert_zero_mqtt()

    def test_malformed_and_missing_profiles_return_safe_codes(self):
        self.assertEqual(self.control.catalog(PROFILE)["error"], "invalid_profile")
        self.profile()
        for value in ({"schema_version": "1.0", "profile_id": PROFILE, "records": {}},
                      {"schema_version": "1.0", "profile_id": OLD_PROFILE, "records": []}):
            private_json(self.directory / (PROFILE + ".json"), value)
            result = self.control.catalog()
            self.assertFalse(result["ok"])
            self.assertNotIn(str(self.directory), json.dumps(result))
        path = self.directory / (PROFILE + ".json")
        path.write_text('{"records":[],"records":[],"secret":"FAKE_SECRET"}')
        self.assertFalse(self.control.catalog()["ok"])
        self.assert_zero_mqtt()

    def test_identifiers_are_validated_before_reading_or_sending(self):
        for value in ("../escape", "A" * 32, "a" * 31, 42, True, {}, []):
            with self.subTest(value=value):
                self.assertEqual(self.control.catalog(value)["error"], "invalid_identifier")
                for ids in ((value, RECORD, COMMAND), (PROFILE, value, COMMAND),
                            (PROFILE, RECORD, value)):
                    result = self.control.send(*ids, confirm_once=True)
                    self.assertEqual(result["error"], "invalid_identifier")
        self.assert_zero_mqtt()

    def test_profile_and_record_counts_are_bounded_and_duplicate_ids_unavailable(self):
        profile = self.profile()
        record = profile["records"][0]
        profile["records"] = [dict(record, record_id=f"{index:032x}") for index in range(128)]
        self.save(profile)
        result = self.control.catalog()
        self.assertEqual(len(result["commands"]), 128)
        profile["records"].append(dict(record, record_id="f" * 32))
        self.save(profile)
        self.assertEqual(self.control.catalog()["error"], "invalid_profile")
        profile["records"] = [record, copy.deepcopy(record)]
        self.save(profile)
        result = self.control.catalog()
        self.assertTrue(result["ok"])
        self.assertTrue(all(not command["replayable"] for command in result["commands"]))
        self.assertTrue(all(command["unavailable_reason"] == "record_not_unique_or_missing"
                            for command in result["commands"]))
        self.assert_zero_mqtt()

    def test_profile_summaries_are_capped_and_replay_journals_ignored(self):
        self.profile()
        for index in range(34):
            self.profile(f"{index:032x}", active=False, records=[])
        private_json(self.directory / ("replay-" + COMMAND + ".json"), {"secret": "FAKE_JOURNAL"})
        result = self.control.catalog()
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["profiles"]), 32)
        self.assertTrue(result["profiles_truncated"])
        self.assertIn(PROFILE, [entry["profile_id"] for entry in result["profiles"]])
        self.assert_zero_mqtt()

    def test_send_requires_literal_confirmation_before_mqtt_or_journal(self):
        self.profile()
        for confirmation in (False, None, 1, "true", [], {}):
            with self.subTest(confirmation=confirmation):
                self.assertEqual(self.send(confirm_once=confirmation)["error"], "confirmation_required")
        self.assert_zero_mqtt()
        self.assertFalse((self.directory / ("replay-" + COMMAND + ".json")).exists())

    def test_send_is_one_durable_commit_and_preserves_learning_files(self):
        self.profile()
        original = {path.name: path.read_bytes() for path in self.directory.iterdir()}
        result = self.send()
        self.assertEqual(result, {
            "ok": True, "command_id": COMMAND, "outcome": "node_acknowledged",
            "attempt_consumed": True, "appliance_response_verified": False,
        })
        self.assertEqual([request["action"] for _, request, _, _ in self.transport.publications],
                         ["ir_raw_prepare", "ir_raw_commit"])
        self.assertEqual(self.transport.simulated_effects, 1)
        self.factory.assert_called_once()
        for name, content in original.items():
            self.assertEqual((self.directory / name).read_bytes(), content)
        journal = self.directory / ("replay-" + COMMAND + ".json")
        self.assertEqual(stat.S_IMODE(journal.stat().st_mode), 0o600)
        self.assertEqual(json.loads(journal.read_bytes())["phase"], "commit_consumed")
        self.assertTrue(self.transport.closed)

    def test_catalog_id_can_be_used_once_and_repeat_has_no_second_mqtt(self):
        self.profile()
        command_id = self.control.catalog()["command_id"]
        self.assertTrue(self.control.send(PROFILE, RECORD, command_id, confirm_once=True)["ok"])
        result = self.control.send(PROFILE, RECORD, command_id, confirm_once=True)
        self.assertEqual(result["error"], "command_already_consumed")
        self.assertTrue(result["attempt_consumed"])
        self.factory.assert_called_once()
        self.assertEqual(self.transport.simulated_effects, 1)

    def test_lost_commit_ack_stays_unknown_and_never_retries(self):
        self.profile()
        self.transport.timeout_action = "ir_raw_commit"
        result = self.send()
        self.assertEqual(result, {
            "ok": False, "command_id": COMMAND, "outcome": "unknown_no_retry",
            "attempt_consumed": True, "appliance_response_verified": False,
        })
        self.assertEqual(self.transport.simulated_effects, 1)
        self.assertEqual(self.send()["error"], "command_already_consumed")
        self.assertEqual(len(self.transport.publications), 2)
        self.factory.assert_called_once()
        self.assertNotIn("FAKE_PRIVATE", json.dumps(result))

    def test_prepare_timeout_preserves_consumed_unknown_result(self):
        self.profile()
        self.transport.timeout_action = "ir_raw_prepare"
        result = self.send()
        self.assertEqual(result["outcome"], "unknown_no_retry")
        self.assertTrue(result["attempt_consumed"])
        self.assertFalse(result["appliance_response_verified"])
        self.assertEqual(self.transport.simulated_effects, 0)
        self.assertEqual(len(self.transport.publications), 1)
        self.assertEqual(self.send()["error"], "command_already_consumed")
        self.factory.assert_called_once()

    def test_learning_capture_arming_and_ready_block_before_replay(self):
        self.profile()
        for data in ({"capture": {"session_id": "e" * 32}, "status": "captured"},
                     {"capture": None, "status": "arming"},
                     {"capture": None, "status": "ready"}):
            with self.subTest(data=data):
                self.session.data = data
                self.assertEqual(self.send()["error"], "learning_capture_active")
        self.assert_zero_mqtt()
        self.assertFalse((self.directory / ("replay-" + COMMAND + ".json")).exists())

    def test_send_holds_session_lock_through_replay(self):
        self.profile()
        acquired = []

        def attempt_learning_lock():
            locked = self.session.lock.acquire(blocking=False)
            acquired.append(locked)
            if locked:
                self.session.lock.release()

        def before_commit():
            worker = threading.Thread(target=attempt_learning_lock)
            worker.start()
            worker.join(timeout=1)
            self.assertFalse(worker.is_alive())

        self.transport.before_commit = before_commit
        self.assertTrue(self.send()["ok"])
        self.assertEqual(acquired, [False])

    def test_actual_learning_records_keep_null_fields_and_block_active_capture(self):
        learning_transport = Mock()
        session = LearningSession(self.directory, learning_transport)
        instance = control.IRControl(session, self.config_path)
        session.start()
        profile_id = session.public()["profile_id"]
        empty = instance.catalog()
        self.assertEqual(empty["commands"], [])
        self.assertEqual(instance.send(profile_id, RECORD, COMMAND, confirm_once=True)["error"],
                         "learning_capture_active")
        capture = sample()
        capture["state"] = dict.fromkeys(STATE_FIELDS)
        capture["state"].update(power=True, temp_c=24)
        self.assertTrue(session.receive(session.data["capture"]["session_id"], capture))
        command = instance.catalog()["commands"][0]
        self.assertEqual(len(command["state"]), 14)
        self.assertIsNone(command["state"]["light"])
        self.assertIs(command["state"]["power"], True)
        self.assertTrue(command["replayable"])
        result = instance.send(profile_id, command["record_id"], COMMAND, confirm_once=True)
        self.assertEqual(result["outcome"], "node_acknowledged")
        self.assertEqual(session.public()["record_count"], 1)
        self.assertEqual(self.transport.simulated_effects, 1)

    def test_old_record_without_metadata_is_still_replayable(self):
        self.profile(records=[{"record_id": RECORD, "capture": sample()}])
        command = self.control.catalog()["commands"][0]
        self.assertIsInstance(command["button"], str)
        self.assertEqual(command["label"], "")
        self.assertEqual(command["recorded_at"], "")
        self.assertTrue(command["replayable"])
        self.assert_zero_mqtt()

    def test_result_projection_failure_stays_unknown_after_replay(self):
        self.profile()
        with patch.object(replay, "replay_once", return_value={}):
            result = self.send()
        self.assertEqual(result["outcome"], "unknown_no_retry")
        self.assertTrue(result["attempt_consumed"])
        self.assertEqual(result["command_id"], COMMAND)
        self.assertEqual(result["error"], "control_unavailable")
        self.assert_zero_mqtt()

    def test_unexpected_replay_exception_is_sanitized_and_not_retryable(self):
        self.profile()
        with patch.object(replay, "replay_once", side_effect=RuntimeError("FAKE_SECRET_PATH")):
            result = self.send()
        self.assertEqual(result["outcome"], "unknown_no_retry")
        self.assertTrue(result["attempt_consumed"])
        self.assertEqual(result["error"], "control_unavailable")
        self.assertNotIn("FAKE_SECRET", json.dumps(result))
        self.assert_zero_mqtt()


if __name__ == "__main__":
    unittest.main()
