#!/usr/bin/env python3

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import serial
import pynmea2


SERIAL_PORT = "/dev/serial0"
BAUDRATE = 9600

STATE_FILE = Path("/opt/gidget/status_state.json")
TRACK_DIR = Path("/opt/gidget/data/tracks")

LOG_INTERVAL_SECONDS = 1
NMEA_TAIL_LIMIT = 20

last_track_log_time = 0


CONSTELLATION_BY_TALKER = {
    "GP": "GPS",
    "GL": "GLONASS",
    "GA": "Galileo",
    "GB": "BeiDou",
    "BD": "BeiDou",
    "GQ": "QZSS",
    "GN": "Multi-GNSS",
}


def utc_now():
    return datetime.now(timezone.utc)


def utc_now_iso():
    return utc_now().isoformat()


def constellation_from_talker(talker):
    return CONSTELLATION_BY_TALKER.get(talker, talker or "Unknown")


def load_state():
    if not STATE_FILE.exists():
        return {}

    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(state):
    temp_file = STATE_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(state, indent=2))
    temp_file.replace(STATE_FILE)


def current_gps_state():
    state = load_state()
    return state.get("gps", {})


def save_gps_state(gps):
    state = load_state()
    state["gps"] = gps
    save_state(state)


def add_nmea_tail(raw):
    gps = current_gps_state()

    tail = gps.get("nmea_tail", [])
    if not isinstance(tail, list):
        tail = []

    tail.append({
        "timestamp": utc_now_iso(),
        "sentence": raw,
    })

    gps["nmea_tail"] = tail[-NMEA_TAIL_LIMIT:]
    gps["last_sentence"] = raw
    gps["timestamp"] = utc_now_iso()

    save_gps_state(gps)


def empty_gps_state(last_sentence=None):
    gps = current_gps_state()

    return {
        "has_fix": False,
        "lat": None,
        "lon": None,
        "altitude_m": None,
        "speed_kmh": None,
        "course_deg": None,
        "satellites": None,
        "timestamp": utc_now_iso(),
        "last_sentence": last_sentence,
        "nmea_tail": gps.get("nmea_tail", [])[-NMEA_TAIL_LIMIT:],
        "satellites_used": gps.get("satellites_used", []),
        "satellites_visible": gps.get("satellites_visible", []),
        "constellations": gps.get("constellations", []),
        "gsa": gps.get("gsa", {}),
    }


def merge_gps_state(gps_data):
    gps = current_gps_state()

    merged = gps.copy()

    for key, value in gps_data.items():
        if value is not None:
            merged[key] = value

    if gps_data.get("has_fix") is False:
        merged["has_fix"] = False

    merged["timestamp"] = gps_data.get("timestamp") or utc_now_iso()
    merged["last_sentence"] = gps_data.get("last_sentence") or gps.get("last_sentence")

    # Preserve telemetry arrays unless explicitly replaced.
    merged.setdefault("nmea_tail", gps.get("nmea_tail", [])[-NMEA_TAIL_LIMIT:])
    merged.setdefault("satellites_used", gps.get("satellites_used", []))
    merged.setdefault("satellites_visible", gps.get("satellites_visible", []))
    merged.setdefault("constellations", gps.get("constellations", []))
    merged.setdefault("gsa", gps.get("gsa", {}))

    save_gps_state(merged)

    return merged


def today_track_file():
    TRACK_DIR.mkdir(parents=True, exist_ok=True)
    filename = utc_now().strftime("%Y-%m-%d.jsonl")
    return TRACK_DIR / filename


def append_track_point(gps_state):
    global last_track_log_time

    now_monotonic = time.monotonic()
    if now_monotonic - last_track_log_time < LOG_INTERVAL_SECONDS:
        return

    if not gps_state.get("has_fix"):
        return

    lat = gps_state.get("lat")
    lon = gps_state.get("lon")

    if lat is None or lon is None:
        return

    point = {
        "timestamp": gps_state.get("timestamp") or utc_now_iso(),
        "lat": float(lat),
        "lon": float(lon),
        "altitude_m": gps_state.get("altitude_m"),
        "speed_kmh": gps_state.get("speed_kmh"),
        "course_deg": gps_state.get("course_deg"),
        "satellites": gps_state.get("satellites"),
    }

    with today_track_file().open("a") as f:
        f.write(json.dumps(point, separators=(",", ":")) + "\n")

    last_track_log_time = now_monotonic


def parse_float_or_none(value):
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def parse_int_or_none(value):
    try:
        if value in (None, ""):
            return None
        return int(value)
    except Exception:
        return None


def update_constellations_from_gps(gps):
    constellations = set()

    for sat in gps.get("satellites_visible", []):
        if sat.get("constellation"):
            constellations.add(sat["constellation"])

    for sat in gps.get("satellites_used", []):
        if sat.get("constellation"):
            constellations.add(sat["constellation"])

    gps["constellations"] = sorted(constellations)
    return gps


def get_msg_talker(msg):
    talker = getattr(msg, "talker", None)
    if talker:
        return talker

    sentence = getattr(msg, "sentence_type", "")
    raw = str(msg)

    if raw.startswith("$") and len(raw) >= 3:
        return raw[1:3]

    return None


