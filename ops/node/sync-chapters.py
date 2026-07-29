#!/usr/bin/env python3
"""Collect every chapter's published site into the ExposeGovernments repo.

    python3 /opt/sync-chapters.py [--dry-run]

Runs on the Proxmox node, because only the node has `pct` and the chapters live
in three different containers.

Why the layout is what it is
----------------------------
The repo root IS Miami's live webroot: /var/www/exposemiamiok on CT 170 is a git
repo whose html/ directory is what nginx serves. Moving Miami under chapters/ to
make the tree symmetric would move the files nginx is serving, so Miami stays at
the root and the other thirteen arrive under chapters/<key>/. The README says
this plainly rather than pretending the layout is tidier than it is.

Excludes the same things Miami's .gitignore excludes - mp4/wav/mp3/pdf - so the
repo stays a readable record of what was published rather than a media dump.
Miami's own webroot alone is 84 GB, almost all mp4; GitHub sees 293 MB of it.
"""

import argparse
import subprocess
import sys

DEST_CT = "170"
DEST = "/var/www/exposemiamiok/chapters"

# key -> (container, webroot)
CHAPTERS = [
    ("oklahoma-city", "170", "/var/www/exposeokc/html"),
    ("tulsa", "170", "/var/www/exposetulsa/html"),
    ("claremore", "170", "/var/www/exposeclaremore/html"),
    ("san-angelo", "175", "/var/www/exposesanangelo/html"),
    ("houston", "175", "/var/www/exposehouston/html"),
    ("dallas", "175", "/var/www/exposedallas/html"),
    ("austin", "175", "/var/www/exposeaustin/html"),
    ("san-antonio", "175", "/var/www/exposesanantonio/html"),
    ("lubbock", "175", "/var/www/exposelubbock/html"),
    ("abilene", "175", "/var/www/exposeabilene/html"),
    ("southaven", "176", "/var/www/exposemississippi/html"),
    ("jackson", "176", "/var/www/exposejackson/html"),
    ("olive-branch", "176", "/var/www/exposeolivebranch/html"),
]

EXCLUDE = ["*.mp4", "*.wav", "*.mp3", "*.pdf", "*.db", "*.log",
           "__pycache__", "*.pyc"]


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=900, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--commit", action="store_true",
                    help="commit and push chapters/ if it changed")
    args = ap.parse_args()

    excl = " ".join(f"--exclude='{e}'" for e in EXCLUDE)
    total = 0
    failed = []

    for key, ct, root in CHAPTERS:
        r = run(["pct", "exec", ct, "--", "bash", "-lc",
                 f"test -d {root} && tar czf - {excl} -C {root} . | base64 -w0"])
        if r.returncode != 0 or not r.stdout.strip():
            failed.append(f"{key}: read failed ({(r.stderr or '').strip()[:80]})")
            continue
        payload = r.stdout.strip()
        size = len(payload) * 3 // 4
        total += size
        if args.dry_run:
            print(f"  {key:14} {size / 1e6:6.1f} MB (dry run)")
            continue

        # Replace the directory wholesale so pages deleted upstream disappear
        # here too - a stale page left behind is how OKC ended up serving a
        # donate link for a different chapter.
        w = run(["pct", "exec", DEST_CT, "--", "bash", "-lc",
                 f"rm -rf {DEST}/{key} && mkdir -p {DEST}/{key} && "
                 # --no-same-owner: the tarball carries the source container's
                 # uids, and extracting as-is fails outright on any file owned
                 # by a uid this container does not know.
                 f"base64 -d | tar xzf - --no-same-owner -C {DEST}/{key}"],
                input=payload)
        if w.returncode != 0:
            failed.append(f"{key}: write failed ({(w.stderr or '').strip()[:80]})")
            continue
        n = run(["pct", "exec", DEST_CT, "--", "bash", "-lc",
                 f"find {DEST}/{key} -type f | wc -l"]).stdout.strip()
        print(f"  {key:14} {size / 1e6:6.1f} MB  {n:>5} files")

    print(f"\n{total / 1e6:.1f} MB across {len(CHAPTERS) - len(failed)} chapters")
    for f in failed:
        print(f"  FAILED {f}")

    if args.commit and not args.dry_run:
        commit_and_push()
    return 1 if failed else 0


def commit_and_push():
    """Publish chapters/ only.

    Stages that one path deliberately. The working tree this lives in is also a
    live webroot and routinely carries hundreds of uncommitted files of
    automated content churn - crime feed, news JSON - that have nothing to do
    with this sync. `git add -A` here would bundle all of it under a message
    claiming it was a chapter sync.
    """
    q = ["pct", "exec", DEST_CT, "--", "bash", "-lc"]
    run(q + ["cd /var/www/exposemiamiok && git add chapters"])
    staged = run(q + ["cd /var/www/exposemiamiok && "
                      "git diff --cached --name-only | wc -l"]).stdout.strip()
    if staged == "0":
        print("  chapters unchanged - nothing to publish")
        return
    msg = f"Sync chapter sites ({staged} files)"
    r = run(q + [f"cd /var/www/exposemiamiok && "
                 f"git -c user.name='Move Weight Foundation' "
                 f"-c user.email='team@moveweight.com' commit -q -m '{msg}' && "
                 f"git push origin main 2>&1 | tail -2"])
    print(f"  published: {msg}")
    if r.stdout.strip():
        print("   ", r.stdout.strip().replace("\n", "\n    "))


if __name__ == "__main__":
    sys.exit(main())
