"""Native Hermes tools for one restricted, human-guided IR learning service."""

import http.client
import json
import math
import re
from typing import Any


_TOOLSET = "xiaoxi_ir_learning"
_TOKEN_NAME = "XIAOXI_IR_LEARNING_TOKEN"
_RESPONSE_LIMIT = 128 * 1024
_STATE_FIELDS = frozenset({
    "power", "mode", "temp_c", "fan", "swingv", "swingh", "light", "turbo",
    "econo", "clean", "sleep", "ifeel", "quiet", "filter",
})
_OBSERVED_FIELDS = _STATE_FIELDS | {"protocol", "bits", "rawlen", "coverage"}
_STATUSES = frozenset({
    "idle", "arming", "ready", "captured", "needs_confirmation", "rejected",
    "expired", "cancelled",
})
_INVALID = object()
_GUIDANCE = (
    "Guide one physical remote key at a time. Compare before/after states across "
    "supported decoded fields. UNKNOWN waveforms stay pending until the user "
    "supplies a manual label and confirms it. Missing or unsupported fields remain "
    "unknown rather than false. These tools manage waveform learning and status "
    "queries without replaying IR."
)


def _result(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, allow_nan=False)


def _error(code: str) -> str:
    return _result({"ok": False, "error": code})


def _token() -> str | None:
    """Read only the current Hermes profile's official credential interface."""
    try:
        from agent.secret_scope import get_secret
        value = get_secret(_TOKEN_NAME)
    except Exception:
        return None
    if not isinstance(value, str) or not 1 <= len(value) <= 4096:
        return None
    if any(ord(char) < 33 or ord(char) > 126 for char in value):
        return None
    return value


def _available() -> bool:
    return _token() is not None


