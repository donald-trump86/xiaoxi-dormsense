"""Authenticated fixed learning and single-attempt snapshot control APIs."""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import signal
import stat
import threading

from .control import ERRORS as CONTROL_ERRORS, IRControl, _unknown
from .model import BUTTONS, ID, LearningSession
from .transport import LearningTransport, strict_json

ACTIONS = {"start", "next", "status", "confirm", "skip", "cancel"}
ERRORS = {"unsupported_button", "session_not_started", "capture_already_active", "profile_record_limit",
          "baseline_required", "receiver_not_ready", "manual_confirmation_not_applicable",
          "explicit_label_confirmation_required", "button_mismatch", "invalid_request"}


def handler_for(session, token, *, control=None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "XiaoxiLearning/1"
        sys_version = ""

        def setup(self):
            super().setup()
            self.connection.settimeout(3)

        def log_message(self, *args):
            pass

        def answer(self, status, body):
            payload = json.dumps(body, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)
            self.close_connection = True

        def do_GET(self):
            if self.path == "/health":
                self.answer(200, {"ok": True})
            else:
                self.answer(404, {"ok": False, "error": "not_found"})

        def control_action(self, request):
            action = request.get("action")
            if action == "list":
                if set(request) - {"action", "profile_id"}:
                    raise ValueError("invalid_request")
                if "profile_id" in request:
                    value = request["profile_id"]
                    if not isinstance(value, str) or not ID.fullmatch(value):
                        raise ValueError("invalid_identifier")
                try:
                    result = (control.catalog(request["profile_id"]) if "profile_id" in request
                              else control.catalog())
                except Exception:
                    return self.answer(503, {"ok": False, "error": "control_unavailable"})
            elif action == "send":
                if set(request) != {"action", "profile_id", "record_id", "command_id", "confirm_once"}:
                    raise ValueError("invalid_request")
                for field in ("profile_id", "record_id", "command_id"):
                    if not isinstance(request[field], str) or not ID.fullmatch(request[field]):
                        raise ValueError("invalid_identifier")
                if request["confirm_once"] is not True:
                    raise ValueError("confirmation_required")
                try:
                    result = control.send(request["profile_id"], request["record_id"],
                                          request["command_id"], confirm_once=True)
                except Exception:
                    return self.answer(503, _unknown(request["command_id"], "control_unavailable"))
            else:
                raise ValueError("invalid_request")
            self.answer(200, result)

        def do_POST(self):
            if self.path != "/api/learning" and not (self.path == "/api/control" and control is not None):
                return self.answer(404, {"ok": False, "error": "not_found"})
            authorizations = self.headers.get_all("Authorization", [])
            if len(authorizations) != 1 or not hmac.compare_digest(authorizations[0], "Bearer " + token):
                return self.answer(401, {"ok": False, "error": "unauthorized"})
            try:
                if (self.headers.get("Transfer-Encoding") or self.headers.get("Content-Encoding")
                        or self.headers.get_content_type() != "application/json"
                        or len(self.headers.get_all("Content-Length", [])) != 1):
                    raise ValueError("invalid_request")
                length_text = self.headers["Content-Length"]
                if not length_text.isascii() or not length_text.isdecimal():
                    raise ValueError("invalid_request")
                length = int(length_text)
                if not 1 <= length <= 2048:
                    raise ValueError("invalid_request")
                payload = self.rfile.read(length)
                if len(payload) != length:
                    raise ValueError("invalid_request")
                request = strict_json(payload)
                if not isinstance(request, dict):
                    raise ValueError("invalid_request")
                if self.path == "/api/control":
                    return self.control_action(request)
                if set(request) - {"action", "button", "label", "confirm", "reason"}:
                    raise ValueError("invalid_request")
                action = request.get("action")
                if not isinstance(action, str) or action not in ACTIONS:
                    raise ValueError("invalid_request")
                allowed = {"start": {"action"}, "status": {"action"}, "cancel": {"action"},
                           "next": {"action", "button"}, "confirm": {"action", "button", "label", "confirm"},
                           "skip": {"action", "button", "reason"}}[action]
                if set(request) - allowed:
                    raise ValueError("invalid_request")
                button = request.get("button")
                if button is not None and (not isinstance(button, str) or button not in BUTTONS):
                    raise ValueError("unsupported_button")
                if action == "start":
                    result = session.start()
                elif action == "status":
                    result = session.public()
                elif action == "next":
                    result = session.next(button)
                elif action == "confirm":
                    if button != session.public().get("button"):
                        raise ValueError("button_mismatch")
                    label = request.get("label")
                    if not isinstance(label, str) or not label.strip():
                        raise ValueError("explicit_label_confirmation_required")
                    result = session.confirm(label, request.get("confirm"))
                elif action == "skip":
                    reason = request.get("reason", "")
                    if not isinstance(reason, str) or len(reason) > 120:
                        raise ValueError("invalid_request")
                    if button is None:
                        raise ValueError("button_mismatch")
                    result = session.skip(reason, button=button)
                else:
                    result = session.cancel()
                self.answer(200, result)
            except (ValueError, TypeError, KeyError, UnicodeDecodeError) as error:
                allowed_errors = CONTROL_ERRORS | {"invalid_request"} if self.path == "/api/control" else ERRORS
                code = str(error) if isinstance(error, ValueError) and str(error) in allowed_errors else "invalid_request"
                body = {"ok": False, "error": code}
                if code == "baseline_required":
                    body["prompt"] = "上次状态不确定，请先录制baseline，之后再录本键。"
                self.answer(200, body)
            except OSError:
                self.answer(503, {"ok": False, "error": "learning_service_unavailable"})

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    path = Path(args.config)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > 16384:
        raise SystemExit("private_config_required")
    config = strict_json(path.read_bytes())
    token = config.get("api_token")
    if not isinstance(token, str) or not 32 <= len(token) <= 128 or not token.isascii():
        raise SystemExit("invalid_api_token")
    transport = LearningTransport(config)
    session = LearningSession(config["state_dir"], transport, expected_rawlen=config.get("expected_rawlen", 280))
    transport.on_capture = session.receive
    transport.on_expire = session.expire
    server = HTTPServer(("0.0.0.0", 8090), handler_for(session, token, control=IRControl(session, args.config)))
    def stop(signum, frame):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    transport.start()
    try:
        server.serve_forever(poll_interval=.25)
    finally:
        server.server_close()
        transport.close()


if __name__ == "__main__":
    main()
