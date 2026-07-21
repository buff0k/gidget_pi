from flask import Blueprint, abort, jsonify, render_template, request, send_file
from pathlib import Path
import mimetypes


from auth import admin_required


blueprint = Blueprint("files", __name__, url_prefix="/files")

PAGE = {
    "id": "files",
    "label": "Files",
    "url": "/files/",
    "order": 35,
    "requires_auth": True,
}


BASE_DIR = Path("/opt/gidget").resolve()

# Reasonable cap so viewing a huge JSONL/log file does not crush the Pi Zero/browser.
MAX_VIEW_BYTES = 512 * 1024


def safe_resolve(relative_path):
    """
    Resolve a requested path safely under /opt/gidget.

    Prevents:
        /etc/passwd
        ../../etc/passwd
        symlink escape outside /opt/gidget
    """
    relative_path = relative_path or "."
    candidate = (BASE_DIR / relative_path).resolve()

    if candidate != BASE_DIR and BASE_DIR not in candidate.parents:
        abort(403)

    return candidate


def relative_to_base(path):
    path = path.resolve()
    if path == BASE_DIR:
        return ""
    return str(path.relative_to(BASE_DIR))


def is_probably_text(path):
    try:
        with path.open("rb") as f:
            chunk = f.read(4096)

        if b"\x00" in chunk:
            return False

        return True
    except Exception:
        return False


def file_type_for_name(path):
    suffix = path.suffix.lower()

    if suffix in [".py"]:
        return "python"
    if suffix in [".js"]:
        return "javascript"
    if suffix in [".css"]:
        return "css"
    if suffix in [".html", ".htm"]:
        return "html"
    if suffix in [".json", ".jsonl"]:
        return "json"
    if suffix in [".service", ".ini", ".conf"]:
        return "ini"
    if suffix in [".sh"]:
        return "bash"
    if suffix in [".txt", ".log"]:
        return "text"

    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "unknown"


@blueprint.route("/")
@admin_required
def index():
    return render_template("files.html")


@blueprint.route("/api/list")
@admin_required
def api_list():
    requested_path = request.args.get("path", "")
    path = safe_resolve(requested_path)

    if not path.exists():
        return jsonify({
            "ok": False,
            "error": "Path does not exist.",
        }), 404

    if not path.is_dir():
        return jsonify({
            "ok": False,
            "error": "Path is not a directory.",
        }), 400

    entries = []

    try:
        for item in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            try:
                stat = item.stat()
                is_dir = item.is_dir()
                is_file = item.is_file()

                entries.append({
                    "name": item.name,
                    "path": relative_to_base(item),
                    "type": "directory" if is_dir else "file" if is_file else "other",
                    "size_bytes": stat.st_size if is_file else None,
                    "modified": stat.st_mtime,
                    "viewable": is_file and stat.st_size <= MAX_VIEW_BYTES and is_probably_text(item),
                    "downloadable": is_file,
                    "file_type": file_type_for_name(item) if is_file else None,
                })
            except Exception:
                continue
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e),
        }), 500

    parent = None
    if path != BASE_DIR:
        parent = relative_to_base(path.parent)

    return jsonify({
        "ok": True,
        "root": str(BASE_DIR),
        "path": relative_to_base(path),
        "parent": parent,
        "entries": entries,
    })


@blueprint.route("/api/view")
@admin_required
def api_view():
    requested_path = request.args.get("path", "")
    path = safe_resolve(requested_path)

    if not path.exists():
        return jsonify({
            "ok": False,
            "error": "File does not exist.",
        }), 404

    if not path.is_file():
        return jsonify({
            "ok": False,
            "error": "Path is not a file.",
        }), 400

    size = path.stat().st_size

    if size > MAX_VIEW_BYTES:
        return jsonify({
            "ok": False,
            "error": f"File is too large to view in browser. Limit is {MAX_VIEW_BYTES} bytes. Use download instead.",
        }), 413

    if not is_probably_text(path):
        return jsonify({
            "ok": False,
            "error": "File appears to be binary. Use download instead.",
        }), 415

    try:
        content = path.read_text(errors="replace")
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e),
        }), 500

    lines = content.splitlines()

    return jsonify({
        "ok": True,
        "path": relative_to_base(path),
        "name": path.name,
        "size_bytes": size,
        "file_type": file_type_for_name(path),
        "line_count": len(lines),
        "lines": lines,
    })


@blueprint.route("/download")
@admin_required
def download():
    requested_path = request.args.get("path", "")
    path = safe_resolve(requested_path)

    if not path.exists() or not path.is_file():
        abort(404)

    return send_file(
        path,
        as_attachment=True,
        download_name=path.name,
    )