def _text(value: Any, token: str, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    return value.replace(token, "[redacted]")[:limit]


def _scalar(value: Any, token: str) -> Any:
    if isinstance(value, str):
        return _text(value, token, 256)
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    return _INVALID


def _project(data: Any, token: str) -> dict:
    """Allow summary fields only; raw timings and state bytes stay in the service."""
    if not isinstance(data, dict) or type(data.get("ok")) is not bool:
        raise ValueError("invalid response envelope")
    if not data["ok"]:
        code = data.get("error")
        if not isinstance(code, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", code):
            code = "learning_service_error"
        return {"ok": False, "error": code.replace(token, "[redacted]")}
    result = {"ok": True}
    status = data.get("status")
    if isinstance(status, str) and status in _STATUSES:
        result["status"] = _text(status, token, 64)
    profile_id = data.get("profile_id")
    if isinstance(profile_id, str) and re.fullmatch(r"[0-9a-fA-F]{32}", profile_id):
        result["profile_id"] = profile_id.replace(token, "[redacted]")
    for key, limit in (("button", 128), ("prompt", 2048), ("message", 2048)):
        value = _text(data.get(key), token, limit)
        if value is not None:
            result[key] = value
    count = data.get("record_count")
    if type(count) is int and count >= 0:
        result["record_count"] = count
    buttons = data.get("recommended_buttons")
    if isinstance(buttons, list):
        result["recommended_buttons"] = [
            _text(item, token, 128) for item in buttons[:32] if isinstance(item, str)
        ]
    observed = data.get("observed")
    if isinstance(observed, dict):
        safe = {}
        for key in _OBSERVED_FIELDS & observed.keys():
            value = _scalar(observed[key], token)
            if value is not _INVALID:
                safe[key] = value
        result["observed"] = safe
    changes = data.get("changes")
    if isinstance(changes, dict):
        safe = {}
        for field in _STATE_FIELDS & changes.keys():
            change = changes[field]
            if not isinstance(change, dict):
                continue
            pair = {}
            for key in ("before", "after"):
                if key in change:
                    value = _scalar(change[key], token)
                    if value is not _INVALID:
                        pair[key] = value
            if pair:
                safe[field] = pair
        result["changes"] = safe
    validation = data.get("validation")
    if isinstance(validation, dict):
        safe = {}
        basis = _text(validation.get("basis"), token, 256)
        if basis is not None:
            safe["basis"] = basis
        warnings = validation.get("warnings")
        if isinstance(warnings, list):
            safe["warnings"] = [
                _text(item, token, 512) for item in warnings[:32] if isinstance(item, str)
            ]
        result["validation"] = safe
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("non-finite JSON constant")


def _request(payload: dict) -> str:
    token = _token()
    if token is None:
        return _error("learning_credentials_unavailable")
    connection = None
    try:
        # http.client neither consults proxy env nor follows HTTP redirects.
        connection = http.client.HTTPConnection("ir-learning", 8090, timeout=5.0)
        connection.request("POST", "/api/learning", body=json.dumps(
            payload, ensure_ascii=False, allow_nan=False
        ).encode("utf-8"), headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "Connection": "close",
        })
        response = connection.getresponse()
        if not 200 <= response.status < 300:
            return _error("learning_http_error")
        content_type = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
        encoding = response.getheader("Content-Encoding", "identity").lower()
        if content_type != "application/json" or encoding not in ("", "identity"):
            return _error("learning_invalid_response")
        length = response.getheader("Content-Length")
        if length is not None and int(length) > _RESPONSE_LIMIT:
            return _error("learning_response_too_large")
        body = response.read(_RESPONSE_LIMIT + 1)
        if len(body) > _RESPONSE_LIMIT:
            return _error("learning_response_too_large")
        data = json.loads(body.decode("utf-8"), parse_constant=_reject_constant)
        return _result(_project(data, token))
    except (ValueError, UnicodeError, RecursionError):
        return _error("learning_invalid_response")
    except Exception:
        # Backend URLs, headers, exception messages and response bodies are private.
        return _error("learning_unavailable")
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def _valid_text(value: Any, limit: int) -> bool:
    return (
        isinstance(value, str) and bool(value.strip()) and len(value) <= limit
        and all(ord(char) >= 32 and ord(char) != 127 for char in value)
    )


def _initialize(args: dict, **_kwargs) -> str:
    if not isinstance(args, dict) or args.keys() - {"action"}:
        return _error("invalid_arguments")
    action = args.get("action", "start")
    if action not in ("start", "status", "cancel"):
        return _error("invalid_arguments")
    return _request({"action": action})


def _learn_key(args: dict, **_kwargs) -> str:
    if not isinstance(args, dict) or not _valid_text(args.get("button"), 128):
        return _error("invalid_arguments")
    action = args.get("action", "capture")
    allowed = {
        "capture": {"button", "action"},
        "confirm": {"button", "action", "label", "confirm"},
        "skip": {"button", "action", "reason"},
    }
    if not isinstance(action, str) or action not in allowed or args.keys() - allowed[action]:
        return _error("invalid_arguments")
    if action == "confirm" and (args.get("confirm") is not True
                                or not _valid_text(args.get("label"), 80)):
        return _error("invalid_arguments")
    for key, limit in (("label", 128), ("reason", 256)):
        if key in args and not _valid_text(args[key], limit):
            return _error("invalid_arguments")
    payload = {"action": "next" if action == "capture" else action, "button": args["button"]}
    for key in ("label", "confirm", "reason"):
        if key in args:
            payload[key] = args[key]
    return _request(payload)


def _status(args: dict, **_kwargs) -> str:
    if not isinstance(args, dict) or args:
        return _error("invalid_arguments")
    return _request({"action": "status"})


def register(ctx) -> None:
    """Official standalone directory-plugin entry point; no import-time I/O."""
    tools = (
        ("xiaoxi_ac_initialize", _initialize,
         "Start a learning session (default), query status, or cancel. Start returns "
         "the first baseline prompt. " + _GUIDANCE,
         {"action": {"type": "string", "enum": ["start", "status", "cancel"], "default": "start"}}, []),
        ("xiaoxi_ac_learn_key", _learn_key,
         "Capture one named physical key (default); after the user replies, confirm "
         "its interpretation with confirm=true, or skip it. Confirmation records a "
         "label only and never transmits IR. Manual UNKNOWN labels require the user. " + _GUIDANCE,
         {
             "button": {"type": "string", "enum": ["baseline", "power", "mode", "temp_up", "temp_down", "fan", "swingv", "swingh", "light", "sleep", "turbo", "clean", "econo", "ifeel", "quiet", "filter", "other"],
                       "description": "Use the returned button identifier; baseline re-establishes current remote state."},
             "action": {"type": "string", "enum": ["capture", "confirm", "skip"], "default": "capture"},
             "label": {"type": "string", "minLength": 1, "maxLength": 128,
                       "description": "User-supplied manual label; confirm action only."},
             "confirm": {"type": "boolean", "description": "Must be true for confirm, after the user agrees."},
             "reason": {"type": "string", "minLength": 1, "maxLength": 256,
                        "description": "Optional reason for skipping; skip action only."},
         }, ["button"]),
        ("xiaoxi_ac_learning_status", _status,
         "Return the active session's bounded summary and current instruction. " + _GUIDANCE, {}, []),
    )
    for name, handler, description, properties, required in tools:
        ctx.register_tool(
            name=name, toolset=_TOOLSET, handler=handler, check_fn=_available,
            schema={"name": name, "description": description, "parameters": {
                "type": "object", "properties": properties, "required": required,
                "additionalProperties": False,
            }},
            description=description,
        )
