"""
Gidget hexapod - Servo 2040 firmware.

Thin peripheral: applies target angles for its 18 channels as they arrive
from the Pi over USB serial, and reports back aggregate rail voltage/current
on a slow independent timer. All IK/gait logic lives on the Pi
(gidget/hexapod_kinematics.py + hexapod_controller.py) - this board does not
compute anything beyond driving PWM and reading its own ADC.

Protocol (newline-delimited JSON, matches hexapod_controller.py):
  Pi -> board, every tick (~50Hz):
    {"t": <epoch float>, "ch": [18 angles in degrees, index = channel]}
  board -> Pi, every ~500ms:
    {"type": "telemetry", "t": <ticks_ms>, "voltage_v": .., "current_a": .., "ok": true}

Local watchdog: if no command line has been received in WATCHDOG_MS, every
channel is driven to neutral independent of the Pi. This is a second
deadman layer beyond the Pi-side command staleness timeout - it covers a
crashed/restarted hexapod_controller.py process, which the Pi-side timeout
alone can't, since the RP2040's PWM hardware would otherwise just keep
outputting its last value indefinitely.

NOTE: the ServoCluster/Analog/AnalogMux calls below follow Pimoroni's
official servo2040 example (read_sensors.py / current_meter.py in
pimoroni-pico), fetched and matched verbatim after earlier guesses got the
AnalogMux constructor wrong - see README.md in this directory for how that
was diagnosed.
"""

import sys
import select
import time
import json

from machine import Pin
from servo import ServoCluster, Calibration, servo2040
from pimoroni import Analog, AnalogMux


NUM_CHANNELS = 18
WATCHDOG_MS = 1000
TELEMETRY_INTERVAL_MS = 500

voltage_sense = Analog(servo2040.SHARED_ADC, servo2040.VOLTAGE_GAIN)
current_sense = Analog(
    servo2040.SHARED_ADC, servo2040.CURRENT_GAIN,
    servo2040.SHUNT_RESISTOR, servo2040.CURRENT_OFFSET,
)
adc_mux = AnalogMux(
    servo2040.ADC_ADDR_0, servo2040.ADC_ADDR_1, servo2040.ADC_ADDR_2,
    # Needs an actual machine.Pin, not a raw int or an Analog(...) wrapper -
    # AnalogMux calls .init() on this internally.
    muxed_pin=Pin(servo2040.SHARED_ADC),
)

cluster = ServoCluster(0, 0, list(range(servo2040.SERVO_1, servo2040.SERVO_18 + 1)))

# CRITICAL: Pimoroni's default calibration (ANGULAR) centers on a raw value
# of 0, with a range of -90..+90 - NOT 0-180 with 90 as center. Confirmed
# directly against Pimoroni's own servo module README and example code
# (servo2040/calibration.py's own comment: "By default its value ranges
# from -90 to +90"; servo_cluster.py's sweep demo uses all_to_mid() for
# center and a +/-90 sweep extent). Every other part of this project
# (hexapod_kinematics.py's IK math, hexapod_controller.py, the web UI's
# manual sliders) assumes the opposite convention - a 0-180 range with 90
# as center, matching how servo angles are conventionally described and
# how MG996 datasheets specify them. Sending a raw 90 under the DEFAULT
# calibration therefore drives every channel to its full end-of-travel,
# not center - a 90 degree error, and almost certainly what's been
# happening on every power-up so far, before the Pi even connects.
#
# Rather than rewrite the 0-180 convention across six files, each channel
# gets a custom calibration here instead: apply_three_pairs maps the SAME
# physical pulse widths (500-2500us, the standard hobby-servo full range)
# onto 0-180 with 90 as center. The actual PWM output for a given physical
# position is identical to Pimoroni's default - only the number used to
# ask for that position changes, to match what the rest of this project
# already assumes. This MUST happen before the neutral-value loop below,
# so the very first pulse each servo ever sees this power-cycle is under
# the corrected calibration, not the default one.
for _channel in range(NUM_CHANNELS):
    _cal = Calibration()
    _cal.apply_three_pairs(500, 1500, 2500, 0, 90, 180)
    cluster.calibration(_channel, _cal)

