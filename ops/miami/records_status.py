#!/usr/bin/env python3
"""Keep the reviewed Miami records-status block and interlinked network feed current after daily refresh."""
from pathlib import Path
import re

OUT = Path("/var/www/exposemiamiok/html/index.html")
NEWS_OUT = Path("/var/www/exposemiamiok/html/local-news.html")
SOURCE = Path("/var/www/exposemiamiok/ops/miami/records-status-block.html")
NET_SOURCE = Path("/var/www/exposemiamiok/ops/miami/network-feed-block.html")
START = "<!-- RECORDS REQUESTS START -->"
END = "<!-- RECORDS REQUESTS END -->"
N_START = "<!-- NETWORK FEED START -->"
N_END = "<!-- NETWORK FEED END -->"


def inject_block(path, start, end, block, anchor="</main>"):
    if not path.exists():
        return
    html = path.read_text(encoding="utf-8")
    if start in html and end in html:
        updated, _ = re.subn(
            re.escape(start) + r".*?" + re.escape(end),
            lambda _: block,
            html,
            count=1,
            flags=re.S,
        )
    elif anchor in html:
        updated = html.replace(anchor, "\n" + block + "\n" + anchor, 1)
    else:
        return
    if updated != html:
        path.write_text(updated, encoding="utf-8")


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

    if NET_SOURCE.exists():
        nblock = NET_SOURCE.read_text(encoding="utf-8").strip()
        if nblock.startswith(N_START) and nblock.endswith(N_END):
            inject_block(OUT, N_START, N_END, nblock)
            inject_block(NEWS_OUT, N_START, N_END, nblock)

    print("records status + network feed current: 24 Nov 2026")


if __name__ == "__main__":
    main()
