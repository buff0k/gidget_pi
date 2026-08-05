#!/usr/bin/env python3
"""
Hexapod channel calibration + wiring map - persisted config, not hardcoded
constants.

This is deliberately separate from hexapod_kinematics.py's geometry
constants (COXA_LENGTH, HOME_X/Y/Z, BODY_X/Y/Z, ...), which describe the
chassis design and ARE portable across a mechanically-identical build.
Trim (how far a channel's true physical center sits from a literal 90 deg
command) and the channel map (which of the 18 channels drives which
leg/joint) are NOT portable - they're facts about this specific robot's
individual servos and wiring, and were wrongly treated as constants ported
from a reference build early in this project. Both are discovered by hand
via the Calibration/Channel Mapping panels on the hexapod web page and
stored here so they survive service restarts and repo updates.

Read by hexapod_controller.py (applied every tick) and written by
pages/hexapod.py's calibration API (one-off, user-triggered edits - not a
high-frequency path, so plain-file writes here are fine, unlike the tmpfs
state/command files).
"""

import json
from pathlib import Path

from hexapod_kinematics import CHANNEL_COUNT, LEG_COUNT, JOINTS


CONFIG_DIR = Path("/opt/gidget/config")
CALIBRATION_FILE = CONFIG_DIR / "hexapod_calibration.json"

# How far a single nudge/save may move a channel's trim from zero. Real
# calibration trim is a few degrees at most (spline-tooth granularity on
# the servo horn) - anything approaching this ceiling almost certainly
# means the wrong channel is assigned, not that this channel needs more
# trim.
MAX_TRIM_DEG = 30.0


def _default_channel_map():
    """
    Sequential guess (leg 0 = channels 0-2, leg 1 = channels 3-5, ...) -
    the same starting placeholder hexapod_kinematics.py originally shipped
    with, kept as the default until confirmed per-channel via the Channel
    Mapping panel's test-jog button.
    """
    channel_map = {}
    channel = 0
    for leg in range(LEG_COUNT):
        for joint in JOINTS:
            channel_map[str(channel)] = {"leg": leg, "joint": joint}
            channel += 1
    return channel_map


def default_calibration():
    return {
        "channel_map": _default_channel_map(),
        "trim_deg": {str(ch): 0.0 for ch in range(CHANNEL_COUNT)},
    }


def _write_atomic(data):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = CALIBRATION_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(data, indent=2, sort_keys=True))
    temp_file.replace(CALIBRATION_FILE)


def calibration_mtime():
    """None if the file doesn't exist yet - callers use this to decide
    whether a reload is needed without reading the file on every check."""
    try:
        return CALIBRATION_FILE.stat().st_mtime
    except FileNotFoundError:
        return None


def load_calibration():
    """
    Loads the calibration file, creating it with defaults if missing so a
    fresh install or a dev environment without it never crashes - it just
    starts at "every channel at 90, sequential channel guess" until
    calibrated. Backfills any channel missing from an existing file (e.g.
    after a CHANNEL_COUNT change) instead of discarding the whole file over
    one bad entry.
    """
    if not CALIBRATION_FILE.exists():
        data = default_calibration()
        _write_atomic(data)
        return data

    try:
        data = json.loads(CALIBRATION_FILE.read_text())
    except Exception:
        data = default_calibration()
        _write_atomic(data)
        return data

    defaults = default_calibration()
    data.setdefault("channel_map", {})
    data.setdefault("trim_deg", {})
    changed = False

    for ch in range(CHANNEL_COUNT):
        key = str(ch)
        if key not in data["channel_map"]:
            data["channel_map"][key] = defaults["channel_map"][key]
            changed = True
        if key not in data["trim_deg"]:
            data["trim_deg"][key] = 0.0
            changed = True

    if changed:
        _write_atomic(data)

    return data


def set_trim(channel, trim_deg):
    trim_deg = max(-MAX_TRIM_DEG, min(MAX_TRIM_DEG, float(trim_deg)))
    data = load_calibration()
    data["trim_deg"][str(int(channel))] = trim_deg
    _write_atomic(data)
    return data


def nudge_trim(channel, delta_deg):
    data = load_calibration()
    key = str(int(channel))
    current = float(data["trim_deg"].get(key, 0.0))
    new_value = max(-MAX_TRIM_DEG, min(MAX_TRIM_DEG, current + float(delta_deg)))
    data["trim_deg"][key] = new_value
    _write_atomic(data)
    return data


def set_channel_map_entry(channel, leg, joint):
    channel = int(channel)
    leg = int(leg)

    if joint not in JOINTS:
        raise ValueError(f"invalid joint {joint!r}")
    if not (0 <= leg < LEG_COUNT):
        raise ValueError(f"invalid leg {leg!r}")
    if not (0 <= channel < CHANNEL_COUNT):
        raise ValueError(f"invalid channel {channel!r}")

    data = load_calibration()
    data["channel_map"][str(channel)] = {"leg": leg, "joint": joint}
    _write_atomic(data)
    return data


def channel_map_by_leg(data):
    """
    {leg: {joint: channel}} - the shape hexapod_kinematics.angles_to_channels
    actually consumes, derived from the stored {channel: {leg, joint}} shape
    (which is what the Channel Mapping panel naturally edits, one channel
    at a time).
    """
    result = {leg: {} for leg in range(LEG_COUNT)}
    for channel_str, entry in data["channel_map"].items():
        result[entry["leg"]][entry["joint"]] = int(channel_str)
    return result


def trim_by_channel(data):
    return {int(ch): float(v) for ch, v in data["trim_deg"].items()}
