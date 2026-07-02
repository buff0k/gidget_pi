#!/usr/bin/env python3

import json
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path("/opt/gidget")
CONFIG_DIR = BASE_DIR / "config"
USERS_FILE = CONFIG_DIR / "users.json"


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def ensure_users_file():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if USERS_FILE.exists():
        return

    data = {
        "users": [
            {
                "username": "admin",
                "password_hash": generate_password_hash("admin"),
                "role": "admin",
                "enabled": True,
                "must_change_password": True,
                "created_at": utc_now_iso(),
                "updated_at": utc_now_iso(),
            }
        ]
    }

    save_users(data)


def load_users():
    ensure_users_file()

    try:
        return json.loads(USERS_FILE.read_text())
    except Exception:
        return {"users": []}


def save_users(data):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    temp_file = USERS_FILE.with_suffix(".tmp")
    temp_file.write_text(json.dumps(data, indent=2))
    temp_file.replace(USERS_FILE)


def find_user(username):
    data = load_users()

    for user in data.get("users", []):
        if user.get("username") == username:
            return user

    return None


def authenticate(username, password):
    user = find_user(username)

    if not user:
        return None

    if not user.get("enabled", False):
        return None

    if not check_password_hash(user.get("password_hash", ""), password):
        return None

    return user


def current_user():
    username = session.get("username")
    if not username:
        return None

    return find_user(username)


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for("auth.login", next=request.path))

        return func(*args, **kwargs)

    return wrapper


def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        user = current_user()

        if not user:
            return redirect(url_for("auth.login", next=request.path))

        if user.get("role") != "admin":
            return "Forbidden", 403

        return func(*args, **kwargs)

    return wrapper


def change_password(username, new_password):
    data = load_users()

    for user in data.get("users", []):
        if user.get("username") == username:
            user["password_hash"] = generate_password_hash(new_password)
            user["must_change_password"] = False
            user["updated_at"] = utc_now_iso()
            save_users(data)
            return True

    return False


def add_user(username, password, role="user"):
    data = load_users()

    if find_user(username):
        return False, "User already exists"

    data.setdefault("users", []).append({
        "username": username,
        "password_hash": generate_password_hash(password),
        "role": role,
        "enabled": True,
        "must_change_password": True,
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    })

    save_users(data)
    return True, "User created"


def set_user_enabled(username, enabled):
    data = load_users()

    for user in data.get("users", []):
        if user.get("username") == username:
            user["enabled"] = bool(enabled)
            user["updated_at"] = utc_now_iso()
            save_users(data)
            return True

    return False
