from flask import Blueprint, jsonify, render_template, request

from auth import admin_required
from wifi_manager import (
    add_wifi_profile,
    connect_wifi_profile,
    current_wifi_status,
    delete_wifi_profile,
    saved_wifi_profiles,
    scan_wifi_networks,
    set_profile_autoconnect,
)


blueprint = Blueprint("config_page", __name__, url_prefix="/config")

PAGE = {
    "id": "config",
    "label": "Config",
    "url": "/config/",
    "order": 30,
    "requires_auth": True,
}


@blueprint.route("/")
@admin_required
def index():
    return render_template("config.html")


@blueprint.route("/api/wifi/current")
@admin_required
def api_wifi_current():
    return jsonify(current_wifi_status())


@blueprint.route("/api/wifi/scan")
@admin_required
def api_wifi_scan():
    return jsonify(scan_wifi_networks())


@blueprint.route("/api/wifi/saved")
@admin_required
def api_wifi_saved():
    return jsonify(saved_wifi_profiles())


@blueprint.route("/api/wifi/add-profile", methods=["POST"])
@admin_required
def api_wifi_add_profile():
    data = request.get_json(silent=True) or {}

    result = add_wifi_profile(
        ssid=data.get("ssid"),
        password=data.get("password"),
        autoconnect=bool(data.get("autoconnect", True)),
        priority=data.get("priority", 0),
        hidden=bool(data.get("hidden", False)),
        profile_name=data.get("profile_name"),
    )

    status_code = 200 if result.get("ok") else 400
    return jsonify(result), status_code


@blueprint.route("/api/wifi/connect", methods=["POST"])
@admin_required
def api_wifi_connect():
    data = request.get_json(silent=True) or {}

    result = connect_wifi_profile(data.get("profile_name"))

    status_code = 200 if result.get("ok") else 400
    return jsonify(result), status_code


@blueprint.route("/api/wifi/delete", methods=["POST"])
@admin_required
def api_wifi_delete():
    data = request.get_json(silent=True) or {}

    if data.get("confirm") != "DELETE":
        return jsonify({
            "ok": False,
            "error": "Confirmation value must be DELETE.",
        }), 400

    result = delete_wifi_profile(data.get("profile_name"))

    status_code = 200 if result.get("ok") else 400
    return jsonify(result), status_code


@blueprint.route("/api/wifi/autoconnect", methods=["POST"])
@admin_required
def api_wifi_autoconnect():
    data = request.get_json(silent=True) or {}

    result = set_profile_autoconnect(
        profile_name=data.get("profile_name"),
        autoconnect=bool(data.get("autoconnect", True)),
        priority=data.get("priority"),
    )

    status_code = 200 if result.get("ok") else 400
    return jsonify(result), status_code
