"""Bounded, pure summaries of three physical node01 HA archive channels.

received_at means HA reception time, not device measurement time. Filter noise
parameters are uncalibrated defaults; smoothing is not a trend forecast or an
accuracy claim. Importing or calling this module performs no I/O.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
from itertools import islice
import math
import re


MAX_ROWS = 100_000
WINDOW_SECONDS = 24 * 60 * 60
FRESHNESS_SECONDS = 35
CLOCK_JITTER_SECONDS = 2
MAX_WRITE_DELAY_SECONDS = 35

# entity, unit, plausibility bounds, process variance/second, measurement variance
_CHANNELS = {
    "temperature": ("sensor.xiaoxi_node01_temperature", "°C", -40, 125,
                    0.0001, 0.04),
    "humidity": ("sensor.xiaoxi_node01_humidity", "%", 0, 100,
                 0.0025, 0.25),
    "light": ("sensor.xiaoxi_node01_light", None, 0, 1, 1e-6, 1e-4),
}
ENTITY_IDS = tuple(spec[0] for spec in _CHANNELS.values())
_BOOT_ID = re.compile(r"node01-[0-9a-f]{8}")
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")


def _iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def _written_timestamp(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("invalid_written_timestamp")
    try:
        timestamp = float(value)
    except (OverflowError, ValueError):
        raise ValueError("invalid_written_timestamp") from None
    if not math.isfinite(timestamp):
        raise ValueError("invalid_written_timestamp")
    return timestamp


def _metadata(attributes, written, cutoff, now):
    if not isinstance(attributes, dict):
        raise ValueError("invalid_attributes")
    if attributes.get("simulated") is not False:
        raise ValueError("not_explicitly_physical")
    boot = attributes.get("boot_id")
    if not isinstance(boot, str) or not _BOOT_ID.fullmatch(boot):
        raise ValueError("invalid_boot_id")
    # HA's template currently omits node_id; do not invent an observed node_id.
    if "node_id" in attributes and attributes["node_id"] != "node01":
        raise ValueError("invalid_node_id")
    sequence = attributes.get("sequence")
    if (isinstance(sequence, bool) or not isinstance(sequence, int)
            or not 0 <= sequence <= 4294967295):
        raise ValueError("invalid_sequence")
    text = attributes.get("received_at")
    try:
        if not isinstance(text, str) or len(text) > 64:
            raise ValueError
        received = datetime.fromisoformat(text)
        if received.tzinfo is None or received.utcoffset() is None:
            raise ValueError
        received = received.timestamp()
    except (ValueError, TypeError, OverflowError, OSError):
        raise ValueError("invalid_received_at") from None
    if not cutoff <= received <= now:
        raise ValueError("received_outside_window")
    lag = written - received
    if not -CLOCK_JITTER_SECONDS <= lag <= MAX_WRITE_DELAY_SECONDS:
        raise ValueError("write_receive_mismatch")
    return boot, sequence, received


def _observation(row, unit, low, high):
    if row["attributes"].get("unit_of_measurement") != unit:
        raise ValueError("invalid_unit")
    text = row.get("state")
    if not isinstance(text, str) or len(text) > 64 or not _NUMBER.fullmatch(text):
        raise ValueError("invalid_state")
    value = float(text)
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError("out_of_range_or_nonfinite")
    return value


def _summarize_channel(spec, rows, cutoff, now):
    entity_id, unit, low, high, q, r = spec
    rejected = Counter()
    ordered = []
    block_current = None
    for index, row in enumerate(rows):
        try:
            written = _written_timestamp(row.get("last_updated_ts"))
        except ValueError as error:
            rejected[str(error)] += 1
            block_current = "unorderable_history"
            continue
        if written < cutoff:
            rejected["written_outside_window"] += 1
        elif written > now:
            rejected["written_in_future"] += 1
            block_current = "future_ha_state"
        else:
            ordered.append((written, index, row))
    ordered.sort(key=lambda item: (item[0], item[1]))

    count = 0
    total = 0.0
    minimum = maximum = first_received = last_received = latest = None
    estimate = variance = filter_received = None
    active_boot = None
    retired_boots = set()
    highwater = {}
    reset_count = gap_count = 0
    latest_healthy = False

    for written, _, row in ordered:
        latest_healthy = False
        try:
            boot, sequence, received = _metadata(
                row.get("attributes"), written, cutoff, now
            )
            value = _observation(row, unit, low, high)
        except ValueError as error:
            rejected[str(error)] += 1
            # Unavailable rows often retain the previous sequence/received_at.
            # Preserve them as reset markers before attempting deduplication.
            if estimate is not None:
                reset_count += 1
                estimate = variance = filter_received = None
            continue

        if boot in retired_boots:
            rejected["retired_boot"] += 1
            continue
        previous_sequence = highwater.get(boot)
        if previous_sequence is not None and sequence <= previous_sequence:
            reason = ("duplicate_sequence" if sequence == previous_sequence
                      else "sequence_regression")
            rejected[reason] += 1
            continue
        if last_received is not None and received <= last_received:
            rejected["received_time_regression"] += 1
            continue

        boot_changed = active_boot is not None and boot != active_boot
        if boot_changed:
            retired_boots.add(active_boot)
        gap = (last_received is not None
               and received - last_received > FRESHNESS_SECONDS)
        if gap:
            gap_count += 1
        if (boot_changed or gap) and estimate is not None:
            reset_count += 1
            estimate = variance = filter_received = None
        active_boot = boot
        highwater[boot] = sequence

        if estimate is None:
            estimate, variance = value, r
        else:
            predicted_variance = variance + q * (received - filter_received)
            gain = predicted_variance / (predicted_variance + r)
            estimate += gain * (value - estimate)
            variance = (1 - gain) * predicted_variance
        filter_received = received
        latest_healthy = True
        count += 1
        total += value
        minimum = value if minimum is None else min(minimum, value)
        maximum = value if maximum is None else max(maximum, value)
        if first_received is None:
            first_received = received
        last_received = received
        latest = {"kind": "archived_observation", "value": value,
                  "received_at": _iso(received)}

    current = None
    if block_current:
        status = block_current
        latest_healthy = False
    elif not ordered:
        status = "no_valid_data"
    elif not latest_healthy:
        status = "latest_ha_state_invalid"
    elif now - last_received >= FRESHNESS_SECONDS:
        status = "stale"
    else:
        status = "fresh"
        current = {
            "kind": "smoothed_current_state", "value": estimate,
            "as_of_received_at": _iso(last_received),
            "age_seconds": now - last_received,
            "algorithmic_variance": variance,
        }
    return {
        "entity_id": entity_id, "unit": unit, "count": count,
        "min": minimum, "max": maximum,
        "mean": total / count if count else None,
        "first_valid_received_at": _iso(first_received) if count else None,
        "last_valid_received_at": _iso(last_received) if count else None,
        "latest_observation": latest,
        "rejected_reasons": dict(sorted(rejected.items())),
        "reset_count": reset_count, "gap_count": gap_count,
        "filter_defaults": {"q_per_second": q, "r": r, "initial_p": r},
        "latest_ha_state_healthy": latest_healthy,
        "current_status": status, "current_estimate": current,
    }


def summarize_history(rows, *, now: datetime) -> dict:
    """Summarize at most 100000 decoded HA rows in the preceding 24 hours.

    Rows contain entity_id, string state, decoded attributes, last_updated_ts.
    Bounds apply to both HA write and HA received time, inclusive. HA write time
    may precede receipt by at most 2s or lag it by at most 35s. Missing/invalid
    metadata cannot establish a current estimate. Duplicate/regressing rows never
    refresh it. Invalid in-window states reset the filter; boot changes and gaps
    greater than 35s also reset it. Age exactly 35s is already expired.

    Temperature -40..125°C is a plausibility bound, not a sensor accuracy claim.
    Output is fixed-size aggregates, not raw time series or arbitrary attributes.
    Raises ValueError for invalid now, a noniterable input, or too many rows.
    """
    try:
        if (not isinstance(now, datetime) or now.tzinfo is None
                or now.utcoffset() is None):
            raise ValueError
        utc_now = now.astimezone(timezone.utc)
        cutoff = utc_now - timedelta(seconds=WINDOW_SECONDS)
        now_timestamp = utc_now.timestamp()
        cutoff_timestamp = cutoff.timestamp()
    except (ValueError, TypeError, OverflowError, OSError):
        raise ValueError("invalid_now") from None
    try:
        bounded_rows = list(islice(iter(rows), MAX_ROWS + 1))
    except TypeError:
        raise ValueError("invalid_rows") from None
    if len(bounded_rows) > MAX_ROWS:
        raise ValueError("too_many_rows")
    grouped = {entity: [] for entity in ENTITY_IDS}
    ignored = 0
    for row in bounded_rows:
        entity_id = row.get("entity_id") if isinstance(row, dict) else None
        if not isinstance(entity_id, str) or entity_id not in grouped:
            ignored += 1
        else:
            grouped[entity_id].append(row)
    return {
        "window": {"start": cutoff.isoformat(), "end": utc_now.isoformat(),
                   "seconds": WINDOW_SECONDS},
        "method": {
            "name": "independent_scalar_random_walk_kalman",
            "calibrated": False, "accuracy_validated": False,
            "trend_forecast": False,
            "variance_interpretation": (
                "algorithmic state variance; not a calibrated confidence interval"
            ),
            "time_basis": "HA received_at; not device measurement time",
            "clock_jitter_seconds": CLOCK_JITTER_SECONDS,
            "max_write_delay_seconds": MAX_WRITE_DELAY_SECONDS,
            "freshness_seconds": FRESHNESS_SECONDS,
        },
        "input": {"rows": len(bounded_rows), "ignored_rows": ignored},
        "channels": {
            name: _summarize_channel(spec, grouped[spec[0]],
                                     cutoff_timestamp, now_timestamp)
            for name, spec in _CHANNELS.items()
        },
    }
