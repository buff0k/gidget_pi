#!/usr/bin/env python3

import json
import socket
import subprocess
from pathlib import Path


BASE_DIR = Path("/opt/gidget")
STATE_FILE = BASE_DIR / "status_state.json"
ENVIRONMENT_FILE = BASE_DIR / "environment_state.json"
LIDAR_FILE = BASE_DIR / "lidar_state.json"
IMU_FILE = BASE_DIR / "imu_state.json"
TRACK_DIR = BASE_DIR / "data" / "tracks"
CPU_SNAPSHOT_FILE = Path("/tmp/gidget_cpu_snapshot.json")


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


def load_json_file(path):
    if not path.exists():
        return {}

    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def load_state():
    return load_json_file(STATE_FILE)


def load_environment():
    return load_json_file(ENVIRONMENT_FILE)


def load_lidar():
    return load_json_file(LIDAR_FILE)


def load_imu():
    return load_json_file(IMU_FILE)


def get_ip():
    ip = run_cmd("ip -4 addr show wlan0 | awk '/inet / {print $2}' | cut -d/ -f1")
    return ip or "No IP"


def get_wifi_signal():
    output = run_cmd("iw dev wlan0 link")
    if not output or "Not connected" in output:
        return {"ssid": "WiFi down", "signal": "n/a"}

    ssid = "unknown"
    signal = "n/a"

    for line in output.splitlines():
        line = line.strip()
        if line.startswith("SSID:"):
            ssid = line.replace("SSID:", "").strip()
        elif line.startswith("signal:"):
            signal = line.replace("signal:", "").strip()

    return {"ssid": ssid, "signal": signal}


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


def read_cpu_times():
    try:
        parts = Path("/proc/stat").read_text().splitlines()[0].split()
        values = [int(value) for value in parts[1:]]
        idle = values[3] + values[4]
        total = sum(values)
        return {"idle": idle, "total": total}
    except Exception:
        return None


def get_cpu_usage():
    current = read_cpu_times()
    cores = 1

    try:
        cores = max(
            1,
            len([
                line for line in Path("/proc/stat").read_text().splitlines()
                if line.startswith("cpu") and line[3:4].isdigit()
            ]),
        )
    except Exception:
        pass

    if not current:
        return {"used_percent": None, "per_core_percent": None, "cores": cores}

    previous = load_json_file(CPU_SNAPSHOT_FILE)

    try:
        CPU_SNAPSHOT_FILE.write_text(json.dumps(current, separators=(",", ":")))
    except Exception:
        pass

    if not previous or previous.get("total") is None or previous.get("idle") is None:
        return {"used_percent": None, "per_core_percent": None, "cores": cores}

    total_delta = current["total"] - int(previous.get("total", 0))
    idle_delta = current["idle"] - int(previous.get("idle", 0))

    if total_delta <= 0:
        used_percent = None
    else:
        used_percent = round(((total_delta - idle_delta) / total_delta) * 100, 1)

    return {
        "used_percent": used_percent,
        "per_core_percent": used_percent,
        "cores": cores,
    }


def get_load_average():
    try:
        one, five, fifteen = Path("/proc/loadavg").read_text().split()[:3]
        return {
            "one_min": float(one),
            "five_min": float(five),
            "fifteen_min": float(fifteen),
        }
    except Exception:
        return {"one_min": None, "five_min": None, "fifteen_min": None}


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
        "cpu_usage": get_cpu_usage(),
        "load_average": get_load_average(),
        "memory": get_memory_usage(),
        "storage": get_storage_usage("/"),
        "uptime_seconds": get_uptime(),
        "gps": state.get("gps", {}),
        "environment": load_environment(),
        "lidar": load_lidar(),
        "imu": load_imu(),
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
