#!/usr/bin/env python3
"""
Merge freshly shipped chapter configs into the ones already on the node.

    python3 shared/deploy/merge_chapters.py <staged-chapters-dir>

Two different things write chapters/*.json and they must not overwrite each
other:

    the workstation   research-driven fields - links, statute, portal, issue,
                      video, footer, identity
    the node          pipeline-driven fields - `features` and `nav`, flipped on
                      when a city's portal first returns data

Shipping the workstation copy wholesale resets the second kind, which un-publishes
the meetings archive and the search page of every chapter until the next weekly
run happens to turn them back on. Shipping nothing means a new chapter never
arrives. So the ship stages its configs and this merges them: new file wins on
everything except the keys the pipeline owns.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
LIVE = ROOT / "chapters"

sys.path.insert(0, str(ROOT))
from scaffold_chapters import PIPELINE_OWNED, preserve  # noqa: E402


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: merge_chapters.py <staged-chapters-dir>")
    staged = Path(sys.argv[1])
    if not staged.is_dir():
        sys.exit(f"no staged directory at {staged}")

    added = merged = 0
    for src in sorted(staged.glob("*.json")):
        new = json.loads(src.read_text(encoding="utf-8"))
        dest = LIVE / src.name
        if dest.exists():
            old = json.loads(dest.read_text(encoding="utf-8"))
            new = preserve(old, new)
            merged += 1
        else:
            added += 1
        dest.write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")

    print(f"  chapters: {merged} merged, {added} new "
          f"(kept {', '.join(PIPELINE_OWNED)} from the node)")


if __name__ == "__main__":
    main()
