#!/usr/bin/env python3
"""
Move Weight Foundation — Anonymous FOIA / Open Records Proxy
=============================================================
Accepts anonymous public records requests, sends them to City of Miami
as Move Weight Foundation (shielding the requester), and tracks bounties.

API Endpoints:
  POST /api/foia/submit     — Submit an anonymous FOIA request
  GET  /api/foia/requests   — List all public requests
  GET  /api/foia/request/:id — Get a specific request
  POST /api/foia/pledge/:id  — Pledge a bounty toward a request
  GET  /api/foia/stats       — Stats for the frontend

Runs on LXC 170 port 5060 (systemd: foia-api.service)
"""

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import smtplib
import subprocess
import threading
import time
from datetime import datetime, timezone
from email.mime.text import MIMEText

# PDF generation for official ORR form (city no longer accepts email FOIAs)
import sys as _sys
_sys.path.insert(0, "/opt")
from importlib import import_module as _import_module
_or_gen = _import_module("orr-pdf-generator")
generate_orr_pdf = _or_gen.generate_orr_pdf
from pathlib import Path
from urllib.parse import urlencode

from flask import Flask, request, jsonify, g
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

import hashlib
import time as _time

POW_DIFFICULTY = 0  # leading zero bytes required
POW_WINDOW = 300     # 5-minute window for nonce validity
RATE_LIMIT = {}      # IP -> [timestamps]

def verify_proof_of_work(nonce, timestamp, difficulty=POW_DIFFICULTY):
    if difficulty == 0: return True, "ok"
    """Verify hashcash-style proof of work. Client must find nonce where
    sha256(timestamp + nonce) starts with `difficulty` zero bytes."""
    try:
        ts = int(timestamp)
        if abs(_time.time() - ts) > POW_WINDOW:
            return False, "Timestamp expired. Please refresh and try again."
        data = f"{ts}:{nonce}".encode()
        h = hashlib.sha256(data).hexdigest()
        if h.startswith("0" * (difficulty * 2)):
            return True, "ok"
        return False, f"Proof of work invalid. Required: {difficulty} zero bytes."
    except:
        return False, "Invalid PoW parameters."

def check_rate_limit(ip):
    """Allow max 3 requests per 5 minutes per IP."""
    now = _time.time()
    if ip not in RATE_LIMIT:
        RATE_LIMIT[ip] = []
    RATE_LIMIT[ip] = [t for t in RATE_LIMIT[ip] if now - t < 300]
    if len(RATE_LIMIT[ip]) >= 3:
        return False
    RATE_LIMIT[ip].append(now)
    return True


