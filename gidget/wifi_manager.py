#!/usr/bin/env python3

import subprocess


NMCLI = "/usr/bin/nmcli"


def run_nmcli(args, timeout=20):
    """
    Run nmcli through passwordless sudo.

    Args must be a list, not a string. This avoids shell escaping problems
    with SSIDs, passwords, and profile names.
    """
    cmd = ["sudo", "-n", NMCLI] + args

    try:
        completed = subprocess.run(
            cmd,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )

        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "cmd": " ".join(cmd),
        }
    except Exception as e:
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": str(e),
            "cmd": " ".join(cmd),
        }


def split_nmcli_t_line(line):
    """
    Split nmcli terse output on unescaped ':'.

    nmcli -t escapes literal colons with backslash, so this parser preserves
    values like SSIDs that may contain ':'.
    """
    parts = []
    current = []
    escaped = False

    for char in line:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            parts.append("".join(current))
            current = []
        else:
            current.append(char)

    parts.append("".join(current))
    return parts


def current_wifi_status():
    device_result = run_nmcli(
        ["-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device"],
        timeout=10,
    )

    active_result = run_nmcli(
        ["-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active"],
        timeout=10,
    )

    wifi_device = None

    if device_result["ok"]:
        for line in device_result["stdout"].splitlines():
            parts = split_nmcli_t_line(line)
            if len(parts) >= 4:
                device, dev_type, state, connection = parts[:4]
                if dev_type == "wifi":
                    wifi_device = {
                        "device": device,
                        "type": dev_type,
                        "state": state,
                        "connection": connection,
                    }
                    break

    active_connections = []
    if active_result["ok"]:
        for line in active_result["stdout"].splitlines():
            parts = split_nmcli_t_line(line)
            if len(parts) >= 3:
                name, con_type, device = parts[:3]
                active_connections.append({
                    "name": name,
                    "type": con_type,
                    "device": device,
                })

    return {
        "ok": device_result["ok"],
        "wifi_device": wifi_device,
        "active_connections": active_connections,
        "error": device_result["stderr"] if not device_result["ok"] else None,
    }


def scan_wifi_networks():
    """
    WiFi scan should not intentionally disconnect current WiFi.
    It may briefly add latency on the Pi Zero WH radio.
    """
    rescan = run_nmcli(["device", "wifi", "rescan"], timeout=20)

    listing = run_nmcli(
        [
            "-t",
            "-f",
            "IN-USE,SSID,BSSID,CHAN,RATE,SIGNAL,SECURITY",
            "device",
            "wifi",
            "list",
        ],
        timeout=20,
    )

    networks = []

    if listing["ok"]:
        for line in listing["stdout"].splitlines():
            parts = split_nmcli_t_line(line)

            while len(parts) < 7:
                parts.append("")

            in_use, ssid, bssid, channel, rate, signal, security = parts[:7]

            if not ssid:
                ssid = "<hidden>"

            networks.append({
                "in_use": in_use == "*",
                "ssid": ssid,
                "bssid": bssid,
                "channel": channel,
                "rate": rate,
                "signal": signal,
                "security": security,
            })

    return {
        "ok": listing["ok"],
        "rescan_ok": rescan["ok"],
        "networks": networks,
        "error": listing["stderr"] if not listing["ok"] else rescan["stderr"],
    }


def saved_wifi_profiles():
    result = run_nmcli(
        ["-t", "-f", "NAME,UUID,TYPE,AUTOCONNECT,AUTOCONNECT-PRIORITY", "connection", "show"],
        timeout=10,
    )

    profiles = []

    if result["ok"]:
        for line in result["stdout"].splitlines():
            parts = split_nmcli_t_line(line)

            while len(parts) < 5:
                parts.append("")

            name, uuid, con_type, autoconnect, priority = parts[:5]

            if con_type not in ("wifi", "802-11-wireless"):
                continue

            profiles.append({
                "name": name,
                "uuid": uuid,
                "type": con_type,
                "autoconnect": autoconnect,
                "priority": priority,
            })

    return {
        "ok": result["ok"],
        "profiles": profiles,
        "error": result["stderr"] if not result["ok"] else None,
    }


