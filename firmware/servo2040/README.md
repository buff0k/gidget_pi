# Servo 2040 firmware

`main.py` is the RP2040-side firmware for the hexapod's Pimoroni Servo 2040. It is **not** part of the Pi's apt/pip dependency chain — `install.sh`/`update.sh` never touch this board. It has to be flashed manually, and re-flashed manually if the board is ever replaced.

It is deliberately thin: it applies servo angles it's told to apply and reports back rail voltage/current. All gait/IK computation happens on the Pi (`gidget/hexapod_kinematics.py` + `gidget/hexapod_controller.py`) — see the protocol description at the top of `main.py`.

## Flashing

1. Install Pimoroni's MicroPython build from their [releases page](https://github.com/pimoroni/pimoroni-pico/releases). There is **no dedicated `servo2040` `.uf2`** — Pimoroni bundles support for their RP2040-based accessory boards (Servo 2040, Motor 2040, Plasma 2040, etc.) into the plain **`pico`** build, since those boards use the standard RP2040 chip with no extra onboard silicon; only boards with genuinely different hardware (Pico W's wireless chip, Tufty's display, Enviro's e-ink) get their own dedicated build. As of v1.27.0, the correct asset is:
   ```text
   pico-v1.27.0-pimoroni-micropython.uf2
   ```
   Check the releases page for a newer version before flashing — this was confirmed against the latest release at the time this was written, not guaranteed to stay current.
   - Hold **BOOT/BOOTSEL** while plugging in USB, or while pressing **RESET**, until it appears as a USB mass-storage drive (commonly `RPI-RP2`).
   - Copy the `.uf2` file onto that drive. The board reboots into MicroPython automatically.
2. Confirm the `servo2040` module is actually present before going further (`mpremote` installs via `pip install mpremote`):
   ```bash
   mpremote connect <port> exec "import servo2040; print(servo2040.SERVO_1, servo2040.NUM_SERVOS)"
   ```
   If that raises `ImportError`, the build doesn't include Servo 2040 support — double check you flashed the `pico` variant, not a different board's build.
3. Copy `main.py` from this directory onto the board as `main.py` (MicroPython runs whatever is saved as `main.py` on boot). Use [Thonny](https://thonny.org/) (Files panel, drag-and-drop) or `mpremote`:
   ```bash
   mpremote connect <port> cp main.py :main.py
   ```
4. Reset the board (or power-cycle it). `main.py` starts automatically and begins listening on USB serial.

## Verifying

The fastest debug loop is running `main.py` live from the Pi without saving it to the board first — this streams the board's stdout (including tracebacks) straight back to your terminal:

```bash
sudo systemctl stop gidget-hexapod.service   # so nothing else holds the port
mpremote connect <port> run firmware/servo2040/main.py
# Ctrl-C to stop
sudo systemctl start gidget-hexapod.service  # hand the port back when done
```

You should see a `{"type": "telemetry", "ok": true, "voltage_v": ..., "current_a": ..., ...}` line roughly every 500ms. `"ok": false` means `read_rail_telemetry()` threw — the `"error"` field it includes gives the exception type and message, which is usually enough to fix directly.

The `Analog`/`AnalogMux` construction in `main.py` is matched verbatim against Pimoroni's own `read_sensors.py`/`current_meter.py` examples (fetched from `pimoroni-pico` on GitHub) — notably `AnalogMux`'s `muxed_pin` argument needs an actual `machine.Pin`, not a raw pin number or an `Analog(...)` wrapper (both fail with `AttributeError: ... has no attribute 'init'`, which is what the constructor calls internally on whatever it's given). If a future Pimoroni firmware update changes this again, that's the failure mode to expect.

Once telemetry looks right, confirm servo motion separately — telemetry failing doesn't necessarily mean channel commands aren't being applied, and vice versa. With `gidget-hexapod.service` running, use the Manual/Diagnostics sliders on `/hexapod/` to drive individual channels directly.

## Calibration convention (0-180, 90 = center) - NOT Pimoroni's default

Pimoroni's default `ServoCluster`/`Servo` calibration (`ANGULAR`) centers on a raw value of **0**, with a range of **-90..+90** - not 0-180 with 90 as center. Confirmed directly against Pimoroni's own source, not inferred:
- `servo2040/calibration.py`'s own comment: `# By default its value ranges from -90 to +90`.
- `servo2040/servo_cluster.py`'s sweep demo: `all_to_mid()` is the center call, and its sweep uses a `+/-90` extent around it.

Everything else in this project (`gidget/hexapod_kinematics.py`'s IK math, `gidget/hexapod_controller.py`, the web UI's manual sliders and Calibration panel) assumes the conventional 0-180-with-90-as-center range. Sending a raw `90` under Pimoroni's *default* calibration therefore drives a channel to its full end-of-travel, not center — a 90 degree error. `main.py` fixes this at startup, before anything is ever commanded, by giving every channel a custom `Calibration` (`apply_three_pairs(500, 1500, 2500, 0, 90, 180)`) that maps the *same* physical pulse widths (500-2500us, the standard hobby-servo full range) onto 0-180 instead. The actual PWM output for a given physical position is unchanged from Pimoroni's default — only the number used to ask for it changes. If this firmware is ever rewritten from scratch, this step is not optional: skipping it means every "90" sent from the Pi side actually means "full deflection."

## Once wired to the actual hexapod

Two things need real values from this board once it's wired up — this firmware doesn't need any changes for either, and both are edited live from the `/hexapod/` web UI (Calibration and Channel Mapping panels), not hardcoded:
- The channel map — which of the 18 channels drives which (leg, joint). Persisted in `config/hexapod_calibration.json` on the Pi (see `gidget/hexapod_calibration.py`), not in this firmware.
- The udev rule (`udev/99-gidget-servo2040.rules`) — needs this board's actual USB VID:PID, found via `lsusb` once it's plugged into the Pi.
