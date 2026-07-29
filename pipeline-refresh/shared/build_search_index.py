#!/usr/bin/env python3
"""
Build a chapter's site search index.

    python shared/build_search_index.py mississippi

Walks the chapter's built site, extracts visible text from every page, and writes
`data/site-search-index.json` in exactly the shape ExposeMiamiOK already produces:

    {"generated_at": ISO8601, "record_count": N,
     "records": [{"title","url","category","source","summary","text"}, ...]}

Matching that shape on purpose — Miami OK's existing search.html consumes it
unchanged, so the same page works across every chapter and Miami OK can move onto
the shared implementation without its index being regenerated.

Run it after build.py and before deploying. The chapter's own build.py shim calls
it automatically.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Chunks that are navigation, not content. Indexing them makes every page match
# every query — the chapter bar alone would put "Move Weight Foundation" in all
# 800 records.
STRIP_BLOCKS = [
    re.compile(r"<script\b.*?</script>", re.S | re.I),
    re.compile(r"<style\b.*?</style>", re.S | re.I),
    re.compile(r"<header\b.*?</header>", re.S | re.I),
    re.compile(r"<footer\b.*?</footer>", re.S | re.I),
    re.compile(r'<div class="chapterbar".*?</div>\s*</div>\s*</div>', re.S | re.I),
    re.compile(r'<div class="donate-banner".*?</div>', re.S | re.I),
    re.compile(r'<nav\b.*?</nav>', re.S | re.I),
]

TAG_RE = re.compile(r"<[^>]+>")
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S | re.I)
DESC_RE = re.compile(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']', re.S | re.I)

ENTITIES = {
    "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'",
    "&mdash;": "—", "&ndash;": "–", "&rarr;": "→", "&darr;": "↓", "&middot;": "·",
    "&ldquo;": "“", "&rdquo;": "”", "&rsquo;": "’", "&nbsp;": " ",
    "&sect;": "§", "&hellip;": "…", "&times;": "×", "&check;": "✓",
}


def detag(html: str) -> str:
    for rx in STRIP_BLOCKS:
        html = rx.sub(" ", html)
    text = TAG_RE.sub(" ", html)
    for ent, ch in ENTITIES.items():
        text = text.replace(ent, ch)
    text = re.sub(r"&#\d+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def categorise(rel: str) -> str:
    """A human-facing bucket, used for the filter buttons on the search page."""
    if rel == "index.html":
        return "Home"
    first = rel.split("/")[0]
    return {
        "documents": "Documents",
        "records": "Open Records",
        "meetings": "Meetings",
        "transcripts": "Transcripts",
        "agenda-packets": "Agenda Packets",
        "resources": "City Resources",
        "blog": "Blog",
    }.get(first, "Site page")


def url_for(rel: str) -> str:
    if rel == "index.html":
        return "/"
    if rel.endswith("/index.html"):
        return "/" + rel[: -len("index.html")]
    return "/" + rel


def build(chapter_key: str, site_dir=None, quiet=False):
    cfg_path = ROOT / "chapters" / f"{chapter_key}.json"
    if not cfg_path.exists():
        sys.exit(f"no chapter config '{chapter_key}'")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    site = Path(site_dir) if site_dir else \
        Path(cfg.get("source_dir") or (ROOT.parent / f"expose{chapter_key}")) / "site"
    site = site if site.is_absolute() else (ROOT / site).resolve()
    if not site.is_dir():
        sys.exit(f"no built site at {site} — run build.py first")

    records = []
    for page in sorted(site.rglob("*.html")):
        rel = page.relative_to(site).as_posix()
        html = page.read_text(encoding="utf-8", errors="replace")

        m = H1_RE.search(html) or TITLE_RE.search(html)
        title = detag(m.group(1)) if m else rel
        title = title.split(" | ")[0].strip() or rel

        d = DESC_RE.search(html)
        text = detag(html)
        summary = detag(d.group(1)) if d else text[:300]

        if len(text) < 40:          # nav-only or placeholder page
            continue

        records.append({
            "title": title,
            "url": url_for(rel),
            "category": categorise(rel),
            "source": cfg["site_name"],
            "summary": summary[:400],
            # Transcripts run to 60k+ chars each; at 400 records that is a
            # multi-megabyte download before the first keystroke. Cap them
            # harder than ordinary pages — enough to match and snippet.
            "text": text[:6000] if rel.startswith("transcripts/") else text[:20000],
        })

    out = site / "data"
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "records": records,
    }
    dest = out / "site-search-index.json"
    dest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    if not quiet:
        size = dest.stat().st_size / 1024
        cats = {}
        for r in records:
            cats[r["category"]] = cats.get(r["category"], 0) + 1
        print(f"  search index: {len(records)} records, {size:.0f} KB -> {dest}")
        for c, n in sorted(cats.items(), key=lambda x: -x[1]):
            print(f"    {n:5d}  {c}")
    return len(records)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chapter")
    ap.add_argument("--site", help="built site dir (default: <chapter>/site)")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    build(a.chapter, a.site, a.quiet)


if __name__ == "__main__":
    main()
