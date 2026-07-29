#!/usr/bin/env python3
"""
Ingest minutes from a CivicPlus Archive Center.

    python3 shared/ingest_archive_minutes.py mississippi

Southaven's AgendaCenter publishes agendas only, which is why this chapter showed
zero minutes. The minutes are not missing — they are in the *Archive* Center, a
separate CivicPlus module that renders its documents as <select> dropdowns rather
than links, so nothing crawling for <a href> ever finds them.

    /Archive.aspx                     the page with the dropdowns
    /Archive.aspx?ADID=<id>           the actual PDF

Reads `archive.label` from the chapter config to pick the right dropdown, then
attaches each set of minutes to the meeting page for the same date.

Minutes are where the votes are. An agenda proves an item was scheduled; only the
minutes show what the body did with it.
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
    import fitz
except ImportError:
    sys.exit("pip install pymupdf")

ROOT = Path(__file__).resolve().parent.parent
UA = ("Mozilla/5.0 (compatible; MoveWeightFoundation/1.0; "
      "+https://foundation.moveweight.com) public-records-archive")

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}
DATE_RE = re.compile(
    r"(" + "|".join(MONTHS) + r")\.?\s+(\d{1,2}),?\s+(\d{4})", re.I)
OPT_RE = re.compile(r'<option value="([0-9_]+)">([^<]+)</option>')

SECTION = """

<section id="minutes">
  <div class="wrap narrow">
    <h2>Minutes, as published</h2>
    <p class="dim" style="font-size:.86rem">
      {pages} page{plural}. This is the record of what the Board actually did &mdash;
      motions, seconds, votes and who was absent. Published in the City's Archive
      Center, which is a different system from its agenda portal.
    </p>
    <div class="hero-btns" style="margin-bottom:18px">
      <a class="btn btn-red" href="{source}" rel="noopener">Download from the City &darr;</a>
    </div>
    <div class="docquote"><pre style="white-space:pre-wrap;font-family:inherit;margin:0">{text}</pre>
      <span class="dq-cite">Source: <a href="{source}" rel="noopener">{source}</a></span>
    </div>
  </div>
</section>
"""


def esc(s):
    return htmlmod.escape(str(s), quote=True)


def find_dropdown(html, label):
    """The <select> that follows a given label, as options [(adid, text)]."""
    i = html.lower().find(label.lower())
    if i < 0:
        return []
    seg = html[i:i + 20000]
    out = []
    for val, text in OPT_RE.findall(seg):
        adid = val.split("_")[-1]
        t = text.strip()
        if "most recent" in t.lower():
            continue
        out.append((adid, t))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chapter")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-mb", type=int, default=60,
                    help="skip absurdly large PDFs (some carry every attachment)")
    a = ap.parse_args()

    cfg = json.loads((ROOT / "chapters" / f"{a.chapter}.json").read_text(encoding="utf-8"))
    arc = cfg.get("archive")
    if not arc:
        sys.exit(f"chapter {a.chapter} has no 'archive' config block")

    base = arc.get("base", cfg["agendas"]["base"]).rstrip("/")
    label = arc.get("label", "Minutes")

    src = Path(cfg.get("source_dir") or (ROOT.parent / f"expose{a.chapter}"))
    src = src if src.is_absolute() else (ROOT / src).resolve()
    pages_dir = src / "src" / "pages"
    mpath = src / "site" / "data" / "meetings.json"
    if not mpath.exists():
        sys.exit("run ingest_agendas.py first")
    meta = json.loads(mpath.read_text(encoding="utf-8"))
    by_date = {m["date"]: m for m in meta["meetings"]}

    s = requests.Session()
    s.headers["User-Agent"] = UA
    r = s.get(base + "/Archive.aspx", timeout=60)
    opts = find_dropdown(r.text, label)
    if a.limit:
        opts = opts[:a.limit]
    print(f"  {len(opts)} documents under '{label}'")

    attached = skipped = 0
    for adid, text in opts:
        m = DATE_RE.search(text)
        if not m:
            continue
        d = date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)))
        meeting = by_date.get(d.isoformat())
        if not meeting:
            skipped += 1
            continue
        frag = pages_dir / f"70-meeting-{meeting['slug']}.html"
        if not frag.exists():
            continue
        cur = frag.read_text(encoding="utf-8")
        if 'id="minutes"' in cur:
            continue

        url = f"{base}/Archive.aspx?ADID={adid}"
        resp = s.get(url, timeout=180)
        if resp.content[:4] != b"%PDF":
            continue
        size_mb = len(resp.content) / 1024 / 1024
        if size_mb > a.max_mb:
            print(f"    {d} : {size_mb:.0f} MB, too large to parse inline — linked only")
            body = ("(These minutes are a %.0f MB PDF, too large to render here. "
                    "Use the download button above.)" % size_mb)
            npages = 0
        else:
            doc = fitz.open(stream=resp.content, filetype="pdf")
            body = re.sub(r"\n{3,}", "\n\n",
                          "\n".join(p.get_text() for p in doc)).strip()
            npages = doc.page_count
            doc.close()
            if len(body) < 60:
                body = ("(These minutes are a scanned image with no text layer. "
                        "Use the download button above.)")

        cur += SECTION.format(pages=npages or "?", plural="" if npages == 1 else "s",
                              source=esc(url), text=esc(body)[:120000])
        frag.write_text(cur, encoding="utf-8")
        meeting["minutes_archived"] = True
        meeting["minutes_url"] = url
        meeting["minutes_pages"] = npages
        attached += 1
        print(f"    {d}: {npages} pages attached")
        time.sleep(0.8)

    meta["minutes_updated_at"] = datetime.now().isoformat()
    mpath.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"  minutes attached to {attached} meetings "
          f"({skipped} had no matching agenda page)")


if __name__ == "__main__":
    main()
