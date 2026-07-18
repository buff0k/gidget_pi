#!/usr/bin/env python3

import json
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import board
import busio

try:
    import adafruit_vl53l1x
except Exception:
    adafruit_vl53l1x = None

try:
    import adafruit_vl53l0x
except Exception:
    adafruit_vl53l0x = None


LIDAR_FILE = Path("/opt/gidget/lidar_state.json")
POLL_SECONDS = 0.10
WRITE_SECONDS = 0.50
HISTORY_LIMIT = 60
I2C_ADDRESS = 0x29
MAX_DISPLAY_MM = 4000


class LidarUnavailable(RuntimeError):
    pass


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def save_lidar_state(data):
    data["timestamp"] = utc_now_iso()
    temp_file = LIDAR_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(data, separators=(",", ":")))
    temp_file.replace(LIDAR_FILE)


def round_or_none(value, decimals=2):
    try:
        if value is None:
            return None
        return round(float(value), decimals)
    except Exception:
        return None


def init_lidar():
    i2c = busio.I2C(board.SCL, board.SDA)

    if adafruit_vl53l1x is not None:
        try:
            sensor = adafruit_vl53l1x.VL53L1X(i2c, address=I2C_ADDRESS)
            sensor.distance_mode = 2
            sensor.timing_budget = 50
            sensor.start_ranging()
            return "VL53L1X", sensor
        except Exception:
            pass

    if adafruit_vl53l0x is not None:
        try:
            sensor = adafruit_vl53l0x.VL53L0X(i2c, address=I2C_ADDRESS)
            return "VL53L0X", sensor
        except Exception:
            pass

    raise LidarUnavailable("No VL53L0X/VL53L1X sensor found at 0x29")


def read_distance_mm(sensor_type, sensor):
    if sensor_type == "VL53L1X":
        if not sensor.data_ready:
            return None

        distance_cm = sensor.distance
        sensor.clear_interrupt()

        if distance_cm is None:
            return None

        return float(distance_cm) * 10.0

    distance_mm = sensor.range

    if distance_mm is None:
        return None

    return float(distance_mm)


def point_from_sample(index, distance_mm):
    safe_distance = max(0, min(MAX_DISPLAY_MM, distance_mm or 0))

    return {
        "x": index,
        "y": safe_distance,
        "distance_mm": round_or_none(distance_mm, 1),
    }


def state_payload(sensor_type, history, distance_mm, sample_index):
    distance_cm = None if distance_mm is None else distance_mm / 10.0
    distance_m = None if distance_mm is None else distance_mm / 1000.0

    return {
        "ok": True,
        "error": None,
        "sensor": sensor_type,
        "address": f"0x{I2C_ADDRESS:02x}",
        "sample_index": sample_index,
        "distance_mm": round_or_none(distance_mm, 1),
        "distance_cm": round_or_none(distance_cm, 2),
        "distance_m": round_or_none(distance_m, 3),
        "max_display_mm": MAX_DISPLAY_MM,
        "history_limit": HISTORY_LIMIT,
        "poll_seconds": POLL_SECONDS,
        "write_seconds": WRITE_SECONDS,
        "points": list(history),
    }


def error_payload(error, history):
    return {
        "ok": False,
        "error": str(error),
        "sensor": "VL53L0X/VL53L1X",
        "address": f"0x{I2C_ADDRESS:02x}",
        "sample_index": None,
        "distance_mm": None,
        "distance_cm": None,
        "distance_m": None,
        "max_display_mm": MAX_DISPLAY_MM,
        "history_limit": HISTORY_LIMIT,
        "poll_seconds": POLL_SECONDS,
        "write_seconds": WRITE_SECONDS,
        "points": list(history),
    }


def main():
    history = deque(maxlen=HISTORY_LIMIT)
    sample_index = 0
    latest_distance_mm = None

    while True:
        try:
            sensor_type, sensor = init_lidar()
            last_write = 0.0

            while True:
                distance_mm = read_distance_mm(sensor_type, sensor)

                if distance_mm is not None:
                    latest_distance_mm = distance_mm
                    sample_index += 1
                    history.append(point_from_sample(sample_index, distance_mm))

                now = time.monotonic()

                if now - last_write >= WRITE_SECONDS:
                    save_lidar_state(state_payload(sensor_type, history, latest_distance_mm, sample_index))
                    last_write = now

                time.sleep(POLL_SECONDS)

        except Exception as e:
            save_lidar_state(error_payload(e, history))
            time.sleep(2)


if __name__ == "__main__":
    main()
