#!/usr/bin/env python3
"""
Build a chapter's meeting-video index from the city's own YouTube channel.

    python3 shared/ingest_videos.py sanangelo

We do NOT download or rehost the video. The city's copy is the authoritative one and
should keep its view count. What this builds is the thing the city does not provide:
a dated, searchable index that links each recording to the agenda and minutes for the
same meeting, so "what happened on 6 January" is one click instead of a scroll through
a playlist of 411 items with names like "City Council LIVE stream 1-6-26".

Reads `video.playlist` (or `video.channel`) from the chapter config.

Requires: yt-dlp.
"""

import argparse
import html as htmlmod
import json
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Cities title their uploads differently and none of them are consistent:
#   San Angelo: "City Council LIVE stream 7-21-26"
#   Southaven:  "Meeting of the ... Mayor and Board of Aldermen - December 3, 2024"
NUM_DATE_RE = re.compile(r"(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})")
MONTHS = {m.lower(): i for i, m in enumerate(
    ["January","February","March","April","May","June","July","August",
     "September","October","November","December"], 1)}
WORD_DATE_RE = re.compile(
    r"(" + "|".join(MONTHS) + r")\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", re.I)


def esc(s):
    return htmlmod.escape(str(s), quote=True)


def parse_date(title):
    t = title.strip()
    w = WORD_DATE_RE.search(t)
    if w:
        mo, dy, yr = MONTHS[w.group(1).lower()], int(w.group(2)), int(w.group(3))
        try:
            return date(yr, mo, dy)
        except ValueError:
            return None
    n = NUM_DATE_RE.search(t)
    if n:
        mo, dy, yr = (int(x) for x in n.groups())
        yr = yr + 2000 if yr < 100 else yr
        try:
            return date(yr, mo, dy)
        except ValueError:
            return None
    return None


def enumerate_playlist(url):
    r = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--dump-json", "--ignore-errors", url],
        capture_output=True, text=True, timeout=1800)
    out = []
    for line in r.stdout.splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        vid, title = d.get("id"), (d.get("title") or "").strip()
        if not vid or not title:
            continue
        out.append({"id": vid, "title": title,
                    "duration": d.get("duration") or 0,
                    "date": (parse_date(title) or date(1970, 1, 1)).isoformat()})
    return out


PAGE = """<!--meta
out: video-archive.html
requires: meetings
title: Meeting video archive
description: Every recorded {body} meeting for {city}, {state}, dated and indexed, linked to the agenda for the same day.
-->

<section class="hero">
  <div class="wrap">
    <span class="eyebrow">Video archive &middot; {city}, {abbr}</span>
    <h1>{count} recorded meetings</h1>
    <p class="lede">
      Every meeting the City has posted, dated and indexed. The recordings are the
      City's own and play on the City's own channel &mdash; we do not rehost them.
      What we add is the index: which date, how long, and the agenda that goes with it.
    </p>
    <div class="hero-btns">
      <a class="btn btn-red" href="/meetings/">Agendas &amp; minutes</a>
      <a class="btn btn-ghost" href="/search.html">Search everything</a>
    </div>
  </div>
</section>

<section>
  <div class="wrap">
    <div class="callout gold">
      <span class="co-label">Longest meetings first tells you something</span>
      <p class="mb0">
        A four-hour meeting is usually a contested one. Sort by duration and you find
        the nights people showed up. Total recorded time indexed here:
        <strong>{hours} hours</strong>.
      </p>
    </div>
    <div class="table-scroll">
      <table>
        <thead><tr><th>Date</th><th>Meeting</th><th>Length</th><th>Watch</th><th>Papers</th></tr></thead>
        <tbody>
{rows}
        </tbody>
      </table>
    </div>
    <p class="src">
      Indexed from the City's published playlist on {captured}. Dates are parsed from the
      City's own video titles; where a title carries no date it is listed as undated.
      <a href="/tips.html">Tell us if a meeting is missing &rarr;</a>
    </p>
  </div>
</section>
"""


def build(chapter, quiet=False):
    cfg = json.loads((ROOT / "chapters" / f"{chapter}.json").read_text(encoding="utf-8"))
    v = cfg.get("video", {})
    url = v.get("playlist") or v.get("channel")
    if not url:
        sys.exit(f"chapter {chapter} has no video.playlist or video.channel configured")

    src = Path(cfg.get("source_dir") or (ROOT.parent / f"expose{chapter}"))
    src = src if src.is_absolute() else (ROOT / src).resolve()

    vids = enumerate_playlist(url)
    if not quiet:
        print(f"  {len(vids)} videos enumerated")
    vids.sort(key=lambda x: x["date"], reverse=True)

    # Link a video to the agenda for the same day where we have one.
    mpath = src / "site" / "data" / "meetings.json"
    by_date = {}
    if mpath.exists():
        for m in json.loads(mpath.read_text(encoding="utf-8"))["meetings"]:
            by_date.setdefault(m["date"], m)

    rows, matched = [], 0
    for x in vids:
        d = x["date"]
        pretty = "undated" if d == "1970-01-01" else d
        mins = int(x["duration"] / 60) if x["duration"] else 0
        length = f"{mins // 60}h {mins % 60:02d}m" if mins >= 60 else (f"{mins}m" if mins else "&mdash;")
        m = by_date.get(d)
        if m:
            matched += 1
            papers = (f'<a href="/meetings/{esc(m["slug"])}.html">Agenda</a>')
        else:
            papers = '<span class="dim">&mdash;</span>'
        rows.append(
            f'          <tr><td class="num">{esc(pretty)}</td>'
            f'<td>{esc(x["title"])}</td>'
            f'<td class="num">{length}</td>'
            f'<td><a href="https://www.youtube.com/watch?v={esc(x["id"])}" rel="noopener">Watch &rarr;</a></td>'
            f"<td>{papers}</td></tr>")

    total_h = round(sum(x["duration"] for x in vids) / 3600)
    (src / "src" / "pages" / "68-video-archive.html").write_text(PAGE.format(
        body=esc(v.get("body", cfg.get("agendas", {}).get("body", "City meeting"))),
        city=esc(cfg["city"]), state=esc(cfg["state"]), abbr=esc(cfg["state_abbr"]),
        count=len(vids), hours=f"{total_h:,}", rows="\n".join(rows),
        captured=date.today().isoformat(),
    ), encoding="utf-8")

    (src / "site" / "data").mkdir(parents=True, exist_ok=True)
    (src / "site" / "data" / "videos.json").write_text(json.dumps(
        {"generated_at": datetime.now().isoformat(), "source": url,
         "count": len(vids), "videos": vids}, indent=1), encoding="utf-8")

    if not quiet:
        print(f"  {total_h:,} hours indexed, {matched} linked to an agenda")
    return len(vids)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chapter")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    build(a.chapter, a.quiet)


if __name__ == "__main__":
    main()
