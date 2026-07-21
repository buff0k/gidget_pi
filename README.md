# gidget_pi

Software stack for **Gidget**, a Raspberry Pi robot controller with a Flask dashboard, GPS tracking, OLED status output, WiFi management, file browsing, a live camera feed, and live sensor telemetry.

The project started on a Pi Zero WH and has since migrated to a Raspberry Pi 5 (2GB) with a Camera Module added. The code still favours simple systemd services and lightweight JSON state files over heavier robotics middleware, since that model carried over cleanly from the Pi Zero build.

## Current features

- Flask dashboard on port `8080`
- Login-protected web UI
- WiFi status and WiFi configuration tools
- GPS telemetry and JSONL track logging
- OLED status display
- Environmental telemetry from AHT20 + BMP280
- VL53L0X / VL53L1X LIDAR/rangefinder telemetry
- BMI160 6-axis IMU telemetry
- Live MJPEG camera stream with sensor overlay
- File browser for track/history data
- System health metrics including CPU temperature, CPU usage, memory, disk, and uptime
- Installer and updater scripts for Raspberry Pi deployment

## Hardware currently supported

### Raspberry Pi

Tested target:

```text
Raspberry Pi 5 (2GB)
Raspberry Pi Camera Module (CSI)
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

## Repository layout

```text
gidget_pi/
├── dependencies.list
├── install.sh
├── pyproject.toml
├── update.sh
├── gidget/
│   ├── app.py
│   ├── auth.py
│   ├── camera_reader.py
│   ├── env_reader.py
│   ├── gps_reader.py
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
    ├── gidget-imu.service
    ├── gidget-lidar.service
    ├── gidget-oled.service
    └── gidget-web.service
```

Runtime files are generated on the Pi and should not be committed:

```text
gidget/config/users.json
gidget/status_state.json
gidget/environment_state.json
gidget/lidar_state.json
gidget/imu_state.json
gidget/camera_state.json
gidget/data/tracks/*.jsonl
```

The camera service also writes the latest JPEG frame to `/dev/shm/gidget/camera_frame.jpg` (tmpfs, RAM-backed) rather than the SD card, so it never appears in the repo or in `/opt/gidget`.

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

gidget-oled.service
    OLED status display
```

Note that `gidget-camera.service` is the sole owner of the camera hardware. The web process never opens the camera itself — it only reads the latest frame that `gidget-camera.service` has written to `/dev/shm/gidget/camera_frame.jpg`. Restarting `gidget-camera.service` briefly interrupts the `/camera/` stream but does not affect the web process.

Useful commands:

```bash
systemctl status gidget-web.service --no-pager
systemctl status gidget-gps.service --no-pager
systemctl status gidget-env.service --no-pager
systemctl status gidget-lidar.service --no-pager
systemctl status gidget-imu.service --no-pager
systemctl status gidget-camera.service --no-pager
systemctl status gidget-oled.service --no-pager

journalctl -u gidget-web.service -n 100 --no-pager
journalctl -u gidget-gps.service -n 100 --no-pager
journalctl -u gidget-env.service -n 100 --no-pager
journalctl -u gidget-lidar.service -n 100 --no-pager
journalctl -u gidget-imu.service -n 100 --no-pager
journalctl -u gidget-camera.service -n 100 --no-pager
journalctl -u gidget-oled.service -n 100 --no-pager
```

## Performance notes

The sensor services intentionally write lightweight JSON state files at human-dashboard rates rather than high-frequency robotics rates. This dates back to the Pi Zero build; the Pi 5 has plenty of headroom for these rates, so they remain conservative by choice rather than necessity.

Current conservative telemetry rates:

| Service | Poll interval | JSON write interval | History length |
|---|---:|---:|---:|
| LIDAR | 0.10s | 0.50s | 60 samples |
| IMU | 0.20s | 0.75s | 60 samples |
| Environment | 5.00s | every sample | latest values |
| Camera | 0.10s (~10 fps) | frame: every capture; state: 2.00s | latest frame only |

The camera writes each JPEG frame to `/dev/shm` (tmpfs) rather than `/opt/gidget` on the SD card, so continuous frame writes don't cause SD card wear. Frame rate/resolution/JPEG quality are set in `camera_reader.py` (`RESOLUTION`, `CAPTURE_SECONDS`, `JPEG_QUALITY`) — raise capture rate or resolution only after confirming CPU headroom, since encoding cost scales with both.

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

For true high-rate telemetry, the likely next architecture step is a single in-memory telemetry service or a message bus rather than several independent services writing full JSON state files.

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
