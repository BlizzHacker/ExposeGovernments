#!/usr/bin/env python3
"""
Pull transcripts for every indexed meeting video and make them searchable.

    python3 shared/ingest_transcripts.py sanangelo

Cities stream their meetings to YouTube, and YouTube auto-captions them. Those
captions are a usable transcript of a public meeting, already generated, free to
fetch. Running Whisper over 900 hours of council audio to produce something that
already exists would be days of compute for no gain.

So: fetch the caption track with yt-dlp, flatten VTT to timestamped paragraphs,
and write a transcript page per meeting. That makes "who said water rates in
March" a search away.

Caveat carried onto every page: auto-captions mis-hear names, dollar figures and
technical terms. They are a finding aid, not a quotable record. The page says so
and links the timestamp so a reader can verify against the video.

Requires: yt-dlp.
"""

import argparse
import html as htmlmod
import json
import re
import subprocess
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TS_RE = re.compile(r"^(\d{2}):(\d{2}):(\d{2})\.\d{3}\s+-->")
TAG_RE = re.compile(r"<[^>]+>")


def esc(s):
    return htmlmod.escape(str(s), quote=True)


def vtt_to_paragraphs(vtt: str, chunk_seconds=120):
    """VTT -> [(mm:ss, text)] merged into readable chunks.

    Auto-caption VTT repeats each line as it rolls, so naive concatenation
    triples the text. Dedupe against the previous line as we go.
    """
    cues, cur_t, buf, last = [], None, [], ""
    for line in vtt.splitlines():
        m = TS_RE.match(line.strip())
        if m:
            h, mi, s = (int(x) for x in m.groups())
            cur_t = h * 3600 + mi * 60 + s
            continue
        t = TAG_RE.sub("", line).strip()
        if not t or t.startswith(("WEBVTT", "Kind:", "Language:")) or t == last:
            continue
        last = t
        if cur_t is not None:
            buf.append((cur_t, t))

    out, start, words = [], None, []
    for t, txt in buf:
        if start is None:
            start = t
        words.append(txt)
        if t - start >= chunk_seconds:
            out.append((start, " ".join(words)))
            start, words = None, []
    if words:
        out.append((start or 0, " ".join(words)))
    return out


def fetch_captions(video_id, tmp):
    url = f"https://www.youtube.com/watch?v={video_id}"
    subprocess.run(
        ["yt-dlp", "--skip-download", "--write-auto-sub", "--write-sub",
         "--sub-lang", "en.*", "--sub-format", "vtt", "--ignore-errors",
         "-o", str(Path(tmp) / "c.%(ext)s"), url],
        capture_output=True, text=True, timeout=300)
    for cand in sorted(Path(tmp).glob("c*.vtt")):
        try:
            return cand.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return None


PAGE = """<!--meta
out: transcripts/{vid}.html
nav: /video-archive.html
requires: meetings
title: {title}
description: Searchable transcript of {body} on {pretty}, {city}, {state}.
-->

<section class="hero">
  <div class="wrap">
    <span class="eyebrow">Transcript &middot; {pretty}</span>
    <h1>{title}</h1>
    <p class="lede">
      Auto-caption transcript of the City's own recording, {mins} minutes long,
      broken into timestamped sections so you can jump to the moment in the video.
    </p>
    <div class="hero-btns">
      <a class="btn btn-red" href="https://www.youtube.com/watch?v={vid}" rel="noopener">Watch the meeting &rarr;</a>
      {agenda_btn}
      <a class="btn btn-ghost" href="/video-archive.html">All recordings</a>
    </div>
  </div>
</section>

<section>
  <div class="wrap narrow">
    <div class="callout gold">
      <span class="co-label">Read this before quoting anything below</span>
      <p class="mb0">
        This is a <strong>machine transcript</strong>, produced by YouTube's automatic
        captioning of the City's recording. It mis-hears names, dollar figures, street
        names and legal terms, and it does not identify speakers. Treat it as a way to
        <em>find</em> the moment, then click the timestamp and verify against the video
        before you rely on a single word of it.
      </p>
    </div>
{body_html}
    <p class="src">Captured {captured} &middot; source:
      <a href="https://www.youtube.com/watch?v={vid}" rel="noopener">youtube.com/watch?v={vid}</a>
    </p>
  </div>
</section>
"""


def build(chapter, limit=0, quiet=False):
    cfg = json.loads((ROOT / "chapters" / f"{chapter}.json").read_text(encoding="utf-8"))
    src = Path(cfg.get("source_dir") or (ROOT.parent / f"expose{chapter}"))
    src = src if src.is_absolute() else (ROOT / src).resolve()
    vpath = src / "site" / "data" / "videos.json"
    if not vpath.exists():
        sys.exit("run ingest_videos.py first")
    vdata = json.loads(vpath.read_text(encoding="utf-8"))
    vids = vdata["videos"]
    if limit:
        vids = vids[:limit]

    mpath = src / "site" / "data" / "meetings.json"
    by_date = {}
    if mpath.exists():
        for m in json.loads(mpath.read_text(encoding="utf-8"))["meetings"]:
            by_date.setdefault(m["date"], m)

    pages_dir = src / "src" / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    body = cfg.get("video", {}).get("body", "meeting")

    done = skipped = failed = 0
    for x in vids:
        frag = pages_dir / f"67-transcript-{x['id']}.html"
        if frag.exists():
            skipped += 1
            continue
        with tempfile.TemporaryDirectory() as td:
            vtt = fetch_captions(x["id"], td)
        if not vtt:
            failed += 1
            continue
        paras = vtt_to_paragraphs(vtt)
        if len(paras) < 2:
            failed += 1
            continue

        chunks = []
        for secs, text in paras:
            stamp = f"{secs // 3600}:{(secs % 3600) // 60:02d}:{secs % 60:02d}"
            chunks.append(
                f'    <p><a class="mono" href="https://www.youtube.com/watch?v={x["id"]}&t={secs}s"'
                f' rel="noopener">[{stamp}]</a> {esc(text)}</p>')

        d = x["date"]
        pretty = "undated" if d == "1970-01-01" else d
        m = by_date.get(d)
        agenda_btn = (f'<a class="btn btn-ghost" href="/meetings/{esc(m["slug"])}.html">Agenda for this meeting</a>'
                      if m else "")
        frag.write_text(PAGE.format(
            vid=esc(x["id"]), title=esc(x["title"][:110]), body=esc(body),
            city=esc(cfg["city"]), state=esc(cfg["state"]), pretty=esc(pretty),
            mins=int(x["duration"] / 60) if x["duration"] else 0,
            agenda_btn=agenda_btn, captured=date.today().isoformat(),
            body_html="\n".join(chunks)[:400000],
        ), encoding="utf-8")
        x["transcript"] = True
        done += 1
        if not quiet and done % 25 == 0:
            print(f"    {done} transcripts…", flush=True)

    vdata["transcripts_generated_at"] = datetime.now().isoformat()
    vpath.write_text(json.dumps(vdata, indent=1), encoding="utf-8")
    if not quiet:
        print(f"  transcripts: {done} new, {skipped} already had one, {failed} unavailable")
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chapter")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    build(a.chapter, a.limit, a.quiet)


if __name__ == "__main__":
    main()
