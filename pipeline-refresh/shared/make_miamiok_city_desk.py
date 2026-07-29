#!/usr/bin/env python3
"""
Build the City Desk page for ExposeMiamiOK.

Miami OK predates the shared template and keeps its contact data in eleven
`resources/*.html` department pages plus a structured county table in
`resources/index.html`. Those pages hold MORE detail than the City Desk format
carries, so this is a restructure and never a replacement: every resources page
stays exactly where it is, and the City Desk links into them.

Reads the live pages, extracts what is there, and writes `city-desk.html`. It
invents nothing — a number appears on the page only if it was already published
on one of Miami OK's own pages.

Run inside LXC 170:  python3 make_miamiok_city_desk.py [--dry-run]
"""

import argparse
import html as htmlmod
import re
import sys
from datetime import date
from pathlib import Path

HTML = Path("/var/www/exposemiamiok/html")
RES = HTML / "resources"
OUT = HTML / "city-desk.html"

PHONE = re.compile(r"\(?\b(?:800|918)\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")
TAG = re.compile(r"<[^>]+>")

# The department pages, in the order a resident is likely to need them, with the
# plain-English "what is this for" the source pages do not state up front.
DEPARTMENTS = [
    ("public-works",          "Public Works",           "&#128736;",
     "Water, sewer, streets, sanitation, stormwater. The utility desk."),
    ("police",                "Police",                 "&#128110;",
     "Non-emergency police business, reports, records."),
    ("fire",                  "Fire",                   "&#128293;",
     "Non-emergency fire business, inspections, burn permits."),
    ("animal-control",        "Animal Control",         "&#128054;",
     "Strays, bites, welfare complaints, the shelter."),
    ("municipal-court",       "Municipal Court",        "&#9878;",
     "Citations, fines, court dates, warrants."),
    ("finance",               "Finance",                "&#128176;",
     "Utility billing, city budget, purchasing, accounts payable."),
    ("community-development", "Community Development",  "&#127959;",
     "Zoning, permits, inspections, code enforcement, planning."),
    ("emergency-management",  "Emergency Management",   "&#9888;",
     "Preparedness, hazard planning, storm response."),
    ("parks-recreation",      "Parks & Recreation",     "&#127795;",
     "Parks, fields, programmes, facility rental."),
    ("government",            "City Government",        "&#127963;",
     "Council, mayor, city manager, clerk, agendas and minutes."),
    ("community",             "Community Services",     "&#129309;",
     "Library, senior services, community programmes."),
]


def text_of(p: Path) -> str:
    h = p.read_text(encoding="utf-8", errors="replace")
    h = re.sub(r"<(script|style)\b.*?</\1>", " ", h, flags=re.S | re.I)
    return re.sub(r"\s+", " ", TAG.sub(" ", h))


def phones_in(p: Path):
    seen, out = set(), []
    for m in PHONE.finditer(text_of(p)):
        d = re.sub(r"\D", "", m.group())
        if len(d) != 10:
            continue
        n = f"{d[:3]}-{d[3:6]}-{d[6:]}"
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def county_rows():
    """The structured county table already published on resources/index.html."""
    src = RES / "index.html"
    if not src.exists():
        return []
    h = re.sub(r"<(script|style)\b.*?</\1>", " ",
               src.read_text(encoding="utf-8", errors="replace"), flags=re.S | re.I)

    def cell(c):
        c = re.sub(r"<br\s*/?>", "\n", c, flags=re.I)
        c = TAG.sub("", c)
        c = htmlmod.unescape(c)
        return [x.strip() for x in c.split("\n") if x.strip()]

    rows = []
    for r in re.findall(r"<tr>(.*?)</tr>", h, re.S | re.I):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S | re.I)
        if len(cells) < 4:
            continue
        office, phone, email, addr = (cell(c) for c in cells[:4])
        if not office or office[0].lower().startswith("office"):
            continue
        rows.append({
            "office": office[0],
            "name": office[1] if len(office) > 1 else "",
            "phones": phone,
            "email": email[0] if email else "",
            "address": addr[0] if addr else "",
            "hours": addr[1] if len(addr) > 1 else "",
        })
    return rows


def esc(s):
    return htmlmod.escape(str(s), quote=True)


