"""Real loopback HTTP only: fake HA fixtures, not HA/Docker/hardware acceptance.

All tokens/data below are fixed dummy TEST FIXTURES, never production telemetry.
Numeric fixtures deliberately have simulated=False to exercise the gateway's
real-source-only projection; this is NOT a claim they came from a real sensor.
The explicit simulated=True rejection/unknown-retention checks pin that policy.
No config/environment/runtime/browser secrets are read; no external HTTP is used.
"""
from contextlib import contextmanager, ExitStack
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "read_gateway.py"
SPEC = importlib.util.spec_from_file_location("private_gateway_http_tests", MODULE_PATH)
gateway = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gateway
SPEC.loader.exec_module(gateway)

HOST = "127.0.0.1"
TEMPERATURE, HUMIDITY = gateway.DEFAULT_ENTITIES
TEMP_PATH = "/api/states/" + TEMPERATURE
HUMIDITY_PATH = "/api/states/" + HUMIDITY
FRONT_TOKEN = "dummy_loopback_front_token_" + "q" * 32
BACK_TOKEN = "dummy_loopback_backend_token_only"
SECRET_CANARY = "DUMMY_TEST_BACKEND_SECRET_DO_NOT_PROJECT"


def fixture(entity_id=TEMPERATURE, state="23.5"):
    """Dummy fixture for the accepted numeric branch, NOT observed sensor data."""
    return {
        "entity_id": entity_id, "state": state,
        "last_changed": SECRET_CANARY,
        "attributes": {
            "unit_of_measurement": "%" if "humidity" in entity_id else "°C",
            "boot_id": "node01-1234abcd", "sequence": 0,
            "simulated": False, "received_at": "2026-06-02T10:20:30Z",
            "secret": SECRET_CANARY, "friendly_name": SECRET_CANARY,
        },
    }


class FakeHAServer(ThreadingHTTPServer):
    """Loopback fake HA: only records requests and returns configured fixtures."""
    daemon_threads = True
    block_on_close = False

    def __init__(self):
        super().__init__((HOST, 0), FakeHAHandler)
        self.lock = threading.Lock()
        self.calls = []
        self.workers = []
        self.errors = []
        self.routes = {}
        self.stall_paths = set()
        self.release = threading.Event()

    def process_request_thread(self, request, client_address):
        with self.lock:
            self.workers.append(threading.current_thread())
        super().process_request_thread(request, client_address)

    def handle_error(self, request, client_address):
        with self.lock:
            self.errors.append("unexpected_fake_server_error")

    def recorded(self):
        with self.lock:
            return list(self.calls)


class FakeHAHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def setup(self):
        self.request.settimeout(1)
        super().setup()

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        with self.server.lock:
            self.server.calls.append((self.command, self.path, list(self.headers.items())))
        if self.path in self.server.stall_paths:
            self.server.release.wait(timeout=1)
        status, body, headers = self.server.routes.get(
            self.path, (404, SECRET_CANARY.encode(), {}))
        response_headers = {"Content-Type": "application/json",
                            "Content-Length": str(len(body)), **headers}
        try:
            self.send_response_only(status)
            for key, value in response_headers.items():
                if value is not None:
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # The gateway deliberately closes rejected/oversized/timed-out reads.
            pass

    # Even a hypothetical forwarded write only records; no service/device exists.
    do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = do_GET
    do_TRACE = do_CONNECT = do_PROPFIND = do_GET


