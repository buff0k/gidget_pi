#!/usr/bin/env python3

import json
import math
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import board
import bmi160 as BMI160


IMU_FILE = Path("/opt/gidget/imu_state.json")
POLL_SECONDS = 0.20
WRITE_SECONDS = 0.75
HISTORY_LIMIT = 60
STANDARD_GRAVITY = 9.80665


class ImuUnavailable(RuntimeError):
    pass


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def round_or_none(value, decimals=2):
    try:
        if value is None:
            return None
        return round(float(value), decimals)
    except Exception:
        return None


def save_imu_state(data):
    data["timestamp"] = utc_now_iso()
    temp_file = IMU_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(data, separators=(",", ":")))
    temp_file.replace(IMU_FILE)


def init_imu():
    i2c = board.I2C()

    try:
        sensor = BMI160.BMI160(i2c)
    except Exception as e:
        raise ImuUnavailable(f"BMI160 not found on I2C bus: {e}") from e

    # Keep ranges conservative and readable for initial robot motion telemetry.
    for attr, value in (
        ("acceleration_range", getattr(BMI160, "ACCEL_RANGE_4G", None)),
        ("gyro_range", getattr(BMI160, "GYRO_RANGE_500", None)),
    ):
        if value is not None:
            try:
                setattr(sensor, attr, value)
            except Exception:
                pass

    return sensor


def vector_magnitude(x, y, z):
    try:
        return math.sqrt((float(x) * float(x)) + (float(y) * float(y)) + (float(z) * float(z)))
    except Exception:
        return None


def tilt_from_accel(ax, ay, az):
    """
    Simple accelerometer-only pitch/roll estimate.

    This is useful when mostly stationary. It is not a fused AHRS estimate and
    will be distorted by vehicle acceleration.
    """
    try:
        ax = float(ax)
        ay = float(ay)
        az = float(az)
        roll = math.degrees(math.atan2(ay, az))
        pitch = math.degrees(math.atan2(-ax, math.sqrt((ay * ay) + (az * az))))
        return pitch, roll
    except Exception:
        return None, None


def sample_imu(sensor):
    ax, ay, az = sensor.acceleration
    gx, gy, gz = sensor.gyro

    acc_mag = vector_magnitude(ax, ay, az)
    gyro_mag = vector_magnitude(gx, gy, gz)
    pitch, roll = tilt_from_accel(ax, ay, az)

    return {
        "acceleration": {
            "x_mps2": round_or_none(ax, 3),
            "y_mps2": round_or_none(ay, 3),
            "z_mps2": round_or_none(az, 3),
            "magnitude_mps2": round_or_none(acc_mag, 3),
            "magnitude_g": round_or_none(None if acc_mag is None else acc_mag / STANDARD_GRAVITY, 3),
        },
        "gyro": {
            "x_dps": round_or_none(gx, 3),
            "y_dps": round_or_none(gy, 3),
            "z_dps": round_or_none(gz, 3),
            "magnitude_dps": round_or_none(gyro_mag, 3),
        },
        "orientation": {
            "pitch_deg": round_or_none(pitch, 2),
            "roll_deg": round_or_none(roll, 2),
            "source": "accelerometer_tilt",
        },
        "temperature_c": round_or_none(getattr(sensor, "temperature", None), 2),
    }


def history_point(index, sample):
    accel = sample.get("acceleration", {})
    gyro = sample.get("gyro", {})
    orientation = sample.get("orientation", {})

    return {
        "x": index,
        "accel_g": accel.get("magnitude_g"),
        "gyro_dps": gyro.get("magnitude_dps"),
        "pitch_deg": orientation.get("pitch_deg"),
        "roll_deg": orientation.get("roll_deg"),
    }


def state_payload(history, latest, sample_index):
    return {
        "ok": True,
        "error": None,
        "sensor": "BMI160",
        "address_hint": "0x68 or 0x69",
        "sample_index": sample_index,
        "poll_seconds": POLL_SECONDS,
        "write_seconds": WRITE_SECONDS,
        **latest,
        "history": list(history),
        "history_limit": HISTORY_LIMIT,
    }


def error_state(error, history):
    return {
        "ok": False,
        "error": str(error),
        "sensor": "BMI160",
        "address_hint": "0x68 or 0x69",
        "sample_index": None,
        "poll_seconds": POLL_SECONDS,
        "write_seconds": WRITE_SECONDS,
        "acceleration": {},
        "gyro": {},
        "orientation": {},
        "temperature_c": None,
        "history": list(history),
        "history_limit": HISTORY_LIMIT,
    }


def main():
    history = deque(maxlen=HISTORY_LIMIT)
    sample_index = 0

    while True:
        try:
            sensor = init_imu()
            last_write = 0.0
            latest = None

            while True:
                latest = sample_imu(sensor)
                sample_index += 1
                history.append(history_point(sample_index, latest))

                now = time.monotonic()
                if now - last_write >= WRITE_SECONDS:
                    save_imu_state(state_payload(history, latest, sample_index))
                    last_write = now

                time.sleep(POLL_SECONDS)

        except Exception as e:
            save_imu_state(error_state(e, history))
            time.sleep(5)


if __name__ == "__main__":
    main()
