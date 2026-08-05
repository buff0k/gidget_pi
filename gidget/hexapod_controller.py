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
import signal
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

# Gait/IK is still stepped every 20ms tick for smooth motion, but the
# board is only sent a new frame this often. MicroPython parsing a full
# 18-channel JSON line plus 18 ServoCluster.value() calls every single
# 20ms tick appears to be more than it can sustain - the Pi's write
# buffer backs up over time and ser.write() eventually times out, even
# though the read side alone (chunked, not byte-by-byte) keeps up fine.
# 20Hz on the wire is still smooth enough for servo motion.
SERIAL_SEND_INTERVAL_SECONDS = 0.05

# Calibrated neutral: 90 deg plus each servo's small per-joint trim
# (COXA_CAL/FEMUR_CAL/TIBIA_CAL, a few degrees at most), NOT a flat 90 for
# every channel. Flat 90 is close enough to "neutral" to be safe, but it is
# not each servo's true calibrated center, which is what idle/manual should
# rest at when nothing else is commanding the leg. This is distinct from the
# home-stance danger below: home-stance angles are tens of degrees off
# center (e.g. femur=146), calibration trim is single digits.
NEUTRAL_CHANNELS = hk.angles_to_channels(hk.set_all_90())

_shutdown_requested = False


def request_shutdown(signum, frame):
    global _shutdown_requested
    _shutdown_requested = True


signal.signal(signal.SIGTERM, request_shutdown)
signal.signal(signal.SIGINT, request_shutdown)


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
    # write_timeout is deliberately more forgiving than the 20ms tick
    # target: a transient stall on the board (ADC read, JSON encode, print)
    # should cost one slow tick, not blow up the whole connection and force
    # a reconnect - repeated reconnect churn is itself a plausible
    # contributor to the RP2040's USB CDC stack wedging under load.
    return serial.Serial(SERIAL_PORT, BAUDRATE, timeout=0, write_timeout=0.2)


def leg_state_payload(leg_xyz, angles, channels, mode, gait, fast, malformed_lines, telemetry, connected):
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
        # Raw 18-channel angles actually sent this tick, regardless of mode -
        # what the manual/diagnostics panel reflects back for each slider.
        "channels": [round(c, 1) for c in channels],
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
        "channels": [],
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
                last_send_time = 0.0

                while True:
                    tick_start = time.monotonic()

                    if _shutdown_requested:
                        # Ask the board to reset itself cleanly rather than
                        # just dropping the connection - a bare disconnect
                        # leaves it wherever it was mid-loop, which is
                        # exactly the state that makes a subsequent
                        # mpremote connection (e.g. firmware flashing
                        # during update.sh) unreliable to interrupt into.
                        # A real reset behaves like the physical reset
                        # button, which has been reliable throughout.
                        try:
                            ser.write(b'{"reset":true}\n')
                            ser.flush()
                        except Exception:
                            pass
                        return

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

                    if mode == "calibrate_90":
                        angles = hk.set_all_90()
                        leg_xyz = hk.home_leg_xyz()
                        channels = hk.angles_to_channels(angles)
                    elif mode == "manual":
                        # Bypasses gait/IK entirely - raw per-channel angles
                        # for wiring/bring-up diagnostics (e.g. testing a
                        # couple of servos before the full rig is wired, or
                        # probing one channel's range). Leg/angle state is
                        # left at its last known value since it's not
                        # meaningful without an IK solve.
                        angles = previous_angles
                        leg_xyz = gait_state.leg_xyz
                        manual_channels = command.get("manual_channels")
                        if isinstance(manual_channels, list) and len(manual_channels) == 18:
                            channels = [hk.clamp(float(v), 0.0, 180.0) for v in manual_channels]
                        else:
                            channels = list(NEUTRAL_CHANNELS)
                    elif mode == "walk":
                        leg_xyz = hk.step_gait(gait_state, commanded_x, commanded_y, commanded_r, fast)
                        angles = hk.leg_angles_for_frame(leg_xyz, previous_angles)
                        channels = hk.angles_to_channels(angles)
                    else:
                        # "idle" (and any unrecognized mode, including the
                        # stale-command fallback in read_command()) is a
                        # true calibrated-neutral state - NOT the IK-computed
                        # home stance. That distinction matters: home-stance
                        # joint angles (visible earlier as e.g. femur=146,
                        # tibia=35) are only safe once servo horns are
                        # physically calibrated against a known 90 deg
                        # reference. Idle must never depend on that having
                        # happened yet - but it should still rest at each
                        # servo's small per-joint trim (NEUTRAL_CHANNELS),
                        # not an untrimmed flat 90 for every channel.
                        angles = previous_angles
                        leg_xyz = gait_state.leg_xyz
                        channels = list(NEUTRAL_CHANNELS)

                    previous_angles = angles

                    now = time.monotonic()
                    if now - last_send_time >= SERIAL_SEND_INTERVAL_SECONDS:
                        frame = json.dumps(
                            {"t": round(time.time(), 2), "ch": [round(a, 1) for a in channels]},
                            separators=(",", ":"),
                        ) + "\n"
                        ser.write(frame.encode("ascii"))
                        last_send_time = now

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
                        leg_xyz, angles, channels, active_mode, gait_state.gait, fast,
                        malformed_lines, telemetry, connected,
                    ))

                    elapsed = time.monotonic() - tick_start
                    time.sleep(max(0.0, FRAME_SECONDS - elapsed))

        except Exception as e:
            save_state(error_state_payload(e))
            time.sleep(2)


if __name__ == "__main__":
    main()
