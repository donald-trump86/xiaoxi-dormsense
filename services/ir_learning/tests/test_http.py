import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from services.ir_learning.server import handler_for


class FakeSession:
    def __init__(self):
        self.calls = []

    def public(self):
        return {"ok": True, "status": "idle", "button": "baseline"}

    def start(self):
        self.calls.append("start")
        return {"ok": True, "status": "ready"}

    def next(self, button):
        self.calls.append(("next", button))
        raise ValueError("baseline_required")

    def confirm(self, label, confirmed):
        self.calls.append(("confirm", label, confirmed))
        return self.public()

    def skip(self, reason, *, button):
        if button != self.public()["button"]:
            raise ValueError("button_mismatch")
        self.calls.append(("skip", reason, button))
        return self.public()

    def cancel(self):
        self.calls.append("cancel")
        return self.public()


class MemoryConnection:
    """Exercise the real HTTP parser without binding a socket."""
    def __init__(self, request):
        self.input = io.BytesIO(request)
        self.output = io.BytesIO()

    def makefile(self, *args):
        return self.input

    def sendall(self, data):
        self.output.write(data)

    def settimeout(self, seconds):
        pass


class HttpBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.session = FakeSession()
        self.token = "offline-test-token-only"
        self.control = None

    def request(self, body, *, path="/api/learning", token=None, method="POST", headers=None):
        payload = (json.dumps(body) if not isinstance(body, str) else body).encode()
        fields = [("Content-Type", "application/json"),
                  ("Authorization", "Bearer " + (self.token if token is None else token)),
                  ("Content-Length", str(len(payload))), *(headers or [])]
        request = (f"{method} {path} HTTP/1.1\r\n" +
                   "".join(f"{key}: {value}\r\n" for key, value in fields) + "\r\n").encode() + payload
        connection = MemoryConnection(request)
        kwargs = {"control": self.control} if self.control is not None else {}
        with patch("socket.socket", side_effect=AssertionError("network_forbidden")):
            handler_for(self.session, self.token, **kwargs)(
                connection, ("127.0.0.1", 0),
                SimpleNamespace(server_name="offline", server_port=0),
            )
        header, response = connection.output.getvalue().split(b"\r\n\r\n", 1)
        return int(header.split()[1]), json.loads(response)

    def test_authentication_precedes_session_action(self):
        status, body = self.request({"action": "start"}, token="wrong")
        self.assertEqual(401, status)
        self.assertEqual("unauthorized", body["error"])
        self.assertEqual([], self.session.calls)

    def test_start_and_status_are_fixed_learning_actions(self):
        self.assertEqual((200, {"ok": True, "status": "ready"}), self.request({"action": "start"}))
        self.assertEqual("idle", self.request({"action": "status"})[1]["status"])
        self.assertEqual(["start"], self.session.calls)

    def test_model_cannot_supply_send_topic_path_or_backend(self):
        for request in ({"action": "ir_raw_commit"}, {"action": "start", "topic": "anything"},
                        {"action": "start", "url": "http://backend"},
                        {"action": "status", "timings_us": [560]}, {"action": "start", "path": "/private"}):
            with self.subTest(request=request):
                self.assertEqual({"ok": False, "error": "invalid_request"}, self.request(request)[1])
        self.assertEqual([], self.session.calls)
        self.assertEqual(404, self.request({"action": "start"}, path="/api/replay")[0])
        self.assertEqual(404, self.request({}, path="/api/states", method="GET")[0])

    def test_duplicate_key_and_oversized_json_fail_closed(self):
        self.assertEqual("invalid_request", self.request('{"action":"start","action":"status"}')[1]["error"])
        self.assertEqual("invalid_request", self.request(" " * 2049)[1]["error"])
        self.assertEqual([], self.session.calls)

    def test_known_model_error_is_sanitized_and_useful(self):
        status, body = self.request({"action": "next", "button": "temp_up"})
        self.assertEqual(200, status)
        self.assertEqual("baseline_required", body["error"])
        self.assertIn("baseline", body["prompt"])
        self.assertNotIn(self.token, json.dumps(body))

    def test_confirmation_requires_supplied_manual_label(self):
        body = self.request({"action": "confirm", "button": "baseline", "confirm": True})[1]
        self.assertEqual("explicit_label_confirmation_required", body["error"])
        self.assertEqual([], self.session.calls)

    def test_skip_is_bound_to_current_button(self):
        for request in ({"action": "skip"}, {"action": "skip", "button": "temp_up"}):
            self.assertEqual("button_mismatch", self.request(request)[1]["error"])
        self.assertEqual([], self.session.calls)
        self.assertTrue(self.request({"action": "skip", "button": "baseline"})[1]["ok"])
        self.assertEqual([("skip", "", "baseline")], self.session.calls)

    def test_confirmation_is_bound_to_pending_button(self):
        body = self.request({"action": "confirm", "button": "power", "confirm": True})[1]
        self.assertEqual("button_mismatch", body["error"])
        self.assertEqual([], self.session.calls)


