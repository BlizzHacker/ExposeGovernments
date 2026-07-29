#!/usr/bin/env python3
"""
Keep foundation.moveweight.com in step with the chapters it claims to run.

    python3 shared/make_foundation.py            # write locally, report the diff
    python3 shared/make_foundation.py --deploy   # and push it to LXC 150

The Foundation homepage is a hand-built page with its own stylesheet and a live
donation flow, and it stays hand-built. What this owns is the part that goes
stale the moment a chapter launches, injected between markers:

    MW:HERO       the headline, the standfirst, the two buttons
    MW:STATS      the stat bar
    MW:MAP        the national map and the per-state summary
    MW:CHAPTERS   the full chapter directory

Everything outside those markers is left byte-for-byte alone.

Why this got rewritten
----------------------
The page was written when the Foundation was one town, and it still read that
way with fourteen chapters live. The stat bar showed Miami OK's own numbers -
508 meetings, 152 crime-feed items - presented as the Foundation's totals. The
headline said "Small-Town America" over a footprint that now includes Houston,
Dallas and San Antonio. The map had three pins. The second button said "Visit
ExposeMiamiOK".

None of that was a lie when it was written, which is exactly why it needed
generating rather than editing: hand-maintained numbers on a transparency site
decay into false ones.

Every figure below is computed from the chapters themselves or from a count
recorded in research/cities.json with the command used to take it. Nothing is
rounded up, and nothing carries a "+" it has not earned.
"""

import argparse
import json
import re
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHAPTERS = ROOT / "chapters"
RESEARCH = ROOT / "research" / "cities.json"
ASSETS = ROOT / "shared" / "assets"
LOCAL = ROOT / "generated" / "foundation-index.html"

NODE = "root@192.168.0.6"
VMID = 150
REMOTE = "/var/www/foundation/index.html"

# The hero sends people to the chapter list, not to a single campaign.
#
# Every area now runs its own GoFundMe so the Foundation can see which city's
# neighbours actually pay for the work there. This page used to point ten links
# at Miami's campaign, which meant a donor arriving at the Foundation - with no
# city in mind - was silently counted as a Miami donor. Sending them to choose
# is both more honest and the only way the per-area numbers mean anything.
GOFUNDME = "#chapter-directory"

# The retired city domains, and where each lives now.
RETIRED = {
    "exposemiamiok.com": "miami.exposeoklahoma.com",
    "www.exposemiamiok.com": "miami.exposeoklahoma.com",
    "exposesanangelo.com": "sanangelo.exposetexas.org",
    "www.exposesanangelo.com": "sanangelo.exposetexas.org",
}

STATE_ORDER = ["oklahoma", "texas", "mississippi"]
STATE_NAME = {"oklahoma": "Oklahoma", "texas": "Texas", "mississippi": "Mississippi"}
STATE_DOMAIN = {"oklahoma": "exposeoklahoma.com", "texas": "exposetexas.org",
                "mississippi": "exposemississippi.com"}
STATE_ICON = {"oklahoma": "&#127765;", "texas": "&#127964;", "mississippi": "&#127807;"}

REGIONS = ("HERO", "STATS", "MAP", "CHAPTERS", "VOLUNTEER")
VOLUNTEERS_URL = "https://volunteers.moveweight.com/"


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
         "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
         "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
         "eighty", "ninety"]


def num_word(n):
    """Spell a count 0-99.

    The Foundation's prose says "fourteen chapters", not "14 chapters", and
    those words were typed in. The headline counts beside them were already
    derived from len(chapters), so the page could - and did - end up saying
    "15 chapters" in one line and "there are fourteen" three paragraphs later.
    Adding a chapter should not mean hunting spelled-out numbers.
    """
    n = int(n)
    if n < 0 or n > 99:
        return str(n)
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] + (f"-{_ONES[ones]}" if ones else "")


def oxford(names):
    """"Oklahoma, Texas and Mississippi" - and correct at two or one."""
    names = list(names)
    if len(names) <= 1:
        return names[0] if names else ""
    return ", ".join(names[:-1]) + " and " + names[-1]


def state_names(chapters):
    """The states actually carrying a chapter, in the canonical order."""
    keys = {c.get("state_key") for c in chapters if c.get("state_key")}
    ordered = [k for k in STATE_ORDER if k in keys]
    ordered += sorted(k for k in keys if k not in STATE_ORDER)
    return [STATE_NAME.get(k, k.title()) for k in ordered]


