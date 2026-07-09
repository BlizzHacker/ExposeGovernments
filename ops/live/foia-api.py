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
import smtplib
import subprocess
import time
from datetime import datetime, timezone
from email.mime.text import MIMEText
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


DATA_DIR = Path("/var/www/exposemiamiok/data/foia")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "requests.json"
PLEDGES_PATH = DATA_DIR / "pledges.json"
ADMIN_TOKEN_PATH = Path("/root/.exposemiami_admin_token")

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
    with open(DB_PATH, "w") as f:
        json.dump(db, f, indent=2, default=str)


def load_pledges():
    if PLEDGES_PATH.exists():
        with open(PLEDGES_PATH) as f:
            return json.load(f)
    return {"pledges": []}


def save_pledges(data):
    with open(PLEDGES_PATH, "w") as f:
        json.dump(data, f, indent=2, default=str)


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

    db = load_db()
    for r in db.get("requests", []):
        if r["id"] == req_id:
            r["bounty_total"] = r.get("bounty_total", 0) + amount
            r["bounty_count"] = r.get("bounty_count", 0) + 1
            save_db(db)

            # Save pledge
            pledges = load_pledges()
            pledges["pledges"].append({
                "request_id": req_id,
                "amount": amount,
                "date": datetime.now(timezone.utc).isoformat(),
            })
            save_pledges(pledges)

            return jsonify({
                "ok": True,
                "message": "Pledge of ${:.2f} recorded. Thank you for supporting transparency!".format(amount),
                "bounty_total": r["bounty_total"],
            })

    return jsonify({"ok": False, "error": "Request not found"}), 404


@app.route("/api/foia/stats", methods=["GET"])
def get_stats():
    db = load_db()
    total = len(db.get("requests", []))
    submitted = sum(1 for r in db.get("requests", []) if r["status"] in ("submitted", "sent", "queued"))
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
AUTHENTIK_ISSUER = "https://authentik.moveweight.com/application/o/foia-admin/"

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

def send_backup(subject, body): pass
def check_admin():
    admin_token = request.headers.get("X-Admin-Token", "")
    manual_token = read_admin_token()
    if admin_token and manual_token and hmac.compare_digest(admin_token, manual_token):
        return True
    """Authenticate via Authentik JWT or fallback token."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        return False
    # Manual fallback token, supplied by an authenticated admin and never by page source.
    if manual_token and hmac.compare_digest(token, manual_token):
        return True
    # Try Authentik JWT validation (accepts any valid Authentik-issued JWT)
    try:
        import jwt
        # Just check it's a valid JWT from our Authentik instance (skip signature if no key)
        payload = jwt.decode(token, options={"verify_signature": False})
        issuer = payload.get("iss", "")
        if "authentik" in issuer.lower() or "moveweight" in issuer.lower():
            return True
    except:
        pass
    return False

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
    
    db = load_db()
    for r in db.get("requests", []):
        if r["id"] == req_id:
            if r["status"] != "pending_review":
                return jsonify({"ok": False, "error": "Request is not pending review"}), 400
            
            # Build and send the actual FOIA email
            email_body = build_foia_email(r)
            subject = "Oklahoma Open Records Act Request — {}".format(req_id)
            email_sent = send_email(r["recipient_email"], subject, email_body)
            
            if email_sent:
                r["status"] = "sent"
                r["updates"].append({
                    "date": datetime.now(timezone.utc).isoformat(),
                    "status": "sent",
                    "note": "APPROVED — Formal request emailed to {}.".format(r["recipient_email"]),
                })
            else:
                r["status"] = "approved_pending_send"
                r["updates"].append({
                    "date": datetime.now(timezone.utc).isoformat(),
                    "status": "approved_pending_send",
                    "note": "APPROVED — Email queued for delivery to {}.".format(r["recipient_email"]),
                })
            
            save_db(db)
            
            # Notify admin of approval
            send_backup("FOIA APPROVED: " + req_id, 
                "Request {} has been approved and sent to {}.".format(req_id, r["recipient_email"]))
            
            return jsonify({"ok": True, "status": r["status"], "request_id": req_id})
    
    return jsonify({"ok": False, "error": "Request not found"}), 404

@app.route("/api/foia/admin/reject/<req_id>", methods=["POST"])
def admin_reject(req_id):
    if not check_admin():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    
    data = request.json or {}
    reason = data.get("reason", "Request does not meet submission guidelines.")
    
    db = load_db()
    for r in db.get("requests", []):
        if r["id"] == req_id:
            r["status"] = "rejected"
            r["updates"].append({
                "date": datetime.now(timezone.utc).isoformat(),
                "status": "rejected",
                "note": "REJECTED — {}".format(reason),
            })
            save_db(db)
            return jsonify({"ok": True, "status": "rejected", "request_id": req_id})
    
    return jsonify({"ok": False, "error": "Request not found"}), 404

@app.route("/api/foia/admin/all", methods=["GET"])
def admin_all():
    if not check_admin():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    
    db = load_db()
    return jsonify({"ok": True, "requests": db.get("requests", [])})

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5060, debug=False)
