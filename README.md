# gidget_pi

Software stack for **Gidget**, a Raspberry Pi-controlled hexapod with a Flask dashboard, GPS tracking, OLED status output, WiFi management, file browsing, a live camera feed, live sensor telemetry, and web-driven leg control.

The project started on a Pi Zero WH and has since migrated to a Raspberry Pi 5 (2GB), added a Camera Module, and added a Pimoroni Servo 2040 driving 18 leg servos. The code still favours simple systemd services and lightweight JSON state files over heavier robotics middleware, since that model carried over cleanly through each hardware change.

## Current features

- Flask dashboard on port `8080`
- Login-protected web UI
- WiFi status and WiFi configuration tools
- GPS telemetry and JSONL track logging
- OLED status display
- Environmental telemetry from AHT20 + BMP280
- VL53L0X / VL53L1X LIDAR/rangefinder telemetry
- BMI160 6-axis IMU telemetry
- Live MJPEG camera stream with sensor overlay, including an optional HUD-style false horizon
- Hexapod leg control: inverse kinematics + 4 gaits (tripod/wave/ripple/tetrapod) computed on the Pi, driven by a web joystick, with a live leg-position visualizer
- File browser for track/history data
- System health metrics including CPU temperature, CPU usage, memory, disk, and uptime
- Installer and updater scripts for Raspberry Pi deployment

## Hardware currently supported

### Raspberry Pi

Tested target:

```text
Raspberry Pi 5 (2GB)
Raspberry Pi Camera Module (CSI)
Pimoroni Servo 2040 (18-channel hexapod leg driver, USB)
Raspberry Pi OS / Debian Trixie based install
I2C enabled
Hardware UART enabled for GPS
Camera auto-detected over CSI
```

Originally built and tested against a Raspberry Pi Zero WH; the sensor code (Blinka/`board`/`busio`) is unchanged by the Pi 5 migration, but installer/config steps below are Pi 5-specific where noted.

### Connected modules

| Module | Interface | Expected address/device | Purpose |
|---|---|---:|---|
| SSD1306 OLED | I2C | `0x3c` | Local status display |
| AHT20 | I2C | `0x38` | Temperature and humidity |
| BMP280 | I2C | `0x76` or `0x77` | Temperature, pressure, approximate altitude |
| VL53L0X / VL53L1X | I2C | `0x29` | Forward distance / range telemetry |
| BMI160 | I2C | `0x68` or `0x69` | Acceleration, gyro, pitch/roll estimate |
| GPS module | UART | `/dev/serial0` | Position, speed, course, track logging |
| Raspberry Pi Camera Module | CSI | `/dev/video0` (via libcamera) | Live MJPEG video feed |
| Pimoroni Servo 2040 | USB (not I2C) | `/dev/gidget-servo2040` (udev-stabilized) | Drives 18x MG996 hexapod leg servos, reports rail voltage/current |

A healthy I2C scan with the current modules may look similar to:

```text
0x29  VL53L0X / VL53L1X
0x38  AHT20
0x3c  SSD1306 OLED
0x68  BMI160, depending on SA0 wiring
0x77  BMP280, depending on breakout address
```

Check with:

```bash
i2cdetect -y 1
```

## Raspberry Pi physical pin wiring

### Shared I2C bus

All current I2C modules share the same Raspberry Pi I2C bus. This means the OLED, AHT20, BMP280, VL53 sensor, and BMI160 all connect to the same SDA/SCL pins.

| Pi physical pin | Pi function | Connected module pins |
|---:|---|---|
| Pin 1 | 3V3 | OLED VCC, AHT20/BMP280 VCC, VL53 VIN/VCC, BMI160 VIN |
| Pin 3 | GPIO2 / SDA1 | OLED SDA, AHT20/BMP280 SDA, VL53 SDA, BMI160 SDA |
| Pin 5 | GPIO3 / SCL1 | OLED SCL, AHT20/BMP280 SCL, VL53 SCL, BMI160 SCL |
| Pin 6 | GND | OLED GND, AHT20/BMP280 GND, VL53 GND, BMI160 GND |

Use 3.3V for sensor boards unless the specific breakout is known to be safely level-shifted for 5V logic.

### SSD1306 OLED

