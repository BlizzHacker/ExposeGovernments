#!/usr/bin/env python3
"""What a reader's donate button actually does, on every live page.

Checks the served HTML rather than the configs. The URL is baked into a
pre-rendered donate_banner, and the two refresh-managed chapters are built from
a separate tree with its own configs - so a correct config proves nothing about
what shipped.
"""

import re
import sys
import urllib.error
import urllib.request

# Values are the FULL campaign slug. An earlier version of this file stored the
# city part only and compared it against the whole slug, so every correct
# chapter reported BAD - the check was broken, not the sites.
PREFIX = "fund-public-records-access-in-"
CHAPTERS = {
    "miami.exposeoklahoma.com": "miami-ok",
    "okc.exposeoklahoma.com": "oklahoma-city",
    "tulsa.exposeoklahoma.com": "tulsa",
    "claremore.exposeoklahoma.com": "claremore",
    "sanangelo.exposetexas.org": "san-angelo",
    "houston.exposetexas.org": "houston",
    "dallas.exposetexas.org": "dallas",
    "austin.exposetexas.org": "austin",
    "sanantonio.exposetexas.org": "san-antonio",
    "lubbock.exposetexas.org": "lubbock",
    "abilene.exposetexas.org": "abilene",
    "southaven.exposemississippi.com": "southaven",
    "jackson.exposemississippi.com": "jackson",
    "olivebranch.exposemississippi.com": "olive-branch",
}

# Anything above a single chapter must not bill one city for a general donation.
HUBS = ["foundation.moveweight.com", "exposeoklahoma.com", "exposetexas.org",
        "exposemississippi.com"]

GF = re.compile(r"https://(?:www\.)?gofundme\.com/f/([a-z0-9-]+)")
SHORT = re.compile(r"https://gofund\.me/[a-z0-9]+")


def get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "mw-donate-check"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return f"ERR {type(e).__name__}", ""


bad = 0
seen_targets = {}
print("chapter donate buttons")
for host, slug in CHAPTERS.items():
    code, html = get(f"https://{host}/")
    if code != 200:
        print(f"  BAD  {host:36} page returned {code}")
        bad += 1
        continue
    slugs = set(GF.findall(html))
    short = bool(SHORT.search(html))
    fallback = "/about.html#funding" in html

    # Miami is no longer an exception. It used a gofund.me share short link that
    # only 301s to this same campaign, which meant every count read "13 of 14"
    # and every check had to special-case it. A short link reappearing is now a
    # failure, not a tolerated variant.
    ok = slugs == {PREFIX + slug}
    detail = f"slugs={sorted(slugs) or 'NONE'}"
    if short:
        ok = False
        detail += " + gofund.me SHORT LINK (should be the canonical URL)"
    if fallback and not slugs:
        detail += " (still on /about.html#funding)"

    # Every chapter's button must point at ITS OWN campaign, never a neighbour's.
    for s in slugs:
        seen_targets.setdefault(s, []).append(host)

    if ok:
        print(f"  ok   {host:36} -> {slug}")
    else:
        print(f"  BAD  {host:36} expected {slug}, got {detail}")
        bad += 1

print("\ncampaign pages resolve")
for slug in sorted(set(CHAPTERS.values())):
    url = f"https://www.gofundme.com/f/{PREFIX}{slug}"
    code, _ = get(url)
    if code != 200:
        print(f"  BAD  {slug:16} {code}")
        bad += 1
    else:
        print(f"  ok   {slug:16} 200")

print("\nhubs")
# The Foundation is allowed - required - to link every chapter's campaign from
# its directory cards. What it must not do is send a general donation to one
# city: the hero, nav, footer and amount widget go to #chapter-directory. The
# state apexes inherit a host chapter's banner and must carry no campaign at all.
for host in HUBS:
    code, html = get(f"https://{host}/")
    if code != 200:
        print(f"  BAD  {host:36} page returned {code}")
        bad += 1
        continue
    slugs = set(GF.findall(html))
    if host == "foundation.moveweight.com":
        want = {PREFIX + s for s in CHAPTERS.values()}
        missing = want - slugs
        if "#chapter-directory" not in html:
            print(f"  BAD  {host:36} general CTA does not point at #chapter-directory")
            bad += 1
        elif missing:
            print(f"  BAD  {host:36} directory is missing {len(missing)} campaign(s): "
                  f"{sorted(s.replace(PREFIX, '') for s in missing)}")
            bad += 1
        else:
            print(f"  ok   {host:36} all {len(want)} campaigns on the directory, "
                  f"general CTA -> #chapter-directory")
    elif slugs or SHORT.search(html):
        print(f"  BAD  {host:36} links a chapter campaign: {sorted(slugs)}")
        bad += 1
    else:
        print(f"  ok   {host:36} no chapter campaign linked")

dupes = {s: h for s, h in seen_targets.items() if len(h) > 1}
if dupes:
    print(f"\n  BAD  a campaign is linked from more than one chapter: {dupes}")
    bad += 1

print(f"\n{bad} problem(s)")
sys.exit(1 if bad else 0)
