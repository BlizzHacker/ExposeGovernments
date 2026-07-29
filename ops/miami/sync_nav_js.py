#!/usr/bin/env python3
"""Rewrite the navItems array inside exposemiami-ui.js from nav_constants.py.

    python3 /opt/sync_nav_js.py

Why this exists
---------------
Miami's navigation had THREE copies, not two. Two were HTML (the drawer and the
desktop bar, both now written by mw-standardize.py from nav_constants.NAV_ITEMS)
and the third was a hardcoded `navItems` array inside
/assets/exposemiami-ui.js. That array is the one a reader actually sees:
`fillLinks()` empties both navs on DOMContentLoaded and refills them from the
script, so whatever the HTML says is discarded in the browser.

That is why the 2026-07-28 nav fix did not reach the public site. The dead
"/#corruption" link and the duplicated "Ottawa County" label were corrected in
nav_constants.py and in all 766 pages of HTML, and the script put both straight
back on every page load.

Rather than hand-editing a fourth copy, the array is generated from
nav_constants.NAV_ITEMS. Run it after any nav change; miami-refresh.sh runs it
before mw-standardize so the HTML and the script cannot disagree again.

Idempotent: re-running with no change to NAV_ITEMS rewrites identical bytes and
reports "unchanged".
"""

import pathlib
import re
import sys

sys.path.insert(0, "/opt")
from nav_constants import NAV_ITEMS          # noqa: E402

JS = pathlib.Path("/var/www/exposemiamiok/html/assets/exposemiami-ui.js")
BACKUPS = pathlib.Path("/opt/backups")
MARKER = re.compile(r"(?:const|var|let)\s+navItems\s*=\s*\[")


def js_string(s):
    """Quote for JS. The labels are plain text but this is generated code."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render():
    rows = "\n".join(
        f"    [{js_string(href)}, {js_string(label)}]," for href, label in NAV_ITEMS
    )
    return (
        "const navItems = [\n"
        "    // GENERATED from /opt/nav_constants.py by /opt/sync_nav_js.py.\n"
        "    // Do not edit by hand - edit NAV_ITEMS there and re-run the script.\n"
        f"{rows}\n"
        "  ]"
    )


def main():
    text = JS.read_text(encoding="utf-8")
    m = MARKER.search(text)
    if not m:
        raise SystemExit("navItems array not found in exposemiami-ui.js")

    # Walk to the matching close bracket rather than regexing across it: the
    # array holds bracket-free string pairs today, but a URL with a "]" in it
    # would silently truncate the file.
    depth = 0
    start = m.end() - 1
    end = None
    for i in range(start, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise SystemExit("unbalanced navItems array in exposemiami-ui.js")

    new = text[: m.start()] + render() + text[end:]
    if new == text:
        print(f"unchanged: {len(NAV_ITEMS)} nav items already in sync")
        return

    # NOT next to the file: /var/www/.../assets is served, so a .bak
    # written there is a publicly fetchable copy of the source.
    BACKUPS.mkdir(parents=True, exist_ok=True)
    (BACKUPS / "exposemiami-ui.js.bak").write_text(text, encoding="utf-8")
    JS.write_text(new, encoding="utf-8")
    old_n = text[m.start():end].count("[") - 1
    print(f"rewrote navItems: {old_n} items -> {len(NAV_ITEMS)} from nav_constants.py")


if __name__ == "__main__":
    main()
