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

# Chapters, grouped by state, in a fixed order so the chapter bar reads identically
# on every page of every site. Three chapters fitted in one flat strip; fourteen do
# not, and a bar that lists Abilene next to Olive Branch tells a Texan nothing. So
# the bar now shows the reader's own state expanded and the other two as hubs.
#
# Order within a state is deliberate: the chapter that broke the story first comes
# first, then the rest by size. It is not alphabetical — Miami, Oklahoma is a town
# of 13,000 and it leads Oklahoma because it earned it.
STATE_ORDER = ["oklahoma", "texas", "mississippi"]
CHAPTER_ORDER = {
    "oklahoma": ["miamiok", "okc", "tulsa", "claremore"],
    "texas": ["sanangelo", "houston", "dallas", "austin", "sanantonio",
              "lubbock", "abilene"],
    "mississippi": ["mississippi", "jackson", "olivebranch"],
}
STATE_HUB = {
    "oklahoma": ("Oklahoma", "exposeoklahoma.com"),
    "texas": ("Texas", "exposetexas.org"),
    "mississippi": ("Mississippi", "exposemississippi.com"),
}

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
def state_key(cfg):
    """Which state a chapter belongs to.

    Chapters generated from research carry `state_key`. The three that predate
    the state domains do not, so they are located by membership in CHAPTER_ORDER
    rather than by guessing from the state name — Mississippi's chapter key is
    literally "mississippi" and inferring from that would work by luck.
    """
    if cfg.get("state_key"):
        return cfg["state_key"]
    for st, keys in CHAPTER_ORDER.items():
        if cfg["key"] in keys:
            return st
    sys.exit(f"chapter '{cfg['key']}' is in no state: add it to CHAPTER_ORDER in build.py")


def chapter_host(cfg):
    """Where this chapter actually lives now.

    The three original chapters still carry their retired domain in `domain`
    (exposesanangelo.com), which 301s to the state subdomain. Linking a reader
    through a redirect on every page of every sibling site is sloppy, so the bar
    always uses canonical_host.
    """
    return cfg.get("canonical_host") or cfg["domain"]


BAR_VERSION = "3"


