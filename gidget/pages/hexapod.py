import json
import time
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

from auth import login_required
import hexapod_kinematics as hk


STATE_FILE = Path("/dev/shm/gidget/hexapod_state.json")
COMMAND_FILE = Path("/dev/shm/gidget/hexapod_command.json")

VALID_MODES = ("idle", "walk", "calibrate_90")

blueprint = Blueprint("hexapod", __name__, url_prefix="/hexapod")

PAGE = {
    "id": "hexapod",
    "label": "Hexapod",
    "url": "/hexapod/",
    "order": 29,
    "requires_auth": True,
}


def load_hexapod_state():
    if not STATE_FILE.exists():
        return {}

    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def clamp_axis(value):
    try:
        return hk.clamp(float(value), -127, 127)
    except Exception:
        return 0.0


def clamp_speed(value):
    try:
        return hk.clamp(float(value), 0.0, 2.0)
    except Exception:
        return 1.0


@blueprint.route("/")
@login_required
def index():
    return render_template("hexapod.html")


@blueprint.route("/api/state")
@login_required
def api_state():
    return jsonify(load_hexapod_state())


@blueprint.route("/api/command", methods=["POST"])
@login_required
def api_command():
    """
    Single command entry point for the hexapod. Any sender that can POST
    this shape - the web joystick today, a future browser-side Gamepad API
    reader, or a future autonomy process - feeds the gait engine the same
    way; hexapod_controller.py never knows or cares which one wrote it.
    """
    data = request.get_json(silent=True) or {}

    mode = data.get("mode", "idle")
    if mode not in VALID_MODES:
        return jsonify({"ok": False, "error": f"invalid mode {mode!r}"}), 400

    gait = data.get("gait", "tripod")
    if gait not in hk.GAIT_NAMES:
        return jsonify({"ok": False, "error": f"invalid gait {gait!r}"}), 400

    command = {
        "mode": mode,
        "gait": gait,
        "x": clamp_axis(data.get("x", 0)),
        "y": clamp_axis(data.get("y", 0)),
        "r": clamp_axis(data.get("r", 0)),
        "speed": clamp_speed(data.get("speed", 1.0)),
        # Server-assigned - never trust a client-supplied timestamp, since
        # this is what the controller's staleness/deadman check relies on.
        "issued_at": time.time(),
        "source": str(data.get("source", "web"))[:32],
    }

    COMMAND_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_file = COMMAND_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(command, separators=(",", ":")))
    temp_file.replace(COMMAND_FILE)

    return jsonify({"ok": True, "command": command})
