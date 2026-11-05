"""Trusted local operator command: one confirmed raw-IR attempt, never a tool.

Run with ``python -m services.ir_learning.replay --help``. Config uses the
learning service's private JSON and fixed state_dir. No profile is modified.
A consumed command ID must never be retried, including after a missing ACK.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import time
import uuid

from .model import BOOT, ID, utc_now, validate_capture
from .transport import LearningTransport, PREFIX, strict_json

MODULUS = 2**32
DEADLINE_MS = 8000


class ReplayError(ValueError):
    """Fixed public error code; never include private input or transport text."""


def _identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ReplayError("invalid_identifier")
    return value


def _private_json(path, limit, *, directory_fd=None):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > limit):
            raise ReplayError("private_0600_file_required")
        with os.fdopen(descriptor, "rb", closefd=False) as source:
            raw = source.read(limit + 1)
        if len(raw) > limit:
            raise ReplayError("private_file_too_large")
        result = strict_json(raw)
        if not isinstance(result, dict):
            raise ReplayError("invalid_private_json")
        return result
    finally:
        os.close(descriptor)


def _state_directory(path):
    if not isinstance(path, str) or not Path(path).is_absolute():
        raise ReplayError("fixed_private_state_dir_required")
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(descriptor)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        os.close(descriptor)
        raise ReplayError("private_0700_state_dir_required")
    return descriptor


def _digest(value):
    canonical = json.dumps(value, sort_keys=True, allow_nan=False,
                           separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _selection(directory_fd, profile_id, record_id, expected_rawlen):
    profile = _private_json(profile_id + ".json", 1024 * 1024,
                            directory_fd=directory_fd)
    records = profile.get("records")
    if (profile.get("schema_version") != "1.0"
            or profile.get("profile_id") != profile_id
            or not isinstance(records, list) or not 1 <= len(records) <= 128):
        raise ReplayError("invalid_profile")
    matches = [record for record in records if isinstance(record, dict)
               and record.get("record_id") == record_id]
    if len(matches) != 1:
        raise ReplayError("record_not_unique_or_missing")
    record = matches[0]
    try:
        sample = validate_capture(record.get("capture"))
        timings = tuple(sample["timings_us"][1:])
        if (sample["nominal_carrier_khz"] != 38
                or sample["rawlen"] != expected_rawlen or not 15 <= len(timings) <= 299
                or len(timings) % 2 != 1
                or any(value > 65535 for value in timings)
                or sum(timings) > 1000000):
            raise ValueError("unsafe_waveform")
    except (ValueError, TypeError, KeyError):
        raise ReplayError("invalid_replay_capture") from None
    return timings, _digest(record)


def _persist(descriptor, directory_fd, intent):
    payload = (json.dumps(intent, allow_nan=False, separators=(",", ":"))
               + "\n").encode()
    os.lseek(descriptor, 0, os.SEEK_SET)
    os.ftruncate(descriptor, 0)
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise ReplayError("intent_write_failed")
        offset += written
    os.fsync(descriptor)
    os.fsync(directory_fd)


def _reserve(directory_fd, command_id, intent):
    try:
        descriptor = os.open(
            "replay-" + command_id + ".json",
            os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW,
            0o600, dir_fd=directory_fd,
        )
    except FileExistsError:
        raise ReplayError("command_already_consumed") from None
    try:
        os.fchmod(descriptor, 0o600)
        _persist(descriptor, directory_fd, intent)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


def _uint32(value):
    if type(value) is not int or not 0 <= value < MODULUS:
        raise ReplayError("invalid_node_time")
    return value


def _status(transport):
    boot, uptime = transport.status()
    if not isinstance(boot, str) or not BOOT.fullmatch(boot):
        raise ReplayError("invalid_node_boot")
    return boot, _uint32(uptime)


def _reply(event, detail, boot, command_id, kind):
    if (not isinstance(event, dict) or not isinstance(detail, dict)
            or event.get("schema_version") != "1.0"
            or event.get("node_id") != "node02"
            or event.get("simulated") is not False
            or event.get("event_type") != "ir_learning"
            or event.get("boot_id") != boot
            or type(event.get("sequence")) is not int
            or not 0 <= event["sequence"] < MODULUS
            or detail.get("kind") != kind
            or detail.get("command_id") != command_id):
        raise ReplayError("invalid_node_reply")


def _elapsed(clock, anchor, limit_ms):
    elapsed = clock() - anchor
    if not 0 <= elapsed < limit_ms / 1000:
        raise ReplayError("local_deadline_expired")


def _publish_once(transport, action, fields, command_id, expected):
    # The existing _exchange generates its own ID. Register the chosen journal
    # nonce explicitly so callback correlation and firmware deduplication agree.
    payload = {"schema_version": "1.0", "node_id": "node02",
               "command_id": command_id, "action": action,
               "ttl_seconds": 10, **fields}
    with transport.condition:
        if not (transport.connected and transport.subscribed
                and transport.online):
            raise ReplayError("receiver_not_ready_no_retry")
        transport.responses[command_id] = None
    try:
        publication = transport.client.publish(
            PREFIX + "/command", json.dumps(payload, separators=(",", ":")),
            qos=0, retain=False,
        )
        if publication.rc != transport.mqtt.MQTT_ERR_SUCCESS:
            raise ReplayError("publish_failed_no_retry")
        transport._wait(lambda: transport.responses.get(command_id) is not None)
        event, detail = transport.responses[command_id]
        if detail.get("kind") != expected:
            raise ReplayError("invalid_node_reply")
        return event, detail
    finally:
        with transport.condition:
            transport.responses.pop(command_id, None)


def _attempt(transport, timings, command_id, descriptor, directory_fd,
             intent, clock):
    first_anchor = clock()
    boot, uptime = _status(transport)
    _elapsed(clock, first_anchor, DEADLINE_MS)
    # Separate prepare/commit command IDs preserve node-side deduplication.
    prepare_id = uuid.uuid4().hex
    while prepare_id == command_id:
        prepare_id = uuid.uuid4().hex
    prepare_anchor = clock()
    event, detail = _publish_once(transport, "ir_raw_prepare", {
        "boot_id": boot, "deadline_ms": (uptime + DEADLINE_MS) % MODULUS,
        "frequency_khz": 38, "timings_us": list(timings),
    }, prepare_id, "prepared")
    _reply(event, detail, boot, prepare_id, "prepared")
    challenge = detail.get("challenge")
    if not isinstance(challenge, str) or not ID.fullmatch(challenge):
        raise ReplayError("invalid_prepared_challenge")
    expires = _uint32(detail.get("expires_ms"))
    commit_anchor = clock()
    current_boot, current_uptime = _status(transport)
    if current_boot != boot:
        raise ReplayError("node_boot_changed")
    if (current_uptime - uptime) % MODULUS > 10000:
        raise ReplayError("invalid_node_time")
    remaining = (expires - current_uptime) % MODULUS
    if not 0 < remaining <= 10000:
        raise ReplayError("prepared_challenge_expired")
    deadline_window = min(DEADLINE_MS, remaining)
    deadline = (current_uptime + deadline_window) % MODULUS
    _elapsed(clock, prepare_anchor, 10000)
    _elapsed(clock, commit_anchor, deadline_window)
    intent.update(phase="commit_consumed", boot_id=boot, attempt=1,
                  deadline_ms=deadline, expires_ms=expires,
                  challenge_sha256=hashlib.sha256(challenge.encode()).hexdigest())
    _persist(descriptor, directory_fd, intent)
    fields = {"boot_id": boot, "deadline_ms": deadline, "challenge": challenge}
    challenge = None  # No reusable challenge or second commit path is exposed.
    _elapsed(clock, prepare_anchor, 10000)
    _elapsed(clock, commit_anchor, deadline_window)
    acknowledged = False
    try:
        event, detail = _publish_once(transport, "ir_raw_commit", fields,
                                     command_id, "sent")
        _reply(event, detail, boot, command_id, "sent")
        acknowledged = True
    except Exception:
        pass  # Publication may have succeeded; the consumed attempt is final.
    finally:
        fields.clear()
    return {
        "ok": acknowledged, "command_id": command_id,
        "outcome": "node_acknowledged" if acknowledged else "unknown_no_retry",
        "attempt_consumed": True, "appliance_response_verified": False,
        "message": ("Node ACK does not verify appliance response; "
                    "do not retry this ID."),
    }


def replay_once(config_path, profile_id, record_id, command_id, *,
                confirm_once=False, transport_factory=None, clock=None):
    """Reserve a nonce, then attempt one commit of a validated saved snapshot.

    Dependency injection is for offline tests. The CLI always uses the existing
    fixed-node02 TLS transport; no host/topic/state-dir override is accepted.
    """
    if confirm_once is not True:
        raise ReplayError("confirmation_required")
    for identifier in (profile_id, record_id, command_id):
        _identifier(identifier)
    directory_fd = descriptor = None
    transport = None
    try:
        config = _private_json(config_path, 16384)
        expected = config.get("expected_rawlen", 280)
        if type(expected) is not int or not 16 <= expected <= 300 or expected % 2:
            raise ReplayError("invalid_expected_rawlen")
        directory_fd = _state_directory(config.get("state_dir"))
        timings, record_digest = _selection(directory_fd, profile_id, record_id,
                                           expected)
        intent = {"schema_version": "1.0", "profile_id": profile_id,
                  "record_id": record_id, "record_sha256": record_digest,
                  "command_id": command_id, "attempt": 0, "boot_id": None,
                  "phase": "reserved_no_commit", "created_at": utc_now()}
        descriptor = _reserve(directory_fd, command_id, intent)
        transport = (transport_factory or LearningTransport)(config)
        transport.start()
        with transport.condition:
            ready = transport.condition.wait_for(
                lambda: transport.connected and transport.subscribed
                and transport.online, timeout=5,
            )
        if not ready:
            raise ReplayError("receiver_not_ready_no_retry")
        return _attempt(transport, timings, command_id, descriptor, directory_fd,
                        intent, clock or time.monotonic)
    except ReplayError:
        raise
    except Exception:
        raise ReplayError("replay_unavailable_no_retry") from None
    finally:
        if transport is not None:
            try:
                transport.close()
            except Exception:
                pass
        if descriptor is not None:
            os.close(descriptor)
        if directory_fd is not None:
            os.close(directory_fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="private service JSON")
    parser.add_argument("--profile", required=True, help="saved profile hex32")
    parser.add_argument("--record", required=True, help="saved record hex32")
    parser.add_argument("--command-id", required=True, help="new local attempt hex32")
    parser.add_argument("--confirm-once", action="store_true",
                        help="authorize exactly this local commit attempt")
    args = parser.parse_args(argv)
    try:
        result = replay_once(args.config, args.profile, args.record,
                             args.command_id, confirm_once=args.confirm_once)
    except ReplayError as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        return 2
    print(json.dumps(result))
    return 0 if result["ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
