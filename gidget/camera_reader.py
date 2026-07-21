#!/usr/bin/env python3

import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

try:
    from picamera2 import Picamera2
except Exception:
    Picamera2 = None


FRAME_DIR = Path("/dev/shm/gidget")
STATE_FILE = FRAME_DIR / "camera_state.json"
FRAME_FILE = FRAME_DIR / "camera_frame.jpg"

RESOLUTION = (1280, 720)
JPEG_QUALITY = 85
CAPTURE_SECONDS = 0.10
WRITE_STATE_SECONDS = 2.0


class CameraUnavailable(RuntimeError):
    pass


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def save_camera_state(data):
    data["timestamp"] = utc_now_iso()
    temp_file = STATE_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(data, separators=(",", ":")))
    temp_file.replace(STATE_FILE)


def state_payload(status, error=None):
    return {
        "ok": error is None,
        "error": error,
        "status": status,
        "camera": "Pi Camera Module",
        "resolution": f"{RESOLUTION[0]}x{RESOLUTION[1]}",
        "jpeg_quality": JPEG_QUALITY,
        "target_fps": round(1 / CAPTURE_SECONDS, 1),
    }


def init_camera():
    if Picamera2 is None:
        raise CameraUnavailable("picamera2 is not installed")

    picam2 = Picamera2()

    config = picam2.create_video_configuration(
        main={"size": RESOLUTION, "format": "RGB888"}
    )

    picam2.configure(config)
    picam2.start()

    return picam2


def capture_jpeg_bytes(picam2):
    frame = picam2.capture_array()

    image = Image.fromarray(frame)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY)

    return buffer.getvalue()


def write_frame(jpeg_bytes):
    temp_file = FRAME_FILE.with_suffix(".tmp")
    temp_file.write_bytes(jpeg_bytes)
    temp_file.replace(FRAME_FILE)


def main():
    """
    Owns the camera exclusively. Frames are written to tmpfs (/dev/shm)
    rather than the SD card so the web process can serve the MJPEG stream
    by reading the latest frame file instead of opening Picamera2 itself -
    the hardware only supports one owner at a time.
    """

    FRAME_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        try:
            picam2 = init_camera()
            save_camera_state(state_payload("running"))
            last_state_write = time.monotonic()

            while True:
                write_frame(capture_jpeg_bytes(picam2))

                now = time.monotonic()

                if now - last_state_write >= WRITE_STATE_SECONDS:
                    save_camera_state(state_payload("running"))
                    last_state_write = now

                time.sleep(CAPTURE_SECONDS)

        except Exception as e:
            save_camera_state(state_payload("error", error=str(e)))
            time.sleep(2)


if __name__ == "__main__":
    main()
