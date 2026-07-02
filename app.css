from flask import Blueprint, render_template

from auth import login_required


blueprint = Blueprint("history", __name__, url_prefix="/history")

PAGE = {
    "id": "history",
    "label": "History",
    "url": "/history/",
    "order": 20,
    "requires_auth": True,
}


@blueprint.route("/")
@login_required
def index():
    return render_template("history.html")
