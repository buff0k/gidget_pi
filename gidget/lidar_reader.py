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
POLL_SECONDS = 0.03
WRITE_SECONDS = 0.12
HISTORY_LIMIT = 120
I2C_ADDRESS = 0x29
MAX_DISPLAY_MM = 4000


class LidarUnavailable(RuntimeError):
    pass


def utc_now_iso():
    return datetime.now(timezone.utc