@contextmanager
def serving(server):
    """Always close listeners and bounded-join every server/request thread."""
    thread = threading.Thread(target=server.serve_forever,
                              kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        if isinstance(server, FakeHAServer):
            server.release.set()
        try:
            server.shutdown()
        finally:
            server.server_close()
            deadline = time.monotonic() + 2
            workers = []
            if isinstance(server, FakeHAServer):
                with server.lock:
                    workers = list(server.workers)
            for worker in [thread, *workers]:
                worker.join(timeout=max(0, deadline - time.monotonic()))
            if any(worker.is_alive() for worker in [thread, *workers]):
                raise AssertionError("loopback server thread did not stop")
            if server.socket.fileno() != -1:
                raise AssertionError("loopback listener was not closed")
            if isinstance(server, FakeHAServer) and server.errors:
                raise AssertionError(server.errors)


class GatewayHTTPTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.stderr = stack.enter_context(patch("sys.stderr", new_callable=io.StringIO))
        # Check after both servers/worker threads finish, before restoring stderr.
        stack.callback(lambda: self.assertEqual(self.stderr.getvalue(), ""))
        self.backend = FakeHAServer()
        stack.enter_context(serving(self.backend))
        self.set_response(json.dumps(fixture()).encode())
        self.set_response(json.dumps(fixture(HUMIDITY, "55")).encode(), path=HUMIDITY_PATH)
        # Canary failure: an aggregate backend fetch must never succeed.
        self.set_response(SECRET_CANARY.encode(), status=500, path="/api/states")
        self.front = gateway.GatewayHTTPServer((HOST, 0), gateway.ReadGatewayHandler)
        self.front.config = gateway.Config(
            f"http://{HOST}:{self.backend.server_port}", BACK_TOKEN, FRONT_TOKEN)
        # Real urllib opener and real HTTP: neither reader nor sockets are mocked.
        self.front.backend_reader = gateway.BackendReader(self.front.config)
        stack.enter_context(serving(self.front))

    def set_response(self, body, status=200, headers=None, path=TEMP_PATH):
        self.backend.routes[path] = (status, body, headers or {})

    def request(self, path=TEMP_PATH, method="GET", auth=None, extra_headers=(), body=b""):
        if auth is None:
            auth = ["Bearer " + FRONT_TOKEN]
        connection = http.client.HTTPConnection(HOST, self.front.server_port, timeout=2)
        try:
            connection.putrequest(method, path, skip_accept_encoding=True)
            for value in auth:
                connection.putheader("Authorization", value)
            for key, value in extra_headers:
                connection.putheader(key, value)
            connection.endheaders(body)
            response = connection.getresponse()
            payload = response.read()
            headers = dict(response.getheaders())
            self.assertEqual(headers.get("Cache-Control"), "no-store")
            self.assertEqual(headers.get("Connection"), "close")
            self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
            self.assertEqual(headers.get("Content-Type"), "application/json; charset=utf-8")
            self.assertNotIn("Server", headers)
            self.assertNotIn("Date", headers)
            wire = str(headers).encode() + payload
            for canary in (FRONT_TOKEN, BACK_TOKEN, SECRET_CANARY):
                self.assertNotIn(canary.encode(), wire)
            if method == "HEAD":
                self.assertEqual(payload, b"")
                value = None
            else:
                self.assertEqual(int(headers["Content-Length"]), len(payload))
                value = json.loads(payload)
            return response.status, value
        finally:
            connection.close()

    def assert_backend_calls(self, paths):
        calls = self.backend.recorded()
        self.assertEqual([path for _, path, _ in calls], paths)
        for method, _, pairs in calls:
            self.assertEqual(method, "GET")
            headers = {key.lower(): value for key, value in pairs}
            self.assertEqual(headers["authorization"], "Bearer " + BACK_TOKEN)
            self.assertEqual(headers["accept"], "application/json")
            self.assertEqual(headers["accept-encoding"], "identity")
            self.assertNotIn(FRONT_TOKEN, str(pairs))
            self.assertNotIn("x-client-secret", headers)

    def assert_backend_error(self, path=TEMP_PATH):
        before = len(self.backend.recorded())
        self.assertEqual(self.request(path), (502, {"error": "backend_unavailable"}))
        self.assertEqual(len(self.backend.recorded()), before + 1)

    def test_fixed_entity_gets_and_backend_only_token(self):
        for path, entity_id, state in [(TEMP_PATH, TEMPERATURE, "23.5"),
                                       (HUMIDITY_PATH, HUMIDITY, "55")]:
            with self.subTest(path=path):
                status, value = self.request(
                    path, extra_headers=(("X-Client-Secret", FRONT_TOKEN),))
                self.assertEqual(status, 200)
                self.assertEqual(value["entity_id"], entity_id)
                self.assertEqual(value["state"], state)
                self.assertEqual(value["attributes"]["sequence"], 0)
        self.assert_backend_calls([TEMP_PATH, HUMIDITY_PATH])

    def test_list_projection_reads_only_fixed_entities_and_drops_secret_attributes(self):
        other_path = "/api/states/light.other"
        self.set_response(SECRET_CANARY.encode(), status=500, path=other_path)
        status, value = self.request("/api/states")
        self.assertEqual(status, 200)
        self.assertEqual([item["entity_id"] for item in value], [TEMPERATURE, HUMIDITY])
        for item in value:
            self.assertEqual(set(item), {"entity_id", "state", "attributes"})
            self.assertEqual(set(item["attributes"]), {
                "unit_of_measurement", "node_id", "boot_id", "sequence",
                "simulated", "received_at"})
            self.assertEqual(item["attributes"]["node_id"], "node01")
        self.assertEqual([item["state"] for item in value], ["23.5", "55"])
        self.assert_backend_calls([TEMP_PATH, HUMIDITY_PATH])

    def test_list_uses_configured_suffix_entities_in_configured_order(self):
        allowed = (HUMIDITY + "_3", TEMPERATURE + "_2")
        self.front.config = gateway.Config(
            f"http://{HOST}:{self.backend.server_port}", BACK_TOKEN, FRONT_TOKEN, allowed)
        self.front.backend_reader = gateway.BackendReader(self.front.config)
        paths = ["/api/states/" + entity_id for entity_id in allowed]
        self.set_response(json.dumps(fixture(allowed[0], "55")).encode(), path=paths[0])
        self.set_response(json.dumps(fixture(allowed[1])).encode(), path=paths[1])
        status, value = self.request("/api/states")
        self.assertEqual(status, 200)
        self.assertEqual([item["entity_id"] for item in value], list(allowed))
        self.assertEqual([item["state"] for item in value], ["55", "23.5"])
        self.assertEqual([item["attributes"]["unit_of_measurement"] for item in value], ["%", "°C"])
        self.assert_backend_calls(paths)
        self.assertEqual(self.request(TEMP_PATH), (404, {"error": "not_found"}))
        self.assert_backend_calls(paths)

    def test_exact_front_bearer_and_duplicate_auth_blocked(self):
        bad_auth = [[], ["Bearer " + BACK_TOKEN], ["Bearer wrong"], ["Bearer "],
                    ["Basic " + FRONT_TOKEN], ["bearer " + FRONT_TOKEN],
                    ["Bearer  " + FRONT_TOKEN], ["Bearer " + FRONT_TOKEN + " "],
                    ["Bearer " + FRONT_TOKEN + "x"], ["Bearer " + "é" * 32],
                    ["Bearer " + FRONT_TOKEN, "Bearer " + FRONT_TOKEN]]
        for auth in bad_auth:
            with self.subTest(auth=auth):
                self.assertEqual(self.request(auth=auth), (401, {"error": "unauthorized"}))
        self.assert_backend_calls([])

    def test_non_get_verbs_and_service_writes_never_forward(self):
        for method in ["POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "TRACE",
                       "CONNECT", "PROPFIND", "get", "FROB"]:
            for path in [TEMP_PATH, "/api/services/light/turn_on"]:
                with self.subTest(method=method, path=path):
                    status, body = self.request(path, method)
                    self.assertEqual(status, 405)
                    if method != "HEAD":
                        self.assertEqual(body, {"error": "method_not_allowed"})
        self.assert_backend_calls([])

    def test_non_exact_paths_never_forward(self):
        for path in ["/api/services", "/api/services/light/turn_on", "/api/config",
                     "/api/states/sensor.other", TEMP_PATH + "_2", TEMP_PATH + "/",
                     "/api/states/", "/api/states?", "/api/states?token=" + FRONT_TOKEN,
                     "/api/states#fragment", "//api/states", "///api/states", "/api//states",
                     "/api/%73tates", "/api%2fstates", "/api/%2573tates",
                     "/api/states/sensor.xiaoxi_node01_%74emperature",
                     "/api/states/../config", "http://127.0.0.1/api/states", "*"]:
            with self.subTest(path=path):
                self.assertEqual(self.request(path), (404, {"error": "not_found"}))
        self.assert_backend_calls([])

    def test_get_body_transfer_encoding_and_duplicate_lengths_never_forward(self):
        for headers, body in [([("Content-Length", "1")], b"x"),
                              ([("Content-Length", "xyz")], b""),
                              ([("Content-Length", "0"), ("Content-Length", "0")], b""),
                              ([("Transfer-Encoding", "chunked")], b"0\r\n\r\n")]:
            with self.subTest(headers=headers):
                self.assertEqual(self.request(extra_headers=headers, body=body),
                                 (400, {"error": "bad_request"}))
        self.assert_backend_calls([])
        self.assertEqual(self.request(extra_headers=(("Content-Length", "0"),))[0], 200)
        self.assert_backend_calls([TEMP_PATH])

    def test_http_redirects_are_not_followed(self):
        for status in [301, 302, 303, 307, 308]:
            with self.subTest(status=status):
                # Even the redirect target is fake loopback, never an external URL.
                self.set_response(SECRET_CANARY.encode(), status,
                                  {"Location": f"http://{HOST}:{self.backend.server_port}/redirect-target"})
                self.assert_backend_error()
        self.assert_backend_calls([TEMP_PATH] * 5)

    def test_backend_bad_bodies_have_fixed_redacted_errors(self):
        bodies = [SECRET_CANARY.encode(), b"\xff", b'{"x":1,"x":2}',
                  b'{"x":NaN}', b'{"x":1e999}', b'{"x":"\\ud800"}',
                  b"[" * 40 + b"]" * 40]
        for body in bodies:
            with self.subTest(body=body):
                self.set_response(body)
                self.assert_backend_error()
        self.assert_backend_calls([TEMP_PATH] * len(bodies))

    def test_backend_oversize_lengths_and_encoding_are_rejected(self):
        cases = [(SECRET_CANARY.encode(), {"Content-Length": str(gateway.MAX_RESPONSE_BYTES + 1)}),
                 (b"x" * (gateway.MAX_RESPONSE_BYTES + 1), {"Content-Length": None}),
                 (b"{}", {"Content-Length": "3"}),
                 (b"{}", {"Content-Length": "-1"}),
                 (b"{}", {"Content-Length": SECRET_CANARY}),
                 (b"{}", {"Content-Encoding": "gzip"})]
        for body, headers in cases:
            with self.subTest(headers=headers):
                self.set_response(body, headers=headers)
                self.assert_backend_error()
        self.assert_backend_calls([TEMP_PATH] * len(cases))

    def test_backend_wrong_entity_invalid_metadata_and_simulation_fail_closed(self):
        wrong_id = fixture(HUMIDITY, "55")
        simulated = fixture()
        simulated["attributes"]["simulated"] = True
        bad_metadata = fixture()
        bad_metadata["attributes"]["received_at"] = SECRET_CANARY
        bad_state = fixture(state=SECRET_CANARY)
        for value in [wrong_id, {}, [], bad_state, bad_metadata, simulated]:
            with self.subTest(value=value):
                self.set_response(json.dumps(value).encode())
                self.assert_backend_error()
        self.assert_backend_calls([TEMP_PATH] * 6)

    def test_list_either_individual_failure_has_no_partial_or_raw_response(self):
        paths = [TEMP_PATH, HUMIDITY_PATH]
        calls = []
        for index, path in enumerate(paths):
            good = fixture() if index == 0 else fixture(HUMIDITY, "55")
            wrong = fixture(HUMIDITY, "55") if index == 0 else fixture()
            bad_metadata = fixture(good["entity_id"], good["state"])
            bad_metadata["attributes"]["received_at"] = SECRET_CANARY
            simulated = fixture(good["entity_id"], good["state"])
            simulated["attributes"]["simulated"] = True
            bodies = [SECRET_CANARY.encode(), b"\xff", b'{"x":1,"x":2}',
                      b'{"x":NaN}', b'{"x":1e999}', b'{"x":"\\ud800"}',
                      b"[" * 40 + b"]" * 40]
            bodies += [json.dumps(value).encode() for value in
                       [{}, [], [good], [good, good], wrong, bad_metadata, simulated]]
            cases = [(body, 200, {}) for body in bodies]
            cases += [(SECRET_CANARY.encode(), status, {
                "X-Backend-Secret": BACK_TOKEN,
                "Location": f"http://{HOST}:{self.backend.server_port}/redirect-target"})
                for status in [201, 204, 301, 302, 303, 307, 308, 401, 403, 404, 500, 503]]
            cases += [(body, 200, headers) for body, headers in [
                (SECRET_CANARY.encode(), {"Content-Length": str(gateway.MAX_RESPONSE_BYTES + 1)}),
                (b"x" * (gateway.MAX_RESPONSE_BYTES + 1), {"Content-Length": None}),
                (b"{}", {"Content-Length": "3"}), (b"{}", {"Content-Length": "-1"}),
                (b"{}", {"Content-Length": SECRET_CANARY}),
                (b"{}", {"Content-Encoding": "gzip"})]]
            for body, status, headers in cases:
                with self.subTest(path=path, status=status, headers=headers, body=body[:80]):
                    self.set_response(body, status, headers, path)
                    self.assertEqual(self.request("/api/states"),
                                     (502, {"error": "backend_unavailable"}))
                    calls.extend(paths[:index + 1])
                    self.assert_backend_calls(calls)
            # Missing fixed endpoint must fail exactly like HA's missing entity.
            del self.backend.routes[path]
            self.assertEqual(self.request("/api/states"),
                             (502, {"error": "backend_unavailable"}))
            calls.extend(paths[:index + 1])
            self.assert_backend_calls(calls)
            self.set_response(json.dumps(good).encode(), path=path)

    def test_list_either_individual_socket_timeout_is_redacted(self):
        paths = [TEMP_PATH, HUMIDITY_PATH]
        calls = []
        for index, path in enumerate(paths):
            with self.subTest(path=path):
                self.backend.stall_paths.add(path)
                self.backend.release.clear()
                try:
                    with patch.object(gateway, "TIMEOUT_SECONDS", 0.1):
                        self.assertEqual(self.request("/api/states"),
                                         (502, {"error": "backend_unavailable"}))
                finally:
                    self.backend.release.set()
                    self.backend.stall_paths.clear()
                calls.extend(paths[:index + 1])
                self.assert_backend_calls(calls)

    def test_unknown_unavailable_do_not_invent_metadata_or_erase_simulated(self):
        for state in ["unknown", "unavailable"]:
            value = {"entity_id": TEMPERATURE, "state": state, "attributes": {}}
            self.set_response(json.dumps(value).encode())
            status, projected = self.request()
            self.assertEqual(status, 200)
            self.assertEqual(projected["state"], state)
            for key in ["boot_id", "sequence", "simulated", "received_at"]:
                self.assertIsNone(projected["attributes"][key])
        previous = fixture(state="unknown")
        previous["attributes"]["simulated"] = True
        self.set_response(json.dumps(previous).encode())
        status, projected = self.request()
        self.assertEqual(status, 200)
        self.assertIs(projected["attributes"]["simulated"], True)
        self.assertEqual(projected["attributes"]["received_at"], "2026-06-02T10:20:30Z")
        self.assert_backend_calls([TEMP_PATH] * 3)

    def test_backend_http_errors_are_redacted(self):
        for status in [201, 204, 401, 403, 404, 500, 503]:
            with self.subTest(status=status):
                self.set_response(SECRET_CANARY.encode(), status,
                                  {"X-Backend-Secret": BACK_TOKEN})
                self.assert_backend_error()
        self.assert_backend_calls([TEMP_PATH] * 7)

    def test_real_backend_socket_timeout_is_short_and_redacted(self):
        self.backend.stall_paths.add(TEMP_PATH)
        started = time.monotonic()
        try:
            # Only timing config is mocked; the backend request/socket is real.
            with patch.object(gateway, "TIMEOUT_SECONDS", 0.1):
                self.assert_backend_error()
        finally:
            self.backend.release.set()
        self.assertLess(time.monotonic() - started, 2)
        self.assert_backend_calls([TEMP_PATH])


if __name__ == "__main__":
    unittest.main()
