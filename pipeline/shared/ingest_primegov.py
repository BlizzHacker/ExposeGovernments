#!/usr/bin/env python3
"""
Ingest agendas and video from a PrimeGov / Granicus portal.

    python3 shared/ingest_primegov.py okc

Southaven and San Angelo run CivicPlus, which `ingest_agendas.py` handles by
scraping HTML. Oklahoma City runs PrimeGov, which is better in every way: a
public JSON API, no key, and agendas AND video in the same record.

    /api/v2/PublicPortal/ListArchivedMeetings?year=YYYY

Each meeting carries dateTime, title, a documentList (HTML agenda, PDF packet),
videoUrl and swagitId. Documents render at:

    /Portal/viewer?id={documentId}&type={compileOutputType}

That parameter shape was recovered from PrimeGov's own .NET error responses,
which leak the controller signature when you pass the wrong arguments.

The viewer is a JavaScript shell, so documents are fetched with headless
Chromium rather than plain HTTP — slower, but it is the only way to get the
rendered agenda text.
"""

import argparse
import html as htmlmod
import json
import re
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("pip install requests")

ROOT = Path(__file__).resolve().parent.parent
UA = ("Mozilla/5.0 (compatible; MoveWeightFoundation/1.0; "
      "+https://foundation.moveweight.com) public-records-archive")

TAG = re.compile(r"<[^>]+>")
SCRIPT = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)

# compileOutputType seen in the wild: 1 = PDF, 3 = HTML agenda.
HTML_AGENDA, PDF_PACKET = 3, 1


def esc(s):
    return htmlmod.escape(str(s), quote=True)


def api(base, year, session):
    url = f"{base}/api/v2/PublicPortal/ListArchivedMeetings?year={year}"
    r = session.get(url, timeout=90)
    if r.status_code != 200:
        return []
    try:
        return r.json()
    except ValueError:
        return []


def render(url, budget=15000, timeout=150):
    """Headless-render a JS page and return its text, or '' on failure."""
    try:
        p = subprocess.run(
            ["chromium", "--headless", "--disable-gpu", "--no-sandbox",
             f"--virtual-time-budget={budget}", "--dump-dom", url],
            capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    dom = p.stdout or ""
    if "no longer available" in dom or "Something went wrong" in dom:
        return ""
    dom = SCRIPT.sub(" ", dom)
    text = htmlmod.unescape(TAG.sub(" ", dom))
    text = re.sub(r"\s+", " ", text).strip()
    # Strip the portal chrome that wraps every document.
    for junk in ("Viewer - PrimeGov Portal Toggle navigation Sign In English",
                 "Powered by Prime Government Solutions"):
        text = text.replace(junk, " ")
    return re.sub(r"\s{2,}", " ", text).strip()


PAGE = """<!--meta
out: meetings/{slug}.html
nav: /meetings/
requires: agenda_packets
title: {title}
description: {desc}
-->

<section class="hero">
  <div class="wrap">
    <span class="eyebrow">{body} &middot; {pretty}</span>
    <h1>{title}</h1>
    <p class="lede">{lede}</p>
    <div class="hero-btns">
      {video_btn}
      <a class="btn btn-ghost" href="{source}" rel="noopener">View on the city's portal</a>
      <a class="btn btn-ghost" href="/meetings/">All meetings</a>
    </div>
  </div>
</section>

<section>
  <div class="wrap narrow">
    <h2>Agenda, as published</h2>
    <p class="dim" style="font-size:.86rem">
      Retrieved from the City's PrimeGov portal on {captured}. The portal renders
      agendas in JavaScript, so this text was captured from the rendered page. The
      city's own copy, linked above, is the authority.
    </p>
    <div class="docquote"><pre style="white-space:pre-wrap;font-family:inherit;margin:0">{text}</pre>
      <span class="dq-cite">Source: <a href="{source}" rel="noopener">{source}</a></span>
    </div>
  </div>
</section>

<section>
  <div class="wrap narrow">
    <h2>Something here worth a records request?</h2>
    <p>
      An agenda shows an item was scheduled. What was decided, how each member voted,
      and what the underlying contract says are separate records &mdash; and they are
      requestable.
    </p>
    <div class="hero-btns">
      <a class="btn btn-red" href="/records/">File a request on this meeting &rarr;</a>
      <a class="btn btn-ghost" href="/tips.html">Send an anonymous tip</a>
    </div>
  </div>
</section>
"""


def build(chapter, years, limit, quiet=False):
    cfg = json.loads((ROOT / "chapters" / f"{chapter}.json").read_text(encoding="utf-8"))
    pg = cfg.get("primegov")
    if not pg or not pg.get("base"):
        sys.exit(f"chapter {chapter} has no 'primegov.base' configured")
    base = pg["base"].rstrip("/")
    body = pg.get("body", "City Council")
    want = [t.lower() for t in pg.get("committees", [])]

    src = Path(cfg.get("source_dir") or (ROOT.parent / f"expose{chapter}"))
    src = src if src.is_absolute() else (ROOT / src).resolve()
    pages = src / "src" / "pages"
    pages.mkdir(parents=True, exist_ok=True)

    s = requests.Session()
    s.headers["User-Agent"] = UA

    meetings = []
    for y in years:
        got = api(base, y, s)
        if not quiet:
            print(f"  {y}: {len(got)} meetings", flush=True)
        meetings.extend(got)

    # Filter to the bodies that actually decide things. A portal carries dozens
    # of advisory committees; the council and its budget sessions are the point.
    if want:
        meetings = [m for m in meetings
                    if any(w in (m.get("title") or "").lower() for w in want)]
        if not quiet:
            print(f"  {len(meetings)} after committee filter {pg['committees']}")

    meetings.sort(key=lambda m: m.get("dateTime") or "", reverse=True)
    if limit:
        meetings = meetings[:limit]

    index, done, empty = [], 0, 0
    for m in meetings:
        dt = (m.get("dateTime") or "")[:10]
        if not dt:
            continue
        slug = f"{dt}-{m.get('id')}"
        frag = pages / f"70-meeting-{slug}.html"
        if frag.exists():
            continue

        docs = m.get("documentList") or []
        doc = next((d for d in docs if d.get("compileOutputType") == HTML_AGENDA), None) \
            or next((d for d in docs if d.get("compileOutputType") == PDF_PACKET), None) \
            or (docs[0] if docs else None)
        if not doc:
            continue

        url = f"{base}/Portal/viewer?id={doc['id']}&type={doc.get('compileOutputType', 3)}"
        text = render(url)
        if len(text) < 120:
            empty += 1
            text = ("(The City's portal did not return this agenda's contents. "
                    "The link above goes to the city's own copy.)")

        title = re.sub(r"\s+", " ", (m.get("title") or body)).strip()
        pretty = datetime.fromisoformat(dt).strftime("%d %B %Y").lstrip("0")
        video = m.get("videoUrl") or ""
        vbtn = (f'<a class="btn btn-red" href="{esc(video)}" rel="noopener">Watch the meeting &rarr;</a>'
                if video else "")
        first = next((ln for ln in text.split(". ") if len(ln) > 30), title)

        frag.write_text(PAGE.format(
            slug=slug, title=esc(f"{title} — {pretty}"), body=esc(body),
            pretty=esc(pretty), source=esc(url), video_btn=vbtn,
            desc=esc(f"{title} agenda for {pretty}, {cfg['city']}, {cfg['state']}."),
            lede=esc(first[:230]), captured=date.today().isoformat(),
            text=esc(text)[:120000],
        ), encoding="utf-8")

        index.append({"slug": slug, "date": dt, "title": f"{title} — {pretty}",
                      "body": body, "pages": 1, "chars": len(text),
                      "source": url, "minutes": None, "video": video})
        done += 1
        if not quiet and done % 10 == 0:
            print(f"    {done} agendas…", flush=True)
        time.sleep(0.4)

    (src / "site" / "data").mkdir(parents=True, exist_ok=True)
    (src / "site" / "data" / "meetings.json").write_text(json.dumps(
        {"generated_at": datetime.now().isoformat(), "count": len(index),
         "meetings": index}, indent=1), encoding="utf-8")

    # Reuse the CivicPlus index writer so both platforms render identically.
    sys.path.insert(0, str(ROOT / "shared"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("ia", ROOT / "shared" / "ingest_agendas.py")
    ia = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ia)
    ia.write_index(pages, index, cfg, body)

    if not quiet:
        print(f"  {done} agendas ingested, {empty} returned no text, "
              f"{sum(1 for m in index if m['video'])} with video")
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chapter")
    ap.add_argument("--years", default="2026,2025")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    build(a.chapter, [int(y) for y in a.years.split(",")], a.limit, a.quiet)


if __name__ == "__main__":
    main()
