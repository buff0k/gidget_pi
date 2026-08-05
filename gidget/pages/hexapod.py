import json
import secrets
import time
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

from auth import login_required
import hexapod_calibration as hcal
import hexapod_kinematics as hk


STATE_FILE = Path("/dev/shm/gidget/hexapod_state.json")
COMMAND_FILE = Path("/dev/shm/gidget/hexapod_command.json")
SESSION_FILE = Path("/dev/shm/gidget/hexapod_session.json")

VALID_MODES = ("idle", "walk", "calibrate_90", "manual")
CHANNEL_COUNT = 18

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


def sanitize_manual_channels(value):
    """
    Only used when mode == "manual" - a full 18-element array of raw
    per-channel angles, bypassing gait/IK entirely. Returns None if the
    shape is wrong, which hexapod_controller.py treats as "all neutral".
    """
    if not isinstance(value, list) or len(value) != CHANNEL_COUNT:
        return None

    try:
        return [hk.clamp(float(v), 0.0, 180.0) for v in value]
    except Exception:
        return None


def valid_channel(value):
    try:
        channel = int(value)
    except (TypeError, ValueError):
        return None
    return channel if 0 <= channel < CHANNEL_COUNT else None


def write_json_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = path.with_suffix(".tmp")
    temp_file.write_text(json.dumps(data, separators=(",", ":")))
    temp_file.replace(path)


def current_session_id():
    if not SESSION_FILE.exists():
        return None

    try:
        return json.loads(SESSION_FILE.read_text()).get("session_id")
    except Exception:
        return None


@blueprint.route("/")
@login_required
def index():
    # Every page load claims exclusive command authority. A tab left open
    # from earlier testing that keeps heartbeating in the background can no
    # longer silently win a "most recent write" race against whatever tab
    # the operator is actually looking at - its commands get rejected the
    # instant a newer session exists, not just eventually timed out.
    session_id = secrets.token_hex(8)
    write_json_atomic(SESSION_FILE, {"session_id": session_id, "started_at": time.time()})
    return render_template("hexapod.html", session_id=session_id)


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

    # Only the session that most recently loaded /hexapod/ may command
    # anything - see index() above. A stale/background tab's POSTs are
    # rejected outright rather than silently overwriting a newer tab's
    # commands, which is exactly what let an old Calibrate-mode session
    # keep driving the hexapod after the operator had switched to Idle.
    if data.get("session_id") != current_session_id():
        return jsonify({"ok": False, "error": "session superseded - reload the page"}), 409

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
        "manual_channels": sanitize_manual_channels(data.get("manual_channels")) if mode == "manual" else None,
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


@blueprint.route("/api/calibration")
@login_required
def api_calibration():
    return jsonify(hcal.load_calibration())


@blueprint.route("/api/calibration/trim", methods=["POST"])
@login_required
def api_calibration_trim():
    """
    Nudges or sets one channel's calibration trim - the small (a few
    degrees) correction between a servo's true physical center and a
    literal 90 deg command. Session-gated like api_command: this causes
    real, immediate servo motion (hexapod_controller.py picks the new
    value up within ~1s, see CalibrationCache in hexapod_controller.py),
    so a stale background tab must not be able to drive it.
    """
    data = request.get_json(silent=True) or {}

    if data.get("session_id") != current_session_id():
        return jsonify({"ok": False, "error": "session superseded - reload the page"}), 409

    channel = valid_channel(data.get("channel"))
    if channel is None:
        return jsonify({"ok": False, "error": "invalid channel"}), 400

    try:
        if "delta" in data:
            result = hcal.nudge_trim(channel, float(data["delta"]))
        elif "trim_deg" in data:
            result = hcal.set_trim(channel, float(data["trim_deg"]))
        else:
            return jsonify({"ok": False, "error": "expected 'delta' or 'trim_deg'"}), 400
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid trim value"}), 400

    return jsonify({"ok": True, "calibration": result})


@blueprint.route("/api/calibration/channel_map", methods=["POST"])
@login_required
def api_calibration_channel_map():
    """
    Assigns one channel to a (leg, joint). Metadata only - no servo motion
    from this call itself - but still session-gated like api_command: a
    stale tab silently reassigning wiring would be at least as confusing
    as one silently changing gait.
    """
    data = request.get_json(silent=True) or {}

    if data.get("session_id") != current_session_id():
        return jsonify({"ok": False, "error": "session superseded - reload the page"}), 409

    channel = valid_channel(data.get("channel"))
    if channel is None:
        return jsonify({"ok": False, "error": "invalid channel"}), 400

    try:
        leg = int(data.get("leg"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid leg"}), 400

    joint = data.get("joint")

    try:
        result = hcal.set_channel_map_entry(channel, leg, joint)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    return jsonify({"ok": True, "calibration": result})
