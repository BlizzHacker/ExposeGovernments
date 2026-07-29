#!/usr/bin/env python3
"""Point each chapter's donate button at that chapter's own GoFundMe campaign.

    python3 shared/set_donate_links.py --check
    python3 shared/set_donate_links.py

Why per-chapter: one campaign per area is the only way to see which city's
neighbours actually fund the work there. A single shared campaign collects the
money and tells you nothing about where it came from.

Two things this refuses to do, both learned from the 404 Austin reported:

  * It verifies every campaign URL is live and publicly reachable before writing
    it anywhere. A donate button pointing at a draft or a typo is worse than one
    pointing at the funding explainer.
  * A chapter with no campaign is left alone, pointing at /about.html#funding.
    Guessing a slug for a campaign that does not exist yet would put a 404
    behind "Fund a public records request" on that chapter - exactly the bug
    that took a month to notice last time.

The URL also lives inside the pre-rendered `donate_banner` HTML in each config,
so setting `donations.url` alone changes nothing a reader can see.
"""

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHAPTERS = ROOT / "chapters"

BASE = "https://www.gofundme.com/f/fund-public-records-access-in-"

# chapter key -> campaign slug. Only chapters whose campaign is actually live.
SLUGS = {
    "okc": "oklahoma-city",
    "tulsa": "tulsa",
    "claremore": "claremore",
    "sanangelo": "san-angelo",
    "houston": "houston",
    "dallas": "dallas",
    "austin": "austin",
    "sanantonio": "san-antonio",
    "lubbock": "lubbock",
    "miamiok": "miami-ok",
}

# Campaigns that do not exist yet, with the slug each one should get. Listed
# here rather than in SLUGS so that a chapter awaiting a campaign is reported as
# pending instead of as a broken link - and so that creating one needs no code
# change at all: the first run after the campaign goes live finds it reachable
# and wires it up. The slug is what GoFundMe derives from the title
# "Fund public records access in <City>", which is how the other nine were made.
PENDING = {
    "abilene": "abilene",
    "mississippi": "southaven",
    "jackson": "jackson",
    "olivebranch": "olive-branch",
}

# Miami OK is on the same URL form as everyone else now. It kept a gofund.me
# share short link for historical reasons; that link only 301s to this campaign,
# and the redirect dragged share tracking parameters along with it. Nothing here
# builds Miami's pages - mw-standardize.py on CT 170 injects its banner - but the
# URL still belongs in one place.
SKIP = set()


def reachable(url):
    req = urllib.request.Request(url, headers={"User-Agent": "MoveWeightFoundation/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report, change nothing")
    args = ap.parse_args()

    changed = skipped = bad = 0
    for p in sorted(CHAPTERS.glob("*.json")):
        if p.stem.startswith("_"):
            continue
        cfg = json.loads(p.read_text(encoding="utf-8"))
        key = cfg["key"]

        if key in SKIP:
            print(f"  --  {key:14s} left as-is ({cfg['donations']['url']})")
            skipped += 1
            continue
        if key not in SLUGS:
            slug = PENDING.get(key)
            if slug and reachable(BASE + slug):
                # Created since the last run. Adopt it rather than making
                # someone remember to edit this file too.
                SLUGS[key] = slug
                print(f"  ++  {key:14s} campaign is now live - adopting it")
            else:
                where = f" (awaiting {BASE}{slug})" if slug else ""
                print(f"  --  {key:14s} no campaign yet - keeps "
                      f"{cfg['donations']['url']}{where}")
                skipped += 1
                continue

        url = BASE + SLUGS[key]
        if not reachable(url):
            print(f"  !!  {key:14s} {url} is NOT reachable - refusing to write it")
            bad += 1
            continue

        if cfg["donations"].get("url") == url and cfg["donations"].get("live"):
            print(f"  ok  {key:14s} already set")
            continue
        if args.check:
            print(f"  ->  {key:14s} would set {url}")
            changed += 1
            continue

        old = cfg["donations"].get("url", "")
        cfg["donations"]["url"] = url
        cfg["donations"]["live"] = True

        # The href is baked into the rendered banner too. Replacing only the
        # old value keeps every other link in that string untouched.
        banner = cfg.get("donate_banner", "")
        if old and old in banner:
            cfg["donate_banner"] = banner.replace(f'"{old}"', f'"{url}"')
        elif banner and url not in banner:
            cfg["donate_banner"] = re.sub(
                r'(<a href=")[^"]*(">Fund a public records request)',
                lambda m: m.group(1) + url + m.group(2), banner, count=1)

        p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")
        print(f"  ->  {key:14s} {url}")
        changed += 1

    print(f"\n  {changed} updated, {skipped} left alone, {bad} unreachable")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