| OLED pin | Pi physical pin | Pi function |
|---|---:|---|
| VCC | Pin 1 | 3V3 |
| GND | Pin 6 | GND |
| SDA | Pin 3 | GPIO2 / SDA1 |
| SCL | Pin 5 | GPIO3 / SCL1 |

Expected I2C address: `0x3c`.

### AHT20 + BMP280 environmental sensor

| Sensor pin | Pi physical pin | Pi function |
|---|---:|---|
| VCC / VIN | Pin 1 | 3V3 |
| GND | Pin 6 | GND |
| SDA | Pin 3 | GPIO2 / SDA1 |
| SCL | Pin 5 | GPIO3 / SCL1 |

Expected I2C addresses:

```text
AHT20   0x38
BMP280  0x76 or 0x77
```

### VL53L0X / VL53L1X range sensor

Minimum wiring:

| Module pin | Pi physical pin | Pi function |
|---|---:|---|
| VIN / VCC | Pin 1 | 3V3 |
| GND | Pin 6 | GND |
| SDA | Pin 3 | GPIO2 / SDA1 |
| SCL | Pin 5 | GPIO3 / SCL1 |

Expected I2C address: `0x29`.

Leave these disconnected for the current single-sensor polling setup:

```text
GPIO1
XSHUT
```

`GPIO1` is normally an optional interrupt/data-ready output. `XSHUT` is useful later for software reset or for running multiple VL53 sensors on the same I2C bus.

Future optional wiring:

| VL53 pin | Suggested Pi physical pin | Pi GPIO | Purpose |
|---|---:|---:|---|
| GPIO1 | Pin 13 | GPIO27 | Data-ready interrupt |
| XSHUT | Pin 11 | GPIO17 | Sensor shutdown/reset/address setup |

### BMI160 6-axis IMU

Minimum I2C wiring:

| BMI160 pin | Pi physical pin | Pi function |
|---|---:|---|
| VIN | Pin 1 | 3V3 preferred |
| GND | Pin 6 | GND |
| SDA | Pin 3 | GPIO2 / SDA1 |
| SCL | Pin 5 | GPIO3 / SCL1 |
| SAO / SA0 | GND or 3V3 | Address select: usually `0x68` or `0x69` |

Leave these disconnected for the current polling setup:

```text
OCS
INT1
INT2
SCX
SDX
CS
```

INT1/INT2 may be useful later for motion interrupts, tap detection, or wake-on-motion. The current service simply polls the sensor.

### GPS module on UART

The GPS module uses the Pi hardware serial port, exposed as `/dev/serial0` when configured correctly.

| GPS pin | Pi physical pin | Pi function | Notes |
|---|---:|---|---|
| VCC | Pin 1 or Pin 2/4 | 3V3 or 5V | Depends on GPS breakout voltage support |
| GND | Pin 6 | GND | Common ground |
| GPS TX | Pin 10 | GPIO15 / RXD0 | GPS transmits NMEA data to Pi RX |
| GPS RX | Pin 8 | GPIO14 / TXD0 | Optional; Pi transmits to GPS |

For simple NMEA reading, the critical line is **GPS TX -> Pi RXD0 / physical pin 10**.

The Pi serial console must be disabled while the hardware serial port remains enabled:

```text
Login shell over serial? No
Serial port hardware enabled? Yes
```

### Raspberry Pi Camera Module (CSI)

The camera connects over the CSI ribbon connector, not GPIO pins:

```text
Power off the Pi before connecting/disconnecting the ribbon cable.
Blue tab on the ribbon faces the USB/Ethernet side on a Pi 5.
Seat the cable fully, then close the connector latch.
```

