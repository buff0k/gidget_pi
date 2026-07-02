from flask import Blueprint, redirect, render_template, request, url_for

from auth import (
    add_user,
    admin_required,
    change_password,
    current_user,
    load_users,
    login_required,
    set_user_enabled,
)


blueprint = Blueprint("users", __name__, url_prefix="/users")

PAGE = {
    "id": "users",
    "label": "Users",
    "url": "/users/",
    "order": 40,
    "requires_auth": True,
}


@blueprint.route("/", methods=["GET", "POST"])
@login_required
def index():
    user = current_user()
    message = None
    error = None

    if request.method == "POST":
        action = request.form.get("action")

        if action == "change_own_password":
            password = request.form.get("password", "")
            confirm = request.form.get("confirm", "")

            if len(password) < 4:
                error = "Password must be at least 4 characters."
            elif password != confirm:
                error = "Passwords do not match."
            else:
                change_password(user["username"], password)
                message = "Password changed."

        elif action == "add_user":
            if user.get("role") != "admin":
                error = "Only admins can add users."
            else:
                username = request.form.get("username", "").strip()
                password = request.form.get("password", "")
                role = request.form.get("role", "user")

                if not username:
                    error = "Username is required."
                elif len(password) < 4:
                    error = "Password must be at least 4 characters."
                else:
                    ok, result = add_user(username, password, role)
                    if ok:
                        message = result
                    else:
                        error = result

        elif action == "disable_user":
            if user.get("role") != "admin":
                error = "Only admins can disable users."
            else:
                username = request.form.get("username")
                if username == user.get("username"):
                    error = "You cannot disable your own account."
                else:
                    set_user_enabled(username, False)
                    message = f"Disabled {username}."

        elif action == "enable_user":
            if user.get("role") != "admin":
                error = "Only admins can enable users."
            else:
                username = request.form.get("username")
                set_user_enabled(username, True)
                message = f"Enabled {username}."

    users_data = load_users()

    return render_template(
        "users.html",
        users=users_data.get("users", []),
        message=message,
        error=error,
    )
