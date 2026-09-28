#!/usr/bin/env python3
"""Keep the reviewed Miami records-status block on the homepage after daily refresh."""
from pathlib import Path
import re

OUT = Path("/var/www/exposemiamiok/html/index.html")
SOURCE = Path("/var/www/exposemiamiok/ops/miami/records-status-block.html")
START = "<!-- RECORDS REQUESTS START -->"
END = "<!-- RECORDS REQUESTS END -->"

def main():
    html = OUT.read_text(encoding="utf-8")
    block = SOURCE.read_text(encoding="utf-8").strip()
    if not block.startswith(START) or not block.endswith(END):
        raise SystemExit("records status source markers missing")
    updated, count = re.subn(
        re.escape(START) + r".*?" + re.escape(END),
        lambda _: block,
        html,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise SystemExit("records status homepage markers missing")
    if updated != html:
        OUT.write_text(updated, encoding="utf-8")
    print("records status current: 28 Sep 2026 partial Animal Control response")

if __name__ == "__main__":
    main()