def load_chapters():
    out = []
    for p in sorted(CHAPTERS.glob("*.json")):
        if p.stem.startswith("_"):
            continue
        out.append(json.loads(p.read_text(encoding="utf-8")))
    return out


def research():
    return json.loads(RESEARCH.read_text(encoding="utf-8"))


def meetings_count(cfg, founding):
    """Meetings this chapter has actually indexed.

    Two sources, because there are two kinds of chapter. The eleven built from
    this template publish generated/meetings.json every week. The three founding
    chapters predate the pipeline and were counted on their containers - those
    numbers live in research/cities.json with the command used to take them.
    """
    f = ROOT / cfg.get("source_dir", "") / "generated" / "meetings.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("count", 0)
    except (OSError, ValueError):
        return founding.get(cfg["key"], {}).get("meetings", 0)


def totals(chapters, data):
    founding = data.get("founding_archives", {})
    n_meetings = sum(meetings_count(c, founding) for c in chapters)
    links = len({u for city in data.get("cities", [])
                 for section in city.get("links", {}).values()
                 for u in [i["url"] for i in section]})
    links += len({n["url"] for city in data.get("cities", []) for n in city.get("news", [])})
    mi = founding.get("miamiok", {})
    return {
        "chapters": len(chapters),
        "states": len({c.get("state_key") for c in chapters if c.get("state_key")}),
        "meetings": n_meetings,
        "captions": mi.get("caption_files", 0),
        "documents": mi.get("documents", 0),
        "links": links,
    }


# ─── regions ───────────────────────────────────────────────────────────
def hero(chapters, t):
    by_state = {}
    for c in chapters:
        by_state.setdefault(c.get("state_key"), []).append(c)
    phrase = ", ".join(
        f"<strong>{len(by_state[s])} in {STATE_NAME[s]}</strong>"
        for s in STATE_ORDER if s in by_state)
    return f'''<header class="hero">
  <div class="badge"><span class="dot"></span> Move Weight Foundation</div>
  <h1 class="fade-up">
    Funding the <span class="grad-text">Truth</span><br>
    Where Nobody Is Watching
  </h1>
  <p class="tagline fade-up-2">
    The Move Weight Foundation runs <strong>{t["chapters"]} public records chapters</strong>
    across {t["states"]} states &mdash; {phrase}. We archive the meetings, file open
    records requests in our own name so residents stay anonymous, and publish every
    document that comes back, whole and unredacted. It is the same job in a town of
    thirteen thousand and in the largest city in Texas: somebody has to read the agenda.
    <strong>Every dollar files another request.</strong>
  </p>
  <div class="btns fade-up-3">
    <a href="{GOFUNDME}" class="btn btn-primary btn-lg">Fund your city&rsquo;s chapter</a>
    <a href="#volunteer" class="btn btn-outline">Give time instead</a>
  </div>
</header>'''


def stats(t):
    # Six figures, each one traceable. "Weekly" is last because it is the claim
    # the others depend on - a big archive that stopped updating is not an asset.
    rows = [
        (f'{t["chapters"]}', "Chapters live"),
        (f'{t["states"]}', "States covered"),
        (f'{t["meetings"]:,}', "Public meetings indexed"),
        (f'{t["captions"]:,}', "Transcript &amp; caption files"),
        (f'{t["links"]}', "Official links re-checked weekly"),
        ("Weekly", "Every chapter refreshes itself"),
    ]
    cells = "\n".join(
        '      <div class="stat-item">\n'
        f'        <div class="stat-num">{n}</div>\n'
        f'        <div class="stat-label">{lab}</div>\n'
        "      </div>" for n, lab in rows)
    return ('<section style="padding-top:0;">\n  <div class="container">\n'
            '    <div class="stats-bar">\n' + cells
            + "\n    </div>\n  </div>\n</section>")


