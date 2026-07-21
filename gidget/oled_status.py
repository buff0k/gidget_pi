#!/usr/bin/env python3

import atexit
import json
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import board
import busio
from PIL import Image, ImageDraw, ImageFont
import adafruit_ssd1306


WIDTH = 128
HEIGHT = 64
I2C_ADDRESS = 0x3C

FRAME_SECONDS = 0.25
SCREEN_SECONDS = 20
WASH_STEPS = 8

STATE_FILE = Path("/dev/shm/gidget/status_state.json")

display = None


def clear_display():
    global display

    if display is not None:
        try:
            display.fill(0)
            display.show()
        except Exception:
            pass


def handle_shutdown(signum, frame):
    clear_display()
    sys.exit(0)


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


def get_hostname():
    try:
        return socket.gethostname()
    except Exception:
        return "gidget"


def get_ip():
    ip = run_cmd("ip -4 addr show wlan0 | awk '/inet / {print $2}' | cut -d/ -f1")
    if ip:
        return ip

    ip = run_cmd("hostname -I | awk '{print $1}'")
    return ip if ip else "No IP"


def get_wifi():
    output = run_cmd("iw dev wlan0 link")
    if not output or "Not connected" in output:
        return "WiFi down", "n/a"

    ssid = "unknown"
    signal = "n/a"

    for line in output.splitlines():
        line = line.strip()
        if line.startswith("SSID:"):
            ssid = line.replace("SSID:", "").strip()
        elif line.startswith("signal:"):
            signal = line.replace("signal:", "").strip()

    return ssid, signal


def get_cpu_temp():
    try:
        temp_c = int(Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip()) / 1000
        return f"{temp_c:.1f}C"
    except Exception:
        return "n/a"


def get_uptime():
    try:
        seconds = int(Path("/proc/uptime").read_text().split(".")[0])
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        if hours:
            return f"{hours}h{mins:02d}m"
        return f"{mins}m"
    except Exception:
        return "n/a"


def get_gps_state():
    if not STATE_FILE.exists():
        return {}

    try:
        state = json.loads(STATE_FILE.read_text())
        return state.get("gps", {})
    except Exception:
        return {}


