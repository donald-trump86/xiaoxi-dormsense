"""Pure offline gateway tests: no sockets, services, Docker or real controls."""
import copy
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError


MODULE_PATH = Path(__file__).resolve().parents[1] / "read_gateway.py"
SPEC = importlib.util.spec_from_file_location("private_read_gateway", MODULE_PATH)
gateway = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gateway
SPEC.loader.exec_module(gateway)

TEMPERATURE = "sensor.xiaoxi_node01_temperature"
HUMIDITY = "sensor.xiaoxi_node01_humidity"
QUERY_TOKEN = "offline_query_token_" + "q" * 32
BACKEND_TOKEN = "offline_backend_secret_must_not_escape"
SECRET = "PRIVATE_BACKEND_RESPONSE_MUST_NOT_ESCAPE"


def entity(entity_id=TEMPERATURE, state="23.5", **attributes):
    unit = "%" if "humidity" in entity_id else "°C"
    attrs = {
        "unit_of_measurement": unit,
        "boot_id": "node01-1234abcd",
        "sequence": 12,
        "simulated": False,
        "received_at": "2026-06-02T10:20:30.123456+00:00",
    }
    attrs.update(attributes)
    return {"entity_id": entity_id, "state": state, "attributes": attrs}


class FakeBackend:
    def __init__(self, value=None, error=None, routes=None):
        self.value = value if value is not None else [entity(), entity(HUMIDITY, "55")]
        self.routes = routes
        if routes is None and isinstance(self.value, list):
            self.routes = {"/api/states/" + item["entity_id"]: item for item in self.value}
        self.error = error
        self.calls = []

    def __call__(self, path):
        self.calls.append(path)
        if path == "/api/states":
            raise AssertionError("aggregate backend fetch forbidden: " + SECRET)
        if self.error:
            raise self.error
        value = self.routes[path] if self.routes is not None else self.value
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)


class MemoryConnection:
    """HTTP parsing and response serialization without opening a socket."""
    def __init__(self, request):
        self.input = io.BytesIO(request)
        self.output = io.BytesIO()
        self.timeouts = []

    def makefile(self, mode, buffering=None):
        return self.input

    def sendall(self, value):
        self.output.write(value)

    def settimeout(self, value):
        self.timeouts.append(value)


