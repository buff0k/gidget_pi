from flask import Blueprint, render_template

from auth import login_required


blueprint = Blueprint("gps_telemetry", __name__, url_prefix="/gps-telemetry")

PAGE = {
    "id": "gps_telemetry",
    "label": "GPS Telemetry",
    "url": "/gps-telemetry/",
    "order": 25,
    "requires_auth": True,
}


@blueprint.route("/")
@login_required
def index():
    return render_template("gps_telemetry.html")