# Command a safe neutral BEFORE enabling PWM output, not after. A channel's
# value before its first explicit .value() call is whatever ServoCluster
# defaults to internally, which was never actually confirmed safe - if it
# is not 90deg (now correctly meaning center, per the calibration fix
# above), enable_all() would drive straight to that default the instant
# output turns on, before the watchdog below ever gets a chance to
# intervene.
for _channel in range(NUM_CHANNELS):
    cluster.value(_channel, 90.0)

cluster.enable_all()

poll = select.poll()
poll.register(sys.stdin, select.POLLIN)


def apply_channels(channels):
    # Confirmed on real hardware: ServoCluster.value(index, angle) takes a
    # raw degree value directly, matching the 0-180 convention used
    # everywhere else in this project - no normalization needed.
    for i in range(min(NUM_CHANNELS, len(channels))):
        cluster.value(i, channels[i])


def apply_neutral():
    for i in range(NUM_CHANNELS):
        cluster.value(i, 90.0)


def read_lines(buffer):
    """
    Drain whatever is waiting on stdin without blocking, split on '\\n'.

    MUST read one byte at a time. MicroPython's sys.stdin.read(n) for n>1
    blocks trying to fill the full requested size even after poll() has
    confirmed data is ready - poll() only guarantees "at least 1 byte is
    available", not "n bytes are available". A previous version of this
    function read(256) per iteration to save per-byte overhead; that is
    what was actually causing the board to hang/wedge, since the Pi sends
    discrete ~150-200 byte JSON lines rather than a continuous stream, so
    the 256-byte read routinely blocked waiting for bytes that weren't
    coming. Every KeyboardInterrupt traceback captured during debugging
    landed inside this function, which is consistent with the board being
    stuck blocked here rather than looping.

    read(1) is confirmed safe: poll()'s "readable" guarantee is exactly
    "read(1) won't block". At the Pi's ~50Hz/~150-200 byte line rate this
    is at most a few hundred read(1) calls per 20ms tick - well inside the
    RP2040's budget - so there's no real throughput reason to batch here.
    """
    lines = []

    while poll.poll(0):
        ch = sys.stdin.read(1)
        if not ch:
            break
        buffer += ch
        if ch == "\n":
            line, buffer = buffer[:-1], ""
            lines.append(line)

    return lines, buffer


def read_rail_telemetry():
    adc_mux.select(servo2040.VOLTAGE_SENSE_ADDR)
    voltage_v = voltage_sense.read_voltage()

    adc_mux.select(servo2040.CURRENT_SENSE_ADDR)
    current_a = current_sense.read_current()

    return voltage_v, current_a


def send_telemetry():
    error = None

    try:
        voltage_v, current_a = read_rail_telemetry()
        ok = True
    except Exception as e:
        voltage_v, current_a = None, None
        ok = False
        # str(e) is often empty on MicroPython for some exception types -
        # the exception's class name is usually the more useful part.
        error = "{}: {}".format(type(e).__name__, e)

    print(json.dumps({
        "type": "telemetry",
        "t": time.ticks_ms(),
        "voltage_v": voltage_v,
        "current_a": current_a,
        "ok": ok,
        "error": error,
    }))


def main():
    buffer = ""
    last_command_ms = time.ticks_ms()
    last_telemetry_ms = time.ticks_ms()
    watchdog_tripped = False

    while True:
        now_ms = time.ticks_ms()

        lines, buffer = read_lines(buffer)
        for line in lines:
            line = line.strip()
            if not line:
                continue

            try:
                payload = json.loads(line)

                if payload.get("reset"):
                    # Requested by hexapod_controller.py's graceful shutdown
                    # handler - a real reset (equivalent to the physical
                    # button) leaves the board in a clean state for
                    # whatever connects next, rather than one that has to
                    # be interrupted out of a running loop.
                    import machine
                    machine.reset()

                channels = payload.get("ch")
                if isinstance(channels, list):
                    apply_channels(channels)
                    last_command_ms = now_ms
                    watchdog_tripped = False
            except Exception:
                # Malformed line, ignored - does not refresh the watchdog.
                pass

        if time.ticks_diff(now_ms, last_command_ms) > WATCHDOG_MS:
            if not watchdog_tripped:
                apply_neutral()
                watchdog_tripped = True

        if time.ticks_diff(now_ms, last_telemetry_ms) > TELEMETRY_INTERVAL_MS:
            send_telemetry()
            last_telemetry_ms = now_ms

        time.sleep_ms(2)


if __name__ == "__main__":
    main()
