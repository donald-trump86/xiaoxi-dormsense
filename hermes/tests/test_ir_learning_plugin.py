"""Offline contract tests for the native IR-learning plugin; sockets stay blocked."""

import importlib.util
import json
from pathlib import Path
import socket
import sys
from types import ModuleType
import unittest
from unittest import mock


PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugins" / "xiaoxi_ir_learning"
SPEC = importlib.util.spec_from_file_location(
    "xiaoxi_ir_learning_offline", PLUGIN_DIR / "__init__.py"
)
PLUGIN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PLUGIN)


class FakeContext:
    def __init__(self):
        self.tools = {}

    def register_tool(self, **entry):
        self.tools[entry["name"]] = entry


class IRLearningPluginTests(unittest.TestCase):
    def setUp(self):
        self.token = "offline-dedicated-learning-token"
        secret_api = ModuleType("agent.secret_scope")
        secret_api.get_secret = mock.Mock(return_value=self.token)
        self.get_secret = secret_api.get_secret
        self.enterContext(mock.patch.dict(sys.modules, {
            "agent": ModuleType("agent"), "agent.secret_scope": secret_api,
        }))
        self.enterContext(mock.patch.object(
            socket, "create_connection", side_effect=AssertionError("offline sockets blocked")
        ))
        self.connection = mock.MagicMock()
        self.response = self.connection.getresponse.return_value
        self.response.status = 200
        self.headers = {"Content-Type": "application/json"}
        self.response.getheader.side_effect = lambda name, default=None: self.headers.get(
            name, default
        )
        self.response.read.return_value = b'{"ok":true,"status":"idle"}'
        self.connect = self.enterContext(mock.patch.object(
            PLUGIN.http.client, "HTTPConnection", return_value=self.connection
        ))
        self.context = FakeContext()
        PLUGIN.register(self.context)

    def invoke(self, tool, arguments=None, **kwargs):
        entry = self.context.tools[tool]
        return json.loads(entry["handler"]({} if arguments is None else arguments, **kwargs))

    def sent(self, path="/api/learning"):
        args, kwargs = self.connection.request.call_args
        self.assertEqual(args[:2], ("POST", path))
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer " + self.token)
        self.assertEqual(kwargs["headers"]["Accept-Encoding"], "identity")
        return json.loads(kwargs["body"])

    def send_arguments(self):
        return {"profile_id": "a" * 32, "record_id": "b" * 32,
                "command_id": "c" * 32, "confirm_once": True}

    def command(self, **overrides):
        result = {
            "profile_id": "a" * 32, "record_id": "b" * 32, "button": "power",
            "label": "synthetic on sample", "recorded_at": "2026-01-01T00:00:00+00:00",
            "state": {"power": True, "mode": 1, "temp_c": 24, "fan": 1},
            "protocol": "KELVINATOR", "bits": 128, "coverage": "full_protocol",
            "semantics_verified": True, "replayable": True,
        }
        result.update(overrides)
        return result

    def catalog(self, **overrides):
        result = {
            "ok": True, "profile_id": "a" * 32, "active_profile_id": "a" * 32,
            "profiles": [{"profile_id": "a" * 32, "record_count": 1, "active": True}],
            "commands": [self.command()], "command_id": "c" * 32,
        }
        result.update(overrides)
        return result

    def reply(self, data):
        self.response.read.return_value = json.dumps(data, allow_nan=False).encode()

    def assert_unknown_send(self, result):
        self.assertIs(result["ok"], False)
        self.assertEqual(result["command_id"], "c" * 32)
        self.assertEqual(result["outcome"], "unknown_no_retry")
        self.assertIs(result["attempt_consumed"], True)
        self.assertIs(result["appliance_response_verified"], False)

    def test_registers_five_native_tools_without_reading_secrets(self):
        self.assertEqual(set(self.context.tools), {
            "xiaoxi_ac_initialize", "xiaoxi_ac_learn_key", "xiaoxi_ac_learning_status",
            "xiaoxi_ac_list_commands", "xiaoxi_ac_send",
        })
        self.get_secret.assert_not_called()
        for name, entry in self.context.tools.items():
            self.assertEqual(entry["toolset"], "xiaoxi_ir_learning")
            self.assertEqual(entry["schema"]["name"], name)
            self.assertIs(entry["schema"]["parameters"]["additionalProperties"], False)
            self.assertFalse(entry.get("override", False))
        manifest = json.loads((PLUGIN_DIR / "plugin.yaml").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "xiaoxi_ir_learning")
        self.assertEqual(manifest["kind"], "standalone")
        self.assertEqual(set(manifest["provides_tools"]), set(self.context.tools))

    def test_initialization_defaults_to_start_and_has_fixed_transport(self):
        self.assertTrue(self.invoke("xiaoxi_ac_initialize")["ok"])
        self.assertEqual(self.sent(), {"action": "start"})
        self.connect.assert_called_once_with("ir-learning", 8090, timeout=5.0)
        self.connection.close.assert_called_once()
        self.get_secret.assert_called_once_with("XIAOXI_IR_LEARNING_TOKEN")
        self.response.read.assert_called_once_with(128 * 1024 + 1)

    def test_all_six_service_actions_are_mapped_without_replay(self):
        cases = [
            ("xiaoxi_ac_initialize", {"action": "status"}, {"action": "status"}),
            ("xiaoxi_ac_initialize", {"action": "cancel"}, {"action": "cancel"}),
            ("xiaoxi_ac_learning_status", {}, {"action": "status"}),
            ("xiaoxi_ac_learn_key", {"button": "电源"}, {"action": "next", "button": "电源"}),
            ("xiaoxi_ac_learn_key", {"button": "电源", "action": "confirm", "label": "manual power", "confirm": True},
             {"action": "confirm", "button": "电源", "label": "manual power", "confirm": True}),
            ("xiaoxi_ac_learn_key", {"button": "定时", "action": "skip", "reason": "no such key"},
             {"action": "skip", "button": "定时", "reason": "no such key"}),
        ]
        for tool, arguments, expected in cases:
            with self.subTest(tool=tool, arguments=arguments):
                self.assertTrue(self.invoke(tool, arguments, task_id="not-forwarded")["ok"])
                self.assertEqual(self.sent(), expected)
        self.assertEqual(self.get_secret.call_count, len(cases))

    def test_invalid_or_extra_arguments_never_open_connection(self):
        cases = [
            ("xiaoxi_ac_initialize", {"action": "replay"}),
            ("xiaoxi_ac_initialize", {"url": "http://other"}),
            ("xiaoxi_ac_learning_status", {"topic": "private"}),
            ("xiaoxi_ac_learn_key", {}),
            ("xiaoxi_ac_learn_key", {"button": ""}),
            ("xiaoxi_ac_learn_key", {"button": "x" * 129}),
            ("xiaoxi_ac_learn_key", {"button": "Power\n"}),
            ("xiaoxi_ac_learn_key", {"button": "Power", "device": "arbitrary"}),
            ("xiaoxi_ac_learn_key", {"button": "Power", "action": "confirm"}),
            ("xiaoxi_ac_learn_key", {"button": "other", "action": "confirm", "confirm": True}),
            ("xiaoxi_ac_learn_key", {"button": "other", "action": "confirm", "confirm": True, "label": " "}),
            ("xiaoxi_ac_learn_key", {"button": "Power", "action": "confirm", "confirm": 1}),
            ("xiaoxi_ac_learn_key", {"button": "Power", "confirm": True}),
            ("xiaoxi_ac_learn_key", {"button": "Power", "action": "skip", "label": "unused"}),
        ]
        for tool, arguments in cases:
            with self.subTest(tool=tool, arguments=arguments):
                result = self.invoke(tool, arguments)
                self.assertFalse(result["ok"])
                self.assertEqual(result["error"], "invalid_arguments")
        self.connect.assert_not_called()
        self.get_secret.assert_not_called()

    def test_missing_or_unscoped_secret_fails_closed(self):
        for value in (None, "", "token\r\nInjected: yes"):
            with self.subTest(value=value):
                self.get_secret.return_value = value
                self.assertEqual(self.invoke("xiaoxi_ac_learning_status"), {
                    "ok": False, "error": "learning_credentials_unavailable",
                })
        self.get_secret.side_effect = RuntimeError("private scope details")
        self.assertEqual(self.invoke("xiaoxi_ac_learning_status"), {
            "ok": False, "error": "learning_credentials_unavailable",
        })
        self.connect.assert_not_called()

    def test_secret_is_resolved_for_each_call_in_current_profile(self):
        self.invoke("xiaoxi_ac_learning_status")
        self.get_secret.return_value = "second-profile-learning-token"
        self.invoke("xiaoxi_ac_learning_status")
        self.assertEqual(self.connection.request.call_args.kwargs["headers"]["Authorization"],
                         "Bearer second-profile-learning-token")
        self.assertEqual(self.get_secret.call_count, 2)

    def test_response_is_projected_at_every_level_preserving_null_and_false(self):
        self.response.read.return_value = json.dumps({
            "ok": True, "status": "needs_confirmation", "profile_id": "a" * 32,
            "button": "电源", "prompt": "请确认按键前后状态", "message": "UNKNOWN",
            "record_count": 1, "recommended_buttons": ["电源", "温度+"],
            "observed": {"power": False, "mode": None, "protocol": "UNKNOWN", "bits": 0,
                         "rawlen": 123, "coverage": "raw_only", "raw": [100, 200],
                         "state_hex": "AABB", "mqtt": "private", "nested": {"raw": [10]}},
            "changes": {"power": {"before": None, "after": False, "raw": [1, 2]},
                        "raw": {"before": 1, "after": 2}},
            "validation": {"basis": "manual", "warnings": ["unrecognized", {"secret": "drop"}],
                           "private": "drop"},
            "raw_timings": [100, 200], "state": "AABB", "backend": "private",
        }, ensure_ascii=False).encode()
        result = self.invoke("xiaoxi_ac_learning_status")
        self.assertEqual(result["observed"], {
            "power": False, "mode": None, "protocol": "UNKNOWN", "bits": 0,
            "rawlen": 123, "coverage": "raw_only",
        })
        self.assertEqual(result["changes"], {"power": {"before": None, "after": False}})
        self.assertEqual(result["validation"], {"basis": "manual", "warnings": ["unrecognized"]})
        self.assertNotIn("raw_timings", result)
        self.assertNotIn("backend", result)
        self.assertEqual(result["record_count"], 1)

    def test_wrong_summary_types_are_dropped_without_inventing_values(self):
        self.response.read.return_value = json.dumps({
            "ok": True, "status": [], "record_count": False,
            "observed": {"power": {"raw": [1, 2]}, "temp_c": 0},
            "changes": {"power": {"before": [], "after": False}},
            "recommended_buttons": ["Power", {"private": "drop"}],
        }).encode()
        self.assertEqual(self.invoke("xiaoxi_ac_learning_status"), {
            "ok": True, "observed": {"temp_c": 0},
            "changes": {"power": {"after": False}}, "recommended_buttons": ["Power"],
        })

    def test_non_json_and_encoded_bodies_are_rejected_before_reading(self):
        for headers in ({"Content-Type": "text/html"}, {
            "Content-Type": "application/json", "Content-Encoding": "gzip",
        }):
            with self.subTest(headers=headers):
                self.headers.clear()
                self.headers.update(headers)
                self.assertEqual(self.invoke("xiaoxi_ac_learning_status"), {
                    "ok": False, "error": "learning_invalid_response",
                })
        self.response.read.assert_not_called()

    def test_token_is_redacted_from_allowed_text_fields(self):
        self.response.read.return_value = json.dumps({
            "ok": True, "status": "captured", "message": "unexpected " + self.token,
            "validation": {"basis": self.token, "warnings": [self.token]},
        }).encode()
        result = json.dumps(self.invoke("xiaoxi_ac_learning_status"))
        self.assertNotIn(self.token, result)
        self.assertIn("[redacted]", result)

    def test_redirect_and_error_status_are_not_followed_or_reflected(self):
        for status in (302, 401, 500):
            with self.subTest(status=status):
                self.response.status = status
                self.response.read.return_value = (self.token + " private backend error").encode()
                self.connection.request.reset_mock()
                result = self.invoke("xiaoxi_ac_learning_status")
                self.assertEqual(result, {"ok": False, "error": "learning_http_error"})
                self.connection.request.assert_called_once()
        self.response.read.assert_not_called()

    def test_response_body_and_declared_length_are_bounded(self):
        self.response.read.return_value = b"x" * (128 * 1024 + 1)
        self.assertEqual(self.invoke("xiaoxi_ac_learning_status")["error"], "learning_response_too_large")
        self.response.read.reset_mock()
        self.headers["Content-Length"] = str(128 * 1024 + 1)
        self.assertEqual(self.invoke("xiaoxi_ac_learning_status")["error"], "learning_response_too_large")
        self.response.read.assert_not_called()

    def test_invalid_payload_and_backend_exception_are_sanitized(self):
        for raw in (b"[]", b"{}", b"null", b"not-json", b"{\"ok\":true,\"record_count\":NaN}"):
            with self.subTest(raw=raw):
                self.response.read.return_value = raw
                self.assertEqual(self.invoke("xiaoxi_ac_learning_status")["error"], "learning_invalid_response")
        self.connection.request.side_effect = OSError(self.token + " private network details")
        self.assertEqual(self.invoke("xiaoxi_ac_learning_status"), {
            "ok": False, "error": "learning_unavailable",
        })
        self.assertTrue(self.connection.close.called)

    def test_service_errors_expose_only_sanitized_code(self):
        self.response.read.return_value = json.dumps({
            "ok": False, "error": "capture_expired", "message": self.token + " backend stack",
        }).encode()
        self.assertEqual(self.invoke("xiaoxi_ac_learning_status"), {
            "ok": False, "error": "capture_expired",
        })
        self.response.read.return_value = json.dumps({"ok": False, "error": "private: " + self.token}).encode()
        self.assertEqual(self.invoke("xiaoxi_ac_learning_status"), {
            "ok": False, "error": "learning_service_error",
        })

    def test_control_schemas_require_exact_ids_and_explicit_boolean(self):
        listing = self.context.tools["xiaoxi_ac_list_commands"]["schema"]["parameters"]
        sending = self.context.tools["xiaoxi_ac_send"]["schema"]["parameters"]
        self.assertEqual(set(listing["properties"]), {"profile_id"})
        self.assertEqual(listing["required"], [])
        self.assertEqual(set(sending["properties"]), set(self.send_arguments()))
        self.assertEqual(set(sending["required"]), set(self.send_arguments()))
        for name in ("profile_id", "record_id", "command_id"):
            self.assertEqual(sending["properties"][name]["pattern"], "^[0-9a-f]{32}$")
        self.assertEqual(sending["properties"]["confirm_once"]["type"], "boolean")
        self.assertEqual(sending["properties"]["confirm_once"]["enum"], [True])
        for name in ("xiaoxi_ac_initialize", "xiaoxi_ac_learn_key", "xiaoxi_ac_learning_status"):
            self.assertIn("without replaying IR", self.context.tools[name]["description"])
        guidance = self.context.tools["xiaoxi_ac_send"]["description"]
        for text in ("full state", "untrusted", "UNKNOWN", "replayable=false",
                     "explicit user instruction", "do not retry", "new user intent"):
            self.assertIn(text, guidance)

    def test_control_actions_have_fixed_route_and_twenty_second_timeout(self):
        cases = [
            ("xiaoxi_ac_list_commands", {}, {"action": "list"}, self.catalog()),
            ("xiaoxi_ac_list_commands", {"profile_id": "d" * 32},
             {"action": "list", "profile_id": "d" * 32}, self.catalog()),
            ("xiaoxi_ac_send", self.send_arguments(), {"action": "send", **self.send_arguments()},
             {"ok": True, "command_id": "c" * 32, "outcome": "node_acknowledged",
              "attempt_consumed": True, "appliance_response_verified": False}),
        ]
        for tool, arguments, payload, response in cases:
            with self.subTest(tool=tool, arguments=arguments):
                self.reply(response)
                self.connect.reset_mock()
                self.connection.reset_mock()
                self.response.read.reset_mock()
                self.assertTrue(self.invoke(tool, arguments, task_id="not-forwarded")["ok"])
                self.assertEqual(self.sent("/api/control"), payload)
                self.connect.assert_called_once_with("ir-learning", 8090, timeout=20.0)
                self.connection.request.assert_called_once()
                self.connection.close.assert_called_once()
                self.response.read.assert_called_once_with(128 * 1024 + 1)
        self.assertEqual(self.get_secret.call_count, 3)

    def test_control_invalid_arguments_never_access_credentials_or_network(self):
        cases = [("xiaoxi_ac_list_commands", []), ("xiaoxi_ac_list_commands", {"profile_id": None})]
        for value in ("", "a" * 31, "a" * 33, "A" * 32, "g" * 32, 123, True):
            cases.append(("xiaoxi_ac_list_commands", {"profile_id": value}))
            for key in ("profile_id", "record_id", "command_id"):
                cases.append(("xiaoxi_ac_send", {**self.send_arguments(), key: value}))
        for value in (False, 1, 0, "true", None, [], {}):
            cases.append(("xiaoxi_ac_send", {**self.send_arguments(), "confirm_once": value}))
        for key in self.send_arguments():
            cases.append(("xiaoxi_ac_send", {name: value for name, value in self.send_arguments().items()
                                              if name != key}))
        for key in ("url", "path", "topic", "timings_us", "protocol", "action", "label", "token"):
            cases.append(("xiaoxi_ac_list_commands", {key: "blocked"}))
            cases.append(("xiaoxi_ac_send", {**self.send_arguments(), key: "blocked"}))
        cases.extend((("xiaoxi_ac_send", {}), ("xiaoxi_ac_send", [])))
        for tool, arguments in cases:
            with self.subTest(tool=tool, arguments=arguments):
                self.assertEqual(self.invoke(tool, arguments), {"ok": False, "error": "invalid_arguments"})
        self.connect.assert_not_called()
        self.get_secret.assert_not_called()

    def test_control_uses_only_current_profile_secret_on_each_request(self):
        with mock.patch.dict("os.environ", {"XIAOXI_IR_LEARNING_TOKEN": "unscoped-token"}):
            self.get_secret.return_value = None
            for tool, arguments in (("xiaoxi_ac_list_commands", {}),
                                    ("xiaoxi_ac_send", self.send_arguments())):
                self.assertEqual(self.invoke(tool, arguments), {
                    "ok": False, "error": "control_credentials_unavailable",
                })
            self.connect.assert_not_called()
        self.get_secret.return_value = self.token
        self.reply(self.catalog())
        self.invoke("xiaoxi_ac_list_commands")
        self.get_secret.return_value = "second-profile-control-token"
        self.invoke("xiaoxi_ac_list_commands")
        self.assertEqual(self.connection.request.call_args.kwargs["headers"]["Authorization"],
                         "Bearer second-profile-control-token")
        self.assertEqual(self.get_secret.call_count, 4)
        self.get_secret.assert_called_with("XIAOXI_IR_LEARNING_TOKEN")

    def test_catalog_projects_every_level_and_redacts_allowed_text(self):
        state = dict.fromkeys(PLUGIN._STATE_FIELDS)
        state.update(power=False, mode=1, temp_c=24.5, fan=2, swingv=0, swingh=0,
                     light=True, turbo=False, econo=False, clean=False, sleep=-1,
                     ifeel=None, quiet=False, filter=False)
        unsafe_state = {**state, "capture": {"timings_us": [100, 200]}, "state_hex": self.token}
        command = self.command(state=unsafe_state, label="untrusted " + self.token,
                               capture={"timings_us": [100, 200]}, secret=self.token,
                               raw=[100, 200], statehex="ABCD")
        unknown = self.command(record_id="d" * 32, protocol="UNKNOWN", bits=0, state=None,
                               semantics_verified=False, replayable=False,
                               unavailable_reason="invalid_replay_capture")
        profiles = [{"profile_id": "a" * 32, "record_count": 2, "active": True,
                     "secret": self.token, "records": [command]}]
        self.reply(self.catalog(profiles=profiles, commands=[command, unknown],
                                capture=command, timings_us=[100, 200], secret=self.token))
        result = self.invoke("xiaoxi_ac_list_commands")
        self.assertEqual(set(result), {"ok", "profile_id", "active_profile_id", "profiles",
                                      "commands", "command_id"})
        self.assertEqual(result["profiles"], [{"profile_id": "a" * 32, "record_count": 2, "active": True}])
        self.assertEqual(result["commands"][0], self.command(state=state, label="untrusted [redacted]"))
        self.assertEqual(result["commands"][1], unknown)
        self.assertIsNone(result["commands"][1]["state"])
        self.assertNotIn(self.token, json.dumps(result))

    def test_catalog_bounds_arrays_and_each_free_text_field(self):
        command = self.command(button="x" * 150, label="x" * 150, recorded_at="x" * 100)
        self.reply(self.catalog(profiles=self.catalog()["profiles"] * 40,
                                commands=[command] * 130, profiles_truncated=True))
        result = self.invoke("xiaoxi_ac_list_commands")
        self.assertEqual(len(result["profiles"]), 32)
        self.assertEqual(len(result["commands"]), 128)
        self.assertIs(result["profiles_truncated"], True)
        self.assertEqual(len(result["commands"][0]["button"]), 128)
        self.assertEqual(len(result["commands"][0]["label"]), 128)
        self.assertEqual(len(result["commands"][0]["recorded_at"]), 64)

    def test_catalog_drops_wrong_types_and_disables_unsafe_states(self):
        profiles = [None, {"profile_id": "A" * 32, "record_count": 1, "active": True},
                    {"profile_id": "a" * 32, "record_count": False, "active": True},
                    {"profile_id": "a" * 32, "record_count": 1, "active": 1}]
        for field, value in (("power", 1), ("light", "false"), ("mode", True),
                             ("temp_c", 1441), ("fan", []), ("sleep", -101)):
            with self.subTest(field=field, value=value):
                self.reply(self.catalog(profiles=profiles, profiles_truncated=1,
                                        commands=[None, self.command(record_id="A" * 32),
                                                  self.command(state={field: value, "quiet": None})]))
                result = self.invoke("xiaoxi_ac_list_commands")
                self.assertEqual(result["profiles"], [])
                self.assertNotIn("profiles_truncated", result)
                self.assertEqual(len(result["commands"]), 1)
                self.assertEqual(result["commands"][0]["state"], {"quiet": None})
                self.assertIs(result["commands"][0]["replayable"], False)
        for overrides in ({"protocol": "UNKNOWN", "state": None}, {"state": []},
                          {"bits": True}, {"semantics_verified": 1}, {"coverage": {}},
                          {"replayable": 1}, {"protocol": "PRIVATE " + self.token}):
            with self.subTest(overrides=overrides):
                self.reply(self.catalog(commands=[self.command(**overrides)]))
                result = self.invoke("xiaoxi_ac_list_commands")
                for command in result["commands"]:
                    self.assertIs(command["replayable"], False)
                self.assertNotIn(self.token, json.dumps(result))

    def test_catalog_empty_and_unknown_state_values_are_not_invented(self):
        for state in (None, {}, {"power": None, "mode": None, "temp_c": None, "fan": None}):
            with self.subTest(state=state):
                self.reply(self.catalog(profile_id=None, active_profile_id=None,
                                        commands=[self.command(state=state, replayable=False)]))
                result = self.invoke("xiaoxi_ac_list_commands")
                self.assertIsNone(result["profile_id"])
                self.assertIsNone(result["active_profile_id"])
                self.assertEqual(result["commands"][0]["state"], state)
        self.reply(self.catalog(profile_id=None, active_profile_id=None, profiles=[], commands=[]))
        result = self.invoke("xiaoxi_ac_list_commands")
        self.assertEqual(result["profiles"], [])
        self.assertEqual(result["commands"], [])

    def test_control_catalog_envelope_and_duplicate_json_keys_are_rejected(self):
        for data in ([], {}, None, {"ok": 1}, self.catalog(command_id="A" * 32),
                     self.catalog(profiles={}), self.catalog(commands="private")):
            with self.subTest(data=data):
                self.reply(data)
                self.assertEqual(self.invoke("xiaoxi_ac_list_commands"), {
                    "ok": False, "error": "control_invalid_response",
                })
        for raw in (b'{"ok":false,"ok":true}',
                    b'{"ok":true,"commands":[{"state":{"power":true,"power":false}}]}',
                    b'{"ok":true,"raw":NaN}'):
            self.response.read.return_value = raw
            self.assertEqual(self.invoke("xiaoxi_ac_list_commands")["error"], "control_invalid_response")

    def test_control_service_errors_project_only_sanitized_codes(self):
        for tool, arguments in (("xiaoxi_ac_list_commands", {}),
                                ("xiaoxi_ac_send", self.send_arguments())):
            for code, expected in (("learning_capture_active", "learning_capture_active"),
                                   ("private: " + self.token, "control_service_error")):
                with self.subTest(tool=tool, code=code):
                    self.reply({"ok": False, "error": code, "message": self.token,
                                "capture": {"timings_us": [100, 200]}})
                    self.assertEqual(self.invoke(tool, arguments), {"ok": False, "error": expected})

    def test_send_acknowledgement_never_claims_appliance_response(self):
        self.reply({"ok": True, "command_id": "c" * 32, "outcome": "node_acknowledged",
                    "attempt_consumed": True, "appliance_response_verified": False,
                    "message": self.token, "capture": {"timings_us": [100, 200]}})
        self.assertEqual(self.invoke("xiaoxi_ac_send", self.send_arguments()), {
            "ok": True, "command_id": "c" * 32, "outcome": "node_acknowledged",
            "attempt_consumed": True, "appliance_response_verified": False,
        })
        self.connection.request.assert_called_once()

    def test_send_unknown_backend_result_keeps_consumed_attempt_and_error(self):
        for code in (None, "command_already_consumed", "publish_failed_no_retry"):
            with self.subTest(code=code):
                expected = {"ok": False, "command_id": "c" * 32, "outcome": "unknown_no_retry",
                            "attempt_consumed": True, "appliance_response_verified": False}
                if code is not None:
                    expected["error"] = code
                self.reply({**expected, "message": self.token, "timings_us": [100, 200]})
                self.connection.request.reset_mock()
                self.assertEqual(self.invoke("xiaoxi_ac_send", self.send_arguments()), expected)
                self.connection.request.assert_called_once()

    def test_send_network_failures_return_unknown_without_retrying(self):
        for name, error in (("request", TimeoutError(self.token)),
                            ("getresponse", OSError(self.token)),
                            ("read", ConnectionError(self.token))):
            with self.subTest(stage=name):
                self.connection.reset_mock()
                target = self.response.read if name == "read" else getattr(self.connection, name)
                target.side_effect = error
                result = self.invoke("xiaoxi_ac_send", self.send_arguments())
                self.assert_unknown_send(result)
                self.assertEqual(result["error"], "control_unavailable")
                self.assertNotIn(self.token, json.dumps(result))
                self.connection.request.assert_called_once()
                self.connection.close.assert_called_once()
                target.side_effect = None
        self.connect.side_effect = OSError(self.token)
        self.connect.reset_mock()
        self.assert_unknown_send(self.invoke("xiaoxi_ac_send", self.send_arguments()))
        self.connect.assert_called_once()

    def test_send_invalid_json_or_result_returns_original_operation_as_unknown(self):
        valid = {"ok": True, "command_id": "c" * 32, "outcome": "node_acknowledged",
                 "attempt_consumed": True, "appliance_response_verified": False}
        replies = [b"[]", b"{}", b"null", b"not-json", b"\xff", b'{"ok":true,"value":NaN}',
                   b'{"ok":true,"ok":false}', b'{"ok":false}',
                   b'{"ok":false,"error":"publish_failed_no_retry","attempt_consumed":true}',
                   json.dumps({"ok": False, "error": "command_already_consumed",
                               "command_id": "c" * 32}).encode(),
                   json.dumps({**valid, "command_id": "d" * 32}).encode(),
                   json.dumps({**valid, "appliance_response_verified": True}).encode(),
                   json.dumps({**valid, "attempt_consumed": 1}).encode(),
                   json.dumps({**valid, "outcome": "sent"}).encode(),
                   json.dumps({**valid, "ok": False}).encode()]
        for raw in replies:
            with self.subTest(raw=raw):
                self.response.read.return_value = raw
                self.connection.request.reset_mock()
                result = self.invoke("xiaoxi_ac_send", self.send_arguments())
                self.assert_unknown_send(result)
                self.assertEqual(result["error"], "control_invalid_response")
                self.connection.request.assert_called_once()

    def test_control_non_json_and_encoded_bodies_are_rejected_before_reading(self):
        for headers in ({"Content-Type": "text/html"},
                        {"Content-Type": "application/json", "Content-Encoding": "gzip"}):
            for tool, arguments in (("xiaoxi_ac_list_commands", {}),
                                    ("xiaoxi_ac_send", self.send_arguments())):
                with self.subTest(headers=headers, tool=tool):
                    self.headers.clear()
                    self.headers.update(headers)
                    result = self.invoke(tool, arguments)
                    self.assertEqual(result["error"], "control_invalid_response")
                    if tool == "xiaoxi_ac_send":
                        self.assert_unknown_send(result)
        self.response.read.assert_not_called()

    def test_control_redirects_and_http_errors_are_not_followed_or_retried(self):
        for status in (302, 401, 500):
            for tool, arguments in (("xiaoxi_ac_list_commands", {}),
                                    ("xiaoxi_ac_send", self.send_arguments())):
                with self.subTest(status=status, tool=tool):
                    self.response.status = status
                    self.connection.request.reset_mock()
                    result = self.invoke(tool, arguments)
                    self.assertEqual(result["error"], "control_http_error")
                    if tool == "xiaoxi_ac_send":
                        self.assert_unknown_send(result)
                    self.connection.request.assert_called_once()
        self.response.read.assert_not_called()

    def test_control_response_body_and_declared_length_are_bounded(self):
        for tool, arguments in (("xiaoxi_ac_list_commands", {}),
                                ("xiaoxi_ac_send", self.send_arguments())):
            with self.subTest(tool=tool):
                self.headers.pop("Content-Length", None)
                self.response.read.return_value = b"x" * (128 * 1024 + 1)
                result = self.invoke(tool, arguments)
                self.assertEqual(result["error"], "control_response_too_large")
                if tool == "xiaoxi_ac_send":
                    self.assert_unknown_send(result)
                self.response.read.reset_mock()
                self.headers["Content-Length"] = str(128 * 1024 + 1)
                result = self.invoke(tool, arguments)
                self.assertEqual(result["error"], "control_response_too_large")
                if tool == "xiaoxi_ac_send":
                    self.assert_unknown_send(result)
                self.response.read.assert_not_called()
        for length in ("-1", "private", "1.5"):
            self.headers["Content-Length"] = length
            self.assertEqual(self.invoke("xiaoxi_ac_list_commands")["error"], "control_invalid_response")


if __name__ == "__main__":
    unittest.main()
