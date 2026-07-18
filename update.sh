#!/usr/bin/env bash
set -Eeuo pipefail

APP_USER="gidget"
APP_GROUP="gidget"
APP_DIR="/opt/gidget"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${APP_DIR}/.venv"
SUDOERS_FILE="/etc/sudoers.d/gidget"
SYSTEMD_DIR="/etc/systemd/system"
SERVICES=(gidget-gps.service gidget-env.service gidget-lidar.service gidget-oled.service gidget-web.service)

log() { printf '\n[update] %s\n' "$*"; }
fail() { printf '\n[update] ERROR: %s\n' "$*" >&2; exit 1; }

require_root() {
    if [ "${EUID}" -ne 0 ]; then
        fail "Run this updater as root, for example: sudo ./update.sh"
    fi
}

read_apt_dependencies() {
    sed 's/#.*$//' "${REPO_DIR}/dependencies.list" | awk 'NF {print $1}'
}

maybe_reexec_after_git_pull() {
    if [ ! -d "${REPO_DIR}/.git" ]; then
        log "No .git directory found; skipping git pull"
        return
    fi

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

    for group in i2c dialout gpio; do
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
    log "Stopping Gidget services"
    for service in "${SERVICES[@]}"; do
        systemctl stop "$service" 2>/dev/null || true
    done
}

sync_application_files() {
    log "Updating application files while preserving runtime config and track history"

    [ -d "${REPO_DIR}/gidget" ] || fail "Missing gidget/ folder in repo root"

    rsync -a --delete \
        --exclude '.venv/' \
        --exclude 'config/users.json' \
        --exclude 'status_state.json' \
        --exclude 'environment_state.json' \
        --exclude 'lidar_state.json' \
        --exclude 'data/tracks/*.jsonl' \
        "${REPO_DIR}/gidget/" "${APP_DIR}/"

    mkdir -p "${APP_DIR}/config" "${APP_DIR}/data/tracks"
}

ensure_runtime_files() {
    log "Preserving or creating runtime config/state"

    if [ ! -f "${APP_DIR}/status_state.json" ]; then
        printf '{}\n' > "${APP_DIR}/status_state.json"
    fi

    if [ ! -f "${APP_DIR}/environment_state.json" ]; then
        printf '{}\n' > "${APP_DIR}/environment_state.json"
    fi

    if [ ! -f "${APP_DIR}/lidar_state.json" ]; then
        printf '{}\n' > "${APP_DIR}/lidar_state.json"
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
    log "Updating systemd service files"

    [ -d "${REPO_DIR}/systemd" ] || fail "Missing systemd/ folder in repo root"

    install -m 0644 "${REPO_DIR}/systemd/gidget-gps.service" "${SYSTEMD_DIR}/gidget-gps.service"
    install -m 0644 "${REPO_DIR}/systemd/gidget-env.service" "${SYSTEMD_DIR}/gidget-env.service"
    install -m 0644 "${REPO_DIR}/systemd/gidget-lidar.service" "${SYSTEMD_DIR}/gidget-lidar.service"
    install -m 0644 "${REPO_DIR}/systemd/gidget-oled.service" "${SYSTEMD_DIR}/gidget-oled.service"
    install -m 0644 "${REPO_DIR}/systemd/gidget-web.service" "${SYSTEMD_DIR}/gidget-web.service"
}

install_sudoers() {
    log "Updating restricted sudo permissions"

    cat > "${SUDOERS_FILE}" <<'EOF_SUDOERS'
gidget ALL=(root) NOPASSWD: /usr/bin/nmcli
gidget ALL=(root) NOPASSWD: /usr/bin/systemctl restart gidget-env.service
gidget ALL=(root) NOPASSWD: /usr/bin/systemctl restart gidget-lidar.service
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
    chmod 0755 "${APP_DIR}/data" "${APP_DIR}/data/tracks" 2>/dev/null || true
}

restart_services() {
    log "Reloading systemd and restarting services"

    systemctl daemon-reload
    systemctl enable "${SERVICES[@]}"
    systemctl restart "${SERVICES[@]}"
}

main() {
    require_root
    maybe_reexec_after_git_pull "$@"
    install_apt_dependencies
    ensure_system_user
    ensure_app_dirs
    create_or_update_venv
    stop_services
    sync_application_files
    ensure_runtime_files
    install_systemd_services
    install_sudoers
    fix_permissions
    restart_services

    log "Update complete"
    printf '\nOpen: http://gidget.local:8080\n'
}

main "$@"
