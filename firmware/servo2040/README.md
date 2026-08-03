# Servo 2040 firmware

`main.py` is the RP2040-side firmware for the hexapod's Pimoroni Servo 2040. It is **not** part of the Pi's apt/pip dependency chain — `install.sh`/`update.sh` never touch this board. It has to be flashed manually, and re-flashed manually if the board is ever replaced.

It is deliberately thin: it applies servo angles it's told to apply and reports back rail voltage/current. All gait/IK computation happens on the Pi (`gidget/hexapod_kinematics.py` + `gidget/hexapod_controller.py`) — see the protocol description at the top of `main.py`.

## Flashing

1. Install [Pimoroni's MicroPython build](https://github.com/pimoroni/pimoroni-pico/releases) for Servo 2040 (the `.uf2` file specific to this board, not a generic RP2040 MicroPython build — it's what provides the `servo`/`pimoroni` modules `main.py` imports).
   - Hold **BOOT/BOOTSEL** while plugging in USB, or while pressing **RESET**, until it appears as a USB mass-storage drive.
   - Copy the `.uf2` file onto that drive. The board reboots into MicroPython automatically.
2. Copy `main.py` from this directory onto the board as `main.py` (MicroPython runs whatever is saved as `main.py` on boot). Use [Thonny](https://thonny.org/) (Files panel, drag-and-drop) or `mpremote`:
   ```bash
   mpremote connect <port> cp main.py :main.py
   ```
3. Reset the board (or power-cycle it). `main.py` starts automatically and begins listening on USB serial.

## Verifying

With the board connected to a PC (not yet the Pi), open a serial terminal (Thonny's REPL, or `mpremote connect <port> repl`) and send a test command line:

```json
{"t": 0, "ch": [90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90,90]}
```

All 18 channels should center. Within ~500ms you should see a `{"type": "telemetry", ...}` line reported back. If servos don't move, or the ADC read fails, cross-check the `ServoCluster`/`Analog`/`AnalogMux` calls in `main.py` against `help(ServoCluster)` / `help(Analog)` on your installed firmware version — Pimoroni has adjusted these constructor signatures across releases, and `main.py` was written against their examples as documented at the time, not verified against real hardware.

## Once wired to the actual hexapod

Two things in `gidget/hexapod_kinematics.py` on the Pi side need real values from this board once it's wired up — this firmware doesn't need any changes for either:
- `CHANNEL_MAP` — which of the 18 channels drives which (leg, joint).
- The udev rule (`udev/99-gidget-servo2040.rules`) — needs this board's actual USB VID:PID, found via `lsusb` once it's plugged into the Pi.