DATA_DIR = Path(os.environ.get("EXPOSE_DATA_DIR", "/var/www/exposemiamiok/data/foia"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "requests.json"
PLEDGES_PATH = DATA_DIR / "pledges.json"
ADMIN_TOKEN_PATH = Path(os.environ.get("EXPOSE_ADMIN_TOKEN_PATH", "/root/.exposemiami_admin_token"))
TRIAGE_DB_PATH = DATA_DIR / "admin-triage.sqlite3"
NETWORK_SNAPSHOT_PATH = DATA_DIR / "network-status.json"
INVESTIGATION_DIR = Path(
    os.environ.get("EXPOSE_INVESTIGATION_DIR", "/var/www/exposemiamiok/data/investigations")
)
DB_WRITE_LOCK = threading.Lock()

CHAPTERS = (
    ("miamiok", "Miami, OK", "miami.exposeoklahoma.com"),
    ("okc", "Oklahoma City, OK", "okc.exposeoklahoma.com"),
    ("tulsa", "Tulsa, OK", "tulsa.exposeoklahoma.com"),
    ("claremore", "Claremore, OK", "claremore.exposeoklahoma.com"),
    ("sanangelo", "San Angelo, TX", "sanangelo.exposetexas.org"),
    ("houston", "Houston, TX", "houston.exposetexas.org"),
    ("dallas", "Dallas, TX", "dallas.exposetexas.org"),
    ("austin", "Austin, TX", "austin.exposetexas.org"),
    ("sanantonio", "San Antonio, TX", "sanantonio.exposetexas.org"),
    ("lubbock", "Lubbock, TX", "lubbock.exposetexas.org"),
    ("abilene", "Abilene, TX", "abilene.exposetexas.org"),
    ("mississippi", "Southaven, MS", "southaven.exposemississippi.com"),
    ("jackson", "Jackson, MS", "jackson.exposemississippi.com"),
    ("olivebranch", "Olive Branch, MS", "olivebranch.exposemississippi.com"),
)
REVIEW_STATUSES = {"new", "in_review", "needs_records", "ready", "closed"}

# ─── City of Miami Records Contacts ────────────────────────────────────
CITY_CONTACTS = {
    "city_clerk": {
        "name": "City Clerk — City of Miami, OK",
        "email": "cityclerk@miamiok.gov",
        "phone": "(918) 542-6685",
        "address": "129 5th Ave NW, Miami, OK 74354",
    },
    "police_records": {
        "name": "Miami Police Department — Records",
        "email": "policerecords@miamiok.gov",
        "phone": "(918) 542-5585",
        "address": "129 5th Ave NW, Miami, OK 74354",
    },
    "city_attorney": {
        "name": "City Attorney — City of Miami, OK",
        "email": "cityattorney@miamiok.gov",
    },
    "county_clerk": {
        "name": "Ottawa County Clerk",
        "email": "countyclerk@ottawa.co.ok.us",
        "phone": "(918) 542-9406",
        "address": "102 E Central Ave, Miami, OK 74354",
    },
    "sheriff": {
        "name": "Ottawa County Sheriff — Records",
        "email": "sheriff@ottawa.co.ok.us",
        "phone": "(918) 542-2806",
    },
}

MOVE_WEIGHT_FOUNDATION = {
    "name": "Move Weight Foundation",
    "email": "foia@moveweight.com",
    "address": "PO Box 451, Miami, OK 74355",
    "phone": "(918) 555-FOIA",
}

FOIA_TEMPLATES = {
    "standard": """Subject: Oklahoma Open Records Act Request — {request_id}

To: {recipient_name}
From: Move Weight Foundation (foia@moveweight.com)
Date: {date}

Dear {recipient_name},

Pursuant to the Oklahoma Open Records Act (51 O.S. § 24A.1 et seq.), Move Weight Foundation hereby requests access to and copies of the following public records:

{description}

{details}

This request is made on behalf of a member of the public who has chosen to remain anonymous due to concerns about retaliation, harassment, or intimidation. Under Oklahoma law, the identity of the requester is not required — only a reasonable description of the records sought.

Please provide an estimate of any fees associated with fulfilling this request before proceeding. If any portion of this request is denied, please cite the specific statutory exemption justifying the denial as required by 51 O.S. § 24A.5.

We request that responsive records be provided electronically where possible. If electronic delivery is not available, please contact us to arrange an alternative.

This request is made in the public interest. Move Weight Foundation is a nonprofit organization dedicated to government transparency in Miami, Oklahoma and Ottawa County.

Sincerely,
Move Weight Foundation
foia@moveweight.com
{address}
{phone}

---
Request ID: {request_id}
Submitted: {date}
Oklahoma Open Records Act — 51 O.S. § 24A.1 et seq.
Track this request: https://exposemiamiok.com/foia/request/{request_id}
""",

    "police": """Subject: Oklahoma Open Records Act Request — Police Records {request_id}

To: Miami Police Department — Records Division
From: Move Weight Foundation (foia@moveweight.com)
Date: {date}

Dear Records Custodian,

Pursuant to the Oklahoma Open Records Act (51 O.S. § 24A.1 et seq.), and specifically 51 O.S. § 24A.8 regarding law enforcement records, Move Weight Foundation requests access to the following:

{description}

{details}

Please include any incident reports, arrest records, dispatch logs, body camera footage, dash camera footage, and investigative files related to this request. If any records are exempt from disclosure, please provide a Vaughn index or similar itemization identifying each withheld record and the specific statutory basis for withholding.

As a nonprofit transparency organization, we request a fee waiver or reduction. If fees cannot be waived, please provide an estimate before proceeding.

Sincerely,
Move Weight Foundation
foia@moveweight.com
---
Request ID: {request_id}
""",
}


def load_db():
    if DB_PATH.exists():
        with open(DB_PATH) as f:
            return json.load(f)
    return {"requests": [], "last_id": 0}


def save_db(db):
    temporary = DB_PATH.with_suffix(".json.tmp")
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, DB_PATH)


def load_pledges():
    if PLEDGES_PATH.exists():
        with open(PLEDGES_PATH) as f:
            return json.load(f)
    return {"pledges": []}


def save_pledges(data):
    temporary = PLEDGES_PATH.with_suffix(".json.tmp")
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, PLEDGES_PATH)


