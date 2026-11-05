"""Persist key transitions separately from unverified human labels and waveforms."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import stat
import threading
import uuid

BUTTONS = {
    "baseline": (None, "先将遥控器对着 C3 接收头，按一次当前设置对应的键，建立基线；避开空调。"),
    "power": ("power", "请按一次开关键。"),
    "mode": ("mode", "请按一次模式键。"),
    "temp_up": ("temp_c", "请按一次温度＋；若已到最高温，先调低并重新建立基线。"),
    "temp_down": ("temp_c", "请按一次温度－；若已到最低温，先调高并重新建立基线。"),
    "fan": ("fan", "请按一次风速键。"),
    "swingv": ("swingv", "请按一次上下扫风键。"),
    "swingh": ("swingh", "请按一次左右扫风键。"),
    "light": ("light", "请按一次屏显／灯光键。"),
    "sleep": ("sleep", "请按一次睡眠键。"),
    "turbo": ("turbo", "请按一次超强键。"),
    "clean": ("clean", "请按一次干燥／自清洁键；不同遥控器含义可能不同。"),
    "econo": ("econo", "请按一次节能键。"),
    "ifeel": ("ifeel", "请按一次感温／随身感键。"),
    "quiet": ("quiet", "请按一次静音键。"),
    "filter": ("filter", "请按一次健康／过滤键。"),
    "other": (None, "请按一次要补录的特殊键，稍后说明名称。"),
}
RECOMMENDED = [key for key in BUTTONS if key not in {"baseline", "other", "filter", "quiet", "ifeel", "econo"}]
STATE_FIELDS = {"power", "mode", "temp_c", "fan", "swingv", "swingh", "light", "turbo", "econo", "clean", "sleep", "ifeel", "quiet", "filter"}
BOOLEAN_FIELDS = {"power", "light", "turbo", "econo", "clean", "ifeel", "quiet", "filter"}
ID = re.compile(r"[0-9a-f]{32}")
BOOT = re.compile(r"node02-[0-9a-f]{8}")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def validate_capture(capture):
    """Validate evidence boundaries, without claiming UNKNOWN physical completeness."""
    if not isinstance(capture, dict) or not BOOT.fullmatch(str(capture.get("boot_id", ""))):
        raise ValueError("invalid_capture_identity")
    times = capture.get("timings_us")
    if (not isinstance(times, list) or not 16 <= len(times) <= 300 or times[0] != 2
            or any(type(t) is not int or not 0 < t < 131070 or t % 2 for t in times)):
        raise ValueError("invalid_capture_timings")
    if (capture.get("overflow") is not False or capture.get("truncated") is not False
            or capture.get("rawlen") != len(times) or len(times) % 2):
        raise ValueError("incomplete_capture")
    protocol = capture.get("protocol")
    bits = capture.get("bits")
    if (not isinstance(protocol, str) or not re.fullmatch(r"[A-Z0-9_]{1,32}", protocol)
            or type(bits) is not int or not 0 <= bits <= 4096):
        raise ValueError("invalid_protocol_metadata")
    state = capture.get("state")
    if protocol == "UNKNOWN" and state is not None:
        raise ValueError("unknown_protocol_has_no_verified_state")
    if state is not None:
        if not isinstance(state, dict) or set(state) - STATE_FIELDS:
            raise ValueError("invalid_state_fields")
        for field, value in state.items():
            if value is None:
                continue
            if field in BOOLEAN_FIELDS:
                if type(value) is not bool:
                    raise ValueError("invalid_state_type")
            elif (type(value) not in (int, float) or not math.isfinite(value)
                  or not -100 <= value <= 1440):
                raise ValueError("invalid_state_type")
    # The demodulating receiver does not measure the carrier frequency.
    capture = dict(capture)
    capture["state"] = dict(state) if state else None
    capture["coverage"] = ("full_protocol" if protocol == "KELVINATOR" and bits == 128
                           else "partial_protocol" if protocol == "GREE" and bits == 64 and len(times) > 140
                           else "library_state" if state else "unknown")
    capture["nominal_carrier_khz"] = 38 if protocol in {"GREE", "KELVINATOR"} else None
    capture["replayable_shape"] = all(t <= 65535 for t in times[1:])
    return capture


class LearningSession:
    def __init__(self, directory, transport, *, expected_rawlen=280):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.directory.stat().st_uid != os.geteuid():
            raise ValueError("state_owner_mismatch")
        os.chmod(self.directory, 0o700)
        self.transport = transport
        self.expected_rawlen = expected_rawlen
        self.lock = threading.RLock()
        self.data = None
        index = self.directory / "active.json"
        if index.exists():
            active = self._read(index)
            profile_id = active.get("profile_id")
            if not isinstance(profile_id, str) or not ID.fullmatch(profile_id):
                raise ValueError("invalid_profile_index")
            self.data = self._read(self.directory / (profile_id + ".json"))
            if self.data.get("profile_id") != profile_id:
                raise ValueError("profile_identity_mismatch")
            # The remote may have changed while this service was stopped.
            self.data["context_uncertain"] = True
            if self.data.get("capture"):
                self.data["capture"] = None
                self.data["status"] = "expired"
                self.data["message"] = "服务重新启动，上一接收窗口已结束；已保存的按键仍在。"
            self._save()

    def _read(self, path):
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or info.st_size > 1024 * 1024):
            raise ValueError("invalid_private_state_file")
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, path, value):
        if path.parent != self.directory:
            raise ValueError("invalid_state_path")
        if path.exists() or path.is_symlink():
            self._read(path)
        temporary = self.directory / (".write-" + uuid.uuid4().hex)
        with os.fdopen(os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w", encoding="utf-8") as output:
            json.dump(value, output, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        # Both paths are fixed children of the verified private state directory.
        os.replace(temporary, path)

    def _save(self):
        self._write(self.directory / (self.data["profile_id"] + ".json"), self.data)
        self._write(self.directory / "active.json", {"profile_id": self.data["profile_id"]})

    def public(self):
        with self.lock:
            if not self.data:
                return {"ok": True, "status": "idle", "prompt": "说“初始化空调”开始逐键学习。", "recommended_buttons": RECOMMENDED}
            data = self.data
            pending = data.get("pending") or {}
            observation = pending.get("capture") or data.get("last_capture") or {}
            observed = dict(observation.get("state") or {})
            observed.update({key: observation[key] for key in ("protocol", "bits", "rawlen", "coverage") if key in observation})
            return {"ok": True, "status": data["status"], "profile_id": data["profile_id"],
                    "button": data.get("button", "baseline"), "prompt": data.get("prompt", ""),
                    "message": data.get("message", ""), "observed": observed,
                    "changes": pending.get("changes", data.get("last_changes", {})),
                    "validation": {"basis": pending.get("basis", data.get("last_basis", "none")),
                                   "warnings": pending.get("warnings", data.get("last_warnings", []))},
                    "record_count": len(data["records"]), "recommended_buttons": RECOMMENDED}

    def start(self):
        with self.lock:
            if self.data and self.data["status"] != "cancelled":
                return self.public()
            self.data = {"schema_version": "1.0", "profile_id": uuid.uuid4().hex, "created_at": utc_now(),
                         "status": "idle", "records": [], "baseline": None, "last_capture": None,
                         "capture": None, "pending": None}
            self._save()
        return self.next("baseline")

    def next(self, button):
        if button not in BUTTONS:
            raise ValueError("unsupported_button")
        with self.lock:
            if not self.data or self.data["status"] == "cancelled":
                raise ValueError("session_not_started")
            if self.data.get("capture"):
                raise ValueError("capture_already_active")
            if len(self.data["records"]) >= 128:
                raise ValueError("profile_record_limit")
            if button != "baseline" and (self.data["baseline"] is None or self.data.get("context_uncertain")):
                raise ValueError("baseline_required")
            session_id = uuid.uuid4().hex
            self.data.update(status="arming", button=button, pending=None, message="", prompt="正在准备接收，请稍候。",
                             capture={"session_id": session_id, "button": button})
            self._save()
        try:
            self.transport.arm(session_id, 45)
        except Exception:
            with self.lock:
                if self.data["capture"] and self.data["capture"]["session_id"] == session_id:
                    self.data.update(status="expired", capture=None, context_uncertain=True,
                                     message="接收窗口未准备成功；请检查节点在线状态并重新建立基线。",
                                     prompt="先请求录制baseline，再按键。")
                    self._save()
            raise ValueError("receiver_not_ready") from None
        with self.lock:
            # A fast remote event may have completed while the ACK was in flight.
            if self.data.get("capture") and self.data["capture"]["session_id"] == session_id:
                self.data.update(status="ready", prompt=BUTTONS[button][1] + " 现在开始，45秒内按一次即可。")
                self._save()
            return self.public()

    def receive(self, session_id, capture):
        with self.lock:
            if not self.data or not self.data.get("capture") or self.data["capture"]["session_id"] != session_id:
                return False
            button = self.data["button"]
            self.data["capture"] = None
            try:
                capture = validate_capture(capture)
                if self.expected_rawlen and capture["rawlen"] != self.expected_rawlen:
                    raise ValueError("unexpected_frame_length")
            except ValueError as error:
                self.data.update(status="rejected", message="本次样本长度或分包不完整，请保持对准后重新录这一键。",
                                 prompt="本次状态不确定，请先重新录制baseline，再录本键。", pending=None, context_uncertain=True)
                self.data["last_basis"] = str(error)
                self._save()
                return False
            before = self.data.get("last_capture") or {}
            before_state, after_state = before.get("state") or {}, capture.get("state") or {}
            # Even a wrong key changes the physical remote's current state.
            self.data["last_capture"] = capture
            changes = {key: {"before": before_state.get(key), "after": after_state.get(key)} for key in STATE_FIELDS
                       if before_state.get(key) is not None and after_state.get(key) is not None
                       and before_state[key] != after_state[key]}
            warnings = []
            if capture["coverage"] == "partial_protocol":
                warnings.append("库只识别了GREE首段；保存了完整波形，扩展段尚未校验。")
            field = BUTTONS[button][0]
            if not after_state or (button != "baseline" and (not field or before_state.get(field) is None or after_state.get(field) is None)):
                basis = "manual_label_unverified"
            elif button == "baseline":
                basis = "library_baseline"
            elif field not in changes:
                basis = "no_expected_change"
            elif button == "temp_up" and after_state[field] <= before_state[field]:
                basis = "wrong_temperature_direction"
            elif button == "temp_down" and after_state[field] >= before_state[field]:
                basis = "wrong_temperature_direction"
            else:
                basis = "library_state_transition"
            self.data["pending"] = {"capture": capture, "before": before, "changes": changes, "basis": basis, "warnings": warnings}
            if basis in {"library_baseline", "library_state_transition"}:
                self._accept("library", button)
            else:
                self.data.update(status="needs_confirmation" if basis == "manual_label_unverified" else "rejected",
                                 message="库无法核对该功能，请说明刚才按键的名称。" if basis == "manual_label_unverified"
                                         else "没有看到该按键应有的变化，本次不会绑定到这个键。",
                                 prompt="可以重录、跳过；未知功能可按实际按键说明后确认暂存。")
                self._save()
            return True

    def _accept(self, source, label):
        pending = self.data["pending"]
        record = {"record_id": uuid.uuid4().hex, "recorded_at": utc_now(), "button": self.data["button"],
                  "label": label, "semantic_source": source, "semantics_verified": source == "library",
                  "appliance_response_verified": False, **pending}
        self.data["records"].append(record)
        self.data["last_capture"] = pending["capture"]
        if self.data["button"] == "baseline":
            self.data["baseline"] = pending["capture"]
            self.data["context_uncertain"] = False
        self.data.update(status="captured", capture=None, pending=None, last_changes=pending["changes"], last_basis=pending["basis"], last_warnings=pending["warnings"],
                         message="已保存样本及按键前后状态。" if source == "library" else "已按你的说明暂存；功能含义和空调效果仍未验证。",
                         prompt="请再选择一个常用键；没有的键可以跳过。")
        self._save()

    def confirm(self, label, confirmed):
        with self.lock:
            if (not self.data or not self.data.get("pending")
                    or self.data["pending"]["basis"] != "manual_label_unverified"):
                raise ValueError("manual_confirmation_not_applicable")
            if confirmed is not True or not isinstance(label, str) or not 1 <= len(label.strip()) <= 80 or any(ord(c) < 32 for c in label):
                raise ValueError("explicit_label_confirmation_required")
            self._accept("user_report_unverified", label.strip())
            return self.public()

    def expire(self, session_id, reason="expired"):
        with self.lock:
            if self.data and self.data.get("capture") and self.data["capture"]["session_id"] == session_id:
                self.data.update(status="expired", capture=None, context_uncertain=True, message="本次接收窗口结束，尚未保存该键；请重新建立基线。", prompt="先请求录制baseline，再按键。")
                self._save()

    def skip(self, reason="", *, button=None):
        with self.lock:
            if not self.data:
                raise ValueError("session_not_started")
            if button is not None and button != self.data.get("button"):
                raise ValueError("button_mismatch")
            active = self.data.get("capture")
            if active:
                self.data["context_uncertain"] = True
            self.data.update(status="captured", capture=None, pending=None, message="已跳过本键，原有样本保留。", prompt="请选择下一个键；接收中跳过需先重新建立基线。")
            self._save()
        if active:
            self.transport.cancel(active["session_id"])
        return self.public()

    def cancel(self):
        with self.lock:
            active = self.data.get("capture") if self.data else None
            if self.data:
                self.data.update(status="cancelled", capture=None, pending=None, context_uncertain=True, message="初始化已停止，已保存样本保留。", prompt="可稍后重新开始。")
                self._save()
        if active:
            self.transport.cancel(active["session_id"])
        return self.public()
