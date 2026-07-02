# gidget_pi

Software stack for the Gidget hexapod Raspberry Pi Zero controller.

This repository installs the Gidget Flask dashboard, GPS logger, OLED status display, WiFi configuration UI, file browser, and systemd services onto a Raspberry Pi.

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
│   ├── gps_reader.py
│   ├── oled_status.py
│   ├── services.py
│   ├── wifi_manager.py
│   ├── pages/
│   ├── static/
│   └── templates/
└── systemd/
    ├── gidget-gps.service
    ├── gidget-oled.service
    └── gidget-web.service
```

Runtime files are generated on the Pi and should not be committed:

```text
gidget/config/users.json
gidget/status_state.json
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
chmod +x install.sh update.sh
sudo ./install.sh
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
cd gidget_pi
git status
sudo ./update.sh
```

The updater runs `git pull --ff-only`, updates application files, preserves runtime config and GPS history, then restarts the Gidget services.

## Services

```text
gidget-web.service
    Flask dashboard on port 8080

gidget-gps.service
    GPS serial reader and JSONL track logger

gidget-oled.service
    OLED status display
```

Useful commands:

```bash
systemctl status gidget-web.service
systemctl status gidget-gps.service
systemctl status gidget-oled.service

journalctl -u gidget-web.service -n 100 --no-pager
journalctl -u gidget-gps.service -n 100 --no-pager
journalctl -u gidget-oled.service -n 100 --no-pager
```
