#!/usr/bin/env python3
"""
Crawl the live sites and report every internal link that does not resolve.

    python research/verify_site_links.py
    python research/verify_site_links.py --host exposemississippi.com

`verify_links.py` checks the OUTBOUND links published from research data. This
checks the site's own links - the nav, the footer, the donate banner, the buttons
in body copy - which is a different failure and the one a reader actually hits.

It exists because Austin clicked "Fund a public records request" on
exposemississippi.com and got a 404, and so did the other twenty links on that
page: the state apex serves a single index.html out of its own web root while
carrying a whole chapter's navigation. Nothing was watching for that.

Every internal href on every page of every chapter, fetched, once. Exit code is
the number of dead links so it can gate a deploy.
"""

import argparse
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

HOSTS = [
    "foundation.moveweight.com",
    "exposeoklahoma.com", "miami.exposeoklahoma.com", "okc.exposeoklahoma.com",
    "tulsa.exposeoklahoma.com", "claremore.exposeoklahoma.com",
    "exposetexas.org", "sanangelo.exposetexas.org", "houston.exposetexas.org",
    "dallas.exposetexas.org", "austin.exposetexas.org",
    "sanantonio.exposetexas.org", "lubbock.exposetexas.org",
    "abilene.exposetexas.org",
    "exposemississippi.com", "southaven.exposemississippi.com",
    "jackson.exposemississippi.com", "olivebranch.exposemississippi.com",
]

# Miami's archive is 654 pages and regenerates constantly; crawling all of it on
# every check costs minutes to re-prove what the standardiser already holds. The
# top-level pages are what carry the navigation.
SKIP_PREFIXES = ("/meetings/", "/agenda-packets/", "/facebook-posts/",
                 "/finance-transcripts/", "/documents/files/", "/transcripts/")

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

HREF = re.compile(r'(?:href|src)="([^"]+)"')


# Codes that mean "ask again", not "this link is broken". Crawling 350 URLs
# through Cloudflare from one address earns rate limiting and the occasional
# challenge; the node reported 40 dead links on a run where every one of them
# answered 200 on retry. A weekly job that cries wolf gets ignored, which costs
# more than the extra requests.
TRANSIENT = {0, 403, 408, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524}


def _fetch_once(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
            return r.status, r.read(400_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # noqa: BLE001
        return 0, type(e).__name__


def head(url, timeout=25):
    code, body = _fetch_once(url, timeout)
    for attempt in (1, 2):
        if code not in TRANSIENT:
            break
        time.sleep(1.5 * attempt)
        code, body = _fetch_once(url, timeout)
    return code, body


def internal_links(host, page_url, html):
    out = set()
    for raw in HREF.findall(html):
        u = raw.split("#")[0].strip()
        if not u or u.startswith(("mailto:", "tel:", "javascript:", "data:")):
            continue
        # Cloudflare rewrites every mailto: into /cdn-cgi/l/email-protection and
        # injects its own script; neither is a link this project controls or a
        # reader ever follows. And an href assembled inside JavaScript - the
        # search page builds one per result - is a template, not a URL.
        if u.startswith("/cdn-cgi/") or "'" in u or "+" in u or "${" in u:
            continue
        full = urllib.parse.urljoin(page_url, u)
        p = urllib.parse.urlsplit(full)
        if p.scheme not in ("http", "https") or p.netloc != host:
            continue
        if p.path.startswith(SKIP_PREFIXES):
            continue
        out.add(urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, p.query, "")))
    return out


def check_host(host):
    """Fetch the homepage, collect its internal links, then check each one."""
    root = f"https://{host}/"
    code, html = head(root)
    if code != 200:
        return host, [(root, code, "homepage")], 0
    # Track which page each link was found on. Without it a dead link is a URL
    # with no answer to "where do I fix this", and grepping the whole site for
    # the href is a guess that fails when the page is served from cache.
    found_on = {}
    for u in internal_links(host, root, html):
        found_on.setdefault(u, root)
    # One hop deeper from the nav, which is where the footer's deep links live.
    for extra in list(found_on)[:12]:
        c, h = head(extra)
        if c == 200 and h:
            for u in internal_links(host, extra, h):
                found_on.setdefault(u, extra)

    targets = list(found_on)
    dead = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for url, (c, _) in zip(targets, pool.map(lambda u: head(u), targets)):
            if c != 200:
                dead.append((url, c, "linked from " + found_on[url]))
    return host, dead, len(targets)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", action="append", help="limit to these hosts")
    args = ap.parse_args()
    hosts = args.host or HOSTS

    total_dead = total_checked = 0
    for host in hosts:
        h, dead, n = check_host(host)
        total_dead += len(dead)
        total_checked += n
        mark = "ok  " if not dead else "DEAD"
        print(f"  {mark} {h:36s} {n:4d} links, {len(dead)} broken")
        for url, code, why in sorted(dead):
            print(f"          {code or '---'}  {url}  {why}")

    print(f"\n  {total_checked} internal links across {len(hosts)} hosts, "
          f"{total_dead} broken")
    return total_dead


if __name__ == "__main__":
    sys.exit(main())
