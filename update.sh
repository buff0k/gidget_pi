#!/usr/bin/env bash
set -Eeuo pipefail

APP_USER="gidget"
APP_GROUP="gidget"
APP_DIR="/opt/gidget"
SHM_DIR="/dev/shm/gidget"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${APP_DIR}/.venv"
SUDOERS_FILE="/etc/sudoers.d/gidget"
SYSTEMD_DIR="/etc/systemd/system"
SERVICES=(gidget-gps.service gidget-env.service gidget-lidar.service gidget-imu.service gidget-camera.service gidget-hexapod.service gidget-oled.service gidget-web.service)
UPDATE_FLAG_FILE="${SHM_DIR}/update_in_progress"

log() { printf '\n[update] %s\n' "$*"; }
fail() { printf '\n[update] ERROR: %s\n' "$*" >&2; exit 1; }

require_root() {
    if [ "${EUID}" -ne 0 ]; then
        fail "Run this updater as root, for example: sudo bash ./update.sh"
    fi
}

mark_update_start() {
    log "Flagging update in progress so the OLED shows 'Updating' instead of going dark"

    mkdir -p "${SHM_DIR}"
    printf '{"status":"updating"}\n' > "${UPDATE_FLAG_FILE}"

    # No matter how this script exits (success, failure, or interrupt), clear
    # the flag so the OLED doesn't get stuck on the update screen forever.
    trap 'rm -f "${UPDATE_FLAG_FILE}" 2>/dev/null || true' EXIT
}

read_apt_dependencies() {
    sed 's/#.*$//' "${REPO_DIR}/dependencies.list" | awk 'NF {print $1}'
}

prepare_git_checkout() {
    if [ ! -d "${REPO_DIR}/.git" ]; then
        return
    fi

    # The repo is normally updated from a Pi where scripts may be chmod +x locally.
    # GitHub's contents API stores files as 100644, so local executable-bit changes
    # can otherwise block git pull with "local changes would be overwritten".
    git -C "${REPO_DIR}" config core.fileMode false
    git -C "${REPO_DIR}" update-index --refresh >/dev/null 2>&1 || true
}

maybe_reexec_after_git_pull() {
    if [ ! -d "${REPO_DIR}/.git" ]; then
        log "No .git directory found; skipping git pull"
        return
    fi

    prepare_git_checkout

    log "Pulling latest code from git"

    local script_path old_sum new_sum
    script_path="$(readlink -f "${BASH_SOURCE[0]}")"
    old_sum="$(sha256sum "$script_path" | awk '{print $1}')"

    git -C "${REPO_DIR}" pull --ff-only

    new_sum="$(sha256sum "$script_path" | awk '{print $1}')"

    if [ "$old_sum" != "$new_sum" ] && [ "${GIDGET_UPDATE_REEXEC:-0}" != "1" ]; then
        log "update.sh changed during git pull; restarting updated updater"
        exec env GIDGET_UPDATE_REEXEC=1 bash "$script_path" "$@"
    fi
}

install_apt_dependencies() {
    log "Ensuring APT dependencies are installed"

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
    mkdir -p "${APP_DIR}" "${APP_DIR}/config" "${APP_DIR}/data/tracks"
    chown -R "${APP_USER}:${APP_GROUP}" "${APP_DIR}"
}

