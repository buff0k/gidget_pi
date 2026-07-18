#!/usr/bin/env python3

import json
import socket
import subprocess
from pathlib import Path


BASE_DIR = Path("/opt/gidget")
STATE_FILE = BASE_DIR / "status_state.json"
ENVIRONMENT_FILE = BASE_DIR / "environment_state.json"
TRACK_DIR = BASE_DIR / "data" / "tracks"


def run_cmd(cmd, timeout=2):
    try:
        return subprocess.check_output(
            cmd,
            shell=True,
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        ).strip()
    except Exception:
        return ""


def load_state