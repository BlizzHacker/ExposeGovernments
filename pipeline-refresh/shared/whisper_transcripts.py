#!/usr/bin/env python3
"""
Transcribe meeting videos that YouTube never captioned.

    python3 shared/whisper_transcripts.py sanangelo

Most city meetings get auto-captions and `ingest_transcripts.py` fetches those in
about a second each. A minority never do — older uploads, live streams that ended
badly, anything YouTube's ASR declined. For San Angelo that is 48 recordings and
137 hours, including a 406-minute budget workshop.

This is the expensive path, so it is deliberately the *fallback*: it only touches
videos with no transcript page already on disk. Audio is downloaded, transcribed
with faster-whisper on CPU, then deleted — we never keep the media.

Ordered by recency, because a 2026 budget workshop matters more than a 2019
special meeting and the job may be interrupted.

Requires: yt-dlp, ffmpeg, faster-whisper.
"""

import argparse
import html as htmlmod
import json
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def esc(s):
    return htmlmod.escape(str(s), quote=True)


PAGE = """<!--meta
out: transcripts/{vid}.html
nav: /video-archive.html
requires: meetings
title: {title}
description: Machine transcript of {body} on {pretty}, {city}, {state}.
-->

<section class="hero">
  <div class="wrap">
    <span class="eyebrow">Transcript &middot; {pretty}</span>
    <h1>{title}</h1>
    <p class="lede">
      {mins} minutes, transcribed from the City's recording. YouTube never captioned
      this meeting, so this text exists only here.
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
        This is a <strong>machine transcript</strong>, produced by speech recognition
        rather than a human. It mis-hears names, dollar figures, street names and legal
        terms, and it does not identify speakers. Use it to <em>find</em> the moment,
        then click the timestamp and verify against the video before relying on a word
        of it.
      </p>
    </div>
{body_html}
    <p class="src">
      Transcribed {captured} with faster-whisper ({model}) &middot; source:
      <a href="https://www.youtube.com/watch?v={vid}" rel="noopener">youtube.com/watch?v={vid}</a>
    </p>
  </div>
</section>
"""


def get_audio(video_id, tmp):
    """16 kHz mono wav — what the model wants, and the smallest useful form."""
    out = Path(tmp) / "a.wav"
    r = subprocess.run(
        ["yt-dlp", "-f", "bestaudio/best", "--no-playlist", "-o", "-",
         "--quiet", f"https://www.youtube.com/watch?v={video_id}"],
        capture_output=True, timeout=3600)
    if not r.stdout:
        return None
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
         "-ac", "1", "-ar", "16000", "-f", "wav", str(out)],
        input=r.stdout, capture_output=True, timeout=3600)
    return out if out.exists() and out.stat().st_size > 1000 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chapter")
    ap.add_argument("--model", default="base.en")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-minutes", type=int, default=0,
                    help="skip recordings longer than this")
    a = ap.parse_args()

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("pip install faster-whisper")

    cfg = json.loads((ROOT / "chapters" / f"{a.chapter}.json").read_text(encoding="utf-8"))
    src = Path(cfg.get("source_dir") or (ROOT.parent / f"expose{a.chapter}"))
    src = src if src.is_absolute() else (ROOT / src).resolve()
    pages_dir = src / "src" / "pages"
    vdata = json.loads((src / "site" / "data" / "videos.json").read_text(encoding="utf-8"))

    mpath = src / "site" / "data" / "meetings.json"
    by_date = {}
    if mpath.exists():
        for m in json.loads(mpath.read_text(encoding="utf-8"))["meetings"]:
            by_date.setdefault(m["date"], m)

    todo = [v for v in vdata["videos"]
            if not (pages_dir / f"67-transcript-{v['id']}.html").exists()]
    if a.max_minutes:
        todo = [v for v in todo if v["duration"] <= a.max_minutes * 60]
    todo.sort(key=lambda v: v["date"], reverse=True)
    if a.limit:
        todo = todo[:a.limit]

    hours = sum(v["duration"] for v in todo) / 3600
    print(f"  {len(todo)} recordings without a transcript, {hours:.0f} hours", flush=True)

    # int8 on CPU: roughly 6-10x realtime on 16 cores, and the accuracy loss is
    # invisible next to the errors council-chamber audio produces anyway.
    model = WhisperModel(a.model, device="cpu", compute_type="int8", cpu_threads=0)
    body = cfg.get("video", {}).get("body", "meeting")
    done = failed = 0

    for v in todo:
        t0 = time.time()
        try:
            with tempfile.TemporaryDirectory() as td:
                wav = get_audio(v["id"], td)
                if not wav:
                    failed += 1
                    print(f"    {v['id']}: no audio", flush=True)
                    continue
                segs, _ = model.transcribe(
                    str(wav), language="en", vad_filter=True,
                    condition_on_previous_text=False)

                chunks, start, words = [], None, []
                for s in segs:
                    if start is None:
                        start = int(s.start)
                    words.append(s.text.strip())
                    if s.end - start >= 120:
                        chunks.append((start, " ".join(words)))
                        start, words = None, []
                if words:
                    chunks.append((start or 0, " ".join(words)))
        except Exception as exc:                      # noqa: BLE001
            failed += 1
            print(f"    {v['id']}: {type(exc).__name__} {exc}", flush=True)
            continue

        if not chunks:
            failed += 1
            continue

        html = []
        for secs, text in chunks:
            stamp = f"{secs // 3600}:{(secs % 3600) // 60:02d}:{secs % 60:02d}"
            html.append(
                f'    <p><a class="mono" href="https://www.youtube.com/watch?v={v["id"]}&t={secs}s"'
                f' rel="noopener">[{stamp}]</a> {esc(text)}</p>')

        d = v["date"]
        pretty = "undated" if d == "1970-01-01" else d
        m = by_date.get(d)
        agenda_btn = (f'<a class="btn btn-ghost" href="/meetings/{esc(m["slug"])}.html">Agenda for this meeting</a>'
                      if m else "")
        (pages_dir / f"67-transcript-{v['id']}.html").write_text(PAGE.format(
            vid=esc(v["id"]), title=esc(v["title"][:110]), body=esc(body),
            city=esc(cfg["city"]), state=esc(cfg["state"]), pretty=esc(pretty),
            mins=int(v["duration"] / 60) if v["duration"] else 0,
            agenda_btn=agenda_btn, captured=date.today().isoformat(),
            model=esc(a.model), body_html="\n".join(html)[:400000],
        ), encoding="utf-8")
        done += 1
        mins = int(v["duration"] / 60)
        print(f"    {v['date']} {mins:>4}min -> {len(chunks)} sections "
              f"in {(time.time() - t0) / 60:.1f}min  [{done}/{len(todo)}]", flush=True)

    print(f"  whisper: {done} transcribed, {failed} failed", flush=True)


if __name__ == "__main__":
    main()
