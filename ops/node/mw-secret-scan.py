#!/usr/bin/env python3
"""Look for credentials before anything is copied into a PUBLIC repository.

    python3 secret_scan.py <path> [<path> ...]

The ExposeGovernments repo is public. Pushing the pipeline source there is only
safe if the source carries no secrets, and "I looked and it seemed fine" is not
a standard worth trusting with an Archive.org key or an SMTP password. This
errs heavily toward false positives - a human reads the list.
"""

import pathlib
import re
import sys

PATTERNS = [
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws-ish key", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("bearer token", re.compile(r"[Bb]earer\s+[A-Za-z0-9._\-]{20,}")),
    ("cloudflare token", re.compile(r"\b[A-Za-z0-9_-]{40}\b(?=.*(?i:cloudflare|CF_))")),
    ("assignment: password", re.compile(
        r"(?i)\b(pass(word|wd)?|passwd)\s*[:=]\s*[\"']?[^\s\"',}\)]{6,}")),
    ("assignment: secret/key/token", re.compile(
        r"(?i)\b(secret|api[_-]?key|access[_-]?key|auth[_-]?token|"
        r"private[_-]?token|s3[_-]?key)\s*[:=]\s*[\"']?[^\s\"',}\)]{8,}")),
    ("smtp url with creds", re.compile(r"(?i)(smtp|imap|ftp|https?)://[^\s:@/]+:[^\s@/]+@")),
]

# Things that look like assignments but are not secrets.
BENIGN = re.compile(
    r"(?i)(password|secret|token|key)\s*[:=]\s*[\"']?("
    r"none|null|true|false|\{|\$|<|\.\.\.|xxx+|your[_-]|example|changeme|"
    r"os\.environ|getenv|input\(|\"\"|''"
    r")")

SKIP_DIR = {".git", "__pycache__", "node_modules", "site-packages", ".venv"}
SKIP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".pdf",
            ".mp4", ".wav", ".mp3", ".zip", ".gz", ".tgz", ".db", ".woff",
            ".woff2", ".ttf"}

hits = 0
scanned = 0
for arg in sys.argv[1:]:
    base = pathlib.Path(arg)
    if not base.exists():
        print(f"  (absent) {base}")
        continue
    files = [base] if base.is_file() else base.rglob("*")
    for p in files:
        if not p.is_file() or p.is_symlink():
            continue
        if any(s in p.parts for s in SKIP_DIR) or p.suffix.lower() in SKIP_EXT:
            continue
        try:
            if p.stat().st_size > 4_000_000:
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        for line_no, line in enumerate(text.splitlines(), 1):
            if len(line) > 2000 or BENIGN.search(line):
                continue
            for label, pat in PATTERNS:
                if pat.search(line):
                    hits += 1
                    snippet = line.strip()[:110]
                    print(f"  {label:26} {p}:{line_no}")
                    print(f"      {snippet}")
                    break

print(f"\nscanned {scanned} files, {hits} potential secret(s)")
sys.exit(2 if hits else 0)
