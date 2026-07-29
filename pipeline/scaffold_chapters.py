#!/usr/bin/env python3
"""
Generate chapters/<key>.json for every city in research/cities.json.

    python scaffold_chapters.py            # write configs for cities that have none
    python scaffold_chapters.py --force    # regenerate all of them
    python scaffold_chapters.py --only houston dallas

`new_chapter.py` scaffolds ONE chapter interactively and assumes it gets its own
LXC and its own domain. That was right when a chapter meant a whole new site.
It is wrong now: a chapter is a city subdomain on a state domain, served from
the state's container, and eleven of them arrive at once. This script is the
bulk path, and it derives everything it can from verified research rather than
from arguments typed at a prompt.

The division of labour that matters:

    research/cities.json   facts about a real city, every URL fetched and checked
    scaffold_chapters.py   turns facts into configuration
    chapters/<key>.json    generated; safe to hand-edit afterwards, and --force
                           will overwrite you, so put durable edits back in
                           cities.json instead

Regenerating is deliberately non-destructive by default. A chapter's config
accumulates real editorial work — custodians, allies, a rewritten hero — and
losing that to a re-run of a scaffolder would be a bad trade.
"""

import argparse
import json
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

ROOT = Path(__file__).resolve().parent
CHAPTERS = ROOT / "chapters"
RESEARCH = ROOT / "research" / "cities.json"

from new_chapter import STATUTES  # noqa: E402  - single source of truth for statute text

# Public submission addresses on moveweight.net, provisioned by
# shared/deploy/mail_areas.sh. The local part is the CITY, which is not always
# the chapter key - Southaven's chapter key is "mississippi" and Miami's is
# "miamiok". These are printed on a public page for citizens to send documents
# to, so the mapping is explicit rather than derived from the key.
SUBMIT_LOCALPART = {
    "mississippi": "southaven", "jackson": "jackson", "olivebranch": "olivebranch",
    "sanangelo": "sanangelo", "houston": "houston", "dallas": "dallas",
    "austin": "austin", "sanantonio": "sanantonio", "lubbock": "lubbock",
    "abilene": "abilene", "miamiok": "miami", "okc": "okc", "tulsa": "tulsa",
    "claremore": "claremore",
}
SUBMIT_DOMAIN = "moveweight.net"

STATE_ABBR = {"oklahoma": "OK", "texas": "TX", "mississippi": "MS"}
STATE_TITLE = {"oklahoma": "Oklahoma", "texas": "Texas", "mississippi": "Mississippi"}

# Content hash of theme.css + chapterbar.css. Derived, never typed: a stale
# version string leaves every reader on a cached stylesheet, which is how the
# new chapter bar shipped as unstyled markup.
CSS_VERSION = "2f467a71"


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def video_cards(sources):
    """Pre-render the watch page's cards.

    Mississippi's config already carries a `video_html` blob and the shared
    watch fragment interpolates it, so this matches that contract exactly
    rather than introducing a second way to express the same thing.
    """
    out = []
    for s in sources:
        note = f"<br>{esc(s['note'])}" if s.get("note") else ""
        out.append(
            '<div class="card">\n'
            '        <div class="card-ico">&#9654;</div>\n'
            f'        <h3>{esc(s["name"])}</h3>\n'
            f'        <p><span class="dim">{esc(s["org"])}</span>{note}</p>\n'
            f'        <a class="card-link" href="{esc(s["url"])}" rel="noopener">Open &rarr;</a>\n'
            "      </div>")
    return "\n      ".join(out)


def nav_for(features):
    # Every entry is gated on the feature that builds its page. "The Question"
    # was in this unconditional base list while its fragment requires the
    # `the_question` feature, so the two founding chapters carried a nav link to
    # a page that was never built - a 404 in the main nav of every page they
    # serve. Nothing was checking, which is why build() now verifies it.
    nav = [{"href": "/", "label": "Home"}]
    if features.get("city_desk"):
        nav.append({"href": "/city-desk.html", "label": "City Desk"})
    if features.get("the_question"):
        nav.append({"href": "/the-question.html", "label": "The Question"})
    if features.get("officials"):
        nav.append({"href": "/officials.html", "label": "Officials"})
    if features.get("meetings"):
        nav.append({"href": "/meetings/", "label": "Meetings"})
    if features.get("documents"):
        nav.append({"href": "/documents/", "label": "Documents"})
    if features.get("watch"):
        nav.append({"href": "/watch.html", "label": "Watch"})
    if features.get("news"):
        nav.append({"href": "/news.html", "label": "News"})
    if features.get("site_search"):
        nav.append({"href": "/search.html", "label": "Search"})
    nav.append({"href": "/records/", "label": "Open Records", "cta": True})
    return nav


