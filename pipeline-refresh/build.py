#!/usr/bin/env python3
"""
Expose chapter builder — one build system for every Move Weight Foundation chapter.

    python build.py mississippi
    python build.py sanangelo --out ../exposesanangelo/site
    python build.py --list

Reads chapters/<key>.json, assembles page fragments, and writes a complete static
site. Fragments come from two places and the chapter's own always wins:

    shared/pages/*.html          every chapter gets these
    <chapter_dir>/src/pages/*.html   chapter-specific, overrides by filename

Placeholders — {{city}}, {{statute.citation}}, {{accent}} — are substituted from the
chapter config using dotted paths, so a shared fragment can say "seven (7) working
days" in Mississippi and "ten (10) business days" in Texas without a fork.

Feature gating: a fragment whose meta block declares `requires: meetings` is skipped
unless that feature is true in the chapter config. That is how one template serves a
chapter with 522 archived meetings and a chapter that launched yesterday.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CHAPTERS = ROOT / "chapters"
SHARED_PAGES = ROOT / "shared" / "pages"

# Every chapter, in a fixed order, so the chapter bar reads identically everywhere.
CHAPTER_ORDER = ["miamiok", "sanangelo", "mississippi"]

PLACEHOLDER_RE = re.compile(r"\{\{([a-zA-Z0-9_.]+)\}\}")
META_RE = re.compile(r"\s*<!--meta\s*(.*?)-->\s*", re.S)


# ─── config ────────────────────────────────────────────────────────────
def load_chapter(key):
    p = CHAPTERS / f"{key}.json"
    if not p.exists():
        avail = ", ".join(sorted(c.stem for c in CHAPTERS.glob("*.json")
                                 if not c.stem.startswith("_")))
        sys.exit(f"no chapter config '{key}'. Available: {avail}")
    return json.loads(p.read_text(encoding="utf-8"))


def dotted(cfg, path):
    cur = cfg
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def substitute(text, cfg):
    def repl(m):
        val = dotted(cfg, m.group(1))
        if val is None:
            # Leave it visible rather than silently emitting an empty string —
            # a stray {{placeholder}} in a page is a bug you want to see.
            return m.group(0)
        return str(val)
    return PLACEHOLDER_RE.sub(repl, text)


# ─── chapter bar ───────────────────────────────────────────────────────
GENERATED_BARS = Path('/opt/expose-template/generated/chapterbars')


def chapter_bar(cfg):
    # Prefer the bar the Foundation pipeline generates for every chapter.
    #
    # This checkout knows about three chapters and used to render its own
    # three-state bar. Because it runs twice a day and the fourteen-chapter
    # pipeline runs weekly, it quietly overwrote San Angelo and Southaven with a
    # stale nav every twelve hours - the "universal" bar was universal on twelve
    # of fourteen sites. One generated file is now the single source of truth;
    # the local builder below stays only as a fallback if that file is missing.
    gen = GENERATED_BARS / f"{cfg['key']}.html"
    if gen.is_file():
        return gen.read_text(encoding='utf-8').rstrip()

    links = []
    for key in CHAPTER_ORDER:
        other = load_chapter(key)
        cur = ' class="cur" aria-current="true"' if other["key"] == cfg["key"] else ""
        # The bar lists STATES, not cities. Chapters are organised by state
        # domain now, so a visitor in Tulsa should see "Oklahoma" and land on
        # the state hub, not be sent to whichever city happens to exist today.
        links.append(
            f'<a href="https://{other["domain"]}/state.html"{cur}>'
            f'{other["state"]}<span class="cb-city"> &middot; {other["city"]}</span></a>')
    return (
        '<div class="chapterbar" data-mw-chapterbar>\n'
        '  <div class="chapterbar-in">\n'
        '    <span class="cb-label">A chapter of the '
        '<a href="https://foundation.moveweight.com">Move Weight Foundation</a></span>\n'
        '    <nav class="cb-links" aria-label="Foundation chapters">\n      '
        + "\n      ".join(links)
        + "\n    </nav>\n  </div>\n</div>"
    )


# ─── fragments ─────────────────────────────────────────────────────────
def parse_meta(text, source):
    m = META_RE.match(text)
    if not m:
        raise ValueError(f"{source}: fragment is missing its <!--meta --> block")
    meta = {}
    for line in m.group(1).strip().splitlines():
        line = line.strip()
        if line and ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, text[m.end():]


def _out_path(src):
    """The `out:` this fragment writes to — the real identity of a page."""
    try:
        meta, _ = parse_meta(src.read_text(encoding="utf-8"), src.name)
        return meta.get("out", src.name)
    except (ValueError, OSError):
        return src.name


def collect_fragments(cfg, chapter_dir):
    """Shared fragments, overridden by chapter fragments writing the same page.

    Keyed on the `out:` target rather than the filename: a chapter's
    80-tips.html must override shared/90-tips.html because both produce
    tips.html. Keying on filename let both through and the last one silently
    won, which is how you ship the wrong tips page.
    """
    frags = {}
    for src in sorted(SHARED_PAGES.glob("*.html")):
        frags[_out_path(src)] = src
    local = chapter_dir / "src" / "pages"
    if local.is_dir():
        for src in sorted(local.glob("*.html")):
            frags[_out_path(src)] = src
    return [frags[k] for k in sorted(frags)]


def nav_html(cfg, current):
    out = []
    for entry in cfg["nav"]:
        href, label = entry["href"], entry["label"]
        cls = ' class="nav-cta"' if entry.get("cta") else ""
        cur = ' aria-current="page"' if href == current else ""
        out.append(f'<a href="{href}"{cls}{cur}>{label}</a>')
    return "\n        ".join(out)


def footer_html(cfg):
    cols = []
    for col in cfg["footer"]:
        items = "\n          ".join(
            f'<a href="{l["href"]}">{l["label"]}</a>' for l in col["links"])
        cols.append(f'<div class="foot-col">\n          <h4>{col["heading"]}</h4>'
                    f'\n          {items}\n        </div>')
    return "\n        ".join(cols)


SHELL = (ROOT / "shared" / "shell.html")

NL = chr(10)
XML_HEAD = ('<?xml version="1.0" encoding="UTF-8"?>' + NL
            + '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + NL)


def build(key, out_dir=None, quiet=False, force=False):
    cfg = load_chapter(key)

    # Some chapters predate this template and are maintained by their own
    # generators. Building one from shared fragments alone would emit a nearly
    # empty site over an archive that exists nowhere else, so it takes --force
    # and an explicit --out.
    if cfg.get("managed") == "legacy" and not force:
        print(f"  {key}: legacy layout, not built from this template.")
        print(f"  {cfg.get('_note', '')}")
        return 0
    chapter_dir = Path(cfg.get("source_dir") or (ROOT.parent / f"expose{key}"))
    out = Path(out_dir) if out_dir else chapter_dir / "site"

    if not SHELL.exists():
        sys.exit(f"missing shell template at {SHELL}")
    shell = SHELL.read_text(encoding="utf-8")

    out.mkdir(parents=True, exist_ok=True)
    bar = chapter_bar(cfg)
    features = cfg.get("features", {})
    built, skipped = [], []

    for frag in collect_fragments(cfg, chapter_dir):
        raw = frag.read_text(encoding="utf-8")
        meta, content = parse_meta(raw, frag.name)

        need = meta.get("requires")
        if need and not features.get(need):
            skipped.append((frag.name, need))
            continue

        out_rel = meta["out"]
        nav_key = meta.get("nav", "/" + out_rel if out_rel != "index.html" else "/")
        title = meta["title"]
        full_title = title if meta.get("bare_title") == "true" else f"{title} | {cfg['site_name']}"
        canonical = f"https://{cfg['canonical_host']}" + (
            "/" if out_rel == "index.html" else "/" + out_rel)

        html = shell.format(
            title=full_title,
            og_title=title,
            description=meta["description"],
            canonical=canonical,
            site_name=cfg["site_name"],
            canonical_host=cfg["canonical_host"],
            city=cfg["city"],
            state=cfg["state"],
            css_version=cfg.get("css_version", "1"),
            chapter_bar=bar,
            logo_prefix=cfg["logo"]["prefix"],
            logo_body=cfg["logo"]["body"],
            nav=nav_html(cfg, nav_key),
            donate_banner="" if meta.get("no_banner") == "true" else cfg["donate_banner"],
            content=content.rstrip(),
            footer_cols=footer_html(cfg),
            footer_disclaimer=cfg["footer_disclaimer"],
            extra_head=meta.get("extra_head", ""),
            extra_body=meta.get("extra_body", ""),
        )
        html = substitute(html, cfg)

        # A chapter can carry archives produced elsewhere. Writing into one
        # from a template fragment would overwrite data that exists nowhere
        # else, so refuse loudly rather than silently clobber.
        top = out_rel.split("/")[0]
        if top in cfg.get("protect", []):
            raise SystemExit(
                f"REFUSING to write {out_rel}: '{top}' is a protected archive "
                f"directory for chapter {key}. Remove it from `protect` only if "
                f"you are certain the template should own it.")
        dest = out / out_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html, encoding="utf-8")
        built.append(f"{frag.name:32s} -> {out_rel}")

    # ── sitemap + robots ───────────────────────────────────────────────
    # Generated from what was actually built. The old hand-written sitemap
    # listed 10 URLs while the site had grown to several hundred meeting,
    # transcript and video pages — none of which were being indexed.
    from datetime import date as _date
    today = _date.today().isoformat()
    urls = []
    for f in sorted(out.rglob("*.html")):
        rel = f.relative_to(out).as_posix()
        if rel == "index.html":
            loc, prio = "/", "1.0"
        elif rel.endswith("/index.html"):
            loc, prio = "/" + rel[:-len("index.html")], "0.8"
        else:
            loc, prio = "/" + rel, "0.7"
        if rel.startswith(("meetings/", "transcripts/")):
            prio = "0.6"
        urls.append(f'  <url><loc>https://{cfg["canonical_host"]}{loc}</loc>'
                    f"<lastmod>{today}</lastmod><priority>{prio}</priority></url>")
    (out / "sitemap.xml").write_text(
        XML_HEAD + NL.join(urls) + NL + "</urlset>" + NL, encoding="utf-8")
    (out / "robots.txt").write_text(
        "User-agent: *" + NL + "Allow: /" + NL + NL
        + f'Sitemap: https://{cfg["canonical_host"]}/sitemap.xml' + NL,
        encoding="utf-8")
    if not quiet:
        print(f"  sitemap: {len(urls)} urls")

    # stylesheet, recoloured for this chapter
    theme_src = ROOT / "shared" / "theme.css"
    if theme_src.exists():
        css = substitute(theme_src.read_text(encoding="utf-8"), cfg)
        (out / "assets").mkdir(exist_ok=True)
        (out / "assets" / "theme.css").write_text(css, encoding="utf-8")

    if not quiet:
        for line in built:
            print("  " + line)
        for name, need in skipped:
            print(f"  {name:32s} -- skipped (feature '{need}' off)")
        print(f"\n  {len(built)} pages -> {out}")
        if skipped:
            print(f"  {len(skipped)} gated off; enable in chapters/{key}.json")
    return len(built)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chapter", nargs="?", help="chapter key, e.g. mississippi")
    ap.add_argument("--out", help="output directory (default: <chapter>/site)")
    ap.add_argument("--list", action="store_true", help="list chapters and exit")
    ap.add_argument("--all", action="store_true", help="build every chapter")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="build a legacy-managed chapter anyway (requires --out)")
    args = ap.parse_args()

    if args.list or (not args.chapter and not args.all):
        print("Chapters:")
        for c in sorted(CHAPTERS.glob("*.json")):
            if c.stem.startswith("_"):
                continue
            d = json.loads(c.read_text(encoding="utf-8"))
            on = sum(1 for v in d.get("features", {}).values() if v)
            print(f"  {c.stem:14s} {d['site_name']:20s} {d['chapter_label']:16s} "
                  f"{on:2d} features")
        return

    if args.all:
        for c in sorted(CHAPTERS.glob("*.json")):
            if not c.stem.startswith("_"):
                print(f"\n=== {c.stem} ===")
                build(c.stem, quiet=args.quiet)
        return

    if args.force and not args.out:
        sys.exit("--force requires --out; refusing to generate over a legacy chapter in place")
    build(args.chapter, args.out, args.quiet, args.force)


if __name__ == "__main__":
    main()