def triage_connection():
    connection = sqlite3.connect(TRIAGE_DB_PATH, timeout=2)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 2000")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS reviews (
            item_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            version INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL
        )
        """
    )
    for path in (TRIAGE_DB_PATH, Path(str(TRIAGE_DB_PATH) + "-wal"), Path(str(TRIAGE_DB_PATH) + "-shm")):
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return connection


def load_reviews(item_ids):
    if not item_ids:
        return {}
    placeholders = ",".join("?" for _ in item_ids)
    with triage_connection() as connection:
        rows = connection.execute(
            "SELECT item_id, status, notes, version, updated_at FROM reviews "
            "WHERE item_id IN ({})".format(placeholders),
            item_ids,
        ).fetchall()
    return {
        row["item_id"]: {
            "status": row["status"],
            "notes": row["notes"],
            "version": row["version"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    }


def default_review():
    return {"status": "new", "notes": "", "version": 0, "updated_at": None}


def load_network_snapshot():
    try:
        data = json.loads(NETWORK_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {"generated_at": None, "chapters": [], "errors": ["No collector snapshot available."]}


def generate_id():
    return secrets.token_hex(8)


def send_email(to_email, subject, body):
    """Send email via sendmail with BCC backup to me@moveweight.com."""
    msg = MIMEText(body)
    msg["From"] = "Move Weight Foundation <foia@moveweight.com>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Reply-To"] = "foia@moveweight.com"
    msg["Bcc"] = "me@moveweight.com"

    try:
        result = subprocess.run(
            ["/sbin/sendmail", "-t", "-oi"],
            input=msg.as_string().encode(),
            timeout=15,
            capture_output=True,
        )
        # Send clean backup copy to me@moveweight.com
        backup = MIMEText(body)
        backup["From"] = "Move Weight Foundation <foia@moveweight.com>"
        backup["To"] = "me@moveweight.com"
        backup["Subject"] = "[FOIA BACKUP] " + subject
        subprocess.run(
            ["/sbin/sendmail", "-t", "-oi"],
            input=backup.as_string().encode(),
            timeout=10,
            capture_output=True,
        )
        return result.returncode == 0
    except Exception as e:
        print("Sendmail error:", e)
        return False


def build_foia_email(request_data):
    """Build the formal FOIA email body."""
    req_type = request_data.get("type", "standard")
    template = FOIA_TEMPLATES.get(req_type, FOIA_TEMPLATES["standard"])

    description = request_data.get("description", "No description provided")
    details = request_data.get("details", "")

    return template.format(
        request_id=request_data.get("id", "UNKNOWN"),
        recipient_name=request_data.get("recipient_name", "City Clerk"),
        description=description,
        details=details,
        date=datetime.now(timezone.utc).strftime("%B %d, %Y"),
        address=MOVE_WEIGHT_FOUNDATION["address"],
        phone=MOVE_WEIGHT_FOUNDATION["phone"],
    )


# ─── API Routes ────────────────────────────────────────────────────────

@app.route("/api/foia/submit", methods=["POST"])
def submit_foia():
    data = request.json or {}
    description = data.get("description", "").strip()
    record_type = data.get("record_type", "standard")

    # Rate limit check
    client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    if not check_rate_limit(client_ip):
        return jsonify({"ok": False, "error": "Rate limit exceeded. Please wait a few minutes before submitting another request."}), 429

    # Proof of work verification
    nonce = data.get("pow_nonce", "")
    pow_ts = data.get("pow_ts", 0)
    valid, msg = verify_proof_of_work(nonce, pow_ts)
    if not valid:
        return jsonify({"ok": False, "error": f"Security check failed: {msg}"}), 400

    if len(description) < 10:
        return jsonify({"ok": False, "error": "Please describe the records you are requesting (at least 10 characters)."}), 400

    req_id = generate_id()
    timestamp = datetime.now(timezone.utc).isoformat()

    # Determine recipient
    recipient_key = data.get("agency", "city_clerk")
    recipient = CITY_CONTACTS.get(recipient_key, CITY_CONTACTS["city_clerk"])

    request_data = {
        "id": req_id,
        "type": record_type,
        "description": description,
        "details": data.get("details", ""),
        "agency": recipient_key,
        "recipient_name": recipient["name"],
        "recipient_email": recipient["email"],
        "status": "submitted",
        "created_at": timestamp,
        "estimated_cost": data.get("estimated_cost", "Unknown — awaiting city response"),
        "bounty_total": 0,
        "bounty_count": 0,
        "updates": [{"date": timestamp, "status": "submitted", "note": "Request submitted to {}.".format(recipient["name"])}],
    }

    # Hold for admin approval — no email until approved
    request_data["status"] = "pending_review"
    request_data["updates"].append({
        "date": datetime.now(timezone.utc).isoformat(),
        "status": "pending_review",
        "note": "Request held for review. Move Weight Foundation will approve and send to {}.".format(recipient["name"]),
    })

    # Save
    with DB_WRITE_LOCK:
        db = load_db()
        db["requests"].append(request_data)
        db["last_id"] = len(db["requests"])
        save_db(db)

    # Also send a confirmation to the foundation
    confirm_body = """
