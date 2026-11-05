"""Offline operator-replay checks; all files and fake credentials are private."""
import contextlib
import copy
import io
import json
from pathlib import Path
import stat
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from services.ir_learning import replay


PROFILE = "a" * 32
RECORD = "b" * 32
COMMAND = "c" * 32
CHALLENGE = "d" * 32
BOOT = "node02-1234abcd"
MODULUS = 2**32


def sample(length=280):
    return {
        "boot_id": BOOT, "protocol": "KELVINATOR", "bits": 128,
        "state": {"power": True, "temp_c": 24}, "rawlen": length,
        "overflow": False, "truncated": False,
        "timings_us": [2] + [500] * (length - 1),
    }


def private_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    path.chmod(0o600)


class FakeTransport:
    """A fake node; only commit increments the simulated effect counter."""

    def __init__(self):
        self.condition = threading.Condition()
        self.connected = self.subscribed = self.online = True
        self.responses = {}
        self.mqtt = SimpleNamespace(MQTT_ERR_SUCCESS=0)
        self.client = SimpleNamespace(publish=self.publish)
        self.readings = [(BOOT, 1000), (BOOT, 1500)]
        self.status_calls = 0
        self.publications = []
        self.prepared_overrides = {}
        self.prepared_boot = BOOT
        self.sent_boot = BOOT
        self.prepare_delay = self.first_status_delay = 0
        self.now = 0.0
        self.expires = 11000
        self.timeout_action = None
        self.publish_rc = 0
        self.simulated_effects = 0
        self.before_commit = lambda: None
        self.started = self.closed = False

    def start(self):
        self.started = True

    def close(self):
        self.closed = True

    def status(self):
        reading = self.readings[self.status_calls]
        self.status_calls += 1
        if self.status_calls == 1:
            self.now += self.first_status_delay
        return reading

    def _wait(self, predicate):
        if not predicate():
            raise ValueError("FAKE_PRIVATE_TRANSPORT_ERROR_DO_NOT_REFLECT")

    def publish(self, topic, payload, *, qos, retain):
        request = json.loads(payload)
        self.publications.append((topic, request, qos, retain))
        action = request["action"]
        if action == "ir_raw_prepare":
            if self.simulated_effects:
                raise AssertionError("prepare_must_not_emit_ir")
            self.now += self.prepare_delay
            kind, boot = "prepared", self.prepared_boot
            detail = {"challenge": CHALLENGE, "expires_ms": self.expires}
        elif action == "ir_raw_commit":
            self.before_commit()
            self.simulated_effects += 1
            kind, boot, detail = "sent", self.sent_boot, {}
        else:
            raise AssertionError("unexpected_action")
        detail.update(kind=kind, command_id=request["command_id"])
        if action == "ir_raw_prepare":
            detail.update(self.prepared_overrides)
        event = {"schema_version": "1.0", "node_id": "node02",
                 "simulated": False, "event_type": "ir_learning",
                 "boot_id": boot, "sequence": 40}
        if self.timeout_action != action and self.publish_rc == 0:
            self.responses[request["command_id"]] = (event, detail)
        return SimpleNamespace(rc=self.publish_rc)


