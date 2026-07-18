# gidget_pi

Software stack for **Gidget**, a Raspberry Pi Zero WH robot controller with a Flask dashboard, GPS tracking, OLED status output, WiFi management, file browsing, and live sensor telemetry.

The current build targets a Pi Zero-class board, so the code favours simple systemd services and lightweight JSON state files over heavier robotics middleware.

## Current features

- Flask dashboard on port `8080`
- Login-protected web UI
- WiFi status and WiFi configuration tools
- GPS telemetry and JSONL track logging
- OLED status display
- Environmental telemetry from AHT20 + BMP280
- VL53L0X / VL53L1X LIDAR/rangefinder telemetry
- BMI160 6-axis IMU telemetry
- File browser for track/history data
- System health metrics including CPU temperature, CPU usage, memory, disk, and uptime
- Installer and updater scripts for Raspberry Pi deployment

## Hardware currently supported

### Raspberry Pi

Tested target:

```text
Raspberry Pi Zero WH
Raspberry Pi OS / Debian Trixie based install
I2C enabled
Hardware UART enabled for GPS
```

### Connected modules

| Module | Interface | Expected address/device | Purpose |
|---|---|---:|---|
| SSD1306 OLED | I2C | `0x3c` | Local status display |
| AHT20 | I2C | `0x38` | Temperature and humidity |
| BMP280 | I2C | `0x76` or `0x77` | Temperature, pressure, approximate altitude |
| VL53L0X / VL53L1X | I2C | `0x29` | Forward distance / range telemetry |
| BMI160 | I2C | `0x68` or `0x69` | Acceleration, gyro, pitch/roll estimate |
| GPS module | UART | `/dev/serial0` | Position, speed, course, track logging |

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
gidget/data/tracks/*.jsonl
```

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

Then reboot:

```bash
sudo reboot
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

gidget-oled.service
    OLED status display
```

Useful commands:

```bash
systemctl status gidget-web.service --no-pager
systemctl status gidget-gps.service --no-pager
systemctl status gidget-env.service --no-pager
systemctl status gidget-lidar.service --no-pager
systemctl status gidget-imu.service --no-pager
systemctl status gidget-oled.service --no-pager

journalctl -u gidget-web.service -n 100 --no-pager
journalctl -u gidget-gps.service -n 100 --no-pager
journalctl -u gidget-env.service -n 100 --no-pager
journalctl -u gidget-lidar.service -n 100 --no-pager
journalctl -u gidget-imu.service -n 100 --no-pager
journalctl -u gidget-oled.service -n 100 --no-pager
```

## Performance notes for Pi Zero

The Pi Zero is CPU constrained. The sensor services intentionally write lightweight JSON state files at human-dashboard rates rather than high-frequency robotics rates.

Current conservative telemetry rates:

| Service | Poll interval | JSON write interval | History length |
|---|---:|---:|---:|
| LIDAR | 0.10s | 0.50s | 60 samples |
| IMU | 0.20s | 0.75s | 60 samples |
| Environment | 5.00s | every sample | latest values |

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
