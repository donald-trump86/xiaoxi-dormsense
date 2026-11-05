"""Private, GET-only HA projection. Import is offline and reads no configuration.

Run with --config pointing to a private, current-owner 0600 JSON regular file.
Use generate_query_token() when provisioning a distinct local Bearer token.
Verified registry IDs may replace the two defaults with node01 HA suffix IDs.

node_id is allowlist identity, NOT a newly observed sample field. Native HA owns
expire_after=35; received_at is HA reception metadata, not a hard source-age
proof. unknown/unavailable retain validated old metadata or explicit nulls.
Socket/urllib timeouts are 5s per I/O, NOT a hard total deadline (DNS and slow
streaming may exceed it). No threads: one bounded-size request at a time.
Deployment must separately enforce nonroot UID 10001 and network isolation.
"""
import argparse
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
import os
import re
import secrets
import stat
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


DEFAULT_ENTITIES = (
    "sensor.xiaoxi_node01_temperature",
    "sensor.xiaoxi_node01_humidity",
)
TIMEOUT_SECONDS = 5
MAX_RESPONSE_BYTES = 256 * 1024
MAX_CONFIG_BYTES = 16 * 1024
MAX_JSON_DEPTH = 32
ENTITY_ID = re.compile(r"[a-z][a-z0-9_]*\.[a-z0-9_]{1,128}")
PRIVATE_ENTITY = re.compile(
    r"sensor\.xiaoxi_(?:node01_(temperature|humidity|light|button_event)|node02_(ir_event))(?:_[0-9]{1,6})?"
)
EVENT_STATE = re.compile(r"[a-z0-9_]{1,64}")
NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
BOOT_ID = re.compile(r"node0[12]-[0-9a-f]{8}")
UTC_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|\+00:00)")


@dataclass(frozen=True)
class Config:
    backend_url: str = field(repr=False)
    backend_token: str = field(repr=False)
    query_token: str = field(repr=False)
    allowed_entities: tuple[str, ...] = DEFAULT_ENTITIES

    def __post_init__(self):
        try:
            if not isinstance(self.backend_url, str) or not self.backend_url.isascii():
                raise ValueError
            if any(ord(char) <= 32 or ord(char) == 127 for char in self.backend_url):
                raise ValueError
            url = urlsplit(self.backend_url)
            if (url.scheme not in {"http", "https"} or not url.hostname
                    or url.username is not None or url.password is not None
                    or url.path not in {"", "/"} or url.query or url.fragment
                    or "?" in self.backend_url or "#" in self.backend_url
                    or "\\" in self.backend_url):
                raise ValueError
            if url.port is not None and not 1 <= url.port <= 65535:
                raise ValueError
            if (not isinstance(self.backend_token, str)
                    or not 1 <= len(self.backend_token) <= 4096
                    or not all(33 <= ord(char) <= 126 for char in self.backend_token)):
                raise ValueError
            if (not isinstance(self.query_token, str)
                    or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", self.query_token)
                    or self.query_token == self.backend_token):
                raise ValueError
            if (not isinstance(self.allowed_entities, (tuple, list))
                    or len(self.allowed_entities) not in (2, 3, 4, 5)):
                raise ValueError
            kinds = []
            for entity_id in self.allowed_entities:
                match = PRIVATE_ENTITY.fullmatch(entity_id) if isinstance(entity_id, str) else None
                kind = (match.group(1) or match.group(2)) if match is not None else None
                if kind is None or kind in kinds:
                    raise ValueError
                kinds.append(kind)
            if not ({"temperature", "humidity"} <= set(kinds)
                    <= {"temperature", "humidity", "light", "button_event", "ir_event"}):
                raise ValueError
            object.__setattr__(self, "allowed_entities", tuple(self.allowed_entities))
            object.__setattr__(self, "backend_url", self.backend_url.rstrip("/"))
        except (ValueError, TypeError, AttributeError):
            raise ValueError("invalid_private_config") from None


def generate_query_token() -> str:
    return secrets.token_urlsafe(32)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("invalid_json")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("invalid_json")


