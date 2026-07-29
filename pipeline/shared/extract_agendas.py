#!/usr/bin/env python3
"""
Pull the text out of each meeting's agenda so the archive can be searched.

    python3 shared/extract_agendas.py --all --limit 150
    python3 shared/extract_agendas.py tulsa

An index of 1,161 meetings that only links out is a filing cabinet with the
drawers welded shut. San Antonio's search index held twelve records - the static
pages - so a resident searching "tax abatement" got nothing, while the abatement
sat in an agenda the chapter had already catalogued. This extracts the text of
each agenda and hands it to the search index, which is the difference between
listing the record and being able to interrogate it.

We do not rehost the documents. The text is indexed; every result links to the
city's own copy.

Which chapters this can serve
----------------------------
    Legistar    austin, dallas          direct PDF, EventAgendaFile
    CivicPlus   lubbock, olivebranch    direct PDF, AgendaCenter/ViewFile
    Granicus    tulsa                   direct PDF, AgendaViewer.php

PrimeGov (Oklahoma City, San Antonio) is deliberately absent. Its portal lists
every meeting publicly but serves the document itself only behind a sign-in -
verified against fresh document ids, with a real browser via FlareSolverr, not
just with curl. Those two chapters say so on the page rather than appearing to
have a thinner archive than they do.

Caching is on disk and keyed by URL, so the weekly run only fetches what is new.
Requires: pymupdf or pdftotext for PDFs; nothing for HTML.
"""

import argparse
import hashlib
import html as htmlmod
import json
import re
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHAPTERS = ROOT / "chapters"

UA = ("Mozilla/5.0 (compatible; MoveWeightFoundation/1.0; "
      "+https://foundation.moveweight.com) public-records-archive")

# Vendors whose agenda document is a plain public fetch. Anything else is left
# alone rather than half-served.
# civicclerk added once its document URL was verified to answer 200 with
# application/pdf. Its agendas are only reachable through
# GetMeetingFileStream(fileId=...) - the portal path serves a viewer shell,
# which is why this vendor was originally treated as not fetchable.
FETCHABLE = {"legistar", "civicplus", "granicus", "civicclerk"}

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

TAGS = re.compile(r"<[^>]+>")
DROP = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
        return r.read(), (r.headers.get("Content-Type") or "").lower()


def pdf_text(raw):
    """Extract text, preferring PyMuPDF and falling back to pdftotext."""
    try:
        import fitz  # PyMuPDF
        with fitz.open(stream=raw, filetype="pdf") as doc:
            return "\n".join(p.get_text() for p in doc)
    except ImportError:
        pass
    except Exception:  # noqa: BLE001 - a malformed PDF is not fatal
        return ""
    if not shutil.which("pdftotext"):
        return ""
    try:
        r = subprocess.run(["pdftotext", "-q", "-", "-"], input=raw,
                           capture_output=True, timeout=120)
        return r.stdout.decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return ""


def html_text(raw):
    s = raw.decode("utf-8", "replace")
    s = DROP.sub(" ", s)
    return re.sub(r"\s+", " ", htmlmod.unescape(TAGS.sub(" ", s))).strip()


def clean(t):
    """Collapse the whitespace a PDF extractor leaves behind."""
    t = re.sub(r"[ \t ]+", " ", t)
    t = re.sub(r"\n\s*\n\s*\n+", "\n\n", t)
    return t.strip()