class FakeResponse:
    def __init__(self, body, status=200, headers=None):
        self.body = io.BytesIO(body)
        self.status = status
        self.headers = headers or {}
        self.read_sizes = []
        self.closed = False

    def read(self, size):
        self.read_sizes.append(size)
        return self.body.read(size)

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.config = gateway.Config("http://ha-backend:8123", BACKEND_TOKEN, QUERY_TOKEN)

    def request(self, backend=None, path="/api/states", method="GET", token=QUERY_TOKEN,
                extra_headers=b"", body=b"", raw=None):
        backend = backend or FakeBackend()
        auth = b"" if token is None else b"Authorization: Bearer " + token.encode() + b"\r\n"
        wire = raw or (method.encode() + b" " + path.encode() + b" HTTP/1.1\r\n"
                       + b"Host: read-gateway\r\n" + auth + extra_headers
                       + b"\r\n" + body)
        connection = MemoryConnection(wire)
        server = SimpleNamespace(config=self.config, backend_reader=backend)
        with patch.object(socket, "socket", side_effect=AssertionError("network forbidden")), \
                patch("sys.stderr", new_callable=io.StringIO) as stderr:
            gateway.ReadGatewayHandler(connection, ("offline", 0), server)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(connection.timeouts, [5])
        result = connection.output.getvalue()
        header, _, payload = result.partition(b"\r\n\r\n")
        status = int(header.split(b" ")[1])
        self.assertIn(b"Cache-Control: no-store", header)
        self.assertNotIn(BACKEND_TOKEN.encode(), result)
        self.assertNotIn(QUERY_TOKEN.encode(), result)
        self.assertNotIn(SECRET.encode(), result)
        self.assertNotIn(b"Server:", header)
        self.assertNotIn(b"Date:", header)
        return status, json.loads(payload) if payload else None, backend

    def test_list_has_only_two_minimal_entities(self):
        data = [entity("light.other_node", "on"), entity(), entity(HUMIDITY, "55")]
        for item in data:
            item["last_changed"] = SECRET
            item["attributes"]["friendly_name"] = SECRET
        status, value, backend = self.request(FakeBackend(data))
        self.assertEqual(status, 200)
        self.assertEqual([item["entity_id"] for item in value], [TEMPERATURE, HUMIDITY])
        for item in value:
            self.assertEqual(set(item), {"entity_id", "state", "attributes"})
            self.assertEqual(set(item["attributes"]), {"unit_of_measurement", "node_id",
                             "boot_id", "sequence", "simulated", "received_at"})
            self.assertEqual(item["attributes"]["node_id"], "node01")
        self.assertEqual(backend.calls, ["/api/states/" + TEMPERATURE, "/api/states/" + HUMIDITY])

    def test_list_reads_configured_order_and_projects_each_endpoint(self):
        allowed = (HUMIDITY + "_3", TEMPERATURE + "_2")
        self.config = gateway.Config("http://ha-backend:8123", BACKEND_TOKEN, QUERY_TOKEN, allowed)
        samples = [entity(allowed[1], "23.5"), entity(allowed[0], "55")]
        status, value, backend = self.request(FakeBackend(samples))
        self.assertEqual(status, 200)
        self.assertEqual([item["entity_id"] for item in value], list(allowed))
        self.assertEqual([item["state"] for item in value], ["55", "23.5"])
        self.assertEqual([item["attributes"]["unit_of_measurement"] for item in value], ["%", "°C"])
        self.assertEqual(backend.calls, ["/api/states/" + entity_id for entity_id in allowed])

    def test_single_reads_both_entities(self):
        for entity_id, state in [(TEMPERATURE, "23.5"), (HUMIDITY, "55")]:
            with self.subTest(entity_id=entity_id):
                status, value, backend = self.request(FakeBackend(entity(entity_id, state)),
                                                       "/api/states/" + entity_id)
                self.assertEqual(status, 200)
                self.assertEqual(value["state"], state)
                self.assertEqual(backend.calls, ["/api/states/" + entity_id])

    def test_all_non_get_verbs_are_blocked_without_backend_calls(self):
        for method in ["POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "TRACE",
                       "CONNECT", "PROPFIND", "get", "FROB"]:
            with self.subTest(method=method):
                status, value, backend = self.request(method=method)
                self.assertEqual(status, 405)
                self.assertEqual(backend.calls, [])
                if method != "HEAD":
                    self.assertEqual(value, {"error": "method_not_allowed"})

    def test_all_non_exact_paths_are_blocked_without_backend_calls(self):
        paths = ["/api/config", "/api/services", "/api/services/light/turn_on",
                 "/api/states/sensor.other", "/api/states/" + TEMPERATURE + "/",
                 "/api/states/", "/api/states?", "/api/states?token=" + QUERY_TOKEN,
                 "/api/states#fragment", "//api/states", "/api//states", "/api/%73tates",
                 "/api/states/sensor.xiaoxi_node01_%74emperature", "/api/states/../config",
                 "http://ha-backend:8123/api/states", "*", "/api/states\x00"]
        for path in paths:
            with self.subTest(path=path):
                status, value, backend = self.request(path=path)
                self.assertEqual(status, 404)
                self.assertEqual(value, {"error": "not_found"})
                self.assertEqual(backend.calls, [])

    def test_authentication_errors_never_call_backend(self):
        for token in [None, "wrong", QUERY_TOKEN + "x", "é" * 32, ""]:
            with self.subTest(token=token):
                status, value, backend = self.request(token=token)
                self.assertEqual(status, 401)
                self.assertEqual(value, {"error": "unauthorized"})
                self.assertEqual(backend.calls, [])
        for authorization in ["Basic " + QUERY_TOKEN, "bearer " + QUERY_TOKEN,
                              "Bearer  " + QUERY_TOKEN, "Bearer " + QUERY_TOKEN + " "]:
            raw = ("GET /api/states HTTP/1.1\r\nAuthorization: " + authorization
                   + "\r\n\r\n").encode()
            status, _, backend = self.request(raw=raw)
            self.assertEqual(status, 401)
            self.assertEqual(backend.calls, [])

    def test_duplicate_auth_and_request_bodies_blocked(self):
        for header in [b"Authorization: Bearer duplicate\r\n", b"Content-Length: 1\r\n",
                       b"Transfer-Encoding: chunked\r\n", b"Content-Length: xyz\r\n",
                       b"Content-Length: 0\r\nContent-Length: 0\r\n"]:
            with self.subTest(header=header):
                status, _, backend = self.request(extra_headers=header)
                self.assertIn(status, [400, 401])
                self.assertEqual(backend.calls, [])

    def test_constant_time_comparison_uses_bytes(self):
        with patch.object(gateway.hmac, "compare_digest", wraps=gateway.hmac.compare_digest) as compare:
            self.request()
        compare.assert_called_once_with(QUERY_TOKEN.encode("ascii"), QUERY_TOKEN.encode("ascii"))

    def test_startup_unknown_unavailable_do_not_invent_metadata(self):
        for state in ["unknown", "unavailable"]:
            with self.subTest(state=state):
                startup = {"entity_id": TEMPERATURE, "state": state,
                           "attributes": {"unit_of_measurement": "°C"}}
                status, value, _ = self.request(FakeBackend(startup), "/api/states/" + TEMPERATURE)
                self.assertEqual(status, 200)
                self.assertEqual(value["state"], state)
                for key in ["boot_id", "sequence", "simulated", "received_at"]:
                    self.assertIsNone(value["attributes"][key])

    def test_unavailable_retains_previous_metadata_not_current_value(self):
        previous = entity(state="unavailable")
        status, value, _ = self.request(FakeBackend(previous), "/api/states/" + TEMPERATURE)
        self.assertEqual(status, 200)
        self.assertEqual(value["state"], "unavailable")
        self.assertEqual(value["attributes"]["received_at"], previous["attributes"]["received_at"])
        self.assertFalse(value["attributes"]["simulated"])

    def test_unknown_can_retain_explicit_simulated_marker(self):
        status, value, _ = self.request(FakeBackend(entity(state="unknown", simulated=True)),
                                        "/api/states/" + TEMPERATURE)
        self.assertEqual(status, 200)
        self.assertTrue(value["attributes"]["simulated"])

    def test_numeric_state_requires_all_sampling_metadata(self):
        for key in ["boot_id", "sequence", "simulated", "received_at"]:
            for missing in [True, False]:
                sample = entity()
                if missing:
                    del sample["attributes"][key]
                else:
                    sample["attributes"][key] = None
                with self.subTest(key=key, missing=missing):
                    status, value, _ = self.request(FakeBackend(sample), "/api/states/" + TEMPERATURE)
                    self.assertEqual(status, 502)
                    self.assertEqual(value, {"error": "backend_unavailable"})

    def test_state_is_finite_numeric_or_exact_unavailable_unknown(self):
        for state in [SECRET, "nan", "NaN", "Infinity", "-Infinity", "1e9999", " 23 ",
                      "true", "None", "", 23.5, False, None, {}, "9" * 1000]:
            with self.subTest(state=state):
                status, value, _ = self.request(FakeBackend(entity(state=state)), "/api/states/" + TEMPERATURE)
                self.assertEqual(status, 502)
                self.assertEqual(value, {"error": "backend_unavailable"})

    def test_sequence_zero_is_valid_first_sample_for_get_and_list(self):
        samples = [entity(sequence=0, boot_id="node01-00000005"),
                   entity(HUMIDITY, "55", sequence=0, boot_id="node01-00000005")]
        for sample in samples:
            with self.subTest(entity_id=sample["entity_id"]):
                status, value, backend = self.request(FakeBackend(sample),
                                                       "/api/states/" + sample["entity_id"])
                self.assertEqual(status, 200)
                self.assertEqual(value["state"], sample["state"])
                self.assertEqual(value["attributes"]["sequence"], 0)
                self.assertEqual(len(backend.calls), 1)
        status, value, _ = self.request(FakeBackend(samples))
        self.assertEqual(status, 200)
        self.assertEqual([item["state"] for item in value], ["23.5", "55"])
        self.assertEqual([item["attributes"]["sequence"] for item in value], [0, 0])

    def test_sequence_zero_is_retained_for_unknown_and_unavailable(self):
        for state in ["unknown", "unavailable"]:
            with self.subTest(state=state):
                sample = entity(state=state, sequence=0, boot_id="node01-00000005")
                status, value, _ = self.request(FakeBackend(sample), "/api/states/" + TEMPERATURE)
                self.assertEqual(status, 200)
                self.assertEqual(value["state"], state)
                self.assertEqual(value["attributes"]["sequence"], 0)
                self.assertEqual(value["attributes"]["received_at"], sample["attributes"]["received_at"])

    def test_zero_boot_counter_is_rejected_even_with_unavailable_metadata(self):
        for state in ["23.5", "unknown", "unavailable"]:
            for path in ["/api/states/" + TEMPERATURE, "/api/states"]:
                with self.subTest(state=state, path=path):
                    sample = entity(state=state, boot_id="node01-00000000")
                    data = sample if path != "/api/states" else [sample, entity(HUMIDITY, "55")]
                    status, value, _ = self.request(FakeBackend(data), path)
                    self.assertEqual(status, 502)
                    self.assertEqual(value, {"error": "backend_unavailable"})

    def test_metadata_types_source_units_and_timestamp_are_validated(self):
        invalid = {"node_id": ["node02", SECRET, None], "unit_of_measurement": [SECRET, "K", None],
                   "boot_id": [SECRET + "/", "", "x" * 65, "boot-test_01", "node02-1234abcd", 1, True],
                   "sequence": [True, -1, 4294967296, 1.5, SECRET],
                   "simulated": [True, "false", 0, SECRET],
                   "received_at": [SECRET, "2026-06-02", "2026-06-02T10:20:30",
                                   "2026-99-02T10:20:30Z", "2026-06-02T10:20:30+08:00", 1]}
        for key, values in invalid.items():
            for invalid_value in values:
                with self.subTest(key=key, value=invalid_value):
                    status, value, _ = self.request(FakeBackend(entity(**{key: invalid_value})),
                                                    "/api/states/" + TEMPERATURE)
                    self.assertEqual(status, 502)
                    self.assertEqual(value, {"error": "backend_unavailable"})

    def test_unavailable_invalid_present_metadata_is_not_echoed(self):
        for attrs in [{"boot_id": SECRET + "/"}, {"received_at": SECRET},
                      {"simulated": "false"}, {"node_id": "node02"}]:
            status, _, _ = self.request(FakeBackend(entity(state="unavailable", **attrs)),
                                        "/api/states/" + TEMPERATURE)
            self.assertEqual(status, 502)

    def test_no_gateway_clock_fabrication_or_hard_source_age_claim(self):
        sample = entity(received_at="2000-01-01T00:00:00Z")
        status, value, _ = self.request(FakeBackend(sample), "/api/states/" + TEMPERATURE)
        self.assertEqual(status, 200)
        self.assertEqual(value["attributes"]["received_at"], "2000-01-01T00:00:00Z")
        self.assertNotIn("fresh", value)

    def test_bad_single_shapes_wrong_ids_and_attributes_fixed_errors(self):
        bad = [[], {}, {"entity_id": "sensor.other", "state": "1", "attributes": {}},
               {"entity_id": TEMPERATURE, "state": "1"},
               {"entity_id": TEMPERATURE, "state": "1", "attributes": []}]
        for value in bad:
            status, body, _ = self.request(FakeBackend(value), "/api/states/" + TEMPERATURE)
            self.assertEqual(status, 502)
            self.assertEqual(body, {"error": "backend_unavailable"})

    def test_list_validates_each_fixed_entity_shape_and_presence(self):
        paths = ["/api/states/" + TEMPERATURE, "/api/states/" + HUMIDITY]
        bad = [None, {}, [], [entity()], [entity(), entity()],
               {"entity_id": "not an id", "state": "on", "attributes": {}},
               {"entity_id": "light.other", "attributes": {}},
               {"entity_id": "light.other", "state": "on", "attributes": []},
               entity(state=SECRET), entity(simulated=True), RuntimeError(SECRET)]
        for index, path in enumerate(paths):
            for invalid in bad:
                with self.subTest(path=path, invalid=invalid):
                    routes = dict(zip(paths, [entity(), entity(HUMIDITY, "55")]))
                    routes[path] = invalid
                    status, value, backend = self.request(FakeBackend(routes=routes))
                    self.assertEqual(status, 502)
                    self.assertEqual(value, {"error": "backend_unavailable"})
                    self.assertEqual(backend.calls, paths[:index + 1])
            routes = {paths[1 - index]: entity(HUMIDITY, "55") if index == 0 else entity()}
            status, value, backend = self.request(FakeBackend(routes=routes))
            self.assertEqual((status, value), (502, {"error": "backend_unavailable"}))
            self.assertEqual(backend.calls, paths[:index + 1])

    def test_list_rejects_swapped_endpoint_identities(self):
        paths = ["/api/states/" + TEMPERATURE, "/api/states/" + HUMIDITY]
        for index, path in enumerate(paths):
            with self.subTest(path=path):
                routes = dict(zip(paths, [entity(), entity(HUMIDITY, "55")]))
                routes[path] = entity(HUMIDITY, "55") if index == 0 else entity()
                status, value, backend = self.request(FakeBackend(routes=routes))
                self.assertEqual((status, value), (502, {"error": "backend_unavailable"}))
                self.assertEqual(backend.calls, paths[:index + 1])

    def test_backend_failures_are_fixed_and_do_not_log(self):
        failures = [TimeoutError(SECRET), URLError(SECRET), OSError(SECRET),
                    HTTPError("http://secret/", 401, SECRET, {"Secret": BACKEND_TOKEN}, None),
                    RecursionError(SECRET), ValueError(SECRET), RuntimeError(SECRET)]
        for error in failures:
            status, value, backend = self.request(FakeBackend(error=error))
            self.assertEqual(status, 502)
            self.assertEqual(value, {"error": "backend_unavailable"})
            self.assertEqual(len(backend.calls), 1)

    def test_http_error_body_closed_without_late_raw_warning(self):
        error = HTTPError("http://secret/", 401, SECRET, {}, io.BytesIO(SECRET.encode()))
        with patch.object(error, "close", wraps=error.close) as close:
            status, value, _ = self.request(FakeBackend(error=error))
            self.assertEqual(status, 502)
            self.assertEqual(value, {"error": "backend_unavailable"})
            close.assert_called_once()

    def test_server_errors_do_not_log_raw_tracebacks(self):
        server = object.__new__(gateway.GatewayHTTPServer)
        with patch("sys.stderr", new_callable=io.StringIO) as stderr:
            server.handle_error(None, ("offline", 0))
        self.assertEqual(stderr.getvalue(), "")
        self.assertLessEqual(server.request_queue_size, 8)

    def test_malformed_request_fixed_error_no_store(self):
        for raw in [b"GET /api/states HTTP/not-a-version\r\n\r\n",
                    b"INVALID\r\n\r\n", b"POST /api/states\r\n\r\n"]:
            with self.subTest(raw=raw):
                status, value, backend = self.request(raw=raw)
                self.assertEqual(status, 400)
                self.assertEqual(value, {"error": "bad_request"})
                self.assertEqual(backend.calls, [])

    def test_verified_private_ids_still_only_node01_temperature_and_humidity(self):
        allowed = (TEMPERATURE + "_2", HUMIDITY + "_3")
        self.config = gateway.Config("http://ha-backend:8123/", BACKEND_TOKEN, QUERY_TOKEN, allowed)
        status, value, _ = self.request(FakeBackend([entity(allowed[0]), entity(allowed[1], "55")]))
        self.assertEqual(status, 200)
        self.assertEqual([item["entity_id"] for item in value], list(allowed))
        status, _, backend = self.request(path="/api/states/" + TEMPERATURE)
        self.assertEqual(status, 404)
        self.assertEqual(backend.calls, [])

    def test_optional_third_light_entity_projection_and_bounds(self):
        light_id = "sensor.xiaoxi_node01_light"
        allowed = (TEMPERATURE, HUMIDITY, light_id)
        self.config = gateway.Config("http://ha-backend:8123/", BACKEND_TOKEN, QUERY_TOKEN, allowed)
        light_item = entity(light_id, "0.245")
        light_item["attributes"].pop("unit_of_measurement", None)
        status, value, _ = self.request(FakeBackend([entity(), entity(HUMIDITY, "55"), light_item]))
        self.assertEqual(status, 200)
        self.assertEqual([item["entity_id"] for item in value], list(allowed))
        self.assertIsNone(value[2]["attributes"]["unit_of_measurement"])
        for bad_state in ["-0.001", "1.001"]:
            bad_light = copy.deepcopy(light_item)
            bad_light["state"] = bad_state
            status, _, _ = self.request(
                FakeBackend([entity(), entity(HUMIDITY, "55"), bad_light]),
                path="/api/states/" + light_id,
            )
            self.assertEqual(status, 502)

    def test_optional_fourth_node02_ir_event_entity_projection_and_bounds(self):
        light_id = "sensor.xiaoxi_node01_light"
        ir_id = "sensor.xiaoxi_node02_ir_event"
        allowed = (TEMPERATURE, HUMIDITY, light_id, ir_id)
        self.config = gateway.Config("http://ha-backend:8123/", BACKEND_TOKEN, QUERY_TOKEN, allowed)
        light_item = entity(light_id, "0.245")
        light_item["attributes"].pop("unit_of_measurement", None)
        ir_item = {
            "entity_id": ir_id,
            "state": "ir_remote_captured",
            "attributes": {
                "node_id": "node02",
                "boot_id": "node02-00000008",
                "sequence": 35,
                "simulated": False,
                "received_at": "2026-11-04T09:10:38.751218+00:00",
                "event_type": "ir_remote_captured",
                "detail": "rx_ok proto=KELVINATOR bits=128 rawlen=280 ac=power=on,mode=0,temp_c=25,fan=3 loopback=false",
            },
        }
        status, value, _ = self.request(
            FakeBackend([entity(), entity(HUMIDITY, "55"), light_item, ir_item]),
            path="/api/states/" + ir_id,
        )
        self.assertEqual(status, 200)
        self.assertEqual(value["entity_id"], ir_id)
        self.assertEqual(value["attributes"]["node_id"], "node02")
        self.assertEqual(value["attributes"]["event_type"], "ir_remote_captured")
        bad_ir = copy.deepcopy(ir_item)
        bad_ir["attributes"]["boot_id"] = "node01-00000008"
        status, _, _ = self.request(
            FakeBackend([entity(), entity(HUMIDITY, "55"), light_item, bad_ir]),
            path="/api/states/" + ir_id,
        )
        self.assertEqual(status, 502)

    def test_unavailable_events_drop_retained_content_in_single_reads(self):
        for event_id, node, previous in [
            ("sensor.xiaoxi_node02_ir_event", "node02", "ir_remote_captured"),
            ("sensor.xiaoxi_node01_button_event", "node01", "button_single_press"),
        ]:
            self.config = gateway.Config("http://ha-backend:8123", BACKEND_TOKEN, QUERY_TOKEN,
                                         (TEMPERATURE, HUMIDITY, event_id))
            for state in ("unknown", "unavailable"):
                with self.subTest(entity=event_id, state=state):
                    item = entity(event_id, state, unit_of_measurement=None, node_id=node,
                                  boot_id=node + "-00000008", event_type=previous,
                                  detail="STALE_EVENT_CONTENT_MUST_NOT_ESCAPE")
                    status, value, backend = self.request(FakeBackend(item), "/api/states/" + event_id)
                    self.assertEqual(status, 200)
                    self.assertEqual(value["state"], state)
                    self.assertIsNone(value["attributes"]["event_type"])
                    self.assertIsNone(value["attributes"]["detail"])
                    self.assertNotIn("STALE_EVENT_CONTENT", json.dumps(value))
                    self.assertEqual(backend.calls, ["/api/states/" + event_id])

    def test_five_entity_list_survives_unavailable_events_without_stale_content(self):
        light_id = "sensor.xiaoxi_node01_light"
        ir_id = "sensor.xiaoxi_node02_ir_event"
        button_id = "sensor.xiaoxi_node01_button_event"
        allowed = (TEMPERATURE, HUMIDITY, light_id, ir_id, button_id)
        self.config = gateway.Config("http://ha-backend:8123", BACKEND_TOKEN, QUERY_TOKEN, allowed)
        for state in ("unknown", "unavailable"):
            with self.subTest(state=state):
                rows = [entity(), entity(HUMIDITY, "55"),
                        entity(light_id, "0.25", unit_of_measurement=None)]
                for event_id, node, previous in [(ir_id, "node02", "ir_remote_captured"),
                                                  (button_id, "node01", "button_single_press")]:
                    rows.append(entity(event_id, state, unit_of_measurement=None, node_id=node,
                                       boot_id=node + "-00000008", event_type=previous,
                                       detail="STALE_EVENT_CONTENT_MUST_NOT_ESCAPE"))
                status, value, backend = self.request(FakeBackend(rows))
                self.assertEqual(status, 200)
                self.assertEqual([item["entity_id"] for item in value], list(allowed))
                self.assertEqual([item["state"] for item in value[:3]], ["23.5", "55", "0.25"])
                self.assertEqual([item["state"] for item in value[3:]], [state, state])
                self.assertTrue(all(item["attributes"]["detail"] is None for item in value[3:]))
                self.assertTrue(all(item["attributes"]["event_type"] is None for item in value[3:]))
                self.assertNotIn("STALE_EVENT_CONTENT", json.dumps(value))
                self.assertEqual(backend.calls, ["/api/states/" + item for item in allowed])

    def test_config_rejects_allowlist_expansion_and_unsafe_targets(self):
        for allowed in [(TEMPERATURE,), (TEMPERATURE, HUMIDITY, "sensor.other"),
                        (TEMPERATURE, TEMPERATURE), (TEMPERATURE, "sensor.xiaoxi_node02_humidity"),
                        (TEMPERATURE, "switch.xiaoxi_node01_humidity"),
                        (TEMPERATURE, "sensor.xiaoxi_node01_secret"),
                        (TEMPERATURE, HUMIDITY + "/x"), TEMPERATURE]:
            with self.assertRaises(ValueError):
                gateway.Config("http://ha-backend:8123", BACKEND_TOKEN, QUERY_TOKEN, allowed)
        for url in ["file:///secret", "http://user:pass@host", "http://host/api", "http://host?x=1",
                    "http://host/#frag", "http://host\r\nSecret: value", "http://host:99999", "http://"]:
            with self.assertRaises(ValueError):
                gateway.Config(url, BACKEND_TOKEN, QUERY_TOKEN)
        for token in ["", "short", "é" * 32, "q" * 200, "q" * 32 + "\n"]:
            with self.assertRaises(ValueError):
                gateway.Config("http://ha-backend:8123", BACKEND_TOKEN, token)
        with self.assertRaises(ValueError):
            gateway.Config("http://ha-backend:8123", "unsafe\nheader", QUERY_TOKEN)
        with self.assertRaises(ValueError):
            gateway.Config("http://ha-backend:8123", QUERY_TOKEN, QUERY_TOKEN)
        self.assertNotIn(BACKEND_TOKEN, repr(self.config))
        self.assertNotIn(QUERY_TOKEN, repr(self.config))

    def test_query_token_generation_is_random_urlsafe(self):
        first, second = gateway.generate_query_token(), gateway.generate_query_token()
        self.assertNotEqual(first, second)
        self.assertGreaterEqual(len(first), 32)
        self.assertRegex(first, r"^[A-Za-z0-9_-]+$")

    def test_cli_binds_fixed_address_single_server_without_starting_it(self):
        server = Mock()
        server.__enter__ = Mock(return_value=server)
        server.__exit__ = Mock(return_value=False)
        with patch.object(gateway, "load_config", return_value=self.config) as load, \
                patch.object(gateway, "GatewayHTTPServer", return_value=server) as constructor:
            gateway.main(["--config", "/offline/private-config.json"])
        load.assert_called_once_with("/offline/private-config.json")
        constructor.assert_called_once_with(("0.0.0.0", 8080), gateway.ReadGatewayHandler)
        self.assertEqual(server.config, self.config)
        server.serve_forever.assert_called_once()


