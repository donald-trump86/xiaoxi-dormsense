"""Authenticated fixed learning API; deliberately contains no IR send endpoint."""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import signal
import stat
import threading

from .model import BUTTONS, LearningSession
from .transport import LearningTransport, strict_json

ACTIONS = {"start", "next", "status", "confirm", "skip", "cancel"}
ERRORS = {"unsupported_button", "session_not_started", "capture_already_active", "profile_record_limit",
          "baseline_required", "receiver_not_ready", "manual_confirmation_not_applicable",
          "explicit_label_confirmation_required", "button_mismatch", "invalid_request"}


def handler_for(session, token):
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

        def do_POST(self):
            if self.path != "/api/learning":
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
                if not isinstance(request, dict) or set(request) - {"action", "button", "label", "confirm", "reason"}:
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
                code = str(error) if isinstance(error, ValueError) and str(error) in ERRORS else "invalid_request"
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
    server = HTTPServer(("0.0.0.0", 8090), handler_for(session, token))
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