def slug(url):
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def extract(key, limit, delay, quiet=False):
    cfg = json.loads((CHAPTERS / f"{key}.json").read_text(encoding="utf-8"))
    vendor = (cfg.get("portal") or {}).get("vendor")
    src = (ROOT / cfg["source_dir"]).resolve()
    mfile = src / "generated" / "meetings.json"
    if vendor not in FETCHABLE or not mfile.exists():
        if not quiet:
            why = ("portal documents are not publicly fetchable"
                   if vendor else "no portal")
            print(f"  {key:13s} skipped - {why}")
        return 0, 0, 0

    meetings = json.loads(mfile.read_text(encoding="utf-8"))["meetings"]
    out = src / "generated" / "agendas"
    out.mkdir(parents=True, exist_ok=True)
    idx_file = out / "index.json"
    idx = {}
    if idx_file.exists():
        try:
            idx = json.loads(idx_file.read_text(encoding="utf-8"))
        except ValueError:
            idx = {}

    # Newest first: the meetings people search for are the recent ones, and a
    # capped run should spend its budget there.
    jobs = []
    for m in meetings:
        for kind in ("agenda", "minutes"):
            u = m.get(f"{kind}_url")
            if u:
                jobs.append((m, kind, u))
    jobs.sort(key=lambda j: j[0]["date"], reverse=True)

    done = fetched = 0
    for m, kind, url in jobs:
        sid = slug(url)
        if sid in idx:
            done += 1
            continue
        if fetched >= limit:
            break
        try:
            raw, ctype = fetch(url)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            idx[sid] = {"url": url, "date": m["date"], "kind": kind,
                        "chars": 0, "error": type(e).__name__}
            fetched += 1
            continue
        text = pdf_text(raw) if ("pdf" in ctype or raw[:4] == b"%PDF") else html_text(raw)
        text = clean(text)
        if len(text) > 40:
            (out / f"{sid}.txt").write_text(text, encoding="utf-8")
        idx[sid] = {"url": url, "date": m["date"], "kind": kind,
                    "body": m.get("body") or m.get("title") or "Meeting",
                    "source_url": m.get("source_url", ""),
                    "chars": len(text)}
        fetched += 1
        done += 1
        # Flush the index periodically. Written only at the end, an interrupted
        # run threw away every document it had just fetched - and this runs under
        # a timeout inside the weekly job, so interruption is the expected case,
        # not the exception.
        if fetched % 20 == 0:
            idx_file.write_text(json.dumps(idx, indent=1), encoding="utf-8")
        # These are city servers publishing to the public, not an API we pay
        # for. A steady trickle costs them nothing and gets the archive built
        # over a few weekly runs.
        time.sleep(delay)

    idx_file.write_text(json.dumps(idx, indent=1), encoding="utf-8")
    got = sum(1 for v in idx.values() if v.get("chars", 0) > 40)
    chars = sum(v.get("chars", 0) for v in idx.values())
    gone = sum(1 for v in idx.values() if v.get("error"))
    if not quiet:
        print(f"  {key:13s} {got:5d} documents  {chars:12,d} chars  "
              f"(+{fetched} this run, {len(jobs) - done} remaining"
              + (f", {gone} unavailable" if gone else "") + ")")
    return got, chars, gone


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--limit", type=int, default=120,
                    help="documents to fetch per chapter per run")
    ap.add_argument("--delay", type=float, default=0.7)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    keys = args.keys
    if args.all:
        keys = []
        for p in sorted(CHAPTERS.glob("*.json")):
            if p.stem.startswith("_"):
                continue
            cfg = json.loads(p.read_text(encoding="utf-8"))
            if (cfg.get("portal") or {}).get("vendor") in FETCHABLE:
                keys.append(p.stem)
    if not keys:
        raise SystemExit("name chapters, or pass --all")

    total_docs = total_chars = total_gone = 0
    for k in keys:
        try:
            d, c, g = extract(k, args.limit, args.delay, args.quiet)
            total_docs += d
            total_chars += c
            total_gone += g
        except Exception as e:  # noqa: BLE001 - one city must not stop the rest
            print(f"  {k:13s} FAILED: {type(e).__name__}: {e}")
    # Always printed, even under --quiet: the weekly runner shows the last line
    # of output as the detail on the public automation page, and "ok" tells a
    # reader nothing. The unavailable count is published rather than hidden -
    # it means the city's own portal advertises an agenda URL that does not
    # serve, which is exactly the sort of thing this project exists to notice.
    lead = "" if args.quiet else "\n"
    print(f"{lead}  {total_docs} documents indexed, {total_chars:,} characters"
          + (f"; {total_gone} listed by the city but not served"
             if total_gone else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
