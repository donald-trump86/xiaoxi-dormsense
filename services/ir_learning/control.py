"""Bounded snapshot catalog and the existing single-attempt replay boundary."""
import os
import uuid

from . import replay
from .model import BUTTONS, ID, validate_capture

PREFLIGHT_ERRORS = {
    "confirmation_required", "invalid_identifier", "private_0600_file_required",
    "private_file_too_large", "invalid_private_json", "fixed_private_state_dir_required",
    "private_0700_state_dir_required", "invalid_expected_rawlen", "invalid_profile",
    "record_not_unique_or_missing", "invalid_replay_capture",
}
ERRORS = PREFLIGHT_ERRORS | {
    "learning_capture_active", "control_unavailable", "command_already_consumed",
    "intent_write_failed", "invalid_node_time", "invalid_node_boot", "invalid_node_reply",
    "local_deadline_expired", "receiver_not_ready_no_retry", "publish_failed_no_retry",
    "invalid_prepared_challenge", "node_boot_changed", "prepared_challenge_expired",
    "replay_unavailable_no_retry",
}


def _error_code(error):
    return str(error) if isinstance(error, replay.ReplayError) and str(error) in ERRORS else "control_unavailable"


def _unknown(command_id, code):
    return {"ok": False, "command_id": command_id, "outcome": "unknown_no_retry",
            "attempt_consumed": True, "appliance_response_verified": False,
            "error": code}


def _text(value, limit):
    return "".join(char for char in value[:limit] if char.isprintable()) if isinstance(value, str) else ""


def _profile(directory_fd, profile_id):
    try:
        value = replay._private_json(profile_id + ".json", 1024 * 1024,
                                     directory_fd=directory_fd)
    except (OSError, ValueError):
        raise replay.ReplayError("invalid_profile") from None
    records = value.get("records")
    if (value.get("schema_version") != "1.0" or value.get("profile_id") != profile_id
            or not isinstance(records, list) or len(records) > 128
            or any(not isinstance(record, dict)
                   or not isinstance(record.get("record_id"), str)
                   or not ID.fullmatch(record["record_id"]) for record in records)):
        raise replay.ReplayError("invalid_profile")
    return records


def _command(directory_fd, profile_id, record, expected_rawlen):
    reason = None
    try:
        capture = validate_capture(record.get("capture"))
    except (ValueError, TypeError, KeyError):
        capture = {}
    try:
        # Reuse the exact operator selection guards, including unique record IDs.
        replay._selection(directory_fd, profile_id, record["record_id"], expected_rawlen)
    except replay.ReplayError as error:
        reason = _error_code(error)
    button = record.get("button")
    result = {
        "profile_id": profile_id, "record_id": record["record_id"],
        "button": button if isinstance(button, str) and button in BUTTONS else "other",
        "label": _text(record.get("label"), 80),
        "recorded_at": _text(record.get("recorded_at"), 64),
        "state": capture.get("state"), "protocol": capture.get("protocol", "UNKNOWN"),
        "bits": capture.get("bits", 0), "coverage": capture.get("coverage", "unknown"),
        "semantics_verified": record.get("semantics_verified") is True and capture.get("state") is not None,
        "replayable": reason is None,
    }
    if reason is not None:
        result["unavailable_reason"] = reason
    return result


class IRControl:
    def __init__(self, session, config_path):
        self.session = session
        self.config_path = config_path

    def catalog(self, profile_id=None) -> dict:
        directory_fd = None
        try:
            if profile_id is not None:
                replay._identifier(profile_id)
            with self.session.lock:
                expected = self.session.expected_rawlen
                if type(expected) is not int or not 16 <= expected <= 300 or expected % 2:
                    raise replay.ReplayError("invalid_expected_rawlen")
                directory_fd = replay._state_directory(str(self.session.directory))
                try:
                    active = replay._private_json("active.json", 1024,
                                                  directory_fd=directory_fd).get("profile_id")
                    replay._identifier(active)
                except FileNotFoundError:
                    active = (self.session.data or {}).get("profile_id")
                    if active is not None:
                        replay._identifier(active)
                except (ValueError, OSError):
                    raise replay.ReplayError("invalid_profile") from None
                selected = profile_id if profile_id is not None else active
                names = sorted(name[:-5] for name in os.listdir(directory_fd)
                               if name.endswith(".json") and ID.fullmatch(name[:-5]))
                # Keep the active and requested profiles visible even beyond the cap.
                preferred = list(dict.fromkeys(value for value in (active, selected) if value is not None))
                visible = (preferred + [value for value in names if value not in preferred])[:32]
                profiles, selected_records = [], []
                for value in visible:
                    records = _profile(directory_fd, value)
                    profiles.append({"profile_id": value, "record_count": len(records),
                                     "active": value == active})
                    if value == selected:
                        selected_records = records
                result = {"ok": True, "profiles": profiles,
                          "commands": [_command(directory_fd, selected, record, expected)
                                       for record in selected_records],
                          "command_id": uuid.uuid4().hex}
                if selected is not None:
                    result["profile_id"] = selected
                if active is not None:
                    result["active_profile_id"] = active
                if len(names) > 32:
                    result["profiles_truncated"] = True
                return result
        except Exception as error:
            return {"ok": False, "error": _error_code(error)}
        finally:
            if directory_fd is not None:
                os.close(directory_fd)

    def send(self, profile_id, record_id, command_id, *, confirm_once=False) -> dict:
        try:
            for identifier in (profile_id, record_id, command_id):
                replay._identifier(identifier)
            if confirm_once is not True:
                raise replay.ReplayError("confirmation_required")
            with self.session.lock:
                data = self.session.data or {}
                if data.get("capture") is not None or data.get("status") in {"arming", "ready"}:
                    raise replay.ReplayError("learning_capture_active")
                try:
                    result = replay.replay_once(self.config_path, profile_id, record_id,
                                                command_id, confirm_once=True)
                    return {key: result[key] for key in (
                        "ok", "command_id", "outcome", "attempt_consumed", "appliance_response_verified",
                    )}
                except Exception as error:
                    code = _error_code(error)
                    if code in PREFLIGHT_ERRORS:
                        return {"ok": False, "error": code}
                    # The nonce may already be durable; never offer a retry.
                    return _unknown(command_id, code)
        except Exception as error:
            return {"ok": False, "error": _error_code(error)}