def build():
    # First pass: which numbers appear on nearly every department page? Those
    # are site-wide (a header or footer line), not that department's. Listing
    # 918-542-6685 on all eleven cards is noise that makes the useful numbers
    # harder to find, so they get hoisted out once instead.
    per_page = {}
    for slug, *_ in DEPARTMENTS:
        p = RES / f"{slug}.html"
        if p.exists():
            per_page[slug] = phones_in(p)

    freq = {}
    for nums in per_page.values():
        for n in set(nums):
            freq[n] = freq.get(n, 0) + 1
    threshold = max(2, int(len(per_page) * 0.6))
    sitewide = sorted(n for n, c in freq.items() if c >= threshold)

    cards, missing = [], []
    for slug, label, ico, blurb in DEPARTMENTS:
        if slug not in per_page:
            missing.append(slug)
            continue
        nums = [n for n in per_page[slug] if n not in sitewide]
        shown = nums[:6]

        # Deliberately NOT labelling one of these "the" number. These pages list
        # several — a state hotline, a fax, a division direct line — and picking
        # the first match put an 800 abuse hotline at the top of the Police card.
        # A directory people actually dial does not get to guess.
        if shown:
            nums_html = ('        <p class="cd-nums">'
                         + " &middot; ".join(f'<a href="tel:{n}">{n}</a>' for n in shown)
                         + (f' <span class="cd-more">+{len(nums) - len(shown)} more</span>'
                            if len(nums) > len(shown) else "")
                         + "</p>")
        else:
            nums_html = '        <p class="cd-nums cd-none">No number published on that page</p>'

        cards.append("\n".join([
            '      <div class="cd-card">',
            f"        <h3>{esc(label)}</h3>",
            f'        <p class="cd-blurb">{esc(blurb)}</p>',
            nums_html,
            f'        <a class="cd-link" href="/resources/{slug}.html">'
            f"Full {esc(label)} page &rarr;</a>",
            "      </div>",
        ]))

    rows = county_rows()
    trs = []
    for r in rows:
        ph = "<br>".join(f'<span class="mono">{esc(x)}</span>' for x in r["phones"])
        em = f'<a href="mailto:{esc(r["email"])}">{esc(r["email"])}</a>' if r["email"] else "&mdash;"
        who = f'<strong>{esc(r["office"])}</strong>'
        if r["name"]:
            who += f'<br><span class="cd-dim">{esc(r["name"])}</span>'
        loc = esc(r["address"])
        if r["hours"]:
            loc += f'<br><span class="cd-dim">{esc(r["hours"])}</span>'
        trs.append(f"          <tr><td>{who}</td><td>{ph}</td><td>{em}</td><td>{loc}</td></tr>")

    # str.format is unusable here — the page carries an inline <style> block and
    # every CSS rule looks like a format field to it.
    sw = ("        <p class=\"cd-nums\">"
          + " &middot; ".join(f'<a href="tel:{n}">{n}</a>' for n in sitewide)
          + "</p>") if sitewide else          '        <p class="cd-nums cd-none">None detected</p>'

    page = PAGE
    for key, val in {
        "{cards}": "\n".join(cards),
        "{county_rows}": "\n".join(trs),
        "{county_count}": str(len(rows)),
        "{dept_count}": str(len(cards)),
        "{today}": date.today().strftime("%B %Y"),
        "{sitewide}": sw,
    }.items():
        page = page.replace(key, val)
    return page, missing, len(rows), len(cards)


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Miami OK City Desk — every number you actually need | ExposeMiamiOK</title>
<meta name="description" content="Every City of Miami and Ottawa County department, phone number and service in one page, with the accountability record attached to each office.">
<link rel="canonical" href="https://exposemiamiok.com/city-desk.html">
<meta property="og:type" content="website">
<meta property="og:site_name" content="ExposeMiamiOK">
<meta property="og:title" content="Miami OK City Desk — every number you actually need">
<meta property="og:url" content="https://exposemiamiok.com/city-desk.html">
<link rel="stylesheet" href="/assets/exposemiami-theme.css">
<style>
/* Scoped to this page. Miami OK's shared stylesheet predates the component
   vocabulary the newer chapters use, and editing a sheet 750 pages depend on
   to style one page is the wrong trade. */
.cd-wrap{max-width:1180px;margin:0 auto;padding:0 20px}
.cd-hero{padding:46px 0 34px;border-bottom:1px solid rgba(148,163,184,.22)}
.cd-eyebrow{display:inline-block;font-size:.72rem;font-weight:800;letter-spacing:.11em;
  text-transform:uppercase;color:#ef4444;background:rgba(220,38,38,.12);
  border:1px solid rgba(220,38,38,.4);padding:5px 13px;border-radius:20px;margin-bottom:16px}
