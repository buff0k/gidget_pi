from flask import Blueprint, render_template

from auth import login_required


blueprint = Blueprint("lidar", __name__, url_prefix="/lidar")

PAGE = {
    "id": "lidar",
    "label": "LIDAR",
    "url": "/lidar/",
    "order": 27,
    "requires_auth": True,
}


@blueprint.route("/")
@login_required
def index():
    return render_template("lidar.html")