class BackendReaderTests(unittest.TestCase):
    def setUp(self):
        self.config = gateway.Config("http://ha-backend:8123", BACKEND_TOKEN, QUERY_TOKEN)

    def read(self, body, status=200, headers=None):
        response = FakeResponse(body, status, headers)
        opener = Mock()
        opener.open.return_value = response
        reader = gateway.BackendReader(self.config, opener=opener)
        value = reader("/api/states/" + TEMPERATURE)
        return value, response, opener

    def test_production_request_get_fixed_target_private_bearer_timeout(self):
        value, response, opener = self.read(json.dumps(entity()).encode())
        self.assertEqual(value["entity_id"], TEMPERATURE)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.full_url, "http://ha-backend:8123/api/states/" + TEMPERATURE)
        self.assertEqual(request.get_header("Authorization"), "Bearer " + BACKEND_TOKEN)
        self.assertEqual(opener.open.call_args.kwargs, {"timeout": 5})
        self.assertTrue(response.closed)
        self.assertTrue(all(0 < size <= gateway.MAX_RESPONSE_BYTES + 1 for size in response.read_sizes))
        self.assertLessEqual(gateway.MAX_RESPONSE_BYTES, 256 * 1024)

    def test_http_error_closes_response_and_raises_only_fixed_error(self):
        error = HTTPError("http://secret/", 302, SECRET, {}, io.BytesIO(SECRET.encode()))
        opener = Mock()
        opener.open.side_effect = error
        reader = gateway.BackendReader(self.config, opener=opener)
        with patch.object(error, "close", wraps=error.close) as close:
            with self.assertRaisesRegex(ValueError, "^invalid_backend_response$"):
                reader("/api/states/" + TEMPERATURE)
            close.assert_called_once()

    def test_reader_blocks_non_allowlisted_targets_before_opener(self):
        opener = Mock()
        opener.open.return_value = FakeResponse(json.dumps(entity()).encode())
        reader = gateway.BackendReader(self.config, opener=opener)
        for path in ["/api/states", "http://other/api/states", "/api/config", "/api/states?x=1",
                     "//api/states", "/api/states/", "/api/states/sensor.other", "/api/%73tates",
                     "/api/states/" + TEMPERATURE + "?x=1",
                     "/api/states/" + TEMPERATURE + "/"]:
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "^invalid_backend_path$"):
                reader(path)
        opener.open.assert_not_called()

    def test_redirects_and_non_200_statuses_are_rejected(self):
        for status in [201, 204, 301, 302, 303, 307, 308, 401, 500]:
            with self.assertRaises(ValueError):
                self.read(b"{}", status, {"Location": "http://secret"})
        handler = gateway.NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, SECRET, {}, "http://secret"))

    def test_default_opener_has_no_redirect_and_no_environment_proxy(self):
        with patch.object(gateway, "build_opener") as build:
            gateway.BackendReader(self.config)
        handlers = build.call_args.args
        self.assertTrue(any(isinstance(item, gateway.NoRedirect) for item in handlers))
        self.assertTrue(any(isinstance(item, gateway.ProxyHandler) and item.proxies == {} for item in handlers))

    def test_invalid_json_utf8_duplicates_nonfinite_and_deep_objects(self):
        bodies = [b"not-json", b"\xff", b'{"a": NaN}', b'{"a": Infinity}', b'{"a": 1e999}',
                  b'{"a":1,"a":2}', b'{"attrs":{"x":1,"x":2}}', b"[" * 1500 + b"]" * 1500,
                  b'{"a":"\\ud800"}', b'{"x":"' + b"a" * gateway.MAX_RESPONSE_BYTES + b'"}']
        for body in bodies:
            with self.subTest(length=len(body)):
                with self.assertRaises(ValueError):
                    self.read(body)

    def test_response_size_length_and_encoding_bounds(self):
        for body, headers in [(b"{}", {"Content-Length": str(gateway.MAX_RESPONSE_BYTES + 1)}),
                              (b"{}", {"Content-Length": "3"}),
                              (b"{}", {"Content-Length": "-1"}),
                              (b"{}", {"Content-Length": SECRET}),
                              (b"{}", {"Content-Encoding": "gzip"})]:
            with self.assertRaises(ValueError):
                self.read(body, headers=headers)

    def test_import_is_offline_and_does_not_read_configuration(self):
        spec = importlib.util.spec_from_file_location("offline_import_probe", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            with patch.object(socket, "socket", side_effect=AssertionError("network")), \
                    patch.object(os, "getenv", side_effect=AssertionError("environment")), \
                    patch.object(os, "open", side_effect=AssertionError("config read")), \
                    patch("builtins.open", side_effect=AssertionError("config read")):
                spec.loader.exec_module(module)
        finally:
            sys.modules.pop(spec.name, None)


class ConfigFileTests(unittest.TestCase):
    """Mock file descriptors only: never create or inspect actual private config."""
    def metadata(self, mode=0o100600, uid=None, size=100):
        return SimpleNamespace(st_mode=mode, st_uid=os.getuid() if uid is None else uid,
                               st_size=size, st_ino=42, st_dev=1)

    def load(self, body, metadata=None):
        metadata = metadata or self.metadata(size=len(body))
        with patch.object(gateway.os, "lstat", return_value=metadata), \
                patch.object(gateway.os, "open", return_value=17) as opened, \
                patch.object(gateway.os, "fstat", return_value=metadata), \
                patch.object(gateway.os, "read", side_effect=[body, b""]) as read, \
                patch.object(gateway.os, "close") as close:
            config = gateway.load_config("/offline/private-config.json")
        close.assert_called_once_with(17)
        self.assertTrue(opened.call_args.args[1] & os.O_NOFOLLOW)
        self.assertTrue(all(0 < call.args[1] <= gateway.MAX_CONFIG_BYTES + 1 for call in read.call_args_list))
        return config

    def body(self, **overrides):
        value = {"backend_url": "http://ha-backend:8123", "backend_token": BACKEND_TOKEN,
                 "query_token": QUERY_TOKEN}
        value.update(overrides)
        return json.dumps(value).encode()

    def test_private_regular_0600_current_owner_config(self):
        config = self.load(self.body())
        self.assertEqual(config.allowed_entities, (TEMPERATURE, HUMIDITY))
        self.assertEqual(config.backend_token, BACKEND_TOKEN)

    def test_rejects_symlink_nonregular_wrong_owner_mode_size(self):
        for metadata in [self.metadata(mode=0o120600), self.metadata(mode=0o040600),
                         self.metadata(mode=0o100640), self.metadata(mode=0o100400),
                         self.metadata(uid=os.getuid() + 1),
                         self.metadata(size=gateway.MAX_CONFIG_BYTES + 1)]:
            with patch.object(gateway.os, "lstat", return_value=metadata), \
                    patch.object(gateway.os, "open") as opened:
                with self.assertRaises(ValueError):
                    gateway.load_config("/offline/config")
                opened.assert_not_called()

    def test_rechecks_descriptor_against_symlink_swap_and_file_change(self):
        before = self.metadata()
        after = self.metadata()
        after.st_ino = 43
        with patch.object(gateway.os, "lstat", return_value=before), \
                patch.object(gateway.os, "open", return_value=17), \
                patch.object(gateway.os, "fstat", return_value=after), \
                patch.object(gateway.os, "read") as read, \
                patch.object(gateway.os, "close") as close:
            with self.assertRaises(ValueError):
                gateway.load_config("/offline/config")
            read.assert_not_called()
            close.assert_called_once_with(17)

    def test_bad_config_json_unknown_keys_missing_fields_fixed_error(self):
        bad = [b"[]", b"{}", b"\xff", b'{"backend_url":"a","backend_url":"b"}',
               self.body(extra=SECRET), self.body(query_token="short"),
               self.body(allowed_entities=[TEMPERATURE, "sensor.other"])]
        for body in bad:
            with self.assertRaisesRegex(ValueError, "^invalid_private_config$"):
                self.load(body)


if __name__ == "__main__":
    unittest.main()