class ReplayTests(unittest.TestCase):
    def setUp(self):
        private = tempfile.TemporaryDirectory(prefix="xiaoxi-ir-replay-tests-")
        self.addCleanup(private.cleanup)
        self.root = Path(private.name)
        self.state_dir = self.root / "state"
        self.state_dir.mkdir(mode=0o700)
        self.config_path = self.root / "config.json"
        self.config = {"state_dir": str(self.state_dir), "expected_rawlen": 280,
                       "mqtt_host": "offline.invalid",
                       "mqtt_username": "offline-test-only",
                       "mqtt_password": "FAKE_NOT_A_CREDENTIAL",
                       "ca_file": str(self.root / "unused-test-ca.pem")}
        private_json(self.config_path, self.config)
        self.profile_path = self.state_dir / (PROFILE + ".json")
        self.profile = {
            "schema_version": "1.0", "profile_id": PROFILE,
            "records": [{"record_id": RECORD, "button": "baseline",
                         "capture": sample()}],
        }
        private_json(self.profile_path, self.profile)
        self.journal = self.state_dir / ("replay-" + COMMAND + ".json")
        self.transport = FakeTransport()
        self.factory = Mock(return_value=self.transport)
        for target in ("socket.socket", "socket.create_connection"):
            guard = patch(target, side_effect=AssertionError("network_forbidden"))
            guard.start()
            self.addCleanup(guard.stop)
        guard = patch("services.ir_learning.model.LearningSession",
                      side_effect=AssertionError("session_mutation_forbidden"))
        guard.start()
        self.addCleanup(guard.stop)

    def run_replay(self, **kwargs):
        return replay.replay_once(
            self.config_path, PROFILE, RECORD, COMMAND,
            confirm_once=kwargs.pop("confirm_once", True),
            transport_factory=self.factory, clock=lambda: self.transport.now,
            **kwargs,
        )

    def commands(self, action):
        return [request for _, request, _, _ in self.transport.publications
                if request["action"] == action]

    def assert_no_network(self):
        self.factory.assert_not_called()
        self.assertEqual(self.transport.status_calls, 0)
        self.assertEqual(self.transport.publications, [])

    def test_missing_consent_makes_zero_mqtt_calls_and_no_journal(self):
        with self.assertRaisesRegex(replay.ReplayError, "confirmation_required"):
            self.run_replay(confirm_once=False)
        self.assert_no_network()
        self.assertFalse(self.journal.exists())

    def test_cli_without_flag_does_not_construct_transport(self):
        output = io.StringIO()
        with patch.object(replay, "LearningTransport", self.factory):
            with contextlib.redirect_stdout(output):
                code = replay.main([
                    "--config", str(self.config_path), "--profile", PROFILE,
                    "--record", RECORD, "--command-id", COMMAND,
                ])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())["error"],
                         "confirmation_required")
        self.assert_no_network()

    def test_invalid_ids_are_rejected_before_any_network(self):
        for profile, record, command in (("../escape", RECORD, COMMAND),
                                         (PROFILE, "B" * 32, COMMAND),
                                         (PROFILE, RECORD, "c" * 31)):
            with self.subTest(ids=(profile, record, command)):
                with self.assertRaisesRegex(replay.ReplayError, "invalid_identifier"):
                    replay.replay_once(self.config_path, profile, record, command,
                                       confirm_once=True,
                                       transport_factory=self.factory)
        self.assert_no_network()

    def test_unestablished_carrier_never_prepares_or_commits(self):
        for protocol, state in (("UNKNOWN", None), ("SAMSUNG", {"power": True})):
            with self.subTest(protocol=protocol):
                value = sample()
                value.update(protocol=protocol, state=state)
                self.profile["records"][0]["capture"] = value
                private_json(self.profile_path, self.profile)
                with self.assertRaisesRegex(replay.ReplayError, "invalid_replay_capture"):
                    self.run_replay()
                self.assert_no_network()
                self.assertFalse(self.journal.exists())

    def test_invalid_waveforms_never_prepare_or_commit(self):
        cases = []
        for field in ("overflow", "truncated"):
            value = sample()
            value[field] = True
            cases.append((field, value))
        for length in (140, 279, 300, 302):
            cases.append((f"length_{length}", sample(length)))
        for name, index, duration in (("sentinel", 0, 4), ("odd_tick", 1, 501),
                                      ("zero", 1, 0), ("uint16", 1, 65536),
                                      ("tick_overflow", 1, 131070),
                                      ("boolean", 1, True)):
            value = sample()
            value["timings_us"][index] = duration
            cases.append((name, value))
        value = sample()
        value["timings_us"][1:] = [4000] * 279
        cases.append(("over_one_second", value))
        for name, value in cases:
            with self.subTest(case=name):
                self.profile["records"][0]["capture"] = value
                private_json(self.profile_path, self.profile)
                with self.assertRaisesRegex(replay.ReplayError,
                                            "invalid_replay_capture"):
                    self.run_replay()
        self.assert_no_network()
        self.assertFalse(self.journal.exists())

    def test_private_config_profile_and_state_modes_are_enforced(self):
        for path, mode in ((self.config_path, 0o644),
                           (self.profile_path, 0o644),
                           (self.state_dir, 0o755)):
            with self.subTest(path=path.name):
                path.chmod(mode)
                with self.assertRaises(replay.ReplayError):
                    self.run_replay()
                path.chmod(0o700 if path == self.state_dir else 0o600)
        self.assert_no_network()

    def test_symlink_config_and_duplicate_record_fail_before_network(self):
        link = self.root / "linked-config.json"
        link.symlink_to(self.config_path)
        with self.assertRaises(replay.ReplayError):
            replay.replay_once(link, PROFILE, RECORD, COMMAND, confirm_once=True,
                               transport_factory=self.factory)
        self.profile["records"].append(copy.deepcopy(self.profile["records"][0]))
        private_json(self.profile_path, self.profile)
        with self.assertRaisesRegex(replay.ReplayError, "record_not_unique"):
            self.run_replay()
        self.assert_no_network()

    def test_commit_once_has_private_durable_intent_and_preserves_profile(self):
        original = self.profile_path.read_bytes()
        observed = []

        def before_commit():
            intent = json.loads(self.journal.read_bytes())
            observed.append(intent)
            self.assertEqual(intent["phase"], "commit_consumed")
            self.assertEqual(intent["attempt"], 1)
            self.assertEqual(intent["profile_id"], PROFILE)
            self.assertEqual(intent["record_id"], RECORD)
            self.assertEqual(intent["boot_id"], BOOT)
            self.assertEqual(stat.S_IMODE(self.journal.stat().st_mode), 0o600)
            self.assertNotIn(CHALLENGE, self.journal.read_text())
            self.assertEqual(self.transport.simulated_effects, 0)

        def create_transport(config):
            reserved = json.loads(self.journal.read_bytes())
            self.assertEqual(reserved["phase"], "reserved_no_commit")
            self.assertEqual(reserved["attempt"], 0)
            self.assertEqual(reserved["command_id"], COMMAND)
            return self.transport

        self.factory.side_effect = create_transport
        self.transport.before_commit = before_commit
        result = self.run_replay()
        self.assertTrue(result["ok"])
        self.assertFalse(result["appliance_response_verified"])
        self.assertEqual(result["outcome"], "node_acknowledged")
        self.assertEqual(len(observed), 1)
        self.assertEqual(self.profile_path.read_bytes(), original)
        self.assertFalse((self.state_dir / "active.json").exists())
        self.assertEqual(len(self.commands("ir_raw_prepare")), 1)
        commit = self.commands("ir_raw_commit")
        self.assertEqual(len(commit), 1)
        self.assertEqual(commit[0]["command_id"], COMMAND)
        self.assertEqual(commit[0]["challenge"], CHALLENGE)
        prepare = self.commands("ir_raw_prepare")[0]
        self.assertNotEqual(prepare["command_id"], COMMAND)
        self.assertEqual(prepare["timings_us"], [500] * 279)
        self.assertEqual(prepare["frequency_khz"], 38)
        self.assertNotIn("raw_us", prepare)
        for topic, request, qos, retain in self.transport.publications:
            self.assertEqual(topic, "xiaoxi/dorm/node02/command")
            self.assertEqual(request["node_id"], "node02")
            self.assertEqual(qos, 0)
            self.assertIs(retain, False)
        self.assertEqual(self.transport.responses, {})
        self.assertTrue(self.transport.closed)

    def test_repeat_command_id_fails_before_second_transport_or_publish(self):
        self.run_replay()
        publications = copy.deepcopy(self.transport.publications)
        with self.assertRaisesRegex(replay.ReplayError, "command_already_consumed"):
            self.run_replay()
        self.factory.assert_called_once()
        self.assertEqual(self.transport.publications, publications)
        self.assertEqual(self.transport.simulated_effects, 1)

    def test_timeout_after_commit_never_retries_or_reflects_exception(self):
        self.transport.timeout_action = "ir_raw_commit"
        result = self.run_replay()
        self.assertEqual(result["outcome"], "unknown_no_retry")
        self.assertFalse(result["ok"])
        self.assertTrue(result["attempt_consumed"])
        self.assertFalse(result["appliance_response_verified"])
        self.assertNotIn("FAKE_PRIVATE_TRANSPORT_ERROR", json.dumps(result))
        self.assertEqual(len(self.commands("ir_raw_commit")), 1)
        self.assertEqual(self.transport.simulated_effects, 1)
        with self.assertRaisesRegex(replay.ReplayError, "command_already_consumed"):
            self.run_replay()
        self.assertEqual(len(self.commands("ir_raw_commit")), 1)

    def test_prepare_emits_no_effect_and_invalid_challenge_prevents_commit(self):
        self.transport.prepared_overrides["challenge"] = "D" * 32
        with self.assertRaisesRegex(replay.ReplayError, "invalid_prepared_challenge"):
            self.run_replay()
        self.assertEqual(len(self.commands("ir_raw_prepare")), 1)
        self.assertEqual(self.commands("ir_raw_commit"), [])
        self.assertEqual(self.transport.simulated_effects, 0)
        self.assertEqual(json.loads(self.journal.read_bytes())["attempt"], 0)

    def test_changed_boot_after_prepare_never_commits(self):
        self.transport.readings[1] = ("node02-87654321", 1500)
        with self.assertRaisesRegex(replay.ReplayError, "node_boot_changed"):
            self.run_replay()
        self.assertEqual(self.commands("ir_raw_commit"), [])

    def test_wrong_reply_boot_or_command_prevents_commit(self):
        for index, kind in enumerate(("boot", "command")):
            with self.subTest(kind=kind):
                self.transport = FakeTransport()
                if kind == "boot":
                    self.transport.prepared_boot = "node02-87654321"
                else:
                    self.transport.prepared_overrides["command_id"] = "0" * 32
                with self.assertRaisesRegex(replay.ReplayError,
                                            "invalid_node_reply"):
                    replay.replay_once(
                        self.config_path, PROFILE, RECORD, f"{index:032x}",
                        confirm_once=True, transport_factory=lambda _: self.transport,
                        clock=lambda: self.transport.now,
                    )
                self.assertEqual(self.commands("ir_raw_commit"), [])

    def test_prepare_timeout_is_consumed_without_any_commit(self):
        self.transport.timeout_action = "ir_raw_prepare"
        with self.assertRaisesRegex(replay.ReplayError,
                                    "replay_unavailable_no_retry"):
            self.run_replay()
        self.assertEqual(len(self.commands("ir_raw_prepare")), 1)
        self.assertEqual(self.commands("ir_raw_commit"), [])
        self.assertEqual(self.transport.simulated_effects, 0)
        with self.assertRaisesRegex(replay.ReplayError, "command_already_consumed"):
            self.run_replay()
        self.factory.assert_called_once()

    def test_wrong_boot_in_commit_ack_remains_ambiguous(self):
        self.transport.sent_boot = "node02-87654321"
        result = self.run_replay()
        self.assertEqual(result["outcome"], "unknown_no_retry")
        self.assertFalse(result["appliance_response_verified"])
        self.assertEqual(len(self.commands("ir_raw_commit")), 1)

    def test_expired_or_implausible_challenge_deadline_prevents_commit(self):
        for index, expires in enumerate((1500, 1499, 20000, True)):
            with self.subTest(expires=expires):
                self.transport = FakeTransport()
                self.transport.expires = expires
                factory = Mock(return_value=self.transport)
                with self.assertRaises(replay.ReplayError):
                    replay.replay_once(
                        self.config_path, PROFILE, RECORD, f"{index:032x}",
                        confirm_once=True, transport_factory=factory,
                        clock=lambda: self.transport.now,
                    )
                self.assertEqual(self.commands("ir_raw_commit"), [])

    def test_stale_local_status_or_prepare_cannot_commit(self):
        self.transport.first_status_delay = 9
        with self.assertRaisesRegex(replay.ReplayError, "local_deadline_expired"):
            self.run_replay()
        self.assertEqual(self.transport.publications, [])
        self.transport = FakeTransport()
        self.transport.prepare_delay = 11
        with self.assertRaisesRegex(replay.ReplayError, "local_deadline_expired"):
            replay.replay_once(
                self.config_path, PROFILE, RECORD, "e" * 32, confirm_once=True,
                transport_factory=lambda config: self.transport,
                clock=lambda: self.transport.now,
            )
        self.assertEqual(self.commands("ir_raw_commit"), [])

    def test_invalid_status_time_or_backwards_uptime_never_commits(self):
        self.transport.readings[0] = (BOOT, True)
        with self.assertRaisesRegex(replay.ReplayError, "invalid_node_time"):
            self.run_replay()
        self.assertEqual(self.transport.publications, [])
        self.transport = FakeTransport()
        self.transport.readings[1] = (BOOT, 999)
        with self.assertRaisesRegex(replay.ReplayError, "invalid_node_time"):
            replay.replay_once(
                self.config_path, PROFILE, RECORD, "e" * 32, confirm_once=True,
                transport_factory=lambda config: self.transport,
                clock=lambda: self.transport.now,
            )
        self.assertEqual(self.commands("ir_raw_commit"), [])

    def test_wrapped_uptime_produces_valid_short_deadlines(self):
        self.transport.readings = [(BOOT, MODULUS - 1000), (BOOT, MODULUS - 500)]
        self.transport.expires = 9000
        self.run_replay()
        self.assertEqual(self.commands("ir_raw_prepare")[0]["deadline_ms"], 7000)
        self.assertEqual(self.commands("ir_raw_commit")[0]["deadline_ms"], 7500)

    def test_journal_failure_prevents_commit(self):
        persist = replay._persist
        count = 0

        def fail_second_write(*args):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("FAKE_PRIVATE_DISK_ERROR")
            return persist(*args)

        with patch.object(replay, "_persist", side_effect=fail_second_write):
            with self.assertRaisesRegex(replay.ReplayError,
                                        "replay_unavailable_no_retry"):
                self.run_replay()
        self.assertEqual(len(self.commands("ir_raw_prepare")), 1)
        self.assertEqual(self.commands("ir_raw_commit"), [])
        self.assertEqual(self.transport.simulated_effects, 0)

    def test_total_exactly_one_second_and_max_300_entry_capture_are_allowed(self):
        self.profile["records"][0]["capture"]["timings_us"] = (
            [2] + [3584] * 278 + [3648]
        )
        private_json(self.profile_path, self.profile)
        self.run_replay()
        self.assertEqual(sum(self.commands("ir_raw_prepare")[0]["timings_us"]),
                         1000000)
        self.config["expected_rawlen"] = 300
        private_json(self.config_path, self.config)
        self.profile["records"][0]["capture"] = sample(300)
        private_json(self.profile_path, self.profile)
        fresh = FakeTransport()
        replay.replay_once(self.config_path, PROFILE, RECORD, "e" * 32,
                           confirm_once=True, transport_factory=lambda _: fresh,
                           clock=lambda: fresh.now)
        self.assertEqual(len(fresh.publications[0][1]["timings_us"]), 299)


if __name__ == "__main__":
    unittest.main()
