"""Bounded, report-only comparison of saved node02 NEC timing evidence.

Sources are the cached IRremoteESP8266 2.9.0 src/ files:
ir_NEC.h:27-46 (constants), ir_NEC.cpp:28-39 (MSB-first sending),
IRrecv.h:20-37 (offset/tick/tolerance/excess), and IRrecv.cpp:194-226,
1257-1407,1495-1536,1608-1682 (capture and matching).

CLI input is a JSON array of decoded MQTT event payloads. This module never
fetches evidence, connects to hardware, emits infrared, or controls a device.
"""

import argparse
import json
from pathlib import Path
import re
from statistics import median


MAX_EVENTS = 256
MAX_TIMINGS = 300
MAX_DURATION_US = 131070  # UINT16_MAX * kRawTick; not optical saturation.
MAX_JSON_BYTES = 1024 * 1024
UINT32_MAX = 2 ** 32 - 1
BOOT_PATTERN = re.compile(r"node02-[0-9a-f]{8}", re.ASCII)
DETAIL_PATTERN = re.compile(
    r"raw_timing capture=([0-9]{1,10}) rawlen=([0-9]{1,5}) "
    r"kept=([0-9]{1,3}) truncated=([01]) overflow=([01]) "
    r"offset=([0-9]{1,3}) count=([0-9]{1,2}) unit=us "
    r"times=([0-9]{1,6}(?:,[0-9]{1,6}){0,15})", re.ASCII
)
VALUE = 0x5A02A55A
BITS = f"{VALUE:032b}"


def _uint(value, maximum, label):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"{label} must be an unsigned integer <= {maximum}")
    return value


def _valid_boot(boot_id):
    if not isinstance(boot_id, str) or BOOT_PATTERN.fullmatch(boot_id) is None:
        raise ValueError("boot_id must have form node02-xxxxxxxx (lowercase hex)")


