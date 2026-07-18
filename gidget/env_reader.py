#!/usr/bin/env python3

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import board
import busio
import adafruit_ahtx0
import adafruit_bmp280


ENV_FILE = Path("/opt/gidget/environment_state.json")
POLL_SECONDS = 5
SEA_LEVEL_PRESSURE_HPA = 1013.25
BMP280_ADDRESSES = (0x76, 0x77)


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def save_environment(data):
    data["timestamp"] = utc_now_iso()

    temp_file = ENV_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(data, indent=2))
    temp_file.replace(ENV_FILE)


def round_or_none(value, decimals=2):
    try:
        if value is None:
            return None
        return round(float(value), decimals)
    except Exception:
        return None


def create_bmp280(i2c):
    last_error = None

    for address in BMP280_ADDRESSES:
        try:
            sensor = adafruit_bmp280.Adafruit_BMP280_I2C(i2c, address=address)
            sensor.sea_level_pressure = SEA_LEVEL_PRESSURE_HPA
            return sensor, address
        except Exception as e:
            last_error = e

    raise RuntimeError(f"BMP280 not found at 0x76 or 0x77: {last_error}")


def init_sensors():
    i2c = busio.I2C(board.SCL, board.SDA)

    aht = adafruit_ahtx0.AHTx0(i2c)
    bmp, bmp_address = create_bmp280(i2c)

    return aht, bmp, bmp_address


def read_environment(aht, bmp, bmp_address):
    aht_temperature = aht.temperature
    humidity = aht.relative_humidity
    bmp_temperature = bmp.temperature
    pressure = bmp.pressure
    altitude = bmp.altitude

    return {
        "ok": True,
        "error": None,
        "sensor": "AHT20+BMP280",
        "aht20": {
            "temperature_c": round_or_none(aht_temperature, 2),
            "humidity_percent": round_or_none(humidity, 2),
        },
        "bmp280": {
            "address": f"0x{bmp_address:02x}",
            "temperature_c": round_or_none(bmp_temperature, 2),
            "pressure_hpa": round_or_none(pressure, 2),
            "altitude_m": round_or_none(altitude, 2),
            "sea_level_pressure_hpa": SEA_LEVEL_PRESSURE_HPA,
        },
    }


def main():
    while True:
        try:
            aht, bmp, bmp_address = init_sensors()

            while True:
                data = read_environment(aht, bmp, bmp_address)
                save_environment(data)
                time.sleep(POLL_SECONDS)

        except Exception as e:
            save_environment({
                "ok": False,
                "error": str(e),
                "sensor": "AHT20+BMP280",
                "aht20": {
                    "temperature_c": None,
                    "humidity_percent": None,
                },
                "bmp280": {
                    "address": None,
                    "temperature_c": None,
                    "pressure_hpa": None,
                    "altitude_m": None,
                    "sea_level_pressure_hpa": SEA_LEVEL_PRESSURE_HPA,
                },
            })
            time.sleep(10)


if __name__ == "__main__":
    main()
