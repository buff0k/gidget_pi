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
- Installer and updater scripts for