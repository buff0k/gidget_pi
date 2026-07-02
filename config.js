from flask import Blueprint, render_template

from auth import login_required


blueprint = Blueprint("home", __name__)

PAGE = {
    "id": "home",
    "label": "Home",
    "url": "/",
    "order": 10,
    "requires_auth": True,
}


@blueprint.route("/")
@login_required
def index():
    return render_template("home.html")
