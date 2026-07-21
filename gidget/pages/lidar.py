import json
from pathlib import Path

from flask import Blueprint, jsonify, render_template

from auth import login_required


LIDAR_FILE = Path("/dev/shm/gidget/lidar_state.json")

blueprint = Blueprint("lidar", __name__, url_prefix="/lidar")

PAGE = {
    "id": "lidar",
    "label": "LIDAR",
    "url": "/lidar/",
    "order": 27,
    "requires_auth": True,
}


def load_lidar_state():
    if not LIDAR_FILE.exists():
        return {}

    try:
        return json.loads(LIDAR_FILE.read_text())
    except Exception:
        return {}


@blueprint.route("/")
@login_required
def index():
    return render_template("lidar.html")


@blueprint.route("/api/state")
@login_required
def api_state():
    return jsonify(load_lidar_state())
