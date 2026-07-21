#!/usr/bin/env python3

import importlib
import secrets

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from auth import (
    authenticate,
    current_user,
    ensure_users_file,
    login_required,
)
from services import (
    current_status,
    read_latest_track_points,
    read_track_date,
    track_dates,
)


PAGE_MODULES = [
    "pages.home",
    "pages.history",
    "pages.gps_telemetry",
    "pages.lidar",
    "pages.imu",
    "pages.camera",
    "pages.config_page",
    "pages.files",
    "pages.users",
]


def create_app():
    from flask import Flask

    app = Flask(
        __name__,
        template_folder="/opt/gidget/templates",
        static_folder="/opt/gidget/static",
    )
    app.secret_key = secrets.token_hex(32)

    ensure_users_file()

    pages = []

    for module_name in PAGE_MODULES:
        module = importlib.import_module(module_name)

        if hasattr(module, "blueprint"):
            app.register_blueprint(module.blueprint)

        if hasattr(module, "PAGE"):
            pages.append(module.PAGE)

    pages.sort(key=lambda p: p.get("order", 999))

    @app.context_processor
    def inject_globals():
        user = current_user()
        visible_pages = []

        if user:
            for page in pages:
                if page.get("id") == "config" and user.get("role") != "admin":
                    continue
                visible_pages.append(page)

        return {
            "pages": visible_pages,
            "current_user": user,
        }

    auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

    @auth_bp.route("/login", methods=["GET", "POST"])
    def login():
        error = None

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            user = authenticate(username, password)

            if user:
                session.clear()
                session["username"] = user["username"]

                next_url = request.args.get("next") or url_for("home.index")
                return redirect(next_url)

            error = "Invalid username or password."

        return render_template("login.html", error=error)

    @auth_bp.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("auth.login"))

    app.register_blueprint(auth_bp)

    @app.route("/api/status")
    @login_required
    def api_status():
        return jsonify(current_status())

    @app.route("/api/track")
    @login_required
    def api_track():
        """
        Compatibility/latest endpoint.

        This no longer reads the whole history then discards most of it.
        It reads newest days first and stops once the limit is reached.
        """
        try:
            limit = int(request.args.get("limit", "1000"))
        except Exception:
            limit = 1000

        limit = max(1, min(limit, 10000))

        return jsonify({
            "limit": limit,
            "points": read_latest_track_points(limit),
        })

    @app.route("/api/track/dates")
    @login_required
    def api_track_dates():
        return jsonify({
            "dates": track_dates(),
        })

    @app.route("/api/track/date/<date>")
    @login_required
    def api_track_date(date):
        points = read_track_date(date)

        return jsonify({
            "date": date,
            "count": len(points),
            "points": points,
        })

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