.cd-hero h1{font-size:clamp(1.9rem,4.2vw,2.8rem);font-weight:900;letter-spacing:-.03em;margin:0 0 .4em}
.cd-lede{font-size:1.06rem;color:#a7b3c7;max-width:70ch;margin:0}
.cd-sec{padding:40px 0;border-top:1px solid rgba(148,163,184,.22)}
.cd-sec h2{font-size:clamp(1.35rem,2.6vw,1.9rem);font-weight:800;margin:0 0 .35em}
.cd-sub{color:#a7b3c7;max-width:72ch;margin:0 0 22px}
.cd-grid{display:grid;gap:15px;grid-template-columns:repeat(auto-fit,minmax(290px,1fr))}
.cd-card{background:#162033;border:1px solid rgba(148,163,184,.22);border-radius:9px;padding:19px 21px}
.cd-card:hover{border-color:rgba(148,163,184,.4)}
.cd-card h3{margin:0 0 .3em;font-size:1.06rem;font-weight:800}
.cd-blurb{color:#a7b3c7;font-size:.92rem;margin:0 0 10px}
.cd-nums{font-family:ui-monospace,Consolas,monospace;font-size:.9rem;margin:0 0 11px;line-height:1.9}
.cd-nums a{color:#f8fafc;text-decoration:none;border-bottom:1px dotted rgba(148,163,184,.5)}
.cd-nums a:hover{color:#ef4444;border-bottom-color:#ef4444}
.cd-more,.cd-none{color:#7c8aa3;font-size:.82rem;font-family:system-ui,sans-serif}
.cd-link{font-weight:700;font-size:.89rem;color:#ef4444;text-decoration:none}
.cd-link:hover{text-decoration:underline}
.cd-note{border-left:3px solid #dc2626;background:rgba(220,38,38,.07);
  border-radius:0 9px 9px 0;padding:15px 19px;margin:20px 0}
.cd-note.warn{border-left-color:#f59e0b;background:rgba(245,158,11,.07)}
.cd-note p{margin:0}
.cd-label{display:block;font-size:.7rem;font-weight:800;letter-spacing:.09em;
  text-transform:uppercase;color:#7c8aa3;margin-bottom:5px}
.cd-scroll{overflow-x:auto;margin:16px 0}
.cd-scroll table{width:100%;border-collapse:collapse;font-size:.9rem;min-width:640px}
.cd-scroll th{background:#1e293b;font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;
  color:#a7b3c7;font-weight:800;text-align:left;padding:10px 12px;white-space:nowrap}
.cd-scroll td{padding:11px 12px;border-bottom:1px solid rgba(148,163,184,.18);vertical-align:top}
.cd-scroll tbody tr:hover{background:rgba(30,41,59,.6)}
.cd-scroll .mono{font-family:ui-monospace,Consolas,monospace}
.cd-dim{color:#7c8aa3}
.cd-foot{color:#7c8aa3;font-size:.86rem}
</style>
</head>
<body>
<main id="main">

<section class="cd-hero">
  <div class="cd-wrap">
    <span class="cd-eyebrow">City Desk &middot; Miami &amp; Ottawa County, Oklahoma</span>
    <h1>Every number you actually need</h1>
    <p class="cd-lede">
      Water off? Pothole? Court date? Need to reach a commissioner? It is all here, in one
      page. Each department links to its full page, which carries more detail than this
      summary &mdash; hours, services, forms and every published contact.
    </p>
  </div>
</section>

<section class="cd-sec">
  <div class="cd-wrap">
    <div class="cd-note">
      <span class="cd-label">Emergencies</span>
      <p class="mb0">
        <strong>Call 911.</strong> This page is a directory published by a nonprofit, not a
        dispatch service and not the City. For anything time-critical, call 911 first.
      </p>
    </div>
  </div>
</section>

<section class="cd-sec" id="departments">
  <div class="cd-wrap">
    <div class="cd-note warn">
      <span class="cd-label">City-wide numbers</span>
      <p>These appear on most department pages rather than belonging to any one of
      them &mdash; try these if a specific line does not get you to a person.</p>
{sitewide}
    </div>
    <div class="cd-head">
      <h2>City of Miami departments</h2>
      <p>
        {dept_count} departments. Every number below already appears on this site's own
        department page for that office &mdash; we list them all rather than guess which is
        the main line, because several pages carry a hotline, a fax and a direct line
        together. The full page has the hours, services and forms, and is unchanged.
      </p>
    </div>
    <div class="cd-grid">
{cards}
    </div>
  </div>
</section>

<section class="cd-sec" id="county">
  <div class="cd-wrap">
    <div class="cd-head">
      <h2>Ottawa County offices</h2>
      <p>
        {county_count} county offices with the elected official who holds each. Several things
        residents assume are city business are county business &mdash; property assessment, the
        tax bill, the courts, the Sheriff and elections.
      </p>
    </div>
    <div class="cd-scroll">
      <table>
        <thead><tr><th>Office</th><th>Phone</th><th>Email</th><th>Address &amp; hours</th></tr></thead>
        <tbody>
{county_rows}
        </tbody>
      </table>
    </div>
  </div>
</section>

<section class="cd-sec" id="accountability">
  <div class="cd-wrap">
    <div class="cd-head">
      <h2>The accountability record</h2>
      <p>The office that answers your pothole call is the office that holds the records.</p>
    </div>
    <div class="cd-grid">
      <div class="card">
        <div class="card-ico">&#128220;</div>
        <h3>Open Records</h3>
        <p>File an Oklahoma Open Records Act request. We file it in the Foundation's name so yours stays off it, and publish whatever comes back.</p>
        <a class="card-link" href="/foia/">File a request &rarr;</a>
      </div>
      <div class="card">
        <div class="card-ico">&#127909;</div>
        <h3>Meeting archive</h3>
        <p>Council meetings with video, machine transcripts and captions &mdash; the deepest archive the Foundation runs.</p>
        <a class="card-link" href="/meetings/">Browse meetings &rarr;</a>
      </div>
      <div class="card">
        <div class="card-ico">&#128203;</div>
        <h3>Agenda packets</h3>
        <p>The packet usually contains the actual contract or ordinance under discussion, before the vote.</p>
        <a class="card-link" href="/agenda-packets/">Open packets &rarr;</a>
      </div>
      <div class="card">
        <div class="card-ico">&#128176;</div>
        <h3>Follow the money</h3>
        <p>City finance, budget reports and audit leads.</p>
        <a class="card-link" href="/follow-the-money.html">Budget record &rarr;</a>
      </div>
      <div class="card">
        <div class="card-ico">&#128269;</div>
        <h3>Search everything</h3>
        <p>Every page, document and transcript on this site, searched in your browser.</p>
        <a class="card-link" href="/search.html">Search &rarr;</a>
      </div>
      <div class="card">
        <div class="card-ico">&#128274;</div>
        <h3>Send a tip</h3>
        <p>If you work for the City or the County and something looks wrong, tell us. We do not log your address.</p>
        <a class="card-link" href="/#signup">Get in touch &rarr;</a>
      </div>
    </div>
  </div>
</section>

<section class="cd-sec">
  <div class="cd-wrap">
    <h2>Who publishes this page</h2>
    <p>
      <strong>The Move Weight Foundation &mdash; not the City of Miami and not Ottawa County.</strong>
      We are a 501(c)(3) nonprofit with no affiliation to either government.
    </p>
    <p class="cd-dim" style="font-size:.88rem">
      Every number here was already published on one of this site's own department pages,
      compiled {today}. Nothing on this page was invented and no department page was changed
      or removed. Governments reorganise and numbers change &mdash; if one is wrong, tell us and
      we will fix it and say when. For the City's own site see
      <a href="https://www.miamiok.gov/" rel="noopener">miamiok.gov</a>.
    </p>
  </div>
</section>

</main>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if not RES.is_dir():
        sys.exit(f"missing {RES}")

    page, missing, ncounty, ndept = build()
    print(f"  departments: {ndept}  county offices: {ncounty}")
    if missing:
        print(f"  ! missing resource pages (skipped, not invented): {missing}")
    if a.dry_run:
        print(f"  WOULD write {OUT} ({len(page)} bytes)")
        return
    OUT.write_text(page, encoding="utf-8")
    print(f"  wrote {OUT} ({len(page)} bytes)")
    print("  run mw-standardize.py to add the chapter bar and head tags")


if __name__ == "__main__":
    main()