def _validate_json(value, depth=0):
    if depth > MAX_JSON_DEPTH:
        raise ValueError("invalid_json")
    if isinstance(value, str):
        value.encode("utf-8", errors="strict")
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("invalid_json")
    elif isinstance(value, dict):
        for key, item in value.items():
            _validate_json(key, depth + 1)
            _validate_json(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _validate_json(item, depth + 1)


def _decode_json(body: bytes, limit: int):
    try:
        if not isinstance(body, bytes) or len(body) > limit:
            raise ValueError
        value = json.loads(body.decode("utf-8", errors="strict"),
                           object_pairs_hook=_unique_object,
                           parse_constant=_reject_constant)
        _validate_json(value)
        return value
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise ValueError("invalid_json") from None


def _private_stat(info):
    if (not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.getuid() or not 0 < info.st_size <= MAX_CONFIG_BYTES):
        raise ValueError("invalid_private_config")


def load_config(path: str) -> Config:
    """No environment fallback; reject final symlinks and recheck the opened inode."""
    descriptor = None
    try:
        before = os.lstat(path)
        _private_stat(before)
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        after = os.fstat(descriptor)
        _private_stat(after)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise ValueError
        chunks = []
        length = 0
        while length <= MAX_CONFIG_BYTES:
            chunk = os.read(descriptor, MAX_CONFIG_BYTES + 1 - length)
            if not chunk:
                break
            chunks.append(chunk)
            length += len(chunk)
        value = _decode_json(b"".join(chunks), MAX_CONFIG_BYTES)
        required = {"backend_url", "backend_token", "query_token"}
        if (not isinstance(value, dict) or not required <= value.keys()
                or value.keys() - required - {"allowed_entities"}):
            raise ValueError
        return Config(**value)
    except (OSError, ValueError, TypeError, RecursionError):
        raise ValueError("invalid_private_config") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _allowed_path(path: str, config: Config) -> bool:
    return path == "/api/states" or path in {
        "/api/states/" + entity_id for entity_id in config.allowed_entities
    }


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class BackendReader:
    """Only server-configured targets, GET, private Bearer; no client headers."""
    def __init__(self, config: Config, opener=None):
        self.config = config
        self.opener = opener if opener is not None else build_opener(ProxyHandler({}), NoRedirect())

    def __call__(self, path: str):
        if path not in {"/api/states/" + entity_id for entity_id in self.config.allowed_entities}:
            raise ValueError("invalid_backend_path")
        request = Request(self.config.backend_url + path, method="GET", headers={
            "Authorization": "Bearer " + self.config.backend_token,
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        })
        try:
            response = self.opener.open(request, timeout=TIMEOUT_SECONDS)
        except HTTPError as error:
            error.close()
            raise ValueError("invalid_backend_response") from None
        with response:
            if response.getcode() != 200:
                raise ValueError("invalid_backend_response")
            encoding = response.headers.get("Content-Encoding", "identity")
            if encoding.lower() != "identity":
                raise ValueError("invalid_backend_response")
            length = response.headers.get("Content-Length")
            if length is not None:
                if (not re.fullmatch(r"[0-9]{1,10}", length)
                        or int(length) > MAX_RESPONSE_BYTES):
                    raise ValueError("invalid_backend_response")
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if length is not None and len(body) != int(length):
                raise ValueError("invalid_backend_response")
        return _decode_json(body, MAX_RESPONSE_BYTES)


def _entity_shape(value):
    if (not isinstance(value, dict)
            or not isinstance(value.get("entity_id"), str)
            or ENTITY_ID.fullmatch(value["entity_id"]) is None
            or not isinstance(value.get("state"), str)
            or not isinstance(value.get("attributes"), dict)):
        raise ValueError("invalid_entity")


def _project_entity(value, expected_id):
    _entity_shape(value)
    if value["entity_id"] != expected_id:
        raise ValueError("invalid_entity")
    state = value["state"]
    attrs = value["attributes"]
    unavailable = state in {"unknown", "unavailable"}
    match = PRIVATE_ENTITY.fullmatch(expected_id)
    kind = match.group(1) or match.group(2)
    expected_node = "node02" if kind == "ir_event" else "node01"
    if not unavailable:
        if kind in ("ir_event", "button_event"):
            if EVENT_STATE.fullmatch(state) is None:
                raise ValueError("invalid_entity")
        else:
            if len(state) > 64 or NUMBER.fullmatch(state) is None or not math.isfinite(float(state)):
                raise ValueError("invalid_entity")
            if kind == "humidity" and not 0 <= float(state) <= 100:
                raise ValueError("invalid_entity")
            if kind == "light" and not 0 <= float(state) <= 1:
                raise ValueError("invalid_entity")
    unit = "%" if kind == "humidity" else ("°C" if kind == "temperature" else None)
    if "node_id" in attrs and attrs["node_id"] != expected_node:
        raise ValueError("invalid_entity")
    if attrs.get("unit_of_measurement") != unit:
        if not unavailable or attrs.get("unit_of_measurement") is not None:
            raise ValueError("invalid_entity")
    metadata = {key: attrs.get(key) for key in ("boot_id", "sequence", "simulated", "received_at")}
    boot = metadata["boot_id"]
    sequence = metadata["sequence"]
    simulated = metadata["simulated"]
    received = metadata["received_at"]
    if boot is not None and (not isinstance(boot, str) or BOOT_ID.fullmatch(boot) is None
                             or not boot.startswith(f"{expected_node}-")
                             or int(boot[len(expected_node) + 1:], 16) == 0):
        raise ValueError("invalid_entity")
    if sequence is not None and (type(sequence) is not int or not 0 <= sequence <= 4294967295):
        raise ValueError("invalid_entity")
    if simulated is not None and type(simulated) is not bool:
        raise ValueError("invalid_entity")
    if received is not None:
        if not isinstance(received, str) or UTC_TIME.fullmatch(received) is None:
            raise ValueError("invalid_entity")
        try:
            timestamp = datetime.fromisoformat(received.replace("Z", "+00:00"))
            if timestamp.utcoffset() != timedelta(0):
                raise ValueError
        except ValueError:
            raise ValueError("invalid_entity") from None
    if not unavailable and (any(item is None for item in metadata.values()) or simulated is not False):
        raise ValueError("invalid_entity")
    extra_attrs = {}
    if kind in ("ir_event", "button_event"):
        event_type = attrs.get("event_type")
        detail = attrs.get("detail")
        if not unavailable:
            if (event_type != state or not isinstance(detail, str)
                    or not 1 <= len(detail) <= 320
                    or not all(32 <= ord(ch) <= 126 for ch in detail)):
                raise ValueError("invalid_entity")
        else:
            # HA retains previous event attributes when availability changes.
            # Preserve the unavailable state without presenting stale event text.
            event_type = detail = None
        extra_attrs = {"event_type": event_type, "detail": detail}
    # This is configured identity, not invented sampling metadata.
    return {"entity_id": expected_id, "state": state, "attributes": {
        "unit_of_measurement": attrs.get("unit_of_measurement"),
        "node_id": expected_node,
        **metadata,
        **extra_attrs,
    }}


class ReadGatewayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def setup(self):
        self.request.settimeout(TIMEOUT_SECONDS)
        super().setup()

    def parse_request(self):
        # BaseHTTPRequestHandler normalizes leading //; retain the raw target.
        words = self.raw_requestline.rstrip(b"\r\n").split()
        self.raw_target = words[1] if len(words) >= 2 else b""
        return super().parse_request()

    def log_message(self, format, *args):
        pass

    def log_error(self, format, *args):
        pass

    def _reply(self, status, value):
        body = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        self.close_connection = True
        self.send_response_only(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if getattr(self, "command", None) != "HEAD":
            self.wfile.write(body)

    def send_error(self, code, message=None, explain=None):
        # Never echo raw request lines, verbs, headers or exception strings.
        if code == 501:
            self._reply(405, {"error": "method_not_allowed"})
        else:
            self._reply(code, {"error": "bad_request"})

    def _deny_method(self):
        self._reply(405, {"error": "method_not_allowed"})

    do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _deny_method

    def do_GET(self):
        config = self.server.config
        try:
            target = self.raw_target.decode("ascii")
        except UnicodeError:
            target = ""
        if target != self.path or not _allowed_path(target, config):
            self._reply(404, {"error": "not_found"})
            return
        authorization = self.headers.get_all("Authorization", [])
        if len(authorization) != 1 or not authorization[0].startswith("Bearer "):
            self._reply(401, {"error": "unauthorized"})
            return
        try:
            supplied = authorization[0][len("Bearer "):].encode("ascii")
        except UnicodeError:
            supplied = b""
        if not hmac.compare_digest(supplied, config.query_token.encode("ascii")):
            self._reply(401, {"error": "unauthorized"})
            return
        lengths = self.headers.get_all("Content-Length", [])
        if (self.headers.get_all("Transfer-Encoding", []) or len(lengths) > 1
                or (lengths and lengths != ["0"])):
            self._reply(400, {"error": "bad_request"})
            return
        try:
            if target == "/api/states":
                value = [_project_entity(self.server.backend_reader("/api/states/" + entity_id), entity_id)
                         for entity_id in config.allowed_entities]
            else:
                value = _project_entity(self.server.backend_reader(target), target[len("/api/states/"):])
        except Exception as error:
            # Close HTTPError response wrappers so their GC cannot log raw errors.
            if isinstance(error, HTTPError):
                error.close()
            # Catch injected reader/HTTP/JSON/recursion failures without disclosure.
            self._reply(502, {"error": "backend_unavailable"})
            return
        self._reply(200, value)


class GatewayHTTPServer(HTTPServer):
    request_queue_size = 8

    def handle_error(self, request, client_address):
        # No socketserver raw tracebacks (including backend exception messages).
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="Private offline-configured read-only HA gateway")
    parser.add_argument("--config", required=True, help="private owner-matched 0600 JSON file")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
    except ValueError:
        parser.exit(2, "invalid_private_config\n")
    # ponytail: single HTTPServer bounds concurrency to one; isolation/rate limiting
    # remain deployment duties. No threads or unbounded executor queue.
    with GatewayHTTPServer(("0.0.0.0", 8080), ReadGatewayHandler) as server:
        server.config = config
        server.backend_reader = BackendReader(config)
        server.timeout = TIMEOUT_SECONDS
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