def map_section(chapters, t):
    svg_path = ASSETS / "us-expansion.svg"
    svg = svg_path.read_text(encoding="utf-8") if svg_path.exists() else ""
    founding = research().get("founding_archives", {})
    by_state = {}
    for c in chapters:
        by_state.setdefault(c.get("state_key"), []).append(c)

    cards = []
    for s in STATE_ORDER:
        rows = by_state.get(s, [])
        if not rows:
            continue
        rows = sorted(rows, key=lambda c: -meetings_count(c, founding))
        n = sum(meetings_count(c, founding) for c in rows)
        names = ", ".join(c["city"] for c in rows)
        cards.append(
            '      <div class="feature-card">\n'
            f'        <div class="ficon">{STATE_ICON[s]}</div><h4>{STATE_NAME[s]}</h4>\n'
            f'        <p><strong>{len(rows)} chapters</strong> &mdash; {esc(names)}.'
            + (f" {n:,} public meetings indexed between them." if n else "")
            + "</p>\n"
            f'        <a href="https://{STATE_DOMAIN[s]}" class="flink">'
            f'{STATE_DOMAIN[s]} &rarr;</a>\n      </div>')
    cards.append(
        '      <div class="feature-card" style="border:1px dashed var(--border,rgba(148,163,184,.22))">\n'
        '        <div class="ficon">&#128205;</div><h4>Your state</h4>\n'
        '        <p>Expansion is limited by people who know which questions to ask, not '
        'by software. If something is happening where you live, tell us.</p>\n'
        '        <a href="mailto:team@moveweight.com" class="flink">Start a chapter &rarr;</a>\n'
        "      </div>")

    return f'''<section id="expansion" class="mwf-expansion-map">
  <div class="container">
    <div class="section-eyebrow">Where we work</div>
    <h2>{t["chapters"]} chapters. <span class="grad-text">{num_word(t["states"]).capitalize()} states down, {num_word(50 - t["states"])} to go.</span></h2>
    <p style="max-width:70ch;color:var(--muted,#a7b3c7)">
      Every state has a public records law. Almost nowhere does anyone use it on the
      ordinary business of local government &mdash; the consent agenda, the utility
      board packet, the tax abatement that passes in nine seconds. The Foundation
      builds a chapter, files the requests in its own name so residents stay anonymous,
      and publishes every document that comes back, in full and permanently.
    </p>
    <div style="margin:26px 0;background:#0f172a;border:1px solid rgba(148,163,184,.22);border-radius:12px;padding:18px">
      {svg}
    </div>
    <div class="feature-grid">
{chr(10).join(cards)}
    </div>
    <p style="font-size:.82rem;color:#7c8aa3;margin-top:18px">
      Boundaries from public US Census cartographic data, Albers equal-area projection.
      City positions are Census Gazetteer internal points. Pins link to the chapter.
      Regenerated {date.today().isoformat()}.
    </p>
  </div>
</section>'''


def directory(chapters):
    founding = research().get("founding_archives", {})
    by_state = {}
    for c in chapters:
        by_state.setdefault(c.get("state_key"), []).append(c)

    def card(cfg):
        host = cfg.get("canonical_host") or cfg["domain"]
        n = meetings_count(cfg, founding)
        bits = []
        if n:
            bits.append(f"{n:,} meetings indexed")
        if cfg["features"].get("documents"):
            bits.append("document library")
        if cfg["features"].get("site_search"):
            bits.append("full-text search")
        detail = ", ".join(bits) or "records desk and statute guide"
        # Each chapter that has its own campaign gets its own fund link. The
        # whole reason for running one campaign per area is to see which city's
        # neighbours pay for the work there, and a single Foundation-wide button
        # destroys exactly that - every donation would land against one city.
        # Chapters without a campaign show nothing rather than a dead link.
        don = cfg.get("donations", {})
        fund = ""
        if don.get("live") and str(don.get("url", "")).startswith("http"):
            fund = (f'\n          <a href="{don["url"]}" target="_blank" '
                    f'rel="noopener" class="flink">Fund {esc(cfg["city"])} &rarr;</a>')
        return ('        <div class="feature-card">\n'
                f'          <h4>{esc(cfg["city"])}, {esc(cfg["state_abbr"])}</h4>\n'
                f'          <p>{esc(cfg["county"])}. {esc(detail[0].upper() + detail[1:])}.</p>\n'
                f'          <a href="https://{host}/" class="flink">{esc(host)} &rarr;</a>'
                f'{fund}\n'
                "        </div>")

    blocks = []
    for st in STATE_ORDER:
        rows = sorted(by_state.get(st, []), key=lambda c: -meetings_count(c, founding))
        if not rows:
            continue
        total = sum(meetings_count(c, founding) for c in rows)
        blocks.append(
            f'      <h3 style="margin-top:32px;">{STATE_NAME[st]} '
            f'&mdash; <a href="https://{STATE_DOMAIN[st]}">{STATE_DOMAIN[st]}</a></h3>\n'
            f'      <p class="section-sub">{len(rows)} chapters'
            + (f", {total:,} public meetings indexed" if total else "")
            + ".</p>\n"
            '      <div class="feature-grid">\n'
            + "\n".join(card(c) for c in rows)
            + "\n      </div>")

    n_ch = len(chapters)
    n_st = len(state_names(chapters))
    n_mt = sum(meetings_count(c, founding) for c in chapters)
    return f'''<section id="chapter-directory">
  <div class="container">
    <div class="section-eyebrow">Every Chapter</div>
    <h2>{n_ch} chapters across {num_word(n_st)} states</h2>
    <p class="section-sub">
      Every chapter runs the same playbook: the statute, the records desk, the meeting
      archive, and a public page that admits what is out of date. {n_mt:,} public
      meetings are indexed across them, refreshed every week from each city&rsquo;s own
      portal. This list is generated from the chapters themselves, so it cannot drift
      from what is actually running.
    </p>
{chr(10).join(blocks)}
    <p class="section-sub" style="margin-top:28px;font-size:.85rem;opacity:.7;">Generated {date.today().isoformat()}.</p>
  </div>
</section>'''


