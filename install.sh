#!/usr/bin/env bash
set -Eeuo pipefail

APP_USER="gidget"
APP_GROUP="gidget"
APP_DIR="/opt/gidget"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${APP_DIR}/.venv"
SUDOERS_FILE="/etc/sudoers.d/gidget"
SYSTEMD_DIR="/etc/systemd/system"
SERVICES=(gidget-gps.service gidget-env.service gidget-lidar.service gidget-imu.service gidget-camera.service gidget-oled.service gidget-web.service)

log() { printf '\n[install] %s\n' "$*"; }
fail() { printf '\n[install] ERROR: %s\n' "$*" >&2; exit 1; }

require_root() {
    if [ "${EUID}" -ne 0 ]; then
        fail "Run this installer as root, for example: sudo bash ./install.sh"
    fi
}

find_pi_config() {
    if [ -f /boot/firmware/config.txt ]; then
        printf '%s\n' /boot/firmware/config.txt
    elif [ -f /boot/config.txt ]; then
        printf '%s\n' /boot/config.txt
    else
        printf '%s\n' ""
    fi
}

config_has_i2c_enabled() {
    local cfg="$1"
    [ -n "$cfg" ] && grep -Eiq '^[[:space:]]*dtparam=i2c(_arm)?=on' "$cfg"
}

config_has_serial_enabled() {
    local cfg="$1"
    [ -n "$cfg" ] && grep -Eiq '^[[:space:]]*enable_uart=1' "$cfg"
}

check_pi_interfaces() {
    log "Checking Raspberry Pi I2C and serial configuration"

    local cfg
    cfg="$(find_pi_config)"

    local i2c_ok=0
    local serial_ok=0

    if [ -e /dev/i2c-1 ] || config_has_i2c_enabled "$cfg"; then
        i2c_ok=1
    fi

    if [ -e /dev/serial0 ] || config_has_serial_enabled "$cfg"; then
        serial_ok=1
    fi

    if [ "$i2c_ok" -ne 1 ] || [ "$serial_ok" -ne 1 ]; then
        cat >&2 <<MSG

Gidget requires I2C and hardware serial to be enabled before installation continues.

Enable them with:
  sudo raspi-config

Then:
  Interface Options -> I2C -> Enable
  Interface Options -> Serial Port
      Login shell over serial? No
      Serial port hardware enabled? Yes

Reboot after changing these settings:
  sudo reboot

Detected config file: ${cfg:-not found}
/dev/i2c-1 present: $([ -e /dev/i2c-1 ] && echo yes || echo no)
/dev/serial0 present: $([ -e /dev/serial0 ] && echo yes || echo no)
MSG
        exit 1
    fi
}

read_apt_dependencies() {
    sed 's/#.*$//' "${REPO_DIR}/dependencies.list" | awk 'NF {print $1}'
}

install_apt_dependencies() {
    log "Installing APT dependencies"

    [ -f "${REPO_DIR}/dependencies.list" ] || fail "Missing dependencies.list in repo root"

    apt-get update
    # shellcheck disable=SC2046
    apt-get install -y $(read_apt_dependencies)
}

ensure_system_user() {
    log "Ensuring system user ${APP_USER} exists"

    if ! id -u "${APP_USER}" >/dev/null 2>&1; then
        useradd --system --home "${APP_DIR}" --shell /usr/sbin/nologin --create-home "${APP_USER}"
    fi

    for group in i2c dialout gpio video render; do
        if getent group "$group" >/dev/null 2>&1; then
            usermod -aG "$group" "${APP_USER}"
        fi
    done
}

ensure_app_dirs() {
    log "Creating application directories"

    mkdir -p "${APP_DIR}"
    mkdir -p "${APP_DIR}/config"
    mkdir -p "${APP_DIR}/data/tracks"
    chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}"
}

create_venv_and_install_pip_deps() {
    log "Creating Python virtual environment and installing pip dependencies"

    if [ ! -x "${VENV_DIR}/bin/python" ]; then
        python3 -m venv "${VENV_DIR}" --system-site-packages
    fi

    chown -R "${APP_USER}:${APP_GROUP}" "${VENV_DIR}"

    "${VENV_DIR}/bin/python" -m pip install --upgrade pip setuptools wheel

    REPO_DIR="${REPO_DIR}" "${VENV_DIR}/bin/python" <<'PY'
import os
import subprocess
import sys
from pathlib import Path
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

repo = Path(os.environ["REPO_DIR"])
pyproject = repo / "pyproject.toml"
data = tomllib.loads(pyproject.read_text())
deps = data.get("project", {}).get("dependencies", [])
if deps:
    subprocess.check_call([sys.executable, "-m", "pip", "install", *deps])
PY
}

sync_application_files() {
    log "Copying application files to ${APP_DIR}"

    [ -d "${REPO_DIR}/gidget" ] || fail "Missing gidget/ folder in repo root"

    rsync -a --delete \
        --exclude '.venv/' \
        --exclude 'config/users.json' \
        --exclude 'status_state.json' \
        --exclude 'environment_state.json' \
        --exclude 'lidar_state.json' \
        --exclude 'imu_state.json' \
        --exclude 'camera_state.json' \
        --exclude 'data/tracks/*.jsonl' \
        "${REPO_DIR}/gidget/" "${APP_DIR}/"

    mkdir -p "${APP_DIR}/config" "${APP_DIR}/data/tracks"
}