def assemble_capture(events, *, boot_id: str, capture_sequence: int) -> dict:
    """Assemble one complete bounded capture; reject even identical duplicates.

    Input consists of decoded event dicts, with at most 256 entries. Ordinary
    event types are ignored. Other valid boots/captures are never mixed into
    the requested capture. Malformed timing events fail closed. ValueError
    means the evidence must not be analyzed as a complete capture.
    """
    _valid_boot(boot_id)
    _uint(capture_sequence, UINT32_MAX, "capture_sequence")
    if isinstance(events, (str, bytes, dict)):
        raise ValueError("events must be an iterable of event dicts")
    try:
        iterator = iter(events)
    except TypeError as exc:
        raise ValueError("events must be an iterable of event dicts") from exc
    chunks = {}
    metadata = None
    for index, event in enumerate(iterator):
        if index >= MAX_EVENTS:
            raise ValueError("too many events (maximum 256)")
        if not isinstance(event, dict):
            raise ValueError("each event must be a dict")
        if event.get("event_type") != "ir_raw_timing":
            continue
        _valid_boot(event.get("boot_id"))
        if (event.get("schema_version") != "1.0" or
                event.get("node_id") != "node02" or
                event.get("simulated") is not False):
            raise ValueError("invalid timing event envelope metadata")
        sequence = _uint(event.get("sequence"), UINT32_MAX, "sequence")
        detail = event.get("detail")
        match = (DETAIL_PATTERN.fullmatch(detail)
                 if isinstance(detail, str) and len(detail) <= 256 else None)
        if match is None:
            raise ValueError("invalid raw_timing ASCII detail format")
        capture, rawlen, kept, truncated, overflow, offset, count = (
            int(value) for value in match.groups()[:7]
        )
        _uint(capture, UINT32_MAX, "capture")
        _uint(rawlen, 65535, "rawlen")
        times = [int(value) for value in match.group(8).split(",")]
        # Historical firmware capped captures at 160; retain those loss flags.
        valid_kept = kept == min(rawlen, MAX_TIMINGS) or (
            rawlen > 160 and kept == 160
        )
        if (rawlen == 0 or not valid_kept or
                truncated != int(rawlen > kept) or
                offset % 16 or offset >= kept or
                not 1 <= count <= 16 or count != min(16, kept - offset) or
                len(times) != count or any(t > MAX_DURATION_US for t in times)):
            raise ValueError("invalid timing chunk size, offset, flags or duration")
        if sequence != (capture + offset // 16) % (2 ** 32):
            raise ValueError("event sequence does not match capture plus part")
        if event["boot_id"] != boot_id or capture != capture_sequence:
            continue
        current_metadata = (rawlen, kept, truncated, overflow)
        if metadata is not None and current_metadata != metadata:
            raise ValueError("inconsistent capture metadata")
        metadata = current_metadata
        if offset in chunks:
            kind = "duplicate" if chunks[offset] == times else "conflicting"
            raise ValueError(f"{kind} timing chunk at offset {offset}")
        chunks[offset] = times
    if metadata is None:
        raise ValueError("incomplete capture: no matching timing chunks")
    rawlen, kept, truncated, overflow = metadata
    missing = sorted(set(range(0, kept, 16)) - chunks.keys())
    if missing:
        raise ValueError(f"incomplete capture: missing offsets {missing}")
    timings = [duration for offset in sorted(chunks) for duration in chunks[offset]]
    return {
        "boot_id": boot_id, "capture_sequence": capture_sequence,
        "rawlen": rawlen, "kept": kept, "truncated": bool(truncated),
        "overflow": bool(overflow), "timings_us": timings,
        "saturated_indices": [i for i, value in enumerate(timings)
                              if value == MAX_DURATION_US],
    }


def _window(duration, *, mark):
    # match() checks raw_ticks*2 against floor(0.75*target)..floor(1.25*target)+1.
    target = duration + 50 if mark else duration - 50
    low, high = int(target * 0.75), int(target * 1.25) + 1
    return [(low + 1) // 2 * 2, high // 2 * 2]  # representable even microseconds


def _stats(values, expected):
    if not values:
        return {"count": 0, "min_us": None, "max_us": None,
                "median_us": None, "median_ratio": None}
    midpoint = median(values)
    return {"count": len(values), "min_us": min(values), "max_us": max(values),
            "median_us": midpoint, "median_ratio": midpoint / expected}


def analyze_nec(timings_us: list[int]) -> dict:
    """Compare a bounded raw_us list to this fixed NEC reference, not a decoder.

    Index zero is the synthetic sentinel. Its value is reported separately and
    excluded from pulse matching. Capture overflow/truncation flags are not
    encoded in durations; callers must retain assemble_capture's metadata.
    """
    if not isinstance(timings_us, list) or len(timings_us) > MAX_TIMINGS:
        raise ValueError("timings_us must be a list with at most 300 entries")
    for duration in timings_us:
        _uint(duration, MAX_DURATION_US, "duration")
    expected = [2, 8960, 4480]
    labels = ["sentinel", "header_mark", "header_space"]
    for bit in BITS:
        expected.extend((560, 1680 if bit == "1" else 560))
        labels.extend(("bit_mark", "one_space" if bit == "1" else "zero_space"))
    expected.append(560)
    labels.append("bit_mark")
    windows = {
        "header_mark": _window(8960, mark=True),
        "header_space": _window(4480, mark=False),
        "bit_mark": _window(560, mark=True),
        "zero_space": _window(560, mark=False),
        "one_space": _window(1680, mark=False),
    }
    mismatches = []
    for index in range(1, min(len(timings_us), len(expected))):
        observed = timings_us[index]
        low, high = windows[labels[index]]
        if not low <= observed <= high:
            mismatches.append({
                "index": index, "field": labels[index],
                "expected_us": expected[index], "observed_us": observed,
                "window_us": [low, high],
                "relative_error": (observed - expected[index]) / expected[index],
            })
    observed_bits = []
    for bit in range(32):
        index = 4 + bit * 2
        duration = timings_us[index] if index < len(timings_us) else None
        if (duration is not None and
                windows["one_space"][0] <= duration <= windows["one_space"][1]):
            observed_bits.append("1")
        elif (duration is not None and
                windows["zero_space"][0] <= duration <= windows["zero_space"][1]):
            observed_bits.append("0")
        else:
            observed_bits.append("?")
    observed_bits = "".join(observed_bits)
    unaligned = [i for i, value in enumerate(timings_us) if value % 2]
    limits = [i for i, value in enumerate(timings_us) if value == MAX_DURATION_US]
    matches = (len(timings_us) == 68 and not mismatches and
               not any(index > 0 for index in unaligned))
    groups = {
        "header_mark": _stats(timings_us[1:2], 8960),
        "header_space": _stats(timings_us[2:3], 4480),
        "data_marks": _stats(timings_us[3:67:2], 560),
        "footer_mark": _stats(timings_us[67:68], 560),
    }
    for symbol, name, nominal in (("0", "zero_spaces", 560),
                                  ("1", "one_spaces", 1680)):
        values = [timings_us[4 + bit * 2] for bit in range(32)
                  if BITS[bit] == symbol and 4 + bit * 2 < len(timings_us)]
        groups[name] = _stats(values, nominal)
    conclusions = []
    if matches:
        conclusions.append(
            "All 67 frame intervals fit the fixed NEC reference windows."
        )
    else:
        if len(timings_us) != 68:
            conclusions.append(
                f"Expected rawlen 68; received {len(timings_us)} durations."
            )
        if mismatches:
            conclusions.append(
                f"{len(mismatches)} frame intervals miss the fixed reference "
                "windows."
            )
        if unaligned:
            conclusions.append(
                "Odd microseconds cannot come directly from raw_ticks * 2."
            )
    if timings_us and timings_us[0] != 2:
        conclusions.append(
            "Index 0 differs from the library sentinel; it is excluded from "
            "pulse matching."
        )
    if limits:
        conclusions.append(
            "Values at 131070 us are storage-limit candidates, not proof of "
            "optical saturation."
        )
    conclusions.append(
        "Timing ratios do not establish a clock fault, carrier frequency, "
        "optical power, or a physical decode."
    )
    return {
        "expected": {
            "library": "IRremoteESP8266 2.9.0", "value_hex": "0x5A02A55A",
            "bits_msb_first": BITS, "rawlen": 68, "raw_tick_us": 2,
            "timings_us": expected, "frame_us": 64400, "min_gap_us": 22400,
            "min_command_us": 108080, "nominal_send_gap_us": 43680,
            "carrier_hz": 38000, "duty_percent": 33,
        },
        "rawlen": len(timings_us),
        "sentinel_us": timings_us[0] if timings_us else None,
        "sentinel_matches_library": bool(timings_us and timings_us[0] == 2),
        "matches_expected_timing": matches, "windows_us": windows,
        "mismatches": mismatches, "observed_bits_by_space": observed_bits,
        "space_value_hex": (f"0x{int(observed_bits, 2):08X}"
                            if "?" not in observed_bits else None),
        "pulse_groups": groups, "non_tick_aligned_indices": unaligned,
        "storage_limit_indices": limits, "conclusions": conclusions,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path, help="JSON array of decoded MQTT events")
    parser.add_argument("--boot-id", required=True)
    parser.add_argument("--capture-sequence", required=True, type=int)
    args = parser.parse_args(argv)
    try:
        with args.evidence.open("rb") as stream:
            content = stream.read(MAX_JSON_BYTES + 1)
        if len(content) > MAX_JSON_BYTES:
            raise ValueError("JSON evidence exceeds 1 MiB")
        events = json.loads(content)
        capture = assemble_capture(events, boot_id=args.boot_id,
                                   capture_sequence=args.capture_sequence)
        comparison = analyze_nec(capture["timings_us"])
        eligible = not (capture["truncated"] or capture["overflow"] or
                        capture["saturated_indices"])
        print(json.dumps({"capture": capture, "nec_comparison": comparison,
                          "capture_without_loss_flags": eligible}, indent=2))
    except (OSError, ValueError, UnicodeError) as exc:
        parser.exit(2, f"nec_timing: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
