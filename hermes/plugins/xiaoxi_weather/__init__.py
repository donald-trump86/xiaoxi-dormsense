"""Native read-only current observations, with city-level network IP location."""

from datetime import datetime, timedelta, timezone
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request


_SOURCE = "https://weather.cma.cn"
_LOCATION_URL = "https://whois.pconline.com.cn/ipJson.jsp?json=true"
_RESPONSE_LIMIT = 128 * 1024
_CHINA = timezone(timedelta(hours=8))


class _WeatherError(Exception):
    """Only fixed public error codes may leave the request boundary."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, allow_nan=False)


def _reject_constant(value: str) -> None:
    raise ValueError("non-finite JSON constant")


def _read_json(url: str, *, location: bool = False):
    try:
        request = urllib.request.Request(url, headers={
            "Accept": "application/json", "Accept-Encoding": "identity",
            "User-Agent": "XiaoXi-DormSense" + "/0.1",
        })
        # Keep urllib's default proxy discovery and verified HTTPS handlers.
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=8.0) as response:
            if response.status != 200:
                raise _WeatherError("weather_http_error")
            content_type = response.headers.get("Content-Type", "")
            if not location and content_type.split(";", 1)[0].strip().lower() != "application/json":
                raise ValueError("unexpected media type")
            if response.headers.get("Content-Encoding", "identity").strip().lower() not in ("", "identity"):
                raise ValueError("unexpected encoding")
            charset = "utf-8"
            for parameter in content_type.split(";")[1:]:
                name, _, value = parameter.partition("=")
                if name.strip().lower() == "charset":
                    charset = value.strip().strip("\"'").lower()
            allowed = ("utf-8", "utf8", "gbk", "gb18030") if location else ("utf-8", "utf8")
            if charset not in allowed:
                raise ValueError("unexpected charset")
            length = response.headers.get("Content-Length")
            if length is not None:
                if not re.fullmatch(r"[0-9]+", length):
                    raise ValueError("invalid length")
                if int(length) > _RESPONSE_LIMIT:
                    raise _WeatherError("weather_response_too_large")
            body = response.read(_RESPONSE_LIMIT + 1)
            if len(body) > _RESPONSE_LIMIT:
                raise _WeatherError("weather_response_too_large")
            if length is not None and len(body) != int(length):
                raise ValueError("length mismatch")
            return json.loads(body.decode(charset), parse_constant=_reject_constant)
    except _WeatherError:
        raise
    except urllib.error.HTTPError as error:
        error.close()
        raise _WeatherError("weather_http_error") from None
    except (ValueError, UnicodeError, RecursionError):
        raise _WeatherError("weather_invalid_response") from None
    except Exception:
        # Never send exception URLs, proxy headers or raw pages to the model.
        raise _WeatherError("weather_unavailable") from None


def _cma(path: str):
    payload = _read_json(_SOURCE + path)
    if (not isinstance(payload, dict) or type(payload.get("code")) is not int
            or payload["code"] != 0 or payload.get("msg") != "success" or "data" not in payload):
        raise ValueError("invalid response envelope")
    return payload["data"]


def _valid_city(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z\u3400-\u9fff '\-·]{0,80}", value) is not None


def _locate_city() -> str:
    try:
        payload = _read_json(_LOCATION_URL, location=True)
        if not isinstance(payload, dict) or payload.get("err") != "":
            raise ValueError("location unavailable")
        for key in ("city", "pro"):
            if not isinstance(payload.get(key), str) or not re.fullmatch(r"[\u3400-\u9fff·]{1,40}", payload[key]):
                raise ValueError("invalid location")
        return payload["city"].removesuffix("市")
    except Exception:
        raise _WeatherError("weather_location_unavailable") from None


def _normalize(city: str) -> str:
    return city.strip().removesuffix("市").casefold().translate({32: None, 39: None, 45: None})


def _resolve_city(city: str) -> dict:
    entries = _cma("/api/autocomplete?" + urllib.parse.urlencode({"q": city}))
    if not isinstance(entries, list):
        raise ValueError("invalid city list")
    candidates, matches = {}, {}
    target = _normalize(city)
    for entry in entries:
        if not isinstance(entry, str) or len(entry) > 256:
            continue
        parts = entry.split("|")
        if len(parts) != 4:
            continue
        station_id, name, pinyin, country = parts
        if (country != "中国" or not re.fullmatch(r"[A-Za-z0-9]{4,12}", station_id)
                or not _valid_city(name) or not name.strip() or not _valid_city(pinyin)):
            continue
        candidate = {"station_id": station_id, "name": name}
        candidates[station_id] = candidate
        if target and target in (_normalize(name), _normalize(pinyin)):
            matches[station_id] = candidate
    if len(matches) == 1:
        return next(iter(matches.values()))
    return {"ok": False, "error": "weather_city_ambiguous" if matches else "weather_city_unknown",
            "needs_location": True, "choices": list((matches or candidates).values())[:5]}


def _text(value, limit: int) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= limit and value.isprintable() and bool(value.strip())


def _observations(data, station_id: str) -> dict:
    if data in (None, {}, []):
        raise _WeatherError("weather_no_observations")
    if not isinstance(data, dict):
        raise ValueError("invalid observations")
    now = data.get("now")
    if now is None or now == {}:
        raise _WeatherError("weather_no_observations")
    location = data.get("location")
    if not isinstance(now, dict) or not isinstance(location, dict):
        raise ValueError("invalid observations")
    name, path = location.get("name"), location.get("path")
    if (location.get("id") != station_id or not _valid_city(name) or not name.strip()
            or not _text(path, 160) or path.split(",", 1)[0].strip() != "中国"):
        raise ValueError("invalid station location")
    current = {}
    for field, output, lower, upper in (
        ("temperature", "temperature_c", -90, 65), ("humidity", "humidity_percent", 0, 100),
        ("windSpeed", "wind_speed_m_s", 0, 150), ("precipitation", "precipitation_mm", 0, 2000),
        ("feelst", "feels_like_c", -120, 100), ("pressure", "pressure_hpa", 300, 1100),
    ):
        if field == "pressure" and field not in now:
            continue
        value = now.get(field)
        if type(value) not in (int, float) or not lower <= value <= upper or not math.isfinite(value):
            raise ValueError("invalid measurement")
        current[output] = value
    if not _text(now.get("windDirection"), 24):
        raise ValueError("invalid wind direction")
    current["wind_direction"] = now["windDirection"]
    timestamp = data.get("lastUpdate")
    if not isinstance(timestamp, str) or not re.fullmatch(r"[0-9]{4}/[0-9]{2}/[0-9]{2} [0-9]{2}:[0-9]{2}", timestamp):
        raise ValueError("invalid observation time")
    observed = datetime.strptime(timestamp, "%Y/%m/%d %H:%M").replace(tzinfo=_CHINA)
    received = datetime.now(_CHINA)
    result = {"ok": True, "source": "中国气象局（weather.cma.cn）",
              "source_url": _SOURCE + "/api/now/" + station_id,
              "location": {"name": name, "path": path}, "station_id": station_id,
              "observed_at": observed.isoformat(), "received_at": received.isoformat()}
    age = (received - observed).total_seconds()
    if age > 90 * 60 or age < -5 * 60:
        result.update(ok=False, error="weather_observations_stale" if age > 0 else "weather_observations_future")
    else:
        result["current"] = current
    return result


def _get_weather(args: dict, **_kwargs) -> str:
    if not isinstance(args, dict) or args.keys() - {"city"} or not _valid_city(args.get("city", "")):
        return _json({"ok": False, "error": "invalid_arguments"})
    city = args.get("city", "").strip()
    location_source = "explicit_city" if city else "network_ip"
    try:
        if not city:
            city = _locate_city()
        station = _resolve_city(city)
        if "error" in station:
            station["location_source"] = location_source
            return _json(station)
        station_id = station["station_id"]
        result = _observations(_cma("/api/now/" + station_id), station_id)
        result["location_source"] = location_source
        return _json(result)
    except _WeatherError as error:
        return _json({"ok": False, "error": str(error)})
    except (ValueError, TypeError, RecursionError, OverflowError):
        return _json({"ok": False, "error": "weather_invalid_response"})
    except Exception:
        return _json({"ok": False, "error": "weather_unavailable"})


def register(ctx) -> None:
    """Official standalone directory-plugin entry point; no import-time I/O."""
    description = (
        "Get current China-city observations from weather.cma.cn, never a future forecast. "
        "Optional city overrides fresh city-level network IP location; network/proxy exit may differ "
        "from the user's city. State the returned city and observation time. Ask the user to choose "
        "a city when location fails or matches are ambiguous. Do not infer sunny/rainy from zero precipitation."
    )
    ctx.register_tool(
        name="xiaoxi_get_weather", toolset="xiaoxi_weather", handler=_get_weather,
        check_fn=lambda: True, description=description,
        schema={"name": "xiaoxi_get_weather", "description": description, "parameters": {
            "type": "object", "properties": {"city": {
                "type": "string", "default": "", "maxLength": 80,
                "description": "Optional China city name or exact pinyin; empty uses fresh network IP location.",
            }}, "required": [], "additionalProperties": False,
        }},
    )
