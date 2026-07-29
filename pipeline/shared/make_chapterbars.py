#!/usr/bin/env python3
"""
Emit every chapter's nav bar as a standalone fragment.

    python3 shared/make_chapterbars.py        -> generated/chapterbars/<key>.html

build.py renders the bar into the pages it builds. Miami OK is legacy and is not
built by this template at all - its pages come from its own generators and a
standardiser injects the bar afterwards. That standardiser used to carry its own
hardcoded copy, which is exactly how the estate ended up serving three different
"universal" bars at once, one of them pointing at domains retired weeks earlier
and every one of its links returning 404.

So the bar is written out here, once per chapter, and the standardiser reads the
file instead of holding an opinion. One generator, one shape, everywhere.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "generated" / "chapterbars"

sys.path.insert(0, str(ROOT))
from build import CHAPTER_ORDER, chapter_bar, load_chapter  # noqa: E402


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    n = 0
    for keys in CHAPTER_ORDER.values():
        for key in keys:
            cfg = load_chapter(key)
            (OUT / f"{key}.html").write_text(chapter_bar(cfg) + "\n", encoding="utf-8")
            n += 1
    print(f"  {n} chapter bars -> {OUT}")


if __name__ == "__main__":
    main()
