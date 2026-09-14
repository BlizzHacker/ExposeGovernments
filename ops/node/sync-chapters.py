#!/usr/bin/env python3
"""Collect every chapter's published site into the ExposeGovernments repo.

The job runs on the operator-approved Proxmox entry node. Containers 175 and
176 currently live on the `slimmer` cluster node, so their reads are relayed
from the entry node over the cluster SSH link. No guest IP is contacted.
"""

import argparse
import os
import shlex
import subprocess

DEST_CT = "170"
DEST_REPO = os.environ.get("EXPOSE_SYNC_REPO", "/opt/expose-sync-worktree")
SYNC_BRANCH = os.environ.get("EXPOSE_SYNC_BRANCH", "sync/expose-chapters")
DEST = DEST_REPO + "/chapters"
VMID_NODES = {"175": "root@slimmer", "176": "root@slimmer"}
SSH_OPTIONS = ["-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new"]

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
EXCLUDE = ["*.mp4", "*.wav", "*.mp3", "*.pdf", "*.db", "*.log", "__pycache__", "*.pyc"]


def run(command, **options):
    return subprocess.run(command, capture_output=True, text=True, timeout=900, **options)


def pct_command(vmid, arguments):
    command = ["pct", *arguments[:1], vmid, *arguments[1:]]
    target = VMID_NODES.get(vmid)
    if not target:
        return command
    return ["ssh", *SSH_OPTIONS, target, shlex.join(command)]


def read_chapter(vmid, web_root, exclude_flags):
    shell_command = "test -d {} && tar czf - {} -C {} . | base64 -w0".format(
        shlex.quote(web_root), exclude_flags, shlex.quote(web_root)
    )
    return run(pct_command(vmid, ["exec", "--", "bash", "-lc", shell_command]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--commit", action="store_true", help="commit and push chapters/ if changed")
    args = parser.parse_args()
    branch_check = "test \"$(git -C {} branch --show-current)\" = {}".format(
        shlex.quote(DEST_REPO), shlex.quote(SYNC_BRANCH)
    )
    if not args.dry_run:
        branch_check += " && test -z \"$(git -C {} status --porcelain)\"".format(
            shlex.quote(DEST_REPO)
        )
        branch_check += " && git -C {} pull --ff-only origin main".format(
            shlex.quote(DEST_REPO)
        )
    preflight = run(pct_command(DEST_CT, ["exec", "--", "bash", "-lc", branch_check]))
    if preflight.returncode != 0:
        raise SystemExit("sync worktree preflight failed: " + (preflight.stderr or "").strip())

    exclude_flags = " ".join("--exclude={}".format(shlex.quote(value)) for value in EXCLUDE)
    total = 0
    failed = []

    for key, vmid, web_root in CHAPTERS:
        result = read_chapter(vmid, web_root, exclude_flags)
        if result.returncode != 0 or not result.stdout.strip():
            failed.append("{}: read failed ({})".format(key, (result.stderr or "").strip()[:120]))
            continue
        payload = result.stdout.strip()
        size = len(payload) * 3 // 4
        total += size
        if args.dry_run:
            print("  {:14} {:6.1f} MB (dry run)".format(key, size / 1e6))
            continue

        destination = "{}/{}".format(DEST, key)
        shell_command = (
            "rm -rf {destination} && mkdir -p {destination} && "
            "base64 -d | tar xzf - --no-same-owner -C {destination}"
        ).format(destination=shlex.quote(destination))
        written = run(
            pct_command(DEST_CT, ["exec", "--", "bash", "-lc", shell_command]), input=payload
        )
        if written.returncode != 0:
            failed.append("{}: write failed ({})".format(key, (written.stderr or "").strip()[:120]))
            continue
        count_command = "find {} -type f | wc -l".format(shlex.quote(destination))
        count = run(pct_command(DEST_CT, ["exec", "--", "bash", "-lc", count_command])).stdout.strip()
        print("  {:14} {:6.1f} MB {:>6} files".format(key, size / 1e6, count))

    print("{:.1f} MB across {} chapters".format(total / 1e6, len(CHAPTERS) - len(failed)))
    for failure in failed:
        print("  FAILED " + failure)
    if args.commit and not args.dry_run and not failed:
        commit_and_push()
    return 1 if failed else 0


def commit_and_push():
    stage = "git -C {} add chapters".format(shlex.quote(DEST_REPO))
    run(pct_command(DEST_CT, ["exec", "--", "bash", "-lc", stage]), check=True)
    count_command = "git -C {} diff --cached --name-only | wc -l".format(shlex.quote(DEST_REPO))
    count = run(pct_command(DEST_CT, ["exec", "--", "bash", "-lc", count_command]), check=True).stdout.strip()
    if count == "0":
        print("  chapters unchanged: nothing to publish")
        return
    message = "Sync chapter sites"
    command = (
        "git -C {repo} -c user.name='Move Weight Foundation' "
        "-c user.email='team@moveweight.com' commit -m {} -m {} && "
        "git -C {repo} push origin HEAD:main"
    ).format(
        shlex.quote(message),
        shlex.quote("Refresh the tracked chapter mirrors from their live web roots."),
        repo=shlex.quote(DEST_REPO),
    )
    result = run(pct_command(DEST_CT, ["exec", "--", "bash", "-lc", command]))
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or result.stdout.strip())


if __name__ == "__main__":
    raise SystemExit(main())