def footer_for(city, county, state_key, domain, appeal_body, features):
    other = [(k, v) for k, v in
             {"oklahoma": "ExposeOklahoma.com", "texas": "ExposeTexas.org",
              "mississippi": "ExposeMississippi.com"}.items() if k != state_key]
    other_domains = {"oklahoma": "exposeoklahoma.com", "texas": "exposetexas.org",
                     "mississippi": "exposemississippi.com"}
    return [
        {"heading": "City Desk", "links": [
            {"href": "/city-desk.html#meetings", "label": "Meetings &amp; How to Speak"},
            {"href": "/city-desk.html#records", "label": "Records &amp; Transparency"},
            {"href": "/city-desk.html#county", "label": f"{esc(county)} Offices"},
            {"href": "/city-desk.html#state", "label": "State Oversight"},
        ]},
        {"heading": "Take Action", "links": [
            {"href": "/records/", "label": "File a Public Records Request"},
            {"href": "/records/#appeal", "label": f"Appeal to the {esc(appeal_body)}"},
            {"href": "/records/#deadline", "label": "Track Your Deadline"},
            {"href": "/tips.html", "label": "Send an Anonymous Tip"},
            {"href": "/tips.html#submit", "label": "Email Us Documents"},
        ]},
        # No unconditional /documents/ here. The document library is off until a
        # chapter has records to put in it, so linking it from every footer put a
        # 404 on all eleven new chapters - found by crawling the live sites, not
        # by reading the template.
        {"heading": "Evidence", "links": ([
            {"href": "/documents/", "label": "Document Library"}]
            if features.get("documents") else []) + [
            {"href": "/the-question.html", "label": f"What We Are Asking {esc(city)}"},
            {"href": "/tips.html#submit", "label": "Send Us a Document"},
            {"href": "/automation.html", "label": "What Is Stale (Automation)"},
            {"href": "/about.html#sources", "label": "How We Source Claims"},
        ]},
        {"heading": "Foundation", "links": [
            {"href": "https://foundation.moveweight.com", "label": "Move Weight Foundation"},
            {"href": f"https://{domain}", "label": f"All {STATE_TITLE[state_key]} chapters"},
        ] + [{"href": f"https://{other_domains[k]}", "label": v} for k, v in other]},
    ]


def build_config(city, state, verified):
    key = city["key"]
    sk = city["state"]
    abbr = STATE_ABBR[sk]
    domain = state["domain"]
    tld = "." + domain.rsplit(".", 1)[1]
    host = f"{city['subdomain']}.{domain}"
    statute = json.loads(json.dumps(STATUTES[abbr]))  # deep copy; never share the dict
    site_name = "Expose" + STATE_TITLE[sk]

    # On day one a chapter ships only what it can fill with verified material:
    # the issue, the link desk, the statute, the video sources, the honest
    # automation dashboard. Everything else stays off.
    #
    # `documents` and `officials` are off deliberately and it is worth being
    # precise about why. Both would be trivial to switch on and both would render
    # a page — an empty document library, and an officials page with no officials
    # transcribed. A nav entry that leads to nothing is worse than a missing nav
    # entry, because the reader concludes the city published nothing rather than
    # that we have not asked yet. They turn on when the records arrive.
    features = {
        "city_desk": True, "records": True, "tips": True, "signup": True,
        "news": True, "watch": True, "the_question": True,
        "automation_status": True,
        "documents": False, "officials": False,
        # Turned on by the first successful weekly ingest, not by the scaffolder —
        # a meetings page with nothing in it is worse than no meetings page.
        "site_search": False, "meetings": False, "agenda_packets": False,
        "court_search": False, "crime_watch": False, "mayor_watch": False,
        "evidence_api": False,
    }

    return {
        "key": key,
        "site_name": site_name,
        "title_suffix": f"{city['city']} | {site_name}",
        "logo": {"prefix": "Expose", "body": STATE_TITLE[sk], "tld": tld},
        "domain": domain,
        "canonical_host": host,
        "hosts": [host],
        "chapter_label": f"{city['short']}, {abbr}",
        "city": city["city"],
        "county": city["county"],
        "state": STATE_TITLE[sk],
        "state_abbr": abbr,
        "state_key": sk,
        "accent": state["accent"],
        "accent2": state["accent2"],
        "accent_hover": state["accent_hover"],
        "infra": {
            # Every city in a state shares that state's container. The site is
            # static; what grows is the agenda archive, and putting all of a
            # state's archives on one filesystem is what makes the weekly ingest
            # a single unit of work instead of eleven.
            "vmid": state["lxc"],
            "ip": state["ip"],
            "node": "Slimmm",
            "shared_container": True,
            "web_root": f"/var/www/expose{key}/html",
            "app_root": f"/opt/expose{key}",
            "records_port": 5060,
            "signup_port": 5050,
        },
        "statute": statute,
        "submit_email": f"{SUBMIT_LOCALPART[key]}@{SUBMIT_DOMAIN}",
        "submit_email_state": f"{sk}@{SUBMIT_DOMAIN}",
        "portal": city["portal"],
        "links": city["links"],
        "news": city.get("news", []),
        "issue": city["issue"],
        "oversight": state["oversight"],
        "sources_verified": verified,
        "donations": {"url": "/about.html#funding", "live": False,
                      "zelle": "team@moveweight.com"},
        "features": features,
        "allies": [],
        "css_version": CSS_VERSION,
        "source_dir": f"../expose-chapters/{key}",
        "nav": nav_for(features),
        "footer": footer_for(city["city"], city["county"], sk, domain,
                             statute["appeal"]["body"], features),
        "donate_banner": (
            '<div class="donate-banner">This site is funded by citizens, not by the city. '
            '<a href="/about.html#funding">Fund a public records request &rarr;</a>'
            '<span class="sep hide-sm">|</span><span class="hide-sm">Zelle: '
            '<strong>team@moveweight.com</strong></span><span class="sep hide-sm">|</span>'
            '<span class="hide-sm">501(c)(3) tax-deductible</span></div>'),
        "footer_disclaimer": (
            'A project of the <a href="https://foundation.moveweight.com">Move Weight '
            f'Foundation</a>, a 501(c)(3) nonprofit. Independent of the City of '
            f'{esc(city["city"])}, {esc(city["county"])} and the State of '
            f'{STATE_TITLE[sk]}.'),
        "video": {
            "enabled": True,
            "intro": (f"These are {esc(city['city'])}'s own recordings and portals. We link to "
                      "them rather than rehosting, so you are watching the authoritative copy."),
            "sources": city["video"],
        },
        "video_intro": (f"These are {esc(city['city'])}'s own recordings and portals. We link to "
                        "them rather than rehosting, so you are watching the authoritative copy."),
        "video_html": video_cards(city["video"]),
        "social": {"note": "Added by the Foundation once an account exists.", "accounts": []},
        "social_html": ('<p class="dim mb0">No social accounts yet for this chapter.</p>'),
    }