New FOIA Request Submitted

Request ID: {id}
Type: {type}
Agency: {agency}
Description: {desc}

Track: https://exposemiamiok.com/foia/request/{id}
""".format(id=req_id, type=record_type, agency=recipient["name"], desc=description[:200])
    send_email("foia@moveweight.com", "New FOIA: {}".format(req_id), confirm_body)

    return jsonify({
        "ok": True,
        "request_id": req_id,
        "status": request_data["status"],
        "tracking_url": "https://exposemiamiok.com/foia/request/{}".format(req_id),
        "message": "Your anonymous request has been submitted for review. Move Weight Foundation will review and send it to the city within 24 hours. Save your Request ID to track progress.",
    })


@app.route("/api/foia/requests", methods=["GET"])
def list_requests():
    db = load_db()
    # Return public-safe data (no emails)
    public = []
    for r in db.get("requests", []):
        public.append({
            "id": r["id"],
            "type": r.get("type", "standard"),
            "description": r["description"][:200],
            "agency": r.get("agency", "city_clerk"),
            "status": r["status"],
            "created_at": r["created_at"],
            "estimated_cost": r.get("estimated_cost", "Unknown"),
            "bounty_total": r.get("bounty_total", 0),
            "bounty_count": r.get("bounty_count", 0),
            "updates_count": len(r.get("updates", [])),
        })
    return jsonify({"ok": True, "requests": public, "total": len(public)})


@app.route("/api/foia/request/<req_id>", methods=["GET"])
def get_request(req_id):
    db = load_db()
    for r in db.get("requests", []):
        if r["id"] == req_id:
            public = dict(r)
            public.pop("recipient_email", None)
            return jsonify({"ok": True, "request": public})
    return jsonify({"ok": False, "error": "Request not found"}), 404


@app.route("/api/foia/pledge/<req_id>", methods=["POST"])
def pledge_bounty(req_id):
    data = request.json or {}
    amount = float(data.get("amount", 0))
    if amount <= 0:
        return jsonify({"ok": False, "error": "Amount must be positive"}), 400

    with DB_WRITE_LOCK:
        db = load_db()
        for record in db.get("requests", []):
            if record["id"] != req_id:
                continue
            record["bounty_total"] = record.get("bounty_total", 0) + amount
            record["bounty_count"] = record.get("bounty_count", 0) + 1
            save_db(db)

            pledges = load_pledges()
            pledges["pledges"].append(
                {
                    "request_id": req_id,
                    "amount": amount,
                    "date": datetime.now(timezone.utc).isoformat(),
                }
            )
            save_pledges(pledges)

            return jsonify(
                {
                    "ok": True,
                    "message": "Pledge of ${:.2f} recorded. Thank you for supporting transparency!".format(amount),
                    "bounty_total": record["bounty_total"],
                }
            )

    return jsonify({"ok": False, "error": "Request not found"}), 404


@app.route("/api/foia/stats", methods=["GET"])
def get_stats():
    db = load_db()
    total = len(db.get("requests", []))
    submitted = sum(
        1
        for r in db.get("requests", [])
        if r["status"] in ("submitted", "sent", "queued", "prepared_for_delivery")
    )
    fulfilled = sum(1 for r in db.get("requests", []) if r["status"] == "fulfilled")
    denied = sum(1 for r in db.get("requests", []) if r["status"] == "denied")
    total_bounties = sum(r.get("bounty_total", 0) for r in db.get("requests", []))

    return jsonify({
        "ok": True,
        "total_requests": total,
        "active_requests": submitted,
        "fulfilled": fulfilled,
        "denied": denied,
        "total_bounties": total_bounties,
        "protected_identities": total,
    })


@app.route("/api/foia/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "service": "Move Weight Foundation FOIA Proxy", "version": "1.0.0"})



# ─── Admin Endpoints ────────────────────────────────────────────────────

def read_admin_token():
    """Read the manual admin token from env or a root-only file."""
    token = os.environ.get("EXPOSEMIAMI_ADMIN_TOKEN", "").strip()
    if token:
        return token
    try:
        if ADMIN_TOKEN_PATH.exists():
            return ADMIN_TOKEN_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return ""

def check_admin():
    """Require the server-issued admin secret.

    OIDC support stays disabled until the server verifies the signature, issuer,
    audience, expiry, and operator role. Decoding a browser-supplied JWT without
    verifying its signature is never authentication.
    """
    admin_token = request.headers.get("X-Admin-Token", "")
    manual_token = read_admin_token()
    if admin_token and manual_token and hmac.compare_digest(admin_token, manual_token):
        return True
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    return bool(token and manual_token and hmac.compare_digest(token, manual_token))

@app.route("/api/foia/admin/pending", methods=["GET"])
def admin_pending():
    if not check_admin():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    
    db = load_db()
    pending = [r for r in db.get("requests", []) if r["status"] in ("pending_review",)]
    return jsonify({"ok": True, "pending": pending, "count": len(pending)})

@app.route("/api/foia/admin/approve/<req_id>", methods=["POST"])
def admin_approve(req_id):
    if not check_admin():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    with DB_WRITE_LOCK:
        db = load_db()
        for record in db.get("requests", []):
            if record["id"] != req_id:
                continue
            if record["status"] != "pending_review":
                return jsonify({"ok": False, "error": "Request is not pending review"}), 400

            # Generate official ORR PDF form (city only accepts in-person/mail)
            pdf_path = generate_orr_pdf(record)
            pdf_url = "/foia/generated/" + pdf_path.name

            record["status"] = "prepared_for_delivery"
            record["pdf_url"] = pdf_url
            record["updates"].append(
                {
                    "date": datetime.now(timezone.utc).isoformat(),
                    "status": "prepared_for_delivery",
                    "note": (
                        "APPROVED: Official ORR form generated. Delivery has not yet been "
                        "recorded. Print and deliver to {}."
                    ).format(record.get("recipient_name", "City Clerk")),
                }
            )
            save_db(db)
            print("FOIA PREPARED: {}: PDF generated at {}".format(req_id, pdf_url))
            return jsonify(
                {
                    "ok": True,
                    "status": record["status"],
                    "request_id": req_id,
                    "pdf_url": pdf_url,
                }
            )

    return jsonify({"ok": False, "error": "Request not found"}), 404

@app.route("/api/foia/admin/reject/<req_id>", methods=["POST"])
def admin_reject(req_id):
    if not check_admin():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    
    data = request.json or {}
    reason = str(data.get("reason") or "Request does not meet submission guidelines.").strip()
    if len(reason) > 500:
        return jsonify({"ok": False, "error": "Rejection reason is limited to 500 characters"}), 400

    with DB_WRITE_LOCK:
        db = load_db()
        for record in db.get("requests", []):
            if record["id"] != req_id:
                continue
            record["status"] = "rejected"
            record["updates"].append(
                {
                    "date": datetime.now(timezone.utc).isoformat(),
                    "status": "rejected",
                    "note": "REJECTED: {}".format(reason),
                }
            )
            save_db(db)
            return jsonify({"ok": True, "status": "rejected", "request_id": req_id})

    return jsonify({"ok": False, "error": "Request not found"}), 404

@app.route("/api/foia/admin/all", methods=["GET"])
def admin_all():
    if not check_admin():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    
    db = load_db()
    return jsonify({"ok": True, "requests": db.get("requests", [])})


@app.route("/api/foia/admin/mark-delivered/<req_id>", methods=["POST"])
def admin_mark_delivered(req_id):
    if not check_admin():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    data = request.json or {}
    delivery_note = (data.get("delivery_note") or "").strip()
    if len(delivery_note) < 5 or len(delivery_note) > 500:
        return jsonify({"ok": False, "error": "Record how and when the request was delivered."}), 400

    with DB_WRITE_LOCK:
        db = load_db()
        for record in db.get("requests", []):
            if record["id"] != req_id:
                continue
            if record["status"] != "prepared_for_delivery":
                return jsonify({"ok": False, "error": "Request is not prepared for delivery"}), 400
            now = datetime.now(timezone.utc).isoformat()
            record["status"] = "sent"
            record["delivered_at"] = now
            record["updates"].append(
                {"date": now, "status": "sent", "note": "Delivery recorded: " + delivery_note}
            )
            save_db(db)
            return jsonify({"ok": True, "request_id": req_id, "status": "sent"})

    return jsonify({"ok": False, "error": "Request not found"}), 404


@app.route("/api/foia/admin/network", methods=["GET"])
def admin_network():
    if not check_admin():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    try:
        limit = min(100, max(1, int(request.args.get("limit", "100"))))
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid limit"}), 400

    snapshot = load_network_snapshot()
    by_key = {
        chapter.get("key"): chapter
        for chapter in snapshot.get("chapters", [])
        if isinstance(chapter, dict) and chapter.get("key")
    }
    chapters = []
    for key, label, host in CHAPTERS:
        collected = by_key.get(key, {})
        chapters.append(
            {
                "key": key,
                "label": label,
                "host": host,
                "health": collected.get("health", {"status": "unknown", "detail": "Not collected"}),
                "automation": collected.get(
                    "automation", {"status": "unknown", "detail": "Not collected"}
                ),
                "requests": collected.get("requests", {"total": 0, "pending": 0}),
            }
        )

    db = load_db()
    items = []
    for record in db.get("requests", []):
        items.append(
            {
                "id": "foia:miamiok:" + record["id"],
                "source_id": record["id"],
                "chapter": "miamiok",
                "kind": "foia",
                "status": record.get("status", "unknown"),
                "created_at": record.get("created_at"),
                "title": record.get("recipient_name") or record.get("agency") or "Records request",
                "description": record.get("description", "")[:4000],
                "pdf_url": record.get("pdf_url"),
            }
        )

    emails_path = DATA_DIR / "emails.json"
    try:
        email_data = json.loads(emails_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        email_data = {"threads": {}}
    for foia_id, messages in email_data.get("threads", {}).items():
        if not isinstance(messages, list) or not messages:
            continue
        latest = messages[-1]
        items.append(
            {
                "id": "inbox:miamiok:" + str(foia_id),
                "source_id": str(foia_id),
                "chapter": "miamiok",
                "kind": "inbox",
                "status": "received",
                "created_at": latest.get("date") or latest.get("fetched_at"),
                "title": latest.get("subject") or "Records correspondence",
                "description": latest.get("body", "")[:4000],
                "message_count": len(messages),
            }
        )

    for draft_path in INVESTIGATION_DIR.glob("*-records-drafts.json"):
        try:
            draft_data = json.loads(draft_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for draft in draft_data.get("drafts", []):
            source_id = str(draft.get("id") or "")
            if not source_id:
                continue
            items.append(
                {
                    "id": "submission:{}:{}".format(draft.get("chapter", "miamiok"), source_id),
                    "source_id": source_id,
                    "chapter": draft.get("chapter", "miamiok"),
                    "kind": "submission",
                    "status": draft.get("status", "draft"),
                    "created_at": draft_data.get("updated_at"),
                    "title": draft.get("title") or draft.get("target") or "Records-request draft",
                    "description": draft.get("text", "")[:4000],
                    "target": draft.get("target"),
                }
            )

    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    items = items[:limit]
    reviews = load_reviews([item["id"] for item in items])
    for item in items:
        item["review"] = reviews.get(item["id"], default_review())

    return jsonify(
        {
            "ok": True,
            "generated_at": snapshot.get("generated_at"),
            "chapters": chapters,
            "items": items,
            "errors": snapshot.get("errors", []),
        }
    )


@app.route("/api/foia/admin/review/<path:item_id>", methods=["POST"])
def admin_review(item_id):
    if not check_admin():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    data = request.json or {}
    status = (data.get("status") or "").strip()
    notes = (data.get("notes") or "").strip()
    expected_version = data.get("expected_version")
    if status not in REVIEW_STATUSES:
        return jsonify({"ok": False, "error": "Invalid review status"}), 400
    if len(notes) > 4000:
        return jsonify({"ok": False, "error": "Review notes are limited to 4,000 characters"}), 400
    if not item_id.startswith(("foia:", "inbox:", "tip:", "submission:")):
        return jsonify({"ok": False, "error": "Invalid item id"}), 400
    try:
        expected_version = int(expected_version)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Expected version is required"}), 400

    now = datetime.now(timezone.utc).isoformat()
    try:
        connection = triage_connection()
        connection.execute("BEGIN IMMEDIATE")
        current = connection.execute(
            "SELECT version FROM reviews WHERE item_id = ?", (item_id,)
        ).fetchone()
        current_version = current["version"] if current else 0
        if current_version != expected_version:
            connection.rollback()
            return jsonify({"ok": False, "error": "Review changed in another session"}), 409
        new_version = current_version + 1
        connection.execute(
            """
            INSERT INTO reviews (item_id, status, notes, version, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(item_id) DO UPDATE SET
                status = excluded.status,
                notes = excluded.notes,
                version = excluded.version,
                updated_at = excluded.updated_at
            """,
            (item_id, status, notes, new_version, now),
        )
        connection.commit()
    except sqlite3.OperationalError:
        return jsonify({"ok": False, "error": "Review store is busy; retry shortly"}), 503
    finally:
        if "connection" in locals():
            connection.close()

    return jsonify(
        {
            "ok": True,
            "review": {"status": status, "notes": notes, "version": new_version, "updated_at": now},
        }
    )

@app.route("/api/foia/admin/inbox", methods=["GET"])
def admin_inbox():
    if not check_admin():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    import json
    from pathlib import Path
    emails_path = Path("/var/www/exposemiamiok/data/foia/emails.json")
    if emails_path.exists():
        with open(emails_path) as f:
            data = json.load(f)
        return jsonify({"ok": True, "threads": data.get("threads", {}), "count": len(data.get("threads", {}))})
    return jsonify({"ok": True, "threads": {}, "count": 0})

@app.route("/api/foia/admin/inbox/reply", methods=["POST"])
def admin_reply():
    if not check_admin():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    data = request.json or {}
    to = data.get("to", "")
    subject = data.get("subject", "")
    body = data.get("body", "")
    if not to or not body:
        return jsonify({"ok": False, "error": "Missing to/subject/body"}), 400
    import subprocess
    result = subprocess.run(["python3", "/opt/foia-inbox.py", "reply", to, subject, body], capture_output=True, text=True, timeout=30)
    return jsonify({"ok": True, "output": result.stdout.strip()})

@app.route("/api/foia/admin/ai-edit", methods=["POST"])
def admin_ai_edit():
    if not check_admin():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    data = request.json or {}
    text = (data.get("text") or "").strip()
    if len(text) < 10:
        return jsonify({"ok": False, "error": "Provide the request text to edit."}), 400
    if len(text) > 12000:
        return jsonify({"ok": False, "error": "Request is too long for one edit pass."}), 400

    try:
        result = subprocess.run(
            ["python3", "/opt/foia-ai-edit.py"],
            input=text,
            capture_output=True,
            text=True,
            timeout=90,
        )
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "AI editor timed out. Try again with a shorter request."}), 504

    edited = (result.stdout or "").strip()
    error = (result.stderr or "").strip()
    if result.returncode != 0:
        return jsonify({"ok": False, "error": error or edited or "AI editor failed."}), 502
    if not edited or edited.lower().startswith("error:"):
        return jsonify({"ok": False, "error": edited or "AI editor returned no text."}), 502

    return jsonify({"ok": True, "edited": edited})


@app.route("/api/foia/pdf/<req_id>", methods=["GET"])
def download_pdf(req_id):
    """Download the generated ORR PDF for a FOIA request."""
    with DB_WRITE_LOCK:
        db = load_db()
        for record in db.get("requests", []):
            if record["id"] != req_id:
                continue
            pdf_url = record.get("pdf_url", "")
            if pdf_url:
                return jsonify({"ok": True, "pdf_url": pdf_url, "request_id": req_id})
            pdf_path = generate_orr_pdf(record)
            pdf_url = "/foia/generated/" + pdf_path.name
            record["pdf_url"] = pdf_url
            save_db(db)
            return jsonify({"ok": True, "pdf_url": pdf_url, "request_id": req_id})
    return jsonify({"ok": False, "error": "Request not found or not yet approved"}), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5060, debug=False)