def text_width(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def draw_right_aligned(draw, text, y, font, fill=255, right_x=WIDTH):
    width = text_width(draw, text, font)
    x = max(0, right_x - width)
    draw.text((x, y), text, font=font, fill=fill)


def scroll_text(draw, text, x, y, max_width, font, tick, fill=255):
    width = text_width(draw, text, font)

    if width <= max_width:
        draw.text((x, y), text, font=font, fill=fill)
        return

    padded = text + "   "
    padded_width = text_width(draw, padded, font)
    offset = int(tick / 2) % max(1, padded_width)

    clip = Image.new("1", (max_width, 12))
    clip_draw = ImageDraw.Draw(clip)

    clip_draw.text((-offset, 0), padded, font=font, fill=255)
    clip_draw.text((padded_width - offset, 0), padded, font=font, fill=255)

    # Paste clipped text onto the main image.
    # This function relies on caller attaching draw.im through ImageDraw.
    draw.bitmap((x, y), clip, fill=fill)


def base_frame(font_small, font_bold):
    image = Image.new("1", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)

    hostname = get_hostname()
    now = datetime.now().strftime("%H:%M:%S")

    draw.text((0, 0), hostname[:10], font=font_bold, fill=255)
    draw_right_aligned(draw, now, 0, font_small)

    draw.line((0, 12, WIDTH, 12), fill=255)

    return image, draw


def draw_wifi_screen(font_small, font_bold, tick):
    image, draw = base_frame(font_small, font_bold)

    ip = get_ip()
    ssid, signal_text = get_wifi()
    temp = get_cpu_temp()
    uptime = get_uptime()

    draw.text((0, 16), "WIFI", font=font_bold, fill=255)
    draw.text((0, 30), "SSID", font=font_small, fill=255)
    scroll_text(draw, ssid, 32, 30, 96, font_small, tick, fill=255)

    draw.text((0, 42), f"Sig {signal_text}", font=font_small, fill=255)
    draw.text((0, 54), f"IP {ip}", font=font_small, fill=255)

    # Tiny alternating footer marker to make it feel alive.
    if tick % 4 < 2:
        draw.point((126, 62), fill=255)
    else:
        draw.point((124, 62), fill=255)

    return image


def draw_gps_screen(font_small, font_bold, tick):
    image, draw = base_frame(font_small, font_bold)

    gps = get_gps_state()

    draw.text((0, 16), "GPS", font=font_bold, fill=255)

    if gps.get("has_fix"):
        lat = gps.get("lat")
        lon = gps.get("lon")
        sats = gps.get("satellites")
        speed = gps.get("speed_kmh")
        course = gps.get("course_deg")

        draw.text((36, 16), f"FIX S{sats}", font=font_small, fill=255)

        if lat is not None and lon is not None:
            draw.text((0, 30), f"La {float(lat):.5f}", font=font_small, fill=255)
            draw.text((0, 42), f"Lo {float(lon):.5f}", font=font_small, fill=255)
        else:
            draw.text((0, 30), "Fix/no coords", font=font_small, fill=255)

        speed_text = "n/a" if speed is None else f"{float(speed):.1f}"
        course_text = "n/a" if course is None else f"{float(course):.0f}"
        draw.text((0, 54), f"{speed_text}km/h {course_text}deg", font=font_small, fill=255)
    else:
        draw.text((36, 16), "SEARCH", font=font_small, fill=255)
        draw.text((0, 30), "Waiting for fix", font=font_small, fill=255)

        # Moving search dots.
        dots = "." * ((tick % 4) + 1)
        draw.text((0, 42), f"Sat scan{dots}", font=font_small, fill=255)

        last = gps.get("last_sentence") or "No NMEA yet"
        if last.startswith("$"):
            sentence_type = last.split(",")[0]
        else:
            sentence_type = last[:16]

        draw.text((0, 54), sentence_type[:18], font=font_small, fill=255)

    return image


def wash_transition(old_image, new_image):
    global display

    for step in range(1, WASH_STEPS + 1):
        image = old_image.copy()
        draw = ImageDraw.Draw(image)

        y_limit = int((HEIGHT / WASH_STEPS) * step)

        crop = new_image.crop((0, 0, WIDTH, y_limit))
        image.paste(crop, (0, 0))

        # Leading wash line.
        if y_limit < HEIGHT:
            draw.line((0, y_limit, WIDTH, y_limit), fill=255)

        display.image(image)
        display.show()
        time.sleep(0.05)


def main():
    global display

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)
    atexit.register(clear_display)

    i2c = busio.I2C(board.SCL, board.SDA)
    display = adafruit_ssd1306.SSD1306_I2C(WIDTH, HEIGHT, i2c, addr=I2C_ADDRESS)

    display.fill(0)
    display.show()

    font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
    font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 11)

    current_screen = 0
    last_switch = time.monotonic()
    tick = 0

    image = draw_wifi_screen(font_small, font_bold, tick)
    display.image(image)
    display.show()

    while True:
        now = time.monotonic()

        if now - last_switch >= SCREEN_SECONDS:
            old_image = image
            current_screen = 1 - current_screen
            last_switch = now

            if current_screen == 0:
                image = draw_wifi_screen(font_small, font_bold, tick)
            else:
                image = draw_gps_screen(font_small, font_bold, tick)

            wash_transition(old_image, image)
        else:
            if current_screen == 0:
                image = draw_wifi_screen(font_small, font_bold, tick)
            else:
                image = draw_gps_screen(font_small, font_bold, tick)

            display.image(image)
            display.show()

        tick += 1
        time.sleep(FRAME_SECONDS)


if __name__ == "__main__":
    main()