def update_gsa(msg, raw):
    """
    GSA lists satellites used for the active fix.
    """
    gps = current_gps_state()

    talker = get_msg_talker(msg)
    constellation = constellation_from_talker(talker)

    used = []

    for i in range(1, 13):
        value = getattr(msg, f"sv_id{i:02d}", None)
        if value:
            used.append({
                "id": str(value),
                "talker": talker,
                "constellation": constellation,
            })

    gps["satellites_used"] = used
    gps["gsa"] = {
        "talker": talker,
        "constellation": constellation,
        "mode": getattr(msg, "mode", None),
        "fix_type": getattr(msg, "mode_fix_type", None),
        "pdop": parse_float_or_none(getattr(msg, "pdop", None)),
        "hdop": parse_float_or_none(getattr(msg, "hdop", None)),
        "vdop": parse_float_or_none(getattr(msg, "vdop", None)),
        "timestamp": utc_now_iso(),
        "last_sentence": raw,
    }
    gps["timestamp"] = utc_now_iso()
    gps["last_sentence"] = raw

    gps = update_constellations_from_gps(gps)
    save_gps_state(gps)


def update_gsv(msg, raw):
    """
    GSV lists visible satellites, usually spread across multiple messages.

    This stores a rolling/current table keyed by talker + satellite id.
    """
    gps = current_gps_state()

    talker = get_msg_talker(msg)
    constellation = constellation_from_talker(talker)

    existing = gps.get("satellites_visible", [])
    by_key = {}

    for sat in existing:
        key = f"{sat.get('talker')}:{sat.get('id')}"
        by_key[key] = sat

    for i in range(1, 5):
        sat_id = getattr(msg, f"sv_prn_num_{i}", None)
        if not sat_id:
            continue

        elevation = getattr(msg, f"elevation_deg_{i}", None)
        azimuth = getattr(msg, f"azimuth_{i}", None)
        snr = getattr(msg, f"snr_{i}", None)

        key = f"{talker}:{sat_id}"

        by_key[key] = {
            "id": str(sat_id),
            "talker": talker,
            "constellation": constellation,
            "elevation_deg": parse_float_or_none(elevation),
            "azimuth_deg": parse_float_or_none(azimuth),
            "snr_db": parse_float_or_none(snr),
            "last_seen": utc_now_iso(),
        }

    satellites = list(by_key.values())

    # Keep recently seen satellites only by rough count. This avoids stale tables growing forever.
    satellites = satellites[-64:]

    satellites.sort(
        key=lambda s: (
            s.get("constellation") or "",
            int(s.get("id")) if str(s.get("id", "")).isdigit() else 9999,
        )
    )

    gps["satellites_visible"] = satellites
    gps["satellites"] = len(satellites) if satellites else gps.get("satellites")
    gps["timestamp"] = utc_now_iso()
    gps["last_sentence"] = raw

    gps = update_constellations_from_gps(gps)
    save_gps_state(gps)


def main():
    while True:
        try:
            with serial.Serial(SERIAL_PORT, BAUDRATE, timeout=1) as ser:
                while True:
                    raw = ser.readline().decode("ascii", errors="ignore").strip()

                    if not raw.startswith("$"):
                        continue

                    add_nmea_tail(raw)

                    try:
                        msg = pynmea2.parse(raw)
                    except pynmea2.ParseError:
                        continue

                    gps_data = None

                    if msg.sentence_type == "RMC":
                        has_fix = getattr(msg, "status", "") == "A"

                        if has_fix:
                            speed_knots = parse_float_or_none(getattr(msg, "spd_over_grnd", None)) or 0
                            speed_kmh = speed_knots * 1.852
                            course_deg = parse_float_or_none(getattr(msg, "true_course", None))

                            gps_data = {
                                "has_fix": True,
                                "lat": float(msg.latitude),
                                "lon": float(msg.longitude),
                                "altitude_m": None,
                                "speed_kmh": round(speed_kmh, 2),
                                "course_deg": course_deg,
                                "satellites": None,
                                "timestamp": utc_now_iso(),
                                "last_sentence": raw,
                            }
                        else:
                            gps_data = empty_gps_state(raw)

                    elif msg.sentence_type == "GGA":
                        has_fix = int(getattr(msg, "gps_qual", 0) or 0) > 0

                        if has_fix:
                            gps_data = {
                                "has_fix": True,
                                "lat": float(msg.latitude),
                                "lon": float(msg.longitude),
                                "altitude_m": parse_float_or_none(getattr(msg, "altitude", None)),
                                "speed_kmh": None,
                                "course_deg": None,
                                "satellites": parse_int_or_none(getattr(msg, "num_sats", None)),
                                "timestamp": utc_now_iso(),
                                "last_sentence": raw,
                            }
                        else:
                            gps_data = empty_gps_state(raw)

                    elif msg.sentence_type == "GSA":
                        update_gsa(msg, raw)

                    elif msg.sentence_type == "GSV":
                        update_gsv(msg, raw)

                    if gps_data:
                        merged = merge_gps_state(gps_data)

                        if gps_data.get("has_fix"):
                            append_track_point(merged)

        except Exception as e:
            gps = current_gps_state()
            gps.update({
                "has_fix": False,
                "lat": None,
                "lon": None,
                "altitude_m": None,
                "speed_kmh": None,
                "course_deg": None,
                "satellites": None,
                "timestamp": utc_now_iso(),
                "last_sentence": f"GPS error: {e}",
                "nmea_tail": gps.get("nmea_tail", [])[-NMEA_TAIL_LIMIT:],
                "satellites_used": gps.get("satellites_used", []),
                "satellites_visible": gps.get("satellites_visible", []),
                "constellations": gps.get("constellations", []),
                "gsa": gps.get("gsa", {}),
            })
            save_gps_state(gps)
            time.sleep(5)


if __name__ == "__main__":
    main()
