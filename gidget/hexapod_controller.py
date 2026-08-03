#!/usr/bin/env python3
"""
Hexapod controller service.

Owns the Servo 2040 USB-serial connection exclusively. All gait/IK math
lives in hexapod_kinematics.py (pure, no hardware); this module is the only
place serial I/O and tmpfs state/command files are touched, matching the
one-owner-per-device pattern used by every other reader in this repo.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import serial

import hexapod_kinematics as hk


SERIAL_PORT = os.environ.get("GIDGET_HEXAPOD_SERIAL_PORT", "/dev/gidget-servo2040")
BAUDRATE = 115200

SHM_DIR = Path("/dev/shm/gidget")
STATE_FILE = SHM_DIR / "hexapod_state.json"
COMMAND_FILE = SHM_DIR / "hexapod_command.json"

FRAME_SECONDS = hk.FRAME_TIME_MS / 1000.0

# Deadman timeout: a command older than this (or missing/corrupt) is treated
# as fully absent, forcing idle/neutral - protects against a dropped
# connection, closed browser tab, or locked phone screen leaving the robot
# walking on a stale command.
COMMAND_STALE_SECONDS = 0.5

# How long without a telemetry line from the board before the dashboard
# should show it as "not reporting" even if the serial port is still open.
TELEMETRY_STALE_SECONDS = 3.0


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_json_file(path):
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def save_state(data):
    SHM_DIR.mkdir(parents=True, exist_ok=True)
    data["timestamp"] = utc_now_iso()
    temp_file = STATE_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(data, separators=(",", ":")))
    temp_file.replace(STATE_FILE)


def clamp_command_axis(value):
    try:
        return hk.clamp(float(value), -127, 127)
    except Exception:
        return 0.0


def read_command():
    """
    Latest command from the web process, with the staleness/deadman check
    applied. A missing file, corrupt JSON, or a command older than
    COMMAND_STALE_SECONDS all fall back to the same neutral/idle command.
    """
    command = load_json_file(COMMAND_FILE)
    issued_at = command.get("issued_at")
    age = None if issued_at is None else time.time() - issued_at

    if not command or age is None or age > COMMAND_STALE_SECONDS:
        return {"mode": "idle", "gait": "tripod", "x": 0, "y": 0, "r": 0, "speed": 1.0, "stale": True}

    command["stale"] = False
    return command


class SerialLineReader:
    """Non-blocking newline-delimited JSON reader over a pyserial handle."""

    def __init__(self, ser):
        self._ser = ser
        self._buffer = ""

    def poll_lines(self):
        waiting = self._ser.in_waiting

        if waiting:
            self._buffer += self._ser.read(waiting).decode("utf-8", errors="ignore")

        lines = []

        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if line:
                lines.append(line)

        return lines


def open_serial():
    return serial.Serial(SERIAL_PORT, BAUDRATE, timeout=0, write_timeout=0.05)


def leg_state_payload(leg_xyz, angles, mode, gait, fast, malformed_lines, telemetry, connected):
    legs = []

    for leg in range(hk.LEG_COUNT):
        x, y, z = leg_xyz[leg]
        coxa, femur, tibia = angles[leg]
        legs.append({
            "index": leg,
            # Coxa-relative (matches the reference sketch's coordinate frame).
            "x": round(x, 1),
            "y": round(y, 1),
            "z": round(z, 1),
            # Body-center-relative - what the web visualizer draws, so it
            # doesn't need to know BODY_X/BODY_Y itself.
            "mount_x": hk.BODY_X[leg],
            "mount_y": hk.BODY_Y[leg],
            "toe_x": round(hk.BODY_X[leg] + x, 1),
            "toe_y": round(hk.BODY_Y[leg] + y, 1),
            "coxa_deg": round(coxa, 1),
            "femur_deg": round(femur, 1),
            "tibia_deg": round(tibia, 1),
            "channels": hk.CHANNEL_MAP[leg],
        })

    return {
        "ok": True,
        "error": None,
        "connected": connected,
        "mode": mode,
        "gait": gait,
        "fast": fast,
        "legs": legs,
        "telemetry": telemetry,
        "malformed_lines": malformed_lines,
    }


def error_state_payload(error):
    return {
        "ok": False,
        "error": str(error),
        "connected": False,
        "mode": "idle",
        "gait": None,
        "fast": None,
        "legs": [],
        "telemetry": {},
        "malformed_lines": 0,
    }


def main():
    gait_state = hk.GaitState()
    previous_angles = hk.set_all_90()
    malformed_lines = 0
    telemetry = {}
    last_telemetry_time = 0.0
    active_gait = gait_state.gait
    active_mode = "idle"

    while True:
        try:
            with open_serial() as ser:
                reader = SerialLineReader(ser)

                while True:
                    tick_start = time.monotonic()
                    command = read_command()

                    mode = command.get("mode", "idle")
                    gait = command.get("gait", "tripod")
                    if gait not in hk.GAIT_NAMES:
                        gait = "tripod"
                    fast = float(command.get("speed", 1.0)) >= 1.0

                    commanded_x = clamp_command_axis(command.get("x", 0))
                    commanded_y = clamp_command_axis(command.get("y", 0))
                    commanded_r = clamp_command_axis(command.get("r", 0))

                    # Reset the gait state machine on a gait change, or when
                    # (re)entering walk mode - avoids resuming mid-stride
                    # from a stale leg position.
                    if gait != active_gait or (mode == "walk" and active_mode != "walk"):
                        hk.reset_gait_state(gait_state, gait)
                        active_gait = gait
                    active_mode = mode

                    if mode == "idle":
                        commanded_x = commanded_y = commanded_r = 0.0

                    if mode == "calibrate_90":
                        angles = hk.set_all_90()
                        leg_xyz = hk.home_leg_xyz()
                    else:
                        leg_xyz = hk.step_gait(gait_state, commanded_x, commanded_y, commanded_r, fast)
                        angles = hk.leg_angles_for_frame(leg_xyz, previous_angles)

                    previous_angles = angles
                    channels = hk.angles_to_channels(angles)

                    frame = json.dumps(
                        {"t": time.time(), "ch": [round(a, 1) for a in channels]},
                        separators=(",", ":"),
                    ) + "\n"
                    ser.write(frame.encode("ascii"))

                    for line in reader.poll_lines():
                        try:
                            payload = json.loads(line)
                        except Exception:
                            malformed_lines += 1
                            continue

                        if payload.get("type") == "telemetry":
                            telemetry = payload
                            last_telemetry_time = time.monotonic()

                    connected = bool(last_telemetry_time) and (
                        time.monotonic() - last_telemetry_time < TELEMETRY_STALE_SECONDS
                    )

                    save_state(leg_state_payload(
                        leg_xyz, angles, active_mode, gait_state.gait, fast,
                        malformed_lines, telemetry, connected,
                    ))

                    elapsed = time.monotonic() - tick_start
                    time.sleep(max(0.0, FRAME_SECONDS - elapsed))

        except Exception as e:
            save_state(error_state_payload(e))
            time.sleep(2)


if __name__ == "__main__":
    main()