class ControlHttpBoundaryTests(HttpBoundaryTests):
    def setUp(self):
        super().setUp()
        self.control = SimpleNamespace(
            catalog=Mock(return_value={"ok": True, "profiles": [], "commands": [],
                                       "command_id": "c" * 32}),
            send=Mock(return_value={"ok": True, "command_id": "c" * 32,
                                    "outcome": "node_acknowledged", "attempt_consumed": True,
                                    "appliance_response_verified": False}),
        )
        self.send_request = {"action": "send", "profile_id": "a" * 32,
                             "record_id": "b" * 32, "command_id": "c" * 32,
                             "confirm_once": True}

    def control_request(self, body, **kwargs):
        return self.request(body, path="/api/control", **kwargs)

    def test_control_authentication_precedes_every_action(self):
        for body in ({"action": "list"}, self.send_request):
            self.assertEqual(401, self.control_request(body, token="wrong")[0])
            self.assertEqual(401, self.control_request(body, headers=[("Authorization", "Bearer " + self.token)])[0])
        self.control.catalog.assert_not_called()
        self.control.send.assert_not_called()

    def test_list_uses_only_optional_profile_identifier(self):
        status, body = self.control_request({"action": "list"})
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.control.catalog.assert_called_once_with()
        self.control.catalog.reset_mock()
        self.assertTrue(self.control_request({"action": "list", "profile_id": "d" * 32})[1]["ok"])
        self.control.catalog.assert_called_once_with("d" * 32)
        self.assertEqual(self.session.calls, [])

    def test_send_passes_exact_arguments_and_preserves_unknown_result(self):
        self.control.send.return_value.update(ok=False, outcome="unknown_no_retry")
        status, body = self.control_request(self.send_request)
        self.assertEqual(status, 200)
        self.assertEqual(body["outcome"], "unknown_no_retry")
        self.assertTrue(body["attempt_consumed"])
        self.assertFalse(body["appliance_response_verified"])
        self.control.send.assert_called_once_with("a" * 32, "b" * 32, "c" * 32,
                                                  confirm_once=True)
        self.assertEqual(self.session.calls, [])

    def test_control_rejects_action_specific_extra_fields_before_send(self):
        for base in ({"action": "list"}, self.send_request):
            for key, value in (("topic", "anything"), ("url", "http://offline.invalid"),
                               ("path", "/private"), ("timings_us", [500]),
                               ("capture", {}), ("frequency_khz", 38), ("confirm", True)):
                with self.subTest(action=base["action"], key=key):
                    body = dict(base, **{key: value})
                    self.assertEqual(self.control_request(body)[1]["error"], "invalid_request")
        self.assertEqual(self.control_request({"action": "list", "confirm_once": True})[1]["error"],
                         "invalid_request")
        self.control.catalog.assert_not_called()
        self.control.send.assert_not_called()

    def test_control_requires_all_send_fields_and_literal_true(self):
        for key in ("profile_id", "record_id", "command_id", "confirm_once"):
            body = dict(self.send_request)
            body.pop(key)
            self.assertEqual(self.control_request(body)[1]["error"], "invalid_request")
        for value in (False, None, 1, "true"):
            body = dict(self.send_request, confirm_once=value)
            self.assertEqual(self.control_request(body)[1]["error"], "confirmation_required")
        self.control.send.assert_not_called()

    def test_control_validates_ids_and_fixed_route(self):
        for key in ("profile_id", "record_id", "command_id"):
            for value in ("../escape", "A" * 32, None, True, {}):
                with self.subTest(key=key, value=value):
                    body = dict(self.send_request, **{key: value})
                    self.assertEqual(self.control_request(body)[1]["error"], "invalid_identifier")
        self.assertEqual(self.control_request({"action": "list", "profile_id": None})[1]["error"],
                         "invalid_identifier")
        self.assertEqual(self.request({"action": "list"}, path="/api/control?profile_id=anything")[0], 404)
        self.assertEqual(self.control_request({}, method="GET")[0], 404)
        self.control.catalog.assert_not_called()
        self.control.send.assert_not_called()

    def test_control_reuses_duplicate_body_size_and_encoding_guards(self):
        for payload in ('{"action":"list","action":"send"}', " " * 2049,
                        '{"action":"list","profile_id":"a","profile_id":"b"}'):
            self.assertEqual(self.control_request(payload)[1]["error"], "invalid_request")
        for headers in ([('Transfer-Encoding', 'chunked')], [('Content-Encoding', 'gzip')],
                        [('Content-Length', '2')]):
            self.assertEqual(self.control_request({"action": "list"}, headers=headers)[1]["error"],
                             "invalid_request")
        self.control.catalog.assert_not_called()
        self.control.send.assert_not_called()

    def test_control_unexpected_exception_never_reflects_private_input(self):
        self.control.send.side_effect = RuntimeError("FAKE_PRIVATE_ERROR_PATH")
        status, body = self.control_request(self.send_request)
        self.assertEqual(status, 503)
        self.assertEqual(body["error"], "control_unavailable")
        self.assertEqual(body["command_id"], "c" * 32)
        self.assertEqual(body["outcome"], "unknown_no_retry")
        self.assertTrue(body["attempt_consumed"])
        self.assertFalse(body["appliance_response_verified"])
        self.assertNotIn("FAKE_PRIVATE", json.dumps(body))


if __name__ == "__main__":
    unittest.main()