def chapter_bar(cfg):
    """The universal bar that sits above every chapter's own header.

    Three incompatible versions of this were live at once, which is what a
    "universal" element becomes the moment it is maintained by hand in more than
    one place:

      * the three founding chapters carried state links pointing at
        `<statedomain>/state.html` - every one of which 404'd, because the hub
        moved to the apex index;
      * the eleven newer chapters listed every city in the reader's state as a
        pill, which is fine for Mississippi's three and a wall for Texas's seven;
      * Miami's injector had its own hardcoded copy naming the retired domains,
        and only ever inserted a bar when none was present, so it could never
        correct one.

    This version is a disclosure: brand on the left, where-you-are in the middle,
    and every chapter one click away inside a panel. It is a fixed height whatever
    the chapter count, which is the property the pill row did not have - the
    Foundation intends to cover fifty states and the bar has to survive that.

    <details> does the open/close natively, so it works with JavaScript off and
    is keyboard-operable for free.
    """
    st = state_key(cfg)
    groups = []
    for other_st in STATE_ORDER:
        label, dom = STATE_HUB[other_st]
        keys = CHAPTER_ORDER[other_st]
        links = []
        for key in keys:
            other = load_chapter(key)
            cur = ' class="cur" aria-current="page"' if other["key"] == cfg["key"] else ""
            links.append(f'<a href="https://{chapter_host(other)}"{cur}>'
                         f'{other["city"]}</a>')
        # Built outside the f-string: a backslash inside an f-string expression
        # is legal from Python 3.12 (PEP 701) and a SyntaxError on 3.11, which is
        # what the Proxmox node runs. It built here and failed every rebuild
        # there.
        hi = ' class="cb-hi"' if other_st == st else ""
        groups.append(
            f'          <section{hi}>\n'
            f'            <a class="cb-state" href="https://{dom}">{label}'
            f'<span class="cb-n">{len(keys)}</span></a>\n            '
            + "\n            ".join(links)
            + "\n          </section>")

    total = sum(len(v) for v in CHAPTER_ORDER.values())
    return (
        f'<div class="chapterbar" data-mw-chapterbar data-mw-bar="{BAR_VERSION}">\n'
        '  <div class="chapterbar-in">\n'
        '    <a class="cb-brand" href="https://foundation.moveweight.com">'
        '<span class="cb-mark" aria-hidden="true">MW</span>'
        '<span class="cb-brand-t">A chapter of the '
        '<strong>Move Weight Foundation</strong></span></a>\n'
        '    <details class="cb-picker">\n'
        '      <summary aria-label="Choose a chapter">'
        f'<span class="cb-here">{cfg["chapter_label"]}</span>'
        f'<span class="cb-of">of {total}</span>'
        '<span class="cb-chev" aria-hidden="true"></span></summary>\n'
        '      <div class="cb-panel" role="group" aria-label="Foundation chapters">\n'
        '        <div class="cb-cols">\n'
        + "\n".join(groups)
        + "\n        </div>\n"
        '        <a class="cb-all" href="https://foundation.moveweight.com/#chapter-directory">'
        f'All {total} chapters and the map &rarr;</a>\n'
        '      </div>\n    </details>\n  </div>\n</div>'
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


# ─── derived blocks ────────────────────────────────────────────────────
# Shared fragments interpolate {{links_html}} and friends. These are computed at
# build time rather than baked into chapters/*.json on purpose: the config should
# hold facts (a URL, a label, a note), and an edit to a fact should show up on the
# next build without anyone remembering to re-run a scaffolder.

VENDOR_LABEL = {
    "primegov": "PrimeGov", "legistar": "Legistar", "civicclerk": "CivicClerk",
    "civicplus": "CivicPlus AgendaCenter", "novus": "NovusAgenda",
    "granicus": "Granicus", "wordpress": "the city's own site",
}

SECTION_ID = {
    "City government": "city", "Records & transparency": "records",
    "County & state": "county", "Meetings & video": "meetings",
}


def _sec_id(heading):
    return SECTION_ID.get(heading, re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-"))


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def links_html(cfg):
    """The City Desk body: one card grid per section of verified links."""
    out = []
    for heading, items in cfg.get("links", {}).items():
        rows = []
        for it in items:
            note = (f'<p class="dim mb0">{it["note"]}</p>') if it.get("note") else ""
            rows.append(
                '<div class="card">\n'
                f'        <h3><a href="{esc(it["url"])}" rel="noopener">{it["label"]}</a></h3>\n'
                f'        {note}\n'
                f'        <p class="mono dim small mb0">{esc(it["url"])}</p>\n'
                "      </div>")
        out.append(
            f'<section id="{_sec_id(heading)}">\n  <div class="wrap">\n'
            f'    <div class="section-head"><h2>{heading}</h2></div>\n'
            '    <div class="cards">\n      ' + "\n      ".join(rows)
            + "\n    </div>\n  </div>\n</section>")
    return "\n\n".join(out)


def links_nav_html(cfg):
    return " ".join(
        f'<a href="#{_sec_id(h)}">{h}</a>' for h in cfg.get("links", {}))


def oversight_html(cfg):
    rows = []
    for o in cfg.get("oversight", []):
        note = f'<p class="dim mb0">{o["note"]}</p>' if o.get("note") else ""
        rows.append('<div class="card">\n'
                    f'        <h3><a href="{esc(o["url"])}" rel="noopener">{o["label"]}</a></h3>\n'
                    f'        {note}\n      </div>')
    return "\n      ".join(rows)


def news_html(cfg):
    """Local and statewide outlets, link-out only.

    The Foundation never republishes a newsroom's work. Half the reason this
    section exists is to send readers to the people who already do the daily
    coverage, so that the chapter can spend its effort on the records nobody
    has asked for yet.
    """
    rows = []
    for n in cfg.get("news", []):
        note = f'<p class="dim mb0">{n["note"]}</p>' if n.get("note") else ""
        rows.append('<div class="card">\n'
                    f'        <h3><a href="{esc(n["url"])}" rel="noopener">{n["name"]}</a></h3>\n'
                    f'        {note}\n      </div>')
    return "\n      ".join(rows)


def link_count(cfg):
    return sum(len(v) for v in cfg.get("links", {}).values()) + len(cfg.get("oversight", []))


def derive(cfg):
    """Add computed values so fragments can reference them as placeholders."""
    cfg = dict(cfg)
    st = state_key(cfg)
    cfg["state_key"] = st
    cfg["state_domain"] = STATE_HUB[st][1]
    cfg["state_hub_label"] = STATE_HUB[st][0]
    cfg["chapter_count"] = len(CHAPTER_ORDER[st])
    cfg["links_html"] = links_html(cfg)
    cfg["links_nav_html"] = links_nav_html(cfg)
    cfg["oversight_html"] = oversight_html(cfg)
    cfg["news_html"] = news_html(cfg)
    cfg["link_count"] = link_count(cfg)
    portal = cfg.get("portal", {})
    cfg["portal_url"] = portal.get("portal_url", "")
    cfg["portal_vendor"] = VENDOR_LABEL.get(portal.get("vendor", ""), portal.get("vendor", ""))
    cfg.setdefault("sources_verified", "")
    addr = cfg.get("submit_email") or ""
    if "@" in addr:
        cfg["submit_user"], cfg["submit_host"] = addr.split("@", 1)
    # The appeal remedy differs enough between states that templating it inline in
    # five fragments would guarantee one of them drifts. It is authored per state
    # in STATUTES rather than assembled here — see the note on `appeal.sentence`.
    ap = cfg["statute"]["appeal"]
    cfg["appeal_sentence"] = ap.get("sentence") or (
        f"A denial appeals to the {ap['body']} ({ap.get('citation', '')}).")
    return cfg


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
    src = cfg.get("source_dir")
    chapter_dir = (ROOT / src).resolve() if src else (ROOT.parent / f"expose{key}")
    out = Path(out_dir) if out_dir else chapter_dir / "site"

    if not SHELL.exists():
        sys.exit(f"missing shell template at {SHELL}")
    shell = SHELL.read_text(encoding="utf-8")

    out.mkdir(parents=True, exist_ok=True)
    bar = chapter_bar(cfg)
    cfg = derive(cfg)
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
        # `title_suffix` carries the city as well as the brand ("Houston |
        # ExposeTexas"). Without it every city on a state domain would ship the
        # identical title on its City Desk page and compete with its own siblings
        # in search. Chapters that predate the state domains fall back to
        # site_name and keep the titles they already have indexed.
        suffix = cfg.get("title_suffix") or cfg["site_name"]
        full_title = title if meta.get("bare_title") == "true" else f"{title} | {suffix}"
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
            # The shell hardcoded ".com", which put "ExposeSanAngelo.com" in the
            # masthead of a page served from sanangelo.exposetexas.org — the one
            # domain we had just retired.
            logo_tld=cfg["logo"].get("tld", ".com"),
            city_badge=f'<span class="city-badge">{cfg["city"]}</span>',
            nav=nav_html(cfg, nav_key),
            donate_banner="" if meta.get("no_banner") == "true" else cfg["donate_banner"],
            content=content.rstrip(),
            footer_cols=footer_html(cfg),
            footer_disclaimer=cfg["footer_disclaimer"],
            extra_head=meta.get("extra_head", ""),
            extra_body=meta.get("extra_body", ""),
        )
        html = substitute(html, cfg)

        dest = out / out_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html, encoding="utf-8")
        built.append(f"{frag.name:32s} -> {out_rel}")

    # Nav and footer come from the config; the pages come from feature-gated
    # fragments. Nothing checked that the two agreed, so a link to a page the
    # build had skipped shipped as a 404 in the navigation of every page -
    # "The Question" on both founding chapters, "/documents/" in eleven footers.
    produced = {("/" + p.relative_to(out).as_posix()).replace("/index.html", "/")
                for p in out.rglob("*.html")}
    produced.add("/")
    wanted = [e["href"] for e in cfg.get("nav", [])]
    wanted += [l["href"] for col in cfg.get("footer", []) for l in col["links"]]
    # Miami OK, San Angelo and Southaven each generate a few pages with their own
    # scripts - video-archive.html, accountability.html. Those pages exist and
    # serve; this build is simply not what makes them, so they are declared in
    # the config rather than being reported as broken every run.
    produced |= set(cfg.get("external_pages", []))
    dangling = sorted({h.split("#")[0] for h in wanted
                       if h.startswith("/") and h.split("#")[0] not in produced
                       and h.split("#")[0] != ""})
    if dangling and not quiet:
        for h in dangling:
            print(f"  ! nav/footer links {h} but this build did not produce it")

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
        css = theme_src.read_text(encoding="utf-8")
        # The chapter bar's styles live in their own file because Miami OK keeps
        # a separate hand-maintained stylesheet and needs the identical rules
        # appended to it. One file, two destinations, no drift.
        bar_css = ROOT / "shared" / "chapterbar.css"
        if bar_css.exists():
            css += "\n" + bar_css.read_text(encoding="utf-8")
        css = substitute(css, cfg)
        (out / "assets").mkdir(exist_ok=True)
        (out / "assets" / "theme.css").write_text(css, encoding="utf-8")

    # Shared assets get the same placeholder substitution as pages. letter.js
    # carries the statute text, and a Texan reading a Mississippi deadline is
    # exactly the failure this whole template exists to prevent.
    assets_src = ROOT / "shared" / "assets"
    if assets_src.is_dir():
        (out / "assets").mkdir(exist_ok=True)
        for a in sorted(assets_src.iterdir()):
            if not a.is_file():
                continue
            if a.suffix in (".js", ".css", ".svg", ".json", ".txt"):
                (out / "assets" / a.name).write_text(
                    substitute(a.read_text(encoding="utf-8"), cfg), encoding="utf-8")
            else:
                (out / "assets" / a.name).write_bytes(a.read_bytes())
        # The shell references /favicon.svg at the site ROOT, not under assets,
        # so a copy goes there too. Fourteen chapters served a 404 on it from
        # every page because the file had never existed.
        fav = assets_src / "favicon.svg"
        if fav.exists():
            (out / "favicon.svg").write_text(
                substitute(fav.read_text(encoding="utf-8"), cfg), encoding="utf-8")

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