def volunteer_section(t):
    """The ask that is not money.

    Deliberately placed after the directory rather than in the hero: somebody
    who has just found their city is far likelier to sign up than somebody who
    has read one headline. It names both kinds of work, because a developer
    reading "volunteer" assumes leafleting and a local reading it assumes code,
    and each of them wrongly concludes there is nothing here for them.
    """
    return f'''<section id="volunteer">
  <div class="container">
    <div class="section-eyebrow">Give Time Instead</div>
    <h2>The work is done by people, and we count their hours</h2>
    <p class="section-sub">
      {t["chapters"]} chapters and {t["meetings"]:,} indexed meetings are almost entirely
      volunteer work. There are two jobs and both are real. <strong>Local foot workers</strong>
      go to the meeting, photograph the posted agenda, walk the ward and send back what
      they saw &mdash; nothing about that requires a computer.
      <strong>Developers</strong> keep the portal adapters alive, because a city can change
      its agenda system on a Tuesday and take a chapter dark until somebody notices.
    </p>
    <p class="section-sub">
      Hours logged in the volunteer register are what a grant application asks for and what
      the Form&nbsp;990 narrative rests on. There is no password &mdash; you put in your
      email, we send you a link.
    </p>
    <div class="btns">
      <a href="{VOLUNTEERS_URL}" class="btn btn-primary">Log volunteer hours</a>
      <a href="{VOLUNTEERS_URL}" class="btn btn-outline">See what needs doing</a>
    </div>
  </div>
</section>'''


# ─── injection ─────────────────────────────────────────────────────────
def wrap(region, body):
    return f"<!-- MW:{region}:START -->\n{body}\n<!-- MW:{region}:END -->"


ANCHORS = {
    # region: (regex marking where it goes on first run, replace_match)
    "HERO": (r"<header class=\"hero\">.*?</header>", True),
    "STATS": (r"<!-- STATS -->\s*<section style=\"padding-top:0;\">.*?</section>", True),
    "MAP": (r"<section id=\"expansion\".*?</section>\s*(?=<!-- MORE PROJECTS -->)", True),
}


def inject(html, region, body):
    block = wrap(region, body)
    start, end = f"<!-- MW:{region}:START -->", f"<!-- MW:{region}:END -->"
    if start in html and end in html:
        return re.sub(re.escape(start) + r".*?" + re.escape(end),
                      lambda _: block, html, flags=re.S), "replaced"
    pat = ANCHORS.get(region)
    if pat:
        m = re.search(pat[0], html, re.S)
        if m:
            return html[:m.start()] + block + html[m.end():], "adopted"
    if region == "CHAPTERS":
        m = re.search(r"<!-- MW:MAP:END -->", html)
        if m:
            return html[:m.end()] + "\n\n" + block + html[m.end():], "inserted"
        m = re.search(r"<section id=\"donate\"", html)
        if m:
            return html[:m.start()] + block + "\n\n  " + html[m.start():], "inserted"
    if region == "VOLUNTEER":
        # Straight after the directory: the reader has just found their city.
        m = re.search(r"<!-- MW:CHAPTERS:END -->", html)
        if m:
            return html[:m.end()] + "\n\n" + block + html[m.end():], "inserted"
    raise SystemExit(f"could not place region {region}")


