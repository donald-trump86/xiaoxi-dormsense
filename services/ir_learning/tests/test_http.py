import http.client
from http.server import HTTPServer
import json
from pathlib import Path
import sys
import threading
import unittest

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


class HttpBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.session = FakeSession()
        self.token = "test-only-credential-not-a-runtime-secret"
        self.server = HTTPServer(("127.0.0.1", 0), handler_for(self.session, self.token))
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)

    def request(self, body, *, path="/api/learning", token=None, method="POST"):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + (self.token if token is None else token)}
        payload = json.dumps(body) if not isinstance(body, str) else body
        try:
            connection.request(method, path, payload, headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read(16384))
        finally:
            connection.close()

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


if __name__ == "__main__":
    unittest.main()
