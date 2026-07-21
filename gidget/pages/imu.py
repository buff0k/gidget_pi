import json
from pathlib import Path

from flask import Blueprint, jsonify, render_template

from auth import login_required


IMU_FILE = Path("/dev/shm/gidget/imu_state.json")

blueprint = Blueprint("imu", __name__, url_prefix="/imu")

PAGE = {
    "id": "imu",
    "label": "IMU",
    "url": "/imu/",
    "order": 28,
    "requires_auth": True,
}


def load_imu_state():
    if not IMU_FILE.exists():
        return {}

    try:
        return json.loads(IMU_FILE.read_text())
    except Exception:
        return {}


@blueprint.route("/")
@login_required
def index():
    return render_template("imu.html")


@blueprint.route("/api/state")
@login_required
def api_state():
    return jsonify(load_imu_state())