def fix_retired(html):
    n = 0
    for old, new in RETIRED.items():
        pat = re.compile(r"(https?://)" + re.escape(old) + r"(?=[/\"'?#]|\b)")
        html, k = pat.subn(lambda m: m.group(1) + new, html)
        n += k
    return html, n


# Donate targets outside the generated regions.
#
# The hand-written parts of this page carried seven links to Miami's campaign -
# the nav CTA, the amount widget, the footer, and a JS constant. Every area now
# has its own campaign, so a Foundation-level donor with no city in mind was
# being counted as a Miami donor. Sending them to the chapter directory to pick
# is the only answer that keeps the per-area numbers meaning anything.
#
# Miami's own campaign is untouched wherever it is named as Miami's.
MIAMI_CAMPAIGN = "https://www.gofundme.com/f/fund-public-records-access-in-miami-ok"
DONATE_FIXES = [
    (f'<a href="{MIAMI_CAMPAIGN}" target="_blank" class="btn nav-cta">'
     'Fund a Records Request</a>',
     '<a href="#chapter-directory" class="btn nav-cta">Fund a Chapter</a>'),

    (f'<a href="{MIAMI_CAMPAIGN}" target="_blank" '
     'class="btn btn-primary btn-lg">\U0001f4b8 Fund a Records Request Now</a>',
     '<a href="#chapter-directory" class="btn btn-primary btn-lg">'
     '\U0001f4b8 Choose a chapter to fund</a>'),

    # Footer and nav "GoFundMe" word-links, three of them, all identical.
    (f'<a href="{MIAMI_CAMPAIGN}">GoFundMe</a>',
     '<a href="#chapter-directory">GoFundMe</a>'),

    # The amount picker builds its href from this constant. Pointing it at the
    # directory loses the pre-filled amount; crediting the wrong city's ledger
    # is the worse of the two, and a chapter picker here is the real fix.
    (f"const base = '{MIAMI_CAMPAIGN}';",
     "const base = '#chapter-directory';"),
]

# Regex forms, for the ones exact strings cannot reach: the submit button spans
# four indented lines, and the prose links come in pairs - a full URL and the
# short link side by side - so replacing only the first left "GoFundMe,
# GoFundMe, or Zelle" on the page.
DONATE_RE = [
    # The amount widget's submit button.
    (re.compile(r'<a href="' + re.escape(MIAMI_CAMPAIGN) + r'"(\s+target="_blank"'
                r'\s+rel="noopener"\s+class="donate-submit")'),
     r'<a href="#chapter-directory"\1'),

    # "Donate via <full>, <short>, or Zelle" -> one link to the directory.
    (re.compile(r'Donate via <a href="[^"]*">GoFundMe</a>,\s*'
                r'<a href="https://gofund\.me/[^"]*"[^>]*>GoFundMe</a>,\s*or Zelle'),
     'Donate via <a href="#chapter-directory">GoFundMe</a> or Zelle'),

    # "Also on GoFundMe ->" in the donate panel.
    (re.compile(r'Also on <a href="https://gofund\.me/[^"]*"([^>]*)>GoFundMe'),
     r'Also on <a href="#chapter-directory"\1>GoFundMe'),
]


