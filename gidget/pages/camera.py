import json
import time
from pathlib import Path

from flask import Blueprint, Response, jsonify, render_template

from auth import login_required


CAMERA_STATE_FILE = Path("/opt/gidget/camera_state.json")
FRAME_FILE = Path("/dev/shm/gidget/camera_frame.jpg")
STREAM_POLL_SECONDS = 0.05


blueprint = Blueprint("camera", __name__, url_prefix="/camera")


PAGE = {
    "id": "camera",
    "label": "Camera",
    "url": "/camera/",
    "order": 29,
    "requires_auth": True,
}


def load_camera_state():
    if not CAMERA_STATE_FILE.exists():
        return {}

    try:
        return json.loads(CAMERA_STATE_FILE.read_text())
    except Exception:
        return {}


@blueprint.route("/")
@login_required
def index():
    return render_template("camera.html")


@blueprint.route("/api/state")
@login_required
def api_state():
    return jsonify(load_camera_state())


@blueprint.route("/stream.mjpg")
@login_required
def stream():
    """
    Serves frames written by the gidget-camera service to tmpfs.

    The web process never opens Picamera2 itself - the camera hardware
    only supports one owner, and that's the camera_reader systemd service.
    """

    def generate():
        last_mtime = None

        while True:
            try:
                mtime = FRAME_FILE.stat().st_mtime_ns
            except FileNotFoundError:
                time.sleep(STREAM_POLL_SECONDS)
                continue

            if mtime != last_mtime:
                try:
                    frame = FRAME_FILE.read_bytes()
                except FileNotFoundError:
                    time.sleep(STREAM_POLL_SECONDS)
                    continue

                last_mtime = mtime

                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + frame
                    + b"\r\n"
                )

            time.sleep(STREAM_POLL_SECONDS)

    return Response(
        generate(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )