#!/usr/bin/env python3
"""
Ingest a chapter's agendas, minutes and packets from a CivicPlus AgendaCenter.

    python shared/ingest_agendas.py mississippi
    python shared/ingest_agendas.py sanangelo --limit 40

Both Southaven and San Angelo run CivicPlus, which exposes every meeting document
at a stable, guessable path:

    /AgendaCenter/ViewFile/Agenda/_MMDDYYYY-NNN
    /AgendaCenter/ViewFile/Minutes/_MMDDYYYY-NNN

So the archive is: scrape the listing, pull each PDF, extract its text, and build
a page per meeting plus an index. No API key, no scraping of anything that is not
already a published public record.

What it writes into the chapter's site/:
    meetings/index.html          the archive index
    meetings/<date>-<id>.html    one page per meeting, full agenda text
    meetings/files/*.pdf         the source PDFs, kept verbatim
    data/meetings.json           machine-readable index

The extracted text feeds the site search index, which is the point: a resident can
search "fee in lieu" and land on the agenda that carried it.

Requires: requests, pymupdf.
"""

import argparse
import html as htmlmod
import json
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("pip install requests")
try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("pip install pymupdf")

ROOT = Path(__file__).resolve().parent.parent

UA = ("Mozilla/5.0 (compatible; MoveWeightFoundation/1.0; "
      "+https://foundation.moveweight.com) public-records-archive")

LINK_RE = re.compile(
    r'href="(/AgendaCenter/ViewFile/(Agenda|Minutes)/_(\d{2})(\d{2})(\d{4})-(\d+))"',
    re.I)


def fetch(url, session, tries=3):
    for i in range(tries):
        try:
            r = session.get(url, timeout=45)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(1.5 * (i + 1))
    return None


def discover(base, session, limit):
    """Every distinct meeting document linked from the AgendaCenter."""
    found = {}
    for path in ("/AgendaCenter", "/AgendaCenter/Search"):
        r = fetch(base + path, session)
        if not r:
            continue
        for href, kind, mm, dd, yyyy, num in LINK_RE.findall(r.text):
            try:
                d = date(int(yyyy), int(mm), int(dd))
            except ValueError:
                continue
            key = (d.isoformat(), num)
            entry = found.setdefault(key, {"date": d.isoformat(), "id": num,
                                           "agenda": None, "minutes": None})
            entry[kind.lower()] = base + href
    rows = sorted(found.values(), key=lambda x: (x["date"], x["id"]), reverse=True)
    return rows[:limit] if limit else rows


def pdf_text(raw: bytes):
    try:
        doc = fitz.open(stream=raw, filetype="pdf")
    except Exception:
        return "", 0
    txt = "\n".join(p.get_text() for p in doc)
    n = doc.page_count
    doc.close()
    return re.sub(r"\n{3,}", "\n\n", txt).strip(), n


def esc(s):
    return htmlmod.escape(str(s), quote=True)


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
      <a class="btn btn-red" href="/meetings/files/{slug}-agenda.pdf">Download the agenda PDF &darr;</a>
      <a class="btn btn-ghost" href="{source}" rel="noopener">View on the city's site</a>
      <a class="btn btn-ghost" href="/meetings/">All meetings</a>
    </div>
  </div>
</section>

<section>
  <div class="wrap narrow">
    <h2>Agenda, as published</h2>
    <p class="dim" style="font-size:.86rem">
      {pages} page{plural}, text extracted from the City's own PDF on {captured}.
      Reproduced in full and unaltered. If the extraction looks wrong, the PDF above is
      the authority.
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
      An agenda tells you an item was discussed. It rarely tells you what was decided, how
      each member voted, or what the underlying contract says. Those are separate records,
      and they are requestable.
    </p>
    <div class="hero-btns">
      <a class="btn btn-red" href="/records/">File a request on this meeting &rarr;</a>
      <a class="btn btn-ghost" href="/tips.html">Send an anonymous tip</a>
    </div>
  </div>
</section>
"""


MINUTES_SECTION = """

<section id="minutes">
  <div class="wrap narrow">
    <h2>Minutes, as published</h2>
    <p class="dim" style="font-size:.86rem">
      {pages} page{plural}. This is the record of what the body actually did &mdash;
      motions, seconds, votes and who was absent.
    </p>
    <div class="hero-btns" style="margin-bottom:18px">
      <a class="btn btn-ghost" href="/meetings/files/{slug}-minutes.pdf">Download the minutes PDF &darr;</a>
    </div>
    <div class="docquote"><pre style="white-space:pre-wrap;font-family:inherit;margin:0">{text}</pre>
      <span class="dq-cite">Source: <a href="{source}" rel="noopener">{source}</a></span>
    </div>
  </div>
</section>
"""


def build(chapter, limit, quiet=False):
    cfg = json.loads((ROOT / "chapters" / f"{chapter}.json").read_text(encoding="utf-8"))
    ag = cfg.get("agendas")
    if not ag or not ag.get("base"):
        sys.exit(f"chapter {chapter} has no 'agendas.base' configured")

    base, body = ag["base"].rstrip("/"), ag.get("body", "Meeting")
    src_dir = Path(cfg.get("source_dir") or (ROOT.parent / f"expose{chapter}"))
    src_dir = src_dir if src_dir.is_absolute() else (ROOT / src_dir).resolve()
    pages_dir = src_dir / "src" / "pages"
    files_dir = src_dir / "site" / "meetings" / "files"
    pages_dir.mkdir(parents=True, exist_ok=True)
    files_dir.mkdir(parents=True, exist_ok=True)

    s_sess = requests.Session()
    s_sess.headers["User-Agent"] = UA

    rows = discover(base, s_sess, limit)
    if not quiet:
        print(f"  discovered {len(rows)} meeting documents at {base}")

    index, kept = [], 0
    for r in rows:
        if not r["agenda"]:
            continue
        slug = f"{r['date']}-{r['id']}"
        resp = fetch(r["agenda"], s_sess)
        if not resp or not resp.content[:4] == b"%PDF":
            if not quiet:
                print(f"    skip {slug}: not a PDF")
            continue
        (files_dir / f"{slug}-agenda.pdf").write_bytes(resp.content)
        text, npages = pdf_text(resp.content)
        if len(text) < 60:
            if not quiet:
                print(f"    {slug}: PDF is a scan, no text layer — PDF kept, page still built")
            text = "(This agenda is a scanned image with no text layer. "
            text += "Download the PDF above to read it.)"

        d = datetime.fromisoformat(r["date"]).date()
        pretty = d.strftime("%d %B %Y").lstrip("0")
        title = f"{body} — {pretty}"
        first = next((ln.strip() for ln in text.splitlines() if len(ln.strip()) > 25),
                     "Agenda as published by the City.")
        (pages_dir / f"70-meeting-{slug}.html").write_text(PAGE.format(
            slug=slug, title=esc(title),
            desc=esc(f"{body} agenda for {pretty}, {cfg['city']}, {cfg['state']}, "
                     f"published in full with the source PDF."),
            body=esc(body), pretty=esc(pretty), source=esc(r["agenda"]),
            lede=esc(first[:240]), pages=npages, plural="" if npages == 1 else "s",
            captured=date.today().isoformat(), text=esc(text)[:120000],
        ), encoding="utf-8")

        # Minutes are where the votes are. An agenda proves an item was scheduled;
        # only the minutes show what the body did with it. Archive them too, because
        # a city that takes a page down takes the vote record with it.
        min_pages = min_chars = 0
        if r["minutes"]:
            mr = fetch(r["minutes"], s_sess)
            if mr and mr.content[:4] == b"%PDF":
                (files_dir / f"{slug}-minutes.pdf").write_bytes(mr.content)
                mtext, min_pages = pdf_text(mr.content)
                min_chars = len(mtext)
                frag = pages_dir / f"70-meeting-{slug}.html"
                cur = frag.read_text(encoding="utf-8")
                cur += MINUTES_SECTION.format(
                    slug=slug, pages=min_pages,
                    plural="" if min_pages == 1 else "s",
                    source=esc(r["minutes"]),
                    text=esc(mtext)[:120000] if min_chars > 60 else
                         "(These minutes are a scanned image with no text layer. "
                         "Download the PDF above to read them.)")
                frag.write_text(cur, encoding="utf-8")
                time.sleep(0.6)

        index.append({"slug": slug, "date": r["date"], "title": title, "body": body,
                      "pages": npages, "chars": len(text), "source": r["agenda"],
                      "minutes": r["minutes"],
                      "minutes_archived": bool(min_chars or min_pages),
                      "minutes_pages": min_pages, "minutes_chars": min_chars})
        kept += 1
        time.sleep(0.6)   # be a polite guest on a city web server

    (src_dir / "site" / "data").mkdir(parents=True, exist_ok=True)
    (src_dir / "site" / "data" / "meetings.json").write_text(json.dumps(
        {"generated_at": datetime.now().isoformat(), "count": len(index),
         "meetings": index}, indent=1), encoding="utf-8")

    write_index(pages_dir, index, cfg, body)
    if not quiet:
        print(f"  {kept} meetings ingested, "
              f"{sum(m['pages'] for m in index)} PDF pages, "
              f"{sum(m['chars'] for m in index):,} chars of agenda text")
    return kept


def write_index(pages_dir, index, cfg, body):
    rows = "\n".join(
        f'          <tr><td class="num">{esc(m["date"])}</td>'
        f'<td><a href="/meetings/{esc(m["slug"])}.html">{esc(m["title"])}</a></td>'
        f'<td class="num">{m["pages"]}</td>'
        f'<td><a href="/meetings/files/{esc(m["slug"])}-agenda.pdf">PDF &darr;</a>'
        + (f' &middot; <a href="/meetings/files/{esc(m["slug"])}-minutes.pdf">Minutes &darr;</a>'
           if m.get("minutes_archived") else
           (f' &middot; <a href="{esc(m["minutes"])}" rel="noopener">Minutes (city)</a>'
            if m["minutes"] else ""))
        + "</td></tr>"
        for m in index)

    (pages_dir / "69-meetings-index.html").write_text(f"""<!--meta
out: meetings/index.html
nav: /meetings/
requires: agenda_packets
title: Meeting archive
description: Every published {body} agenda for {cfg['city']}, {cfg['state']} — full text, searchable, with the City's own PDF attached.
-->

<section class="hero">
  <div class="wrap">
    <span class="eyebrow">Meeting archive &middot; {esc(cfg['city'])}, {esc(cfg['state_abbr'])}</span>
    <h1>{len(index)} meetings, in full</h1>
    <p class="lede">
      Every {esc(body)} agenda the City has published, with the text extracted so you can
      search it. The PDFs are the City's own and are kept exactly as published.
      <strong>An agenda tells you an item existed</strong> &mdash; what was decided and how
      each member voted are separate records, and they are requestable.
    </p>
    <div class="hero-btns">
      <a class="btn btn-red" href="/search.html">Search every agenda &rarr;</a>
      <a class="btn btn-ghost" href="/records/">Request minutes or a vote tally</a>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="table-scroll">
      <table>
        <thead><tr><th>Date</th><th>Meeting</th><th>Pages</th><th>Source</th></tr></thead>
        <tbody>
{rows}
        </tbody>
      </table>
    </div>
    <p class="src">
      Captured from the City's AgendaCenter on {date.today().isoformat()}. We re-check
      regularly; if a meeting is missing here it is because the City has not published it.
      <a href="/tips.html">Tell us if you spot a gap &rarr;</a>
    </p>
  </div>
</section>
""", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chapter")
    ap.add_argument("--limit", type=int, default=0, help="max meetings (0 = all)")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    build(a.chapter, a.limit, a.quiet)


if __name__ == "__main__":
    main()