# Copy fixes outside the generated regions. Each is a whole sentence so a partial
# match cannot mangle the page, and each is idempotent.
COPY = [
    # The flagship section introduced Miami as if it were the Foundation.
    ("Each chapter applies the same playbook to a different town: file the records, "
     "publish the documents, keep a dated and sourced timeline. The playbook travels. "
     "The local facts do not.",
     "Three chapters are written up in depth below because they have the longest "
     "record behind them. They are not the whole Foundation &mdash; there are "
     "@@CHAPTERS_WORD@@, and the full list is further down. Each applies the same playbook to "
     "a different place: file the records, publish the documents, keep a dated and "
     "sourced timeline. The playbook travels. The local facts do not."),

    # Flagship headings still carried the retired brand names. The links were
    # repointed weeks ago; the words on the buttons were not, so the page sent
    # readers to a domain it simultaneously told them was the site's name.
    ("<h3>ExposeMiamiOK.com</h3>", "<h3>miami.exposeoklahoma.com</h3>"),
    ("<h3>ExposeSanAngelo.com</h3>", "<h3>sanangelo.exposetexas.org</h3>"),
    ("<h3>ExposeMississippi.com</h3>", "<h3>southaven.exposemississippi.com</h3>"),
    # These use a literal arrow character, not &rarr;. Matching the entity
    # silently did nothing, which is the argument for verifying a copy fix
    # applied rather than assuming it did.
    ("Visit ExposeMiamiOK.com →", "Visit the Miami chapter →"),
    ("Visit ExposeSanAngelo.com →", "Visit the San Angelo chapter →"),
    ("Visit ExposeMississippi.com →", "Visit the Southaven chapter →"),
    ("ExposeSanAngelo keeps the dated record",
     "The San Angelo chapter keeps the dated record"),
    # A footer column named after one chapter, in a footer for fourteen.
    ("<h5>ExposeMiamiOK</h5>", "<h5>Miami, Oklahoma</h5>"),

    # 508 was the count when the sentence was written. It is 522, counted on the
    # container. Rounding a real number up with a "+" is how a transparency site
    # ends up with a figure nobody can reproduce. Note the literal em-dash: this
    # part of the page uses the character, not the entity.
    ("508+ city council meetings with AI transcripts. Every public meeting since "
     "2016 — watchable, searchable, permanent.",
     "522 archived city council meetings with machine transcripts and captions. "
     "Every public meeting since 2016 — watchable, searchable, permanent, and "
     "mirrored so it survives the city deleting it."),

    ("Visit ExposeSanAngelo.com &rarr;", "Visit the San Angelo chapter &rarr;"),
    ("Visit ExposeMississippi.com &rarr;", "Visit the Southaven chapter &rarr;"),

    # The social preview still announced three chapters to anyone sharing a link.
    ("Three chapters: ExposeMiamiOK.com, ExposeSanAngelo.com and "
     "ExposeMississippi.com. Fund public records requests. Demand accountability.",
     "@@CHAPTERS_WORD_CAP@@ public records chapters across @@STATES@@. "
     "Fund records requests. Demand accountability."),

    # Miami's crime feed count was a snapshot presented as a standing figure.
    ("152+ live items from official sources.",
     "A continuously updated feed from official sources."),

    # The donation copy sent every dollar to one chapter. The <strong> tags are
    # part of the match: the sentence is marked up mid-clause and a plain-text
    # match found nothing.
    ("Your donation goes directly to <strong>funding public records requests</strong> "
     "through ExposeMiamiOK.",
     "Your donation goes directly to <strong>funding public records requests</strong> "
     "across all @@CHAPTERS_WORD@@ chapters &mdash; whichever city the next document has to be "
     "prised out of."),
    ("Funded requests published at "
     "<a href=\"https://miami.exposeoklahoma.com/foia/\">exposemiamiok.com/foia/</a>.",
     "Funded requests and the responses to them are published on the chapter that "
     "filed them."),

    # The footer described the whole Foundation as one site.
    ("ExposeMiamiOK.com is an independent community resource. No affiliation with "
     "any government entity.",
     "Every chapter is an independent community resource with no affiliation to any "
     "government entity."),
]


def apply_copy(html, chapters):
    """Apply the prose rewrites, filling the count tokens from the real list.

    Plain markers rather than str.format: these strings are prose carrying HTML
    entities and CSS-ish punctuation, and one stray brace would raise at build
    time on copy that has nothing to do with counting.
    """
    names = state_names(chapters)
    tokens = {
        "@@CHAPTERS_WORD@@": num_word(len(chapters)),
        "@@CHAPTERS_WORD_CAP@@": num_word(len(chapters)).capitalize(),
        "@@STATES@@": oxford(names),
        "@@STATES_WORD@@": num_word(len(names)),
    }
    n = 0
    for old, new in COPY:
        if old in html:
            for tok, val in tokens.items():
                new = new.replace(tok, val)
            html = html.replace(old, new)
            n += 1
    if "@@" in html:
        leftover = re.findall(r"@@[A-Z_]+@@", html)
        raise SystemExit(f"unsubstituted count token(s) in the page: {set(leftover)}")
    return html, n


