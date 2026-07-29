#!/usr/bin/env python3
"""
Re-verify every URL in research/cities.json.

    python research/verify_links.py
    python research/verify_links.py --fail-only

The chapters publish these links to residents who are trying to file a records
request. A link that 404s sends someone to a dead end at the exact moment they
were about to act, so this is run before every deploy and on the weekly timer.

A 3xx is reported, not accepted silently: a city that moved its records page
moved it for a reason, and the new URL belongs in cities.json rather than in a
redirect we hope keeps working.

Exit code is the number of URLs that failed, so it can gate a deploy.
"""

import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "cities.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# Some city sites reject non-browser clients outright (sa.gov and okc.gov both
# answer 403 to anything that is not a full browser). A 403 from a host we have
# already confirmed by hand is not a broken link, so it is reported as WARN and
# does not fail the run.
SOFT = {403, 405, 429, 503}

# Hosts that answer a bot with an error regardless of how the request is dressed.
# Facebook returns 400 to anything without a session. The link is still the one
# the city itself publishes, so it is checked but never allowed to fail a deploy.
SOFT_HOSTS = ("facebook.com", "www.facebook.com")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _once(url):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    opener = urllib.request.build_opener(NoRedirect,
                                         urllib.request.HTTPSHandler(context=ctx))
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept": "text/html,*/*"})
    try:
        with opener.open(req, timeout=25) as r:
            return r.status, ""
    except urllib.error.HTTPError as e:
        if 300 <= e.code < 400:
            return e.code, e.headers.get("Location", "")
        return e.code, ""
    except Exception as e:  # noqa: BLE001 - a DNS or TLS failure is a dead link too
        return 0, type(e).__name__


def check(url):
    """Fetch once, and give a connection-level failure a second chance.

    Every chapter in a state shares that state's oversight links, so a full run
    hits texasattorneygeneral.gov and oklahoma.gov once per Texas and Oklahoma
    chapter within a couple of minutes. The first run on the node reported six
    of those as dead; every one of them answered fine on retry. Publishing
    "this link is dead" to a resident because a server briefly reset a
    connection is worse than being slightly slower, so a code-0 or 5xx result
    is retried once after a pause.
    """
    code, extra = _once(url)
    # A 3xx is only good news if its target is. nondoc.com was recorded from a
    # 301 whose destination turned out to be a hard 404 - the redirect looked
    # like a healthy link and the chapter would have shipped a dead one.
    if 300 <= code < 400 and extra:
        target = extra if extra.startswith("http") else             urllib.parse.urljoin(url, extra)
        tcode, _ = _once(target)
        if tcode >= 400 and tcode not in SOFT:
            return tcode, f"via redirect -> {target}"
    if code == 0 or code >= 500:
        time.sleep(2.5)
        code2, extra2 = _once(url)
        # Keep the better of the two: a transient reset should not outrank a
        # successful fetch.
        if code2 and (code == 0 or code2 < code):
            return code2, extra2
    return code, extra


def collect(data):
    """Every URL in the file, with a human label for where it came from."""
    seen = {}

    def add(url, where):
        if url and url.startswith("http"):
            seen.setdefault(url, where)

    for name, st in data.get("states", {}).items():
        for o in st.get("oversight", []):
            add(o["url"], f"state:{name}")
    for c in data.get("cities", []):
        k = c["key"]
        p = c.get("portal", {})
        add(p.get("portal_url"), f"{k}:portal")
        # Legistar's `api` is an OData service root, which 404s on its own; the
        # chapter stores an `api_probe` endpoint so this check exercises the real
        # thing the ingest will call rather than a path that never answers.
        api = p.get("api_probe") or p.get("api", "")
        add(api.replace("{year}", "2026"), f"{k}:api")
        for v in c.get("video", []):
            add(v["url"], f"{k}:video")
        for section, items in c.get("links", {}).items():
            for it in items:
                add(it["url"], f"{k}:{section}")
        for n in c.get("news", []):
            add(n["url"], f"{k}:news")
    return seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fail-only", action="store_true")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--chapter", help="only this city's links (plus its state's)")
    args = ap.parse_args()

    data = json.loads(DATA.read_text(encoding="utf-8"))
    if args.chapter:
        # The weekly runner checks one chapter at a time. Without this it
        # re-fetched all 136 URLs once per chapter - roughly 1,500 requests at
        # every city's expense, to answer a question about one of them.
        city = next((c for c in data["cities"] if c["key"] == args.chapter), None)
        if not city:
            sys.exit(f"no city '{args.chapter}' in cities.json")
        data = {"cities": [city],
                "states": {city["state"]: data["states"][city["state"]]}}
    urls = collect(data)
    results = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for url, (code, extra) in zip(urls, pool.map(check, urls)):
            results.append((code, extra, url, urls[url]))

    def soft(r):
        return r[0] in SOFT or any(h in r[2] for h in SOFT_HOSTS)

    bad = [r for r in results if (r[0] >= 400 and not soft(r)) or r[0] == 0]
    warn = [r for r in results if r[0] >= 400 and soft(r)]
    moved = [r for r in results if 300 <= r[0] < 400]

    if args.json:
        print(json.dumps({
            "checked": len(results), "ok": len(results) - len(bad) - len(warn) - len(moved),
            "warn": len(warn), "moved": len(moved), "failed": len(bad),
            "failures": [{"code": c, "url": u, "where": w} for c, _, u, w in bad],
            "redirects": [{"code": c, "url": u, "to": e, "where": w} for c, e, u, w in moved],
        }, indent=2))
        return len(bad)

    for code, extra, url, where in sorted(results, key=lambda r: (-r[0], r[3])):
        ok = not (code >= 400 or code == 0)
        if args.fail_only and ok and not (300 <= code < 400):
            continue
        tag = ("OK  " if ok and code < 300 else
               "MOVE" if 300 <= code < 400 else
               "WARN" if soft((code, extra, url, where)) else "FAIL")
        print(f"{tag} {code or '---':>3}  {where:<28} {url}"
              + (f"\n            -> {extra}" if extra else ""))

    print(f"\n  {len(results)} urls  |  {len(bad)} failed  {len(warn)} warn  "
          f"{len(moved)} redirect")
    return len(bad)


if __name__ == "__main__":
    sys.exit(main())
