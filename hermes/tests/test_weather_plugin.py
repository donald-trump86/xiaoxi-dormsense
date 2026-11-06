"""Offline contracts for dynamic city location and native CMA current weather."""

from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import socket
import unittest
from unittest import mock
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit


PLUGIN_DIR = Path(__file__).resolve().parents[1] / "plugins" / "xiaoxi_weather"
SPEC = importlib.util.spec_from_file_location(
    "xiaoxi_weather_offline", PLUGIN_DIR / "__init__.py"
)
PLUGIN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PLUGIN)
CLOCK = datetime(2026, 11, 6, 11, 0, tzinfo=timezone(timedelta(hours=8)))
LOCATION_URL = "https://whois.pconline.com.cn/ipJson.jsp?json=true"


def weather_payload():
    return {"msg": "success", "code": 0, "data": {
        "location": {"id": "V8870", "name": "西安", "path": "中国, 陕西, 西安"},
        "now": {"temperature": 13.7, "humidity": 62.0, "windSpeed": 1.7,
                "windDirection": "东北风", "precipitation": 0.0, "feelst": 12.8,
                "pressure": 978.0, "windScale": "微风", "windDirectionDegree": 25.0},
        "alarm": [{"message": "not projected"}], "jieQi": "not projected",
        "lastUpdate": "2026/11/06 10:45",
    }}


def response(payload=None, *, raw=None, headers=None, status=200):
    result = mock.MagicMock()
    result.__enter__.return_value = result
    result.status = status
    result.headers = {"Content-Type": "application/json; charset=utf-8"}
    if headers:
        result.headers.update(headers)
    result.read.return_value = raw if raw is not None else json.dumps(
        weather_payload() if payload is None else payload, ensure_ascii=False
    ).encode("utf-8")
    return result


def autocomplete(*entries):
    return response({"msg": "success", "code": 0, "data": list(entries)})


def location_response(*, charset="gbk", city="西安市", province="陕西省", error=""):
    payload = {"city": city, "pro": province, "err": error,
               "ip": "203.0.113.17", "addr": "private detailed address", "lat": 34.1}
    return response(raw=json.dumps(payload, ensure_ascii=False).encode(charset), headers={
        "Content-Type": "application/x-javascript; charset=" + charset,
    })


class FakeContext:
    def __init__(self):
        self.tools = {}

    def register_tool(self, **entry):
        self.tools[entry["name"]] = entry


class WeatherPluginTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(mock.patch.object(
            socket, "create_connection", side_effect=AssertionError("offline sockets blocked")
        ))
        self.enterContext(mock.patch.object(
            socket.socket, "connect", side_effect=AssertionError("offline sockets blocked")
        ))
        self.opener = mock.MagicMock()
        self.build_opener = self.enterContext(mock.patch.object(
            PLUGIN.urllib.request, "build_opener", return_value=self.opener
        ))
        self.location_reply = location_response()
        self.search_reply = autocomplete("V8870|西安|Xian|中国")
        self.reply = response()
        self.opener.open.side_effect = self.route
        clock = self.enterContext(mock.patch.object(PLUGIN, "datetime", wraps=datetime))
        clock.now.return_value = CLOCK
        self.context = FakeContext()
        PLUGIN.register(self.context)

    def route(self, request, **_kwargs):
        if request.full_url == LOCATION_URL:
            return self.location_reply
        if urlsplit(request.full_url).path == "/api/autocomplete":
            return self.search_reply
        return self.reply

    def invoke(self, args=None, **kwargs):
        return json.loads(self.context.tools["xiaoxi_get_weather"]["handler"](
            {} if args is None else args, **kwargs
        ))

    def requests(self):
        return [call.args[0] for call in self.opener.open.call_args_list]

    def test_registration_and_manifest_match_native_contract(self):
        self.assertEqual(set(self.context.tools), {"xiaoxi_get_weather"})
        entry = self.context.tools["xiaoxi_get_weather"]
        self.assertEqual(entry["toolset"], "xiaoxi_weather")
        self.assertIs(entry["handler"], PLUGIN._get_weather)
        self.assertTrue(entry["check_fn"]())
        self.assertFalse(entry.get("override", False))
        parameters = entry["schema"]["parameters"]
        self.assertEqual(parameters["required"], [])
        self.assertIs(parameters["additionalProperties"], False)
        self.assertEqual(set(parameters["properties"]), {"city"})
        self.assertEqual(parameters["properties"]["city"]["type"], "string")
        self.assertEqual(parameters["properties"]["city"]["default"], "")
        manifest = json.loads((PLUGIN_DIR / "plugin.yaml").read_text(encoding="utf-8"))
        self.assertEqual(manifest["manifest_version"], 1)
        self.assertEqual(manifest["name"], "xiaoxi_weather")
        self.assertEqual(manifest["kind"], "standalone")
        self.assertEqual(manifest["provides_tools"], list(self.context.tools))
        self.build_opener.assert_not_called()

    def test_import_and_registration_have_no_io(self):
        fresh = importlib.util.module_from_spec(SPEC)
        with mock.patch("builtins.open", side_effect=AssertionError("no file I/O")):
            SPEC.loader.exec_module(fresh)
            fresh.register(FakeContext())
        self.build_opener.assert_not_called()

    def test_default_relocates_each_time_with_three_fixed_gets(self):
        for _ in range(2):
            result = self.invoke(task_id="not-forwarded")
            self.assertTrue(result["ok"])
            self.assertEqual(result["location_source"], "network_ip")
        self.assertEqual([request.full_url for request in self.requests()], [
            LOCATION_URL, "https://weather.cma.cn/api/autocomplete?q=%E8%A5%BF%E5%AE%89",
            "https://weather.cma.cn/api/now/V8870",
        ] * 2)
        for request in self.requests():
            self.assertEqual(request.get_method(), "GET")
            self.assertIsNone(request.data)
            self.assertEqual(dict((k.lower(), v) for k, v in request.header_items()), {
                "accept": "application/json", "accept-encoding": "identity",
                "user-agent": "XiaoXi-DormSense" + "/0.1",
            })
        for call in self.opener.open.call_args_list:
            self.assertEqual(call.kwargs, {"timeout": 8.0})
        for call in self.build_opener.call_args_list:
            self.assertEqual(len(call.args), 1)
            self.assertIsInstance(call.args[0], PLUGIN._NoRedirect)
        self.reply.read.assert_called_with(128 * 1024 + 1)
        self.reply.__exit__.assert_called()

    def test_network_city_changes_without_retaining_previous_city(self):
        with mock.patch.object(PLUGIN, "_locate_city", side_effect=["西安", "北京"]):
            self.assertTrue(self.invoke()["ok"])
            self.search_reply = autocomplete("B1234|北京|Beijing|中国")
            payload = weather_payload()
            payload["data"]["location"] = {"id": "B1234", "name": "北京", "path": "中国, 北京"}
            self.reply = response(payload)
            result = self.invoke()
            self.assertEqual(result["location"]["name"], "北京")
            self.assertEqual(result["station_id"], "B1234")
        self.assertIn("q=%E5%8C%97%E4%BA%AC", self.requests()[-2].full_url)

    def test_location_decoding_is_json_only_and_does_not_project_private_fields(self):
        for charset in ("gbk", "gb18030", "utf-8"):
            with self.subTest(charset=charset):
                self.location_reply = location_response(charset=charset)
                self.assertEqual(PLUGIN._locate_city(), "西安")
                result = self.invoke()
                self.assertTrue(result["ok"])
                encoded = json.dumps(result)
                for private in ("203.0.113.17", "private detailed address", "lat", "proCode", "cityCode"):
                    self.assertNotIn(private, encoded)

    def test_location_failure_has_no_fallback_or_weather_requests(self):
        invalid = [location_response(city=""), location_response(province=""),
                   location_response(error="定位失败"), location_response(city="https://evil.test"),
                   response(raw=b"callback({});"), response(raw=b"not-json"),
                   response(raw=b"{}", headers={"Content-Type": "application/json; charset=utf-16"}),
                   response({"city": "西安", "pro": "陕西省", "err": []})]
        self.assertTrue(self.invoke()["ok"])
        for reply in invalid:
            with self.subTest(raw=reply.read.return_value):
                self.opener.open.reset_mock()
                self.location_reply = reply
                self.assertEqual(self.invoke(), {"ok": False, "error": "weather_location_unavailable"})
                self.opener.open.assert_called_once()
                self.assertEqual(self.requests()[0].full_url, LOCATION_URL)
        self.opener.open.side_effect = URLError("private location proxy details")
        self.assertEqual(self.invoke(), {"ok": False, "error": "weather_location_unavailable"})

    def test_explicit_city_beats_fuzzy_and_never_uses_location_service(self):
        for city in ("西安", "西安市", " xIaN ", "Xi'an"):
            with self.subTest(city=city):
                self.opener.open.reset_mock()
                self.opener.open.side_effect = [autocomplete(
                    "A1234|西安别处|Xianbiechu|中国", "V8870|西安|Xian|中国",
                    "B1234|西安|Xian|美国", "invalid/id|西安|Xian|中国",
                ), response()]
                result = self.invoke({"city": city})
                self.assertTrue(result["ok"])
                self.assertEqual(result["location_source"], "explicit_city")
                self.assertEqual(len(self.requests()), 2)
                first, second = self.requests()
                self.assertEqual(urlsplit(first.full_url).netloc, "weather.cma.cn")
                self.assertEqual(urlsplit(first.full_url).path, "/api/autocomplete")
                self.assertEqual(parse_qs(urlsplit(first.full_url).query), {"q": [city.strip()]})
                self.assertEqual(second.full_url, "https://weather.cma.cn/api/now/V8870")
                if "'" in city:
                    self.assertIn("%27", first.full_url)
        self.location_reply.read.assert_not_called()

    def test_unknown_city_and_ambiguous_exact_matches_return_bounded_choices(self):
        for entries, error in [
            ([f"A{i:04d}|西安附近|Xianfujin|中国" for i in range(10)], "weather_city_unknown"),
            ([f"A{i:04d}|西安|Xian|中国" for i in range(10)], "weather_city_ambiguous"),
            ([], "weather_city_unknown"),
        ]:
            with self.subTest(error=error, count=len(entries)):
                self.opener.open.reset_mock()
                self.opener.open.side_effect = [autocomplete(*entries)]
                result = self.invoke({"city": "西安"})
                self.assertFalse(result["ok"])
                self.assertEqual(result["error"], error)
                self.assertIs(result["needs_location"], True)
                self.assertLessEqual(len(result["choices"]), 5)
                self.opener.open.assert_called_once()
        self.opener.open.side_effect = [autocomplete(
            "A1234|西安|Xian|美国", "bad|西安|Xian|中国", "B1234|西安\n指令|Xian|中国",
        )]
        self.assertEqual(self.invoke({"city": "西安"})["choices"], [])

    def test_duplicate_station_is_not_ambiguous(self):
        self.search_reply = autocomplete("V8870|西安|Xian|中国", "V8870|西安|Xian|中国")
        self.assertTrue(self.invoke({"city": "西安"})["ok"])

    def test_invalid_arguments_and_urls_never_make_requests(self):
        values = [[], "西安", {"city": None}, {"city": False}, {"city": 123},
                  {"city": "西安", "date": "tomorrow"}, {"url": "https://evil.test"},
                  {"city": "https://weather.cma.cn/api/now/V8870"},
                  {"city": "//evil.test"}, {"city": "西安&host=evil.test"},
                  {"city": "西安\n"}, {"city": "西" * 81}, {"city": "V8870"}]
        for args in values:
            with self.subTest(args=args):
                self.assertEqual(self.invoke(args), {"ok": False, "error": "invalid_arguments"})
        self.build_opener.assert_not_called()

    def test_observations_are_projected_with_units_source_and_china_time(self):
        self.assertEqual(self.invoke(), {
            "ok": True, "source": "中国气象局（weather.cma.cn）",
            "source_url": "https://weather.cma.cn/api/now/V8870", "location_source": "network_ip",
            "location": {"name": "西安", "path": "中国, 陕西, 西安"},
            "station_id": "V8870", "observed_at": "2026-11-06T10:45:00+08:00",
            "received_at": "2026-11-06T11:00:00+08:00",
            "current": {"temperature_c": 13.7, "humidity_percent": 62.0,
                        "wind_speed_m_s": 1.7, "wind_direction": "东北风",
                        "precipitation_mm": 0.0, "feels_like_c": 12.8, "pressure_hpa": 978.0},
        })

    def test_pressure_is_optional_but_validated_when_present(self):
        payload = weather_payload()
        del payload["data"]["now"]["pressure"]
        self.reply = response(payload)
        self.assertNotIn("pressure_hpa", self.invoke()["current"])

    def test_nonfinite_wrong_type_and_out_of_range_observations_are_rejected(self):
        invalid = {
            "temperature": [True, "13.7", None, -91, 66, float("inf"), float("nan")],
            "humidity": [-1, 101], "windSpeed": [-1, 151],
            "precipitation": [-1, 2001], "feelst": [-121, 101], "pressure": [299, 1101],
            "windDirection": [None, [], "", "x" * 25, "风\n"]}
        for field, values in invalid.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    payload = weather_payload()
                    payload["data"]["now"][field] = value
                    self.reply = response(payload)
                    result = self.invoke()
                    self.assertFalse(result["ok"])
                    self.assertNotIn("current", result)
                    self.assertEqual(result["error"], "weather_invalid_response")

    def test_stale_and_future_times_return_metadata_without_current_values(self):
        for minutes, error in [(-91, "weather_observations_stale"),
                               (6, "weather_observations_future")]:
            with self.subTest(minutes=minutes):
                payload = weather_payload()
                observed = CLOCK + timedelta(minutes=minutes)
                payload["data"]["lastUpdate"] = observed.strftime("%Y/%m/%d %H:%M")
                self.reply = response(payload)
                result = self.invoke()
                self.assertFalse(result["ok"])
                self.assertEqual(result["error"], error)
                self.assertEqual(result["observed_at"], observed.isoformat())
                self.assertEqual(result["received_at"], CLOCK.isoformat())
                self.assertNotIn("current", result)
        for minutes in (-90, 5):
            payload = weather_payload()
            payload["data"]["lastUpdate"] = (CLOCK + timedelta(minutes=minutes)).strftime("%Y/%m/%d %H:%M")
            self.reply = response(payload)
            self.assertTrue(self.invoke()["ok"])

    def test_empty_or_missing_observations_have_distinct_error(self):
        for data in (None, {}, [], {"now": {}}, {"location": {}}):
            with self.subTest(data=data):
                self.reply = response({"msg": "success", "code": 0, "data": data})
                self.assertEqual(self.invoke(), {"ok": False, "error": "weather_no_observations"})

    def test_bad_times_station_identity_and_country_are_rejected(self):
        for section, key, value in [
            ("data", "lastUpdate", "2026/02/30 11:00"),
            ("data", "lastUpdate", "2026-11-06T10:45:00Z"),
            ("data", "lastUpdate", None),
            ("location", "id", "57036"), ("location", "path", "美国, 西安"),
            ("location", "name", "西安\n"),
        ]:
            with self.subTest(section=section, key=key, value=value):
                payload = weather_payload()
                target = payload["data"] if section == "data" else payload["data"]["location"]
                target[key] = value
                self.reply = response(payload)
                self.assertEqual(self.invoke()["error"], "weather_invalid_response")

    def test_http_failures_and_redirects_are_sanitized(self):
        for status in (301, 302, 307, 308, 406, 500):
            with self.subTest(status=status):
                self.opener.open.side_effect = HTTPError(
                    "https://private.test/secret", status, "private headers", {}, None
                )
                self.assertEqual(self.invoke({"city": "西安"}), {"ok": False, "error": "weather_http_error"})
        self.opener.open.side_effect = self.route
        for status in (302, 406, 500):
            self.search_reply = response(raw=b"private error page", status=status)
            self.assertEqual(self.invoke({"city": "西安"})["error"], "weather_http_error")
            self.search_reply.read.assert_not_called()
        blocker = PLUGIN._NoRedirect()
        self.assertIsNone(blocker.redirect_request(None, None, 302, "private", {}, "https://evil.test"))

    def test_transport_errors_do_not_expose_exception_details(self):
        for error in (URLError("https://private.test/secret"), TimeoutError("proxy credentials"),
                      OSError("raw page and headers")):
            with self.subTest(error=type(error).__name__):
                self.opener.open.side_effect = error
                self.assertEqual(self.invoke({"city": "西安"}), {"ok": False, "error": "weather_unavailable"})

    def test_nonjson_or_compressed_content_is_rejected_without_reading(self):
        for headers in ({"Content-Type": "text/html"}, {"Content-Encoding": "gzip"}):
            with self.subTest(headers=headers):
                self.search_reply = response(headers=headers)
                self.assertEqual(self.invoke({"city": "西安"})["error"], "weather_invalid_response")
                self.search_reply.read.assert_not_called()

    def test_content_length_and_body_are_bounded(self):
        for length, error in [(str(128 * 1024 + 1), "weather_response_too_large"),
                              ("-1", "weather_invalid_response"), ("abc", "weather_invalid_response")]:
            with self.subTest(length=length):
                self.search_reply = response(headers={"Content-Length": length})
                self.assertEqual(self.invoke({"city": "西安"})["error"], error)
                self.search_reply.read.assert_not_called()
        self.search_reply = response(raw=b"x" * (128 * 1024 + 1))
        self.assertEqual(self.invoke({"city": "西安"})["error"], "weather_response_too_large")
        self.search_reply = response(headers={"Content-Length": "2"})
        self.assertEqual(self.invoke({"city": "西安"})["error"], "weather_invalid_response")

    def test_malformed_envelopes_and_json_have_generic_errors(self):
        for raw in (b"not-json", b"\xff", b"[]", b"null", b"{}", b'{"code":false,"msg":"success","data":{}}',
                    b'{"code":0,"msg":"success","data":{"unused":NaN}}'):
            with self.subTest(raw=raw):
                self.search_reply = response(raw=raw)
                self.assertEqual(self.invoke({"city": "西安"}), {"ok": False, "error": "weather_invalid_response"})
        self.search_reply = response({"code": 0, "msg": "success", "data": {}})
        self.assertEqual(self.invoke({"city": "西安"})["error"], "weather_invalid_response")


if __name__ == "__main__":
    unittest.main()