# Keys the pipeline owns, not the scaffolder. `features` is flipped by data
# arriving - ingest_meetings.py turns `meetings` on the first time a city's
# portal answers - and `nav` follows from it. A --force regeneration that reset
# them would silently un-publish the meetings archive and the search page of
# every chapter, which is exactly what happened the first time this ran.
PIPELINE_OWNED = ("features", "nav", "allies", "donations", "social")


def preserve(old, new):
    """Refresh the research-driven fields, keep the pipeline-driven ones.

    `features` is merged by OR rather than taken from either side. Every flag in
    this system means "there is data behind this page", and it is only ever
    turned on - by ingest_meetings.py when a portal first answers, or by hand
    when a library first has documents in it. Letting one side win outright meant
    a workstation ship could un-publish an archive the node had just built, and a
    node merge could ignore a page the workstation had just enabled. Turning a
    feature back OFF is a deliberate edit, made once, in chapters/<key>.json.

    `nav` is then regenerated from the merged features rather than merged itself,
    so the menu can never disagree with the pages that actually exist.
    """
    # Snapshot the incoming features BEFORE the copy loop below replaces them,
    # or the OR runs old-against-old and every incoming flag is discarded.
    incoming = dict(new.get("features") or {})
    for k in PIPELINE_OWNED:
        if k in old:
            new[k] = old[k]
    feats = dict(old.get("features") or {})
    for k, v in incoming.items():
        feats[k] = bool(feats.get(k)) or bool(v)
    new["features"] = feats
    new["nav"] = nav_for(feats)
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="overwrite existing chapter configs")
    ap.add_argument("--only", nargs="*", help="limit to these keys")
    args = ap.parse_args()

    data = json.loads(RESEARCH.read_text(encoding="utf-8"))
    verified = data["verified"]
    written, skipped = [], []

    for city in data["cities"]:
        key = city["key"]
        if args.only and key not in args.only:
            continue
        dest = CHAPTERS / f"{key}.json"
        if dest.exists() and not args.force:
            skipped.append(key)
            continue
        state = data["states"][city["state"]]
        cfg = build_config(city, state, verified)
        if dest.exists():
            cfg = preserve(json.loads(dest.read_text(encoding="utf-8")), cfg)
        dest.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
        src = (ROOT / cfg["source_dir"] / "src" / "pages").resolve()
        src.mkdir(parents=True, exist_ok=True)
        written.append(key)

    for k in written:
        print(f"  wrote    chapters/{k}.json")
    for k in skipped:
        print(f"  skipped  chapters/{k}.json (exists; --force to replace)")
    print(f"\n  {len(written)} written, {len(skipped)} skipped")


if __name__ == "__main__":
    main()
