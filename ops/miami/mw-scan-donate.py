#!/usr/bin/env python3
"""Every page of a chapter must fund THAT chapter. Count where it does not.

The homepage check missed this: sub-pages are written by different generators at
different times, so a meeting page can carry a donate banner from whenever that
page was last built - pointing at whichever campaign was current then. OKC's
meeting pages fund Miami.

Run inside a chapter container:  python3 scan_donate_pages.py <webroot> <slug>
"""

import pathlib
import re
import sys
from collections import Counter

GF = re.compile(r"https://(?:www\.)?gofundme\.com/f/([a-z0-9-]+)|https://gofund\.me/([a-z0-9]+)")

root = pathlib.Path(sys.argv[1])
expect = sys.argv[2]

pages = 0
with_link = 0
found = Counter()
wrong_pages = []

for p in root.rglob("*.html"):
    if p.name.endswith(".bak") or ".bak." in p.name:
        continue
    try:
        t = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        continue
    pages += 1
    hits = {m.group(1) or ("short:" + m.group(2)) for m in GF.finditer(t)}
    if not hits:
        continue
    with_link += 1
    for h in hits:
        found[h] += 1
    if hits - {expect}:
        wrong_pages.append((str(p.relative_to(root)), sorted(hits - {expect})))

print(f"  pages={pages} with_donate_link={with_link}")
for slug, n in found.most_common():
    mark = "ok " if slug == expect else "WRONG"
    print(f"    {mark} {slug:44} {n:>5} pages")
if wrong_pages:
    print(f"    -> {len(wrong_pages)} page(s) fund another chapter, e.g.:")
    for path, slugs in wrong_pages[:3]:
        print(f"       {path}  {slugs}")
