#!/usr/bin/env python3

import json
import socket
import subprocess
from pathlib import Path


BASE_DIR = Path("/opt/gidget")
STATE_FILE = BASE_DIR / "status_state.json"
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


def load_state():
    if not STATE_FILE.exists():
        return {}

    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def get_ip():
    ip = run_cmd("ip -4 addr show wlan0 | awk '/inet / {print $2}' | cut -d/ -f1")
    return ip or "No IP"


def get_wifi_signal():
    output = run_cmd("iw dev wlan0 link")
    if not output or "Not connected" in output:
        return {
            "ssid": "WiFi down",
            "signal": "n/a",
        }

    ssid = "unknown"
    signal = "n/a"

    for line in output.splitlines():
        line = line.strip()
        if line.startswith("SSID:"):
            ssid = line.replace("SSID:", "").strip()
        elif line.startswith("signal:"):
            signal = line.replace("signal:", "").strip()

    return {
        "ssid": ssid,
        "signal": signal,
    }


def get_cpu_temp():
    try:
        temp = int(Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip()) / 1000
        return round(temp, 1)
    except Exception:
        return None


def get_uptime():
    try:
        seconds = int(Path("/proc/uptime").read_text().split(".")[0])
        return seconds
    except Exception:
        return None


def get_load_average():
    try:
        one, five, fifteen = Path("/proc/loadavg").read_text().split()[:3]
        return {
            "one_min": float(one),
            "five_min": float(five),
            "fifteen_min": float(fifteen),
        }
    except Exception:
        return {
            "one_min": None,
            "five_min": None,
            "fifteen_min": None,
        }


def get_memory_usage():
    try:
        meminfo = {}

        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            meminfo[key] = int(value.strip().split()[0])

        total_kb = meminfo.get("MemTotal")
        available_kb = meminfo.get("MemAvailable")

        if not total_kb or available_kb is None:
            raise ValueError("Missing meminfo values")

        used_kb = total_kb - available_kb

        return {
            "total_mb": round(total_kb / 1024, 1),
            "used_mb": round(used_kb / 1024, 1),
            "available_mb": round(available_kb / 1024, 1),
            "used_percent": round((used_kb / total_kb) * 100, 1),
        }
    except Exception:
        return {
            "total_mb": None,
            "used_mb": None,
            "available_mb": None,
            "used_percent": None,
        }


def get_storage_usage(path="/"):
    try:
        output = run_cmd(f"df -h {path} | awk 'NR==2 {{print $2, $3, $4, $5}}'")
        parts = output.split()

        if len(parts) != 4:
            raise ValueError("Unexpected df output")

        total, used, available, percent = parts

        return {
            "path": path,
            "total": total,
            "used": used,
            "available": available,
            "used_percent": percent,
        }
    except Exception:
        return {
            "path": path,
            "total": None,
            "used": None,
            "available": None,
            "used_percent": None,
        }


def current_status():
    state = load_state()

    return {
        "hostname": socket.gethostname(),
        "ip": get_ip(),
        "wifi": get_wifi_signal(),
        "cpu_temp_c": get_cpu_temp(),
        "load_average": get_load_average(),
        "memory": get_memory_usage(),
        "storage": get_storage_usage("/"),
        "uptime_seconds": get_uptime(),
        "gps": state.get("gps", {}),
    }


def track_files():
    if not TRACK_DIR.exists():
        return []

    return sorted(TRACK_DIR.glob("*.jsonl"))


def track_dates():
    dates = []

    for path in track_files():
        dates.append({
            "date": path.stem,
            "filename": path.name,
            "size_bytes": path.stat().st_size,
        })

    # Newest first.
    dates.sort(key=lambda item: item["date"], reverse=True)
    return dates


def read_track_date(date):
    """
    Read one YYYY-MM-DD.jsonl file completely.

    This is intentionally date-scoped so the browser can load newest first
    instead of forcing the Pi to read every track file before responding.
    """
    safe_date = "".join(ch for ch in str(date) if ch.isdigit() or ch == "-")

    if not safe_date:
        return []

    path = TRACK_DIR / f"{safe_date}.jsonl"

    if not path.exists():
        return []

    points = []

    try:
        with path.open("r") as f:
            for line_number, line in enumerate(f, start=1):
                line = line.strip()

                if not line:
                    continue

                try:
                    point = json.loads(line)
                except Exception:
                    continue

                if point.get("lat") is None or point.get("lon") is None:
                    continue

                point["_line"] = line_number
                point["_date"] = safe_date
                points.append(point)
    except Exception:
        return []

    return points


def read_latest_track_points(limit=1000):
    """
    Fast latest-points helper for compatibility/API previews.

    Reads from newest files backwards and stops as soon as enough points exist.
    """
    limit = max(1, int(limit))
    points = []

    for item in track_dates():
        day_points = read_track_date(item["date"])

        if not day_points:
            continue

        points = day_points + points

        if len(points) >= limit:
            return points[-limit:]

    return points[-limit:]