create_or_update_venv() {
    log "Updating Python virtual environment dependencies"

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

stop_services() {
    log "Stopping Gidget services (leaving gidget-oled.service running to show update status)"
    for service in "${SERVICES[@]}"; do
        if [ "$service" = "gidget-oled.service" ]; then
            continue
        fi
        systemctl stop "$service" 2>/dev/null || true
    done
}

sync_application_files() {
    log "Updating application files while preserving runtime config and track history"

    [ -d "${REPO_DIR}/gidget" ] || fail "Missing gidget/ folder in repo root"

    rsync -a --delete \
        --exclude '.venv/' \
        --exclude 'config/users.json' \
        --exclude 'config/secret_key' \
        --exclude 'config/hexapod_calibration.json' \
        --exclude 'data/tracks/*.jsonl' \
        "${REPO_DIR}/gidget/" "${APP_DIR}/"

    mkdir -p "${APP_DIR}/config" "${APP_DIR}/data/tracks"
}

ensure_runtime_files() {
    log "Preserving or creating runtime config/state"

    # Live sensor telemetry moved from ${APP_DIR}/*_state.json (SD card) to
    # tmpfs at ${SHM_DIR}. Make sure the directory exists and is owned by the
    # gidget user; any old *_state.json files under APP_DIR were already
    # removed above since sync_application_files no longer excludes them.
    mkdir -p "${SHM_DIR}"
    chown "${APP_USER}:${APP_GROUP}" "${SHM_DIR}"
    chmod 0755 "${SHM_DIR}"

    if [ ! -f "${APP_DIR}/config/users.json" ]; then
        cd "${APP_DIR}"
        "${VENV_DIR}/bin/python" - <<'PY'
from auth import ensure_users_file
ensure_users_file()
PY
    fi
}

install_systemd_services() {
    log "Updating systemd service files"

    [ -d "${REPO_DIR}/systemd" ] || fail "Missing systemd/ folder in repo root"

    install -m 0644 "${REPO_DIR}/systemd/gidget-gps.service" "${SYSTEMD_DIR}/gidget-gps.service"
    install -m 0644 "${REPO_DIR}/systemd/gidget-env.service" "${SYSTEMD_DIR}/gidget-env.service"
    install -m 0644 "${REPO_DIR}/systemd/gidget-lidar.service" "${SYSTEMD_DIR}/gidget-lidar.service"
    install -m 0644 "${REPO_DIR}/systemd/gidget-imu.service" "${SYSTEMD_DIR}/gidget-imu.service"
    install -m 0644 "${REPO_DIR}/systemd/gidget-camera.service" "${SYSTEMD_DIR}/gidget-camera.service"
    install -m 0644 "${REPO_DIR}/systemd/gidget-hexapod.service" "${SYSTEMD_DIR}/gidget-hexapod.service"
    install -m 0644 "${REPO_DIR}/systemd/gidget-oled.service" "${SYSTEMD_DIR}/gidget-oled.service"
    install -m 0644 "${REPO_DIR}/systemd/gidget-web.service" "${SYSTEMD_DIR}/gidget-web.service"
}

install_udev_rules() {
    log "Updating udev rules"

    [ -d "${REPO_DIR}/udev" ] || fail "Missing udev/ folder in repo root"

    install -m 0644 "${REPO_DIR}/udev/99-gidget-servo2040.rules" /etc/udev/rules.d/99-gidget-servo2040.rules

    udevadm control --reload-rules
    udevadm trigger
}

install_sudoers() {
    log "Updating restricted sudo permissions"

    cat > "${SUDOERS_FILE}" <<'EOF_SUDOERS'
gidget ALL=(root) NOPASSWD: /usr/bin/nmcli
gidget ALL=(root) NOPASSWD: /usr/bin/systemctl restart gidget-env.service
gidget ALL=(root) NOPASSWD: /usr/bin/systemctl restart gidget-lidar.service
gidget ALL=(root) NOPASSWD: /usr/bin/systemctl restart gidget-imu.service
gidget ALL=(root) NOPASSWD: /usr/bin/systemctl restart gidget-camera.service
gidget ALL=(root) NOPASSWD: /usr/bin/systemctl restart gidget-hexapod.service
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
    chmod 0755 "${APP_DIR}/data" "${APP_DIR}/data/tracks" 2>/dev/null || true

    chown "${APP_USER}:${APP_GROUP}" "${SHM_DIR}" 2>/dev/null || true
    chmod 0755 "${SHM_DIR}" 2>/dev/null || true
}

update_hexapod_firmware() {
    log "Checking for a connected Servo 2040 to update firmware on"

    if ! "${VENV_DIR}/bin/python" -c "import mpremote" >/dev/null 2>&1; then
        log "mpremote not installed in venv - skipping Servo 2040 firmware update"
        return
    fi

    # gidget-hexapod.service was just stopped, which now asks the board to
    # reset itself cleanly on the way out (see hexapod_controller.py's
    # shutdown handler). That reset + USB re-enumeration takes a moment -
    # give it time before scanning for the device node, rather than
    # possibly catching it mid-reboot.
    sleep 2

    local port=""
    for candidate in /dev/gidget-servo2040 /dev/ttyACM0 /dev/ttyACM1; do
        if [ -e "$candidate" ]; then
            port="$candidate"
            break
        fi
    done

    if [ -z "$port" ]; then
        log "No Servo 2040 detected - skipping firmware update"
        return
    fi

    log "Flashing firmware/servo2040/main.py to Servo 2040 at ${port}"

    # Interrupting a running MicroPython program and then immediately
    # entering raw REPL mode is a known-flaky handshake - it can fail fast
    # ("could not enter raw repl") or, worse, just hang indefinitely with
    # no error at all. `timeout` bounds every attempt so this step can
    # never block the rest of update.sh forever - a stuck attempt gets
    # killed and counted as a failed attempt, not an indefinite hang.
    local attempt flashed
    flashed=0

    for attempt in 1 2 3; do
        if timeout 15 "${VENV_DIR}/bin/python" -m mpremote connect "$port" cp "${REPO_DIR}/firmware/servo2040/main.py" :main.py; then
            flashed=1
            break
        fi
        log "Flash attempt ${attempt} failed or timed out, retrying..."
        sleep 1
    done

    if [ "$flashed" -eq 1 ]; then
        timeout 10 "${VENV_DIR}/bin/python" -m mpremote connect "$port" reset || true
        log "Servo 2040 firmware updated"
    else
        log "WARNING: Servo 2040 firmware update failed after 3 attempts - board may need a manual reset, see firmware/servo2040/README.md"
    fi
}

restart_services() {
    log "Reloading systemd and restarting services"

    systemctl daemon-reload
    systemctl enable "${SERVICES[@]}"
    systemctl restart "${SERVICES[@]}"
}

main() {
    require_root
    mark_update_start
    maybe_reexec_after_git_pull "$@"
    install_apt_dependencies
    ensure_system_user
    ensure_app_dirs
    create_or_update_venv
    stop_services
    sync_application_files
    ensure_runtime_files
    install_systemd_services
    install_udev_rules
    install_sudoers
    fix_permissions
    update_hexapod_firmware
    restart_services

    log "Update complete"
    printf '\nOpen: http://gidget.local:8080\n'
}

main "$@"