def profile_exists(name):
    result = run_nmcli(["-t", "-f", "NAME", "connection", "show"], timeout=10)

    if not result["ok"]:
        return False

    names = [line.strip() for line in result["stdout"].splitlines()]
    return name in names


def add_wifi_profile(ssid, password, autoconnect=True, priority=0, hidden=False, profile_name=None):
    ssid = (ssid or "").strip()
    password = password or ""
    profile_name = (profile_name or ssid).strip()

    if not ssid:
        return {
            "ok": False,
            "error": "SSID is required.",
        }

    if not profile_name:
        return {
            "ok": False,
            "error": "Profile name is required.",
        }

    if profile_exists(profile_name):
        return {
            "ok": False,
            "error": f"A connection profile named '{profile_name}' already exists.",
        }

    try:
        priority_int = int(priority)
    except Exception:
        priority_int = 0

    add_args = [
        "connection",
        "add",
        "type",
        "wifi",
        "ifname",
        "wlan0",
        "con-name",
        profile_name,
        "ssid",
        ssid,
    ]

    add_result = run_nmcli(add_args, timeout=20)
    if not add_result["ok"]:
        return {
            "ok": False,
            "error": add_result["stderr"] or add_result["stdout"],
        }

    modify_steps = []

    if password:
        modify_steps.append([
            "connection",
            "modify",
            profile_name,
            "wifi-sec.key-mgmt",
            "wpa-psk",
        ])
        modify_steps.append([
            "connection",
            "modify",
            profile_name,
            "wifi-sec.psk",
            password,
        ])

    modify_steps.append([
        "connection",
        "modify",
        profile_name,
        "connection.autoconnect",
        "yes" if autoconnect else "no",
    ])

    modify_steps.append([
        "connection",
        "modify",
        profile_name,
        "connection.autoconnect-priority",
        str(priority_int),
    ])

    if hidden:
        modify_steps.append([
            "connection",
            "modify",
            profile_name,
            "wifi.hidden",
            "yes",
        ])

    for step in modify_steps:
        result = run_nmcli(step, timeout=20)
        if not result["ok"]:
            return {
                "ok": False,
                "error": result["stderr"] or result["stdout"],
            }

    return {
        "ok": True,
        "message": f"Saved WiFi profile '{profile_name}' for SSID '{ssid}'.",
    }


def connect_wifi_profile(profile_name):
    profile_name = (profile_name or "").strip()

    if not profile_name:
        return {
            "ok": False,
            "error": "Profile name is required.",
        }

    result = run_nmcli(["connection", "up", profile_name], timeout=45)

    return {
        "ok": result["ok"],
        "message": result["stdout"] if result["ok"] else None,
        "error": result["stderr"] or result["stdout"] if not result["ok"] else None,
    }


def delete_wifi_profile(profile_name):
    profile_name = (profile_name or "").strip()

    if not profile_name:
        return {
            "ok": False,
            "error": "Profile name is required.",
        }

    result = run_nmcli(["connection", "delete", profile_name], timeout=20)

    return {
        "ok": result["ok"],
        "message": result["stdout"] if result["ok"] else None,
        "error": result["stderr"] or result["stdout"] if not result["ok"] else None,
    }


def set_profile_autoconnect(profile_name, autoconnect=True, priority=None):
    profile_name = (profile_name or "").strip()

    if not profile_name:
        return {
            "ok": False,
            "error": "Profile name is required.",
        }

    result = run_nmcli(
        [
            "connection",
            "modify",
            profile_name,
            "connection.autoconnect",
            "yes" if autoconnect else "no",
        ],
        timeout=20,
    )

    if not result["ok"]:
        return {
            "ok": False,
            "error": result["stderr"] or result["stdout"],
        }

    if priority is not None and priority != "":
        try:
            priority_int = int(priority)
        except Exception:
            priority_int = 0

        result = run_nmcli(
            [
                "connection",
                "modify",
                profile_name,
                "connection.autoconnect-priority",
                str(priority_int),
            ],
            timeout=20,
        )

        if not result["ok"]:
            return {
                "ok": False,
                "error": result["stderr"] or result["stdout"],
            }

    return {
        "ok": True,
        "message": f"Updated autoconnect settings for '{profile_name}'.",
    }