def normalise_counts(html, chapters):
    """Rewrite the spelled-out counts in the prose to match the real chapter list.

    These three sentences sit outside the generated regions. The COPY table put
    them there once, and from then on its `old` string no longer matched - so
    they froze. The headline counts beside them are derived, which is the worst
    combination: the page would have read "15 chapters" at the top and "there
    are fourteen" three paragraphs down, and nothing would have flagged it.

    Matched on the shape of the sentence rather than its current number, so this
    is idempotent and does not need to know which vintage it is looking at.
    """
    word = num_word(len(chapters))
    names = state_names(chapters)
    subs = [
        (r"[A-Z][a-z-]+ public records chapters across [^\".]+\.",
         f"{word.capitalize()} public records chapters across {oxford(names)}."),
        (r"there are [a-z-]+, and the full list",
         f"there are {word}, and the full list"),
        (r"across all [a-z-]+ chapters &mdash;",
         f"across all {word} chapters &mdash;"),
    ]
    n = 0
    for pat, rep in subs:
        html, k = re.subn(pat, rep, html)
        n += k
    return html, n


def apply_donate_fixes(html):
    """Repoint hand-written donate links at the chapter directory.

    replace() with no count, because the footer/nav "GoFundMe" link appears
    three times and all three are the same mistake.
    """
    n = 0
    for old, new in DONATE_FIXES:
        if old in html:
            n += html.count(old)
            html = html.replace(old, new)
    for pat, repl in DONATE_RE:
        html, k = pat.subn(repl, html)
        n += k
    return html, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deploy", action="store_true")
    ap.add_argument("--source", help="read the page from here instead of the node")
    args = ap.parse_args()

    if args.source:
        html = Path(args.source).read_text(encoding="utf-8")
    else:
        html = subprocess.run(["ssh", NODE, f"pct exec {VMID} -- cat {REMOTE}"],
                              capture_output=True, text=True, encoding="utf-8",
                              check=True).stdout
    if len(html) < 5000:
        raise SystemExit(f"refusing to work on a {len(html)}-byte page; read failed")

    before = len(html)
    chapters = load_chapters()
    t = totals(chapters, research())

    html, fixed = fix_retired(html)
    html, copied = apply_copy(html, chapters)
    html, counted = normalise_counts(html, chapters)
    html, donated = apply_donate_fixes(html)
    how = {}
    for region, body in (("HERO", hero(chapters, t)),
                         ("STATS", stats(t)),
                         ("MAP", map_section(chapters, t)),
                         ("CHAPTERS", directory(chapters)),
                         ("VOLUNTEER", volunteer_section(t))):
        html, how[region] = inject(html, region, body)

    LOCAL.parent.mkdir(parents=True, exist_ok=True)
    LOCAL.write_text(html, encoding="utf-8")
    print("  regions: " + ", ".join(f"{k} {v}" for k, v in how.items()))
    print(f"  {fixed} retired-domain links repaired, {copied} copy fixes, "
          f"{donated} donate links repointed, {counted} spelled-out counts refreshed")
    print(f"  {t['chapters']} chapters / {t['states']} states / "
          f"{t['meetings']:,} meetings / {t['links']} links")
    print(f"  {before:,} -> {len(html):,} bytes  ->  {LOCAL}")

    if args.deploy:
        subprocess.run(["ssh", NODE, f"pct exec {VMID} -- cp {REMOTE} "
                        f"{REMOTE}.bak.$(date +%Y%m%d-%H%M%S)"], check=False)
        tmp = "/tmp/foundation-index.html"
        subprocess.run(["ssh", NODE, f"cat > {tmp}"],
                       input=html.encode("utf-8"), check=True)
        subprocess.run(["ssh", NODE, f"pct push {VMID} {tmp} {REMOTE}"], check=True)
        subprocess.run(["ssh", NODE, f"rm -f {tmp}"], check=False)
        print("  deployed to foundation.moveweight.com")


if __name__ == "__main__":
    main()