Unlike I2C and serial, the camera does **not** need a `raspi-config` toggle on a current Bookworm/Trixie-based Raspberry Pi OS install — the legacy `Enable Camera` option was removed along with the legacy camera stack. The libcamera stack auto-detects the camera on boot as long as `camera_auto_detect=1` is present in `/boot/firmware/config.txt` (this is the default on a stock Raspberry Pi OS image; only check it if the camera isn't detected).

Verify detection after connecting the camera and rebooting:

```bash
rpicam-hello --list-cameras
```

A detected Camera Module 3 looks similar to:

```text
0 : imx708 [4608x2592 10-bit RGGB] (/base/axi/pcie@1000120000/rp1/i2c@88000/imx708@1a)
```

If the camera isn't listed:

```text
Reseat the CSI ribbon cable at both ends (camera and Pi 5 connector).
Confirm camera_auto_detect=1 in /boot/firmware/config.txt, then reboot.
For a camera that isn't auto-detected (e.g. an older/third-party sensor),
add its dtoverlay explicitly, for example:
    dtoverlay=imx708
then reboot.
```

If `Picamera2` reports out-of-memory or buffer allocation errors on the 2GB Pi 5, raise the CMA (contiguous memory) reservation used by the display/camera stack, for example:

```text
dtoverlay=vc4-kms-v3d,cma-256
```

in `/boot/firmware/config.txt`, then reboot.

The `gidget` service user needs `video`/`render` group membership to access `/dev/video*` — the installer adds this automatically (see [Installation](#initial-install)).

### Pimoroni Servo 2040 (18-channel hexapod driver)

The Servo 2040 drives all 18 leg servos and connects to the Pi over **USB, not I2C** — despite the RP2040 having I2C hardware, Pimoroni's stock MicroPython firmware doesn't support running it as an I2C target/slave device, so USB serial is the only practical link:

```text
Servo power: 18x MG996 servos powered from the Servo 2040's own dedicated
             5V servo power rail (JST-PH input), separate from its USB/logic
             power. Size this supply for real stall current across 18
             servos, not just typical running current.
Data:        Servo 2040 USB-C -> Pi 5 USB-A, plain USB cable.
```

All gait/IK computation runs on the Pi (`gidget/hexapod_kinematics.py` + `gidget/hexapod_controller.py`); the Servo 2040 itself only runs the thin peripheral firmware in `firmware/servo2040/` (flashed manually — see that directory's `README.md`, since it's outside this repo's apt/pip dependency chain).

Two things are real hardware facts that only get filled in once the board is wired up — both are called out with `PLACEHOLDER` comments at the point they're used, so they're easy to find:

```text
CHANNEL_MAP in gidget/hexapod_kinematics.py
    Which of the Servo 2040's 18 channels drives which (leg, joint).
    Ships as a sequential 0-17 placeholder in leg order.

idVendor/idProduct in udev/99-gidget-servo2040.rules
    The board's actual USB VID:PID, so /dev/gidget-servo2040 stays a
    stable path regardless of USB enumeration order. Find the real
    values once connected with:
        lsusb
        udevadm info -a -n /dev/ttyACM0 | grep -E 'idVendor|idProduct'
```

The leg geometry constants (segment lengths, home positions, per-leg calibration) in `hexapod_kinematics.py` are **not** placeholders — they're ported as final values from the reference hexapod build this project is based on.

## Repository layout

```text
gidget_pi/
├── dependencies.list
├── install.sh
├── pyproject.toml
├── update.sh
├── firmware/
│   └── servo2040/
│       ├── main.py
│       └── README.md
├── udev/
│   └── 99-gidget-servo2040.rules
├── gidget/
│   ├── app.py
│   ├── auth.py
│   ├── camera_reader.py
│   ├── env_reader.py
│   ├── gps_reader.py
│   ├── hexapod_controller.py
│   ├── hexapod_kinematics.py
│   ├── imu_reader.py
│   ├── lidar_reader.py
│   ├── oled_status.py
│   ├── services.py
│   ├── wifi_manager.py
│   ├── pages/
│   ├── static/
│   └── templates/
└── systemd/
    ├── gidget-camera.service
    ├── gidget-env.service
    ├── gidget-gps.service
    ├── gidget-hexapod.service
    ├── gidget-imu.service
    ├── gidget-lidar.service
    ├── gidget-oled.service
    └── gidget-web.service
```

Runtime files are generated on the Pi and should not be committed:

```text
gidget/config/users.json
gidget/data/tracks/*.jsonl
```

Live sensor telemetry (GPS status, LIDAR, IMU, environment, camera, and hexapod state) is written to `/dev/shm/gidget/` (tmpfs, RAM-backed) rather than `/opt/gidget` on the SD card, so none of it appears in the repo or on disk:

```text
/dev/shm/gidget/status_state.json
/dev/shm/gidget/environment_state.json
/dev/shm/gidget/lidar_state.json
/dev/shm/gidget/imu_state.json
/dev/shm/gidget/camera_state.json
/dev/shm/gidget/camera_frame.jpg
/dev/shm/gidget/hexapod_state.json
/dev/shm/gidget/hexapod_command.json
```

`hexapod_command.json` is the one file in that list written by the web process rather than a reader service — it's the relay the dashboard's joystick uses to reach `gidget-hexapod.service` (see [Services](#services) below), timestamped so the controller can detect and ignore a stale command.

This is deliberate: these files are rewritten multiple times per second (GPS state in particular used to be rewritten on nearly every NMEA sentence, several times a second) and have no need to survive a reboot, so keeping them off the SD card avoids wearing out the card. Only GPS track history (`gidget/data/tracks/*.jsonl`) persists to the SD card, since that's data you actually want to keep across reboots.

## Raspberry Pi prerequisites

Before installing, enable I2C and hardware serial:

```bash
sudo raspi-config
```

Use:

```text
Interface Options -> I2C -> Enable
Interface Options -> Serial Port
    Login shell over serial? No
    Serial port hardware enabled? Yes
```

Connect the Camera Module to the CSI connector (see [Raspberry Pi Camera Module (CSI)](#raspberry-pi-camera-module-csi) above). No `raspi-config` toggle is needed for the camera on Bookworm/Trixie-based Raspberry Pi OS — `camera_auto_detect=1` is on by default.

Connect the Servo 2040 over USB (see [Pimoroni Servo 2040](#pimoroni-servo-2040-18-channel-hexapod-driver) above) — no `raspi-config` step either, since it's a plain USB serial device, not an I2C/CSI peripheral. Its own firmware needs to be flashed separately; see `firmware/servo2040/README.md`.

Then reboot:

```bash
sudo reboot
```

After reboot, confirm the camera is detected before running the installer:

```bash
rpicam-hello --list-cameras
```

## Initial install

```bash
git clone https://github.com/buff0k/gidget_pi
cd gidget_pi
sudo bash ./install.sh
```

The installer creates a default web login:

```text
Username: admin
Password: admin
```

Change the password on first login.

Open the dashboard at:

```text
http://gidget.local:8080
```

## Update existing install

From the cloned repository on the Pi:

```bash
cd ~/gidget_pi
git status
sudo bash ./update.sh
```

Use `sudo bash ./update.sh` rather than relying on the executable bit. This avoids local `chmod +x` mode changes blocking `git pull`.

The updater runs `git pull --ff-only`, updates Python dependencies, updates application files, preserves runtime config and track history, installs current systemd unit files, then restarts the Gidget services.

## Web pages

| Path | Purpose |
|---|---|
| `/` | Main dashboard with GPS, environment, network, and system health |
| `/history/` | GPS track history |
| `/gps/` | GPS telemetry view |
| `/lidar/` | LIDAR/rangefinder telemetry and range history |
| `/imu/` | BMI160 acceleration, gyro, and tilt telemetry |
| `/camera/` | Live MJPEG camera stream with LIDAR/IMU/climate overlay |
| `/hexapod/` | Hexapod joystick control, gait/mode selection, and live leg-position visualizer |
| `/config/` | Configuration/admin tools |
| `/files/` | File browser |
| `/users/` | User management |

## Services

```text
gidget-web.service
    Flask dashboard on port 8080

gidget-gps.service
    GPS serial reader and JSONL track logger

gidget-env.service
    AHT20/BMP280 environmental sensor reader

gidget-lidar.service
    VL53L0X/VL53L1X range sensor reader

gidget-imu.service
    BMI160 accelerometer/gyro reader

gidget-camera.service
    Owns the camera exclusively; captures JPEG frames to tmpfs for the web
    process to stream, and writes camera_state.json

gidget-hexapod.service
    Owns the Servo 2040 serial connection exclusively; runs the 20ms
    gait/IK tick loop, sends servo angles, reads back rail voltage/current,
    and writes hexapod_state.json

gidget-oled.service
    OLED status display
```

Note that `gidget-camera.service` is the sole owner of the camera hardware and `gidget-hexapod.service` is the sole owner of the Servo 2040 serial connection — the web process never touches either piece of hardware directly, it only reads the tmpfs state each writes and, for the hexapod, writes a command file the controller polls (`/dev/shm/gidget/hexapod_command.json`). A command older than 0.5s is treated as stale and forced to idle/neutral, so a dropped browser connection can't leave the robot walking; the Servo 2040's own firmware (`firmware/servo2040/`) additionally holds a second, independent watchdog in case `gidget-hexapod.service` itself crashes or is mid-restart.

Useful commands:

```bash
systemctl status gidget-web.service --no-pager
systemctl status gidget-gps.service --no-pager
systemctl status gidget-env.service --no-pager
systemctl status gidget-lidar.service --no-pager
systemctl status gidget-imu.service --no-pager
systemctl status gidget-camera.service --no-pager
systemctl status gidget-hexapod.service --no-pager
systemctl status gidget-oled.service --no-pager

journalctl -u gidget-web.service -n 100 --no-pager
journalctl -u gidget-gps.service -n 100 --no-pager
journalctl -u gidget-env.service -n 100 --no-pager
journalctl -u gidget-lidar.service -n 100 --no-pager
journalctl -u gidget-imu.service -n 100 --no-pager
journalctl -u gidget-camera.service -n 100 --no-pager
journalctl -u gidget-hexapod.service -n 100 --no-pager
journalctl -u gidget-oled.service -n 100 --no-pager
```

## Performance notes

Sensor services write their JSON state files to `/dev/shm/gidget/` (tmpfs, RAM-backed) rather than `/opt/gidget` on the SD card. Because RAM writes carry no wear cost, write cadence is set to match poll cadence for LIDAR and IMU rather than being throttled behind it, which keeps dashboard/overlay latency close to the sensor's own sampling rate.

Current telemetry rates:

| Service | Poll interval | JSON write interval | History length |
|---|---:|---:|---:|
| LIDAR | 0.10s | 0.10s | 60 samples |
| IMU | 0.20s | 0.20s | 60 samples |
| Environment | 5.00s | every sample | latest values |
| GPS | per NMEA sentence | per NMEA sentence | latest values (track history separately, see below) |
| Camera | 0.10s (~10 fps) | frame: every capture; state: 2.00s | latest frame only |
| Hexapod | 0.02s (50Hz gait tick) | every tick | latest leg positions only |

GPS is the busiest writer by far — a typical module emits several NMEA sentences (RMC, GGA, GSA, GSV) per second, each triggering a state rewrite. This is fine on tmpfs but would have been a serious SD card wear source if left on disk, which is why it moved along with the others.

GPS **track history** (`gidget/data/tracks/*.jsonl`) is the one telemetry write that intentionally stays on the SD card, since it's meant to persist across reboots. It's throttled independently to one append per second while the vehicle has a fix and is moving, which keeps it lightweight regardless of how often the tmpfs state above is rewritten.

The camera writes each JPEG frame to `/dev/shm` (tmpfs) as well, so continuous frame writes don't cause SD card wear. Frame rate/resolution/JPEG quality are set in `camera_reader.py` (`RESOLUTION`, `CAPTURE_SECONDS`, `JPEG_QUALITY`) — raise capture rate or resolution only after confirming CPU headroom, since encoding cost scales with both.

The hexapod's 50Hz tick is the fastest loop in this codebase — it's the one place the Pi 5's headroom over the original Pi Zero actually matters for correctness, not just comfort, since IK + gait math for 18 servos has to complete well inside each 20ms frame. If that loop ever falls behind, `gidget-hexapod.service` logs are the first place to check (`journalctl -u gidget-hexapod.service`), followed by whether the Servo 2040's USB serial write is blocking (see the reconnect/error handling notes in `hexapod_controller.py`).

If CPU is pinned, identify the process first:

```bash
ps -eo pid,comm,pcpu,pmem,args --sort=-pcpu | head -20
```

To isolate a service:

```bash
sudo systemctl stop gidget-imu.service
sleep 10
ps -eo pid,comm,pcpu,pmem,args --sort=-pcpu | head -20
sudo systemctl start gidget-imu.service
```

The SD-card-wear concern that used to motivate throttling write cadence is now addressed by keeping all live telemetry state on tmpfs (see above). If even tighter latency is needed later (sub-100ms robotics-rate control loops rather than dashboard/overlay display), the next architecture step would be a shared-memory struct or a message bus between services, rather than per-service JSON files — but for the current dashboard/overlay use case, tmpfs JSON at poll-matched write rates is sufficient.

## Development notes

Python dependencies are defined in `pyproject.toml` and installed into:

```text
/opt/gidget/.venv
```

Application files are synced to:

```text
/opt/gidget
```

The `gidget` system user owns the runtime directory and runs the service processes.
