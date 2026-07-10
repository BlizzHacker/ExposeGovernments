#!/usr/bin/env python3
"""Serve evidence files only to authenticated admins."""
import hmac
import json
import mimetypes
import os
from flask import Flask, request, send_file, jsonify, abort, after_this_request
from flask_cors import CORS
from pathlib import Path

app = Flask(__name__)
CORS(app)

EVIDENCE_DIR = Path("/opt/evidence-private")
MAYOR_WATCH_FEED = Path("/opt/facebook-scrape/mayor-watch-feed.json")
ADMIN_TOKEN_PATH = Path("/root/.exposemiami_admin_token")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def read_admin_token():
    token = os.environ.get("EXPOSEMIAMI_ADMIN_TOKEN", "").strip()
    if token:
        return token
    try:
        if ADMIN_TOKEN_PATH.exists():
            return ADMIN_TOKEN_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return ""


def check_auth():
    manual_token = read_admin_token()
    candidates = [
        request.headers.get("X-Admin-Token", "").strip(),
        request.headers.get("Authorization", "").replace("Bearer ", "", 1).strip(),
    ]
    if manual_token:
        for token in candidates:
            if token and hmac.compare_digest(token, manual_token):
                return True

    # Authentik JWTs are validated loosely here to match the existing FOIA admin API.
    token = candidates[1]
    if token:
        try:
            import jwt

            payload = jwt.decode(token, options={"verify_signature": False})
            issuer = (payload.get("iss") or "").lower()
            if "authentik" in issuer or "moveweight" in issuer:
                return True
        except Exception:
            pass
    return False


def require_auth():
    if not check_auth():
        return jsonify({"error": "Unauthorized"}), 401
    return None


def safe_files(kind):
    base = EVIDENCE_DIR / kind
    if not base.exists():
        return []
    files = []
    for path in sorted(base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            files.append({
                "name": path.name,
                "size": path.stat().st_size,
                "modified": int(path.stat().st_mtime),
                "url": f"/api/evidence/{kind[:-1]}/{path.name}",
            })
    return files


def send_private_file(kind, filename):
    auth_error = require_auth()
    if auth_error:
        return auth_error

    base = (EVIDENCE_DIR / kind).resolve()
    path = (base / filename).resolve()
    if base not in path.parents or path.suffix.lower() not in IMAGE_EXTENSIONS or not path.exists():
        abort(404)

    @after_this_request
    def no_store(response):
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    return send_file(path, mimetype=mimetypes.guess_type(path.name)[0] or "application/octet-stream")

@app.route("/api/evidence/screenshots", methods=["GET"])
def list_screenshots():
    auth_error = require_auth()
    if auth_error:
        return auth_error
    screenshots = safe_files("screenshots")
    return jsonify({"screenshots": screenshots, "count": len(screenshots)})

@app.route("/api/evidence/screenshot/<filename>", methods=["GET"])
def get_screenshot(filename):
    return send_private_file("screenshots", filename)

@app.route("/api/evidence/photos", methods=["GET"])
def list_photos():
    auth_error = require_auth()
    if auth_error:
        return auth_error
    photos = safe_files("photos")
    return jsonify({"photos": photos, "count": len(photos)})

@app.route("/api/evidence/photo/<filename>", methods=["GET"])
def get_photo(filename):
    return send_private_file("photos", filename)

@app.route("/api/evidence/stats", methods=["GET"])
def stats():
    auth_error = require_auth()
    if auth_error:
        return auth_error
    sc = len(safe_files("screenshots"))
    ph = len(safe_files("photos"))
    return jsonify({"screenshots": sc, "photos": ph, "total": sc + ph})

@app.route("/api/evidence/mayor-watch-feed", methods=["GET"])
def mayor_watch_feed():
    auth_error = require_auth()
    if auth_error:
        return auth_error
    if not MAYOR_WATCH_FEED.exists():
        return jsonify({"generated": None, "stats": {}, "evidence": []})
    try:
        return jsonify(json.loads(MAYOR_WATCH_FEED.read_text(encoding="utf-8")))
    except Exception:
        return jsonify({"error": "Feed unavailable"}), 500

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5070, debug=False)