create_default_runtime_files() {
    log "Creating default runtime config/state where missing"

    if [ ! -f "${APP_DIR}/status_state.json" ]; then
        printf '{}\n' > "${APP_DIR}/status_state.json"
    fi

    if [ ! -f "${APP_DIR}/environment_state.json" ]; then
        printf '{}\n' > "${APP_DIR}/environment_state.json"
    fi

    if [ ! -f "${APP_DIR}/lidar_state.json" ]; then
        printf '{}\n' > "${APP_DIR}/lidar_state.json"
    fi

    if [ ! -f "${APP_DIR}/imu_state.json" ]; then
        printf '{}\n' > "${APP_DIR}/imu_state.json"
    fi

    if [ ! -f "${APP_DIR}/camera_state.json" ]; then
        printf '{}\n' > "${APP_DIR}/camera_state.json"
    fi

    if [ ! -f "${APP_DIR}/config/users.json" ]; then
        cd "${APP_DIR}"
        "${VENV_DIR}/bin/python" - <<'PY'
from auth import ensure_users_file
ensure_users_file()
PY
    fi
}

install_systemd_services() {
    log "Installing systemd service files"

    [ -d "${REPO_DIR}/systemd" ] || fail "Missing systemd/ folder in repo root"

    install -m 0644 "${REPO_DIR}/systemd/gidget-gps.service" "${SYSTEMD_DIR}/gidget-gps.service"
    install -m 0644 "${REPO_DIR}/systemd/gidget-env.service" "${SYSTEMD_DIR}/gidget-env.service"
    install -m 0644 "${REPO_DIR}/systemd/gidget-lidar.service" "${SYSTEMD_DIR}/gidget-lidar.service"
    install -m 0644 "${REPO_DIR}/systemd/gidget-imu.service" "${SYSTEMD_DIR}/gidget-imu.service"
    install -m 0644 "${REPO_DIR}/systemd/gidget-camera.service" "${SYSTEMD_DIR}/gidget-camera.service"
    install -m 0644 "${REPO_DIR}/systemd/gidget-oled.service" "${SYSTEMD_DIR}/gidget-oled.service"
    install -m 0644 "${REPO_DIR}/systemd/gidget-web.service" "${SYSTEMD_DIR}/gidget-web.service"
}

install_sudoers() {
    log "Installing restricted sudo permissions for Gidget web actions"

    cat > "${SUDOERS_FILE}" <<'EOF_SUDOERS'
gidget ALL=(root) NOPASSWD: /usr/bin/nmcli
gidget ALL=(root) NOPASSWD: /usr/bin/systemctl restart gidget-env.service
gidget ALL=(root) NOPASSWD: /usr/bin/systemctl restart gidget-lidar.service
gidget ALL=(root) NOPASSWD: /usr/bin/systemctl restart gidget-imu.service
gidget ALL=(root) NOPASSWD: /usr/bin/systemctl restart gidget-camera.service
gidget ALL=(root) NOPASSWD: /usr/bin/systemctl restart gidget-oled.service
gidget ALL=(root) NOPASSWD: /usr/bin/systemctl restart gidget-gps.service
gidget ALL=(root) NOPASSWD: /usr/bin/systemctl restart gidget-web.service
gidget ALL=(root) NOPASSWD: /usr/sbin/reboot
EOF_SUDOERS

    chmod 0440 "${SUDOERS_FILE}"
    visudo -cf "${SUDOERS_FILE}" >/dev/null
}

fix_permissions() {
    log "Fixing ownership and permissions"

    chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}"

    find "${APP_DIR}" -type d -exec chmod 0755 {} +
    find "${APP_DIR}" -type f -exec chmod 0644 {} +

    chmod 0755 "${APP_DIR}"/*.py 2>/dev/null || true
    chmod 0755 "${APP_DIR}/pages"/*.py 2>/dev/null || true

    chmod 0750 "${APP_DIR}/config"
    chmod 0640 "${APP_DIR}/config/users.json" 2>/dev/null || true
    chmod 0644 "${APP_DIR}/status_state.json" 2>/dev/null || true
    chmod 0644 "${APP_DIR}/environment_state.json" 2>/dev/null || true
    chmod 0644 "${APP_DIR}/lidar_state.json" 2>/dev/null || true
    chmod 0644 "${APP_DIR}/imu_state.json" 2>/dev/null || true
    chmod 0644 "${APP_DIR}/camera_state.json" 2>/dev/null || true
    chmod 0755 "${APP_DIR}/data" "${APP_DIR}/data/tracks" 2>/dev/null || true
}

enable_and_start_services() {
    log "Enabling and starting Gidget services"

    systemctl daemon-reload
    systemctl enable --now "${SERVICES[@]}"
}

main() {
    require_root
    check_pi_interfaces
    install_apt_dependencies
    ensure_system_user
    ensure_app_dirs
    create_venv_and_install_pip_deps
    sync_application_files
    create_default_runtime_files
    install_systemd_services
    install_sudoers
    fix_permissions
    enable_and_start_services

    log "Install complete"
    printf '\nOpen: http://gidget.local:8080\nDefault login: admin / admin\nChange the default password on first login.\n'
}

main "$@"
