#!/usr/bin/env python3
"""Publish the code that builds the estate, not just the pages it produces.

    python3 /opt/sync-source.py [--dry-run] [--commit]

The repo held published HTML and nothing else, so every generator, standardiser
and check lived only on a server with no version history - including everything
changed in a working session. If CT 170 were lost, the sites would be
recoverable and the machinery that maintains them would not.

Runs on the node: the sources are spread across the node itself and CT 170.

Safety
------
The repository is PUBLIC, so this uses an **allowlist**, never a directory
sweep. /opt on CT 170 also holds ia-upload.py, the social poster and the comment
API, which read Archive.org keys, tokens and passwords from config; a denylist
would publish anything newly dropped there that nobody remembered to exclude.

Every file is scanned for credentials before it is committed and the publish is
abandoned if anything is found - belt as well as braces.
"""

import argparse
import subprocess
import sys

DEST_CT = "170"
REPO = "/var/www/exposemiamiok"

# (destination in repo, source container or "node", source path)
# Directories are copied whole; single files are copied as themselves.
SOURCES = [
    # The generator that builds thirteen of the fourteen chapters.
    ("pipeline", "node", "/opt/expose-template"),
    # The second pipeline: San Angelo and Southaven are built from this tree.
    ("pipeline-refresh/shared", "node", "/root/expose-work/expose-template/shared"),
    ("pipeline-refresh/chapters", "node", "/root/expose-work/expose-template/chapters"),
    ("pipeline-refresh/build.py", "node", "/root/expose-work/expose-template/build.py"),
    ("pipeline-refresh/refresh.sh", "node", "/root/expose-work/expose-template/refresh.sh"),
    # Estate-wide checks and the sync scripts themselves.
    ("ops/node/mw-verify.py", "node", "/opt/mw-verify.py"),
    ("ops/node/mw-check-donate.py", "node", "/opt/mw-check-donate.py"),
    ("ops/node/mw-secret-scan.py", "node", "/opt/mw-secret-scan.py"),
    ("ops/node/sync-chapters.py", "node", "/opt/sync-chapters.py"),
    ("ops/node/sync-source.py", "node", "/opt/sync-source.py"),
    # Miami's own machinery. Named individually and deliberately: the rest of
    # /opt on CT 170 handles credentials.
    ("ops/miami/nav_constants.py", DEST_CT, "/opt/nav_constants.py"),
    ("ops/miami/mw-standardize.py", DEST_CT, "/opt/mw-standardize.py"),
    ("ops/miami/sync_nav_js.py", DEST_CT, "/opt/sync_nav_js.py"),
    ("ops/miami/records_status.py", DEST_CT, "/opt/records_status.py"),
    ("ops/miami/miami-refresh.sh", DEST_CT, "/opt/miami-refresh.sh"),
    ("ops/miami/mw-scan-donate.py", DEST_CT, "/opt/mw-scan-donate.py"),
    ("ops/miami/exposemiamiok_navigation_update.py", DEST_CT,
     "/usr/local/bin/exposemiamiok_navigation_update.py"),
]

# Never publish, whatever an allowlisted directory happens to contain.
EXCLUDE = ["*.pyc", "__pycache__", "*.log", "*.db", "*.mp4", "*.wav", "*.mp3",
           "*.pdf", "*.png", "*.jpg", ".env", "*.key", "*.pem", "secrets*",
           "credentials*", "*token*", "config.json", "node_modules"]


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=900, **kw)


def fetch(where, path, is_dir):
    """Read a file or directory as a base64 tarball, from node or container."""
    excl = " ".join(f"--exclude='{e}'" for e in EXCLUDE)
    if is_dir:
        cmd = f"test -d {path} && tar czf - {excl} -C {path} . | base64 -w0"
    else:
        cmd = (f"test -f {path} && tar czf - {excl} "
               f"-C {path.rsplit('/', 1)[0]} {path.rsplit('/', 1)[1]} | base64 -w0")
    if where == "node":
        return run(["bash", "-lc", cmd])
    return run(["pct", "exec", where, "--", "bash", "-lc", cmd])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--commit", action="store_true")
    args = ap.parse_args()

    failed = []
    total = 0
    for dest, where, path in SOURCES:
        is_dir = "." not in path.rsplit("/", 1)[-1]
        r = fetch(where, path, is_dir)
        if r.returncode != 0 or not r.stdout.strip():
            failed.append(f"{dest}: unreadable {path}")
            continue
        payload = r.stdout.strip()
        size = len(payload) * 3 // 4
        total += size
        if args.dry_run:
            print(f"  {dest:46} {size / 1e3:7.0f} KB (dry run)")
            continue

        target = f"{REPO}/{dest}"
        if is_dir:
            setup = f"rm -rf {target} && mkdir -p {target} && base64 -d | tar xzf - --no-same-owner -C {target}"
        else:
            parent = target.rsplit("/", 1)[0]
            setup = (f"mkdir -p {parent} && rm -f {target} && "
                     f"base64 -d | tar xzf - --no-same-owner -C {parent}")
        w = run(["pct", "exec", DEST_CT, "--", "bash", "-lc", setup], input=payload)
        if w.returncode != 0:
            failed.append(f"{dest}: write failed ({(w.stderr or '').strip()[:80]})")
            continue
        print(f"  {dest:46} {size / 1e3:7.0f} KB")

    print(f"\n{total / 1e6:.2f} MB, {len(SOURCES) - len(failed)}/{len(SOURCES)} sources")
    for f in failed:
        print(f"  FAILED {f}")
    if failed:
        return 1
    if args.dry_run:
        return 0

    # ── the gate ─────────────────────────────────────────────────────────────
    # /opt, not /tmp: a gate that vanishes on reboot is not a gate.
    scan = run(["pct", "exec", DEST_CT, "--", "bash", "-lc",
                f"python3 /opt/mw-secret-scan.py {REPO}/pipeline "
                f"{REPO}/pipeline-refresh {REPO}/ops 2>&1 | tail -25"])
    print("\nsecret scan of what would be published:")
    print("  " + (scan.stdout or "").strip().replace("\n", "\n  "))
    if "0 potential secret" not in (scan.stdout or ""):
        print("\nREFUSING to commit: the scan found something. Nothing was pushed.")
        return 2

    if args.commit:
        publish()
    return 0


def publish():
    q = ["pct", "exec", DEST_CT, "--", "bash", "-lc"]
    run(q + [f"cd {REPO} && git add pipeline pipeline-refresh ops"])
    staged = run(q + [f"cd {REPO} && git diff --cached --name-only | wc -l"]).stdout.strip()
    if staged == "0":
        print("\nsource unchanged - nothing to publish")
        return
    msg = f"Sync pipeline and ops source ({staged} files)"
    r = run(q + [f"cd {REPO} && git -c user.name='Move Weight Foundation' "
                 f"-c user.email='team@moveweight.com' commit -q -m '{msg}' && "
                 f"git push origin main 2>&1 | tail -2"])
    print(f"\npublished: {msg}")
    if r.stdout.strip():
        print("  " + r.stdout.strip().replace("\n", "\n  "))


if __name__ == "__main__":
    sys.exit(main())
