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

    def sent(self):
        args, kwargs = self.connection.request.call_args
        self.assertEqual(args[:2], ("POST", "/api/learning"))
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer " + self.token)
        return json.loads(kwargs["body"])

    def test_registers_only_three_native_tools_without_reading_secrets(self):
        self.assertEqual(set(self.context.tools), {
            "xiaoxi_ac_initialize", "xiaoxi_ac_learn_key", "xiaoxi_ac_learning_status",
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


if __name__ == "__main__":
    unittest.main()
