#!/usr/bin/env python3
"""
Mirror a chapter's primary documents to the Internet Archive.

    python3 shared/archive_to_ia.py mississippi --dry-run
    python3 shared/archive_to_ia.py mississippi

Everything this project publishes depends on a city continuing to host a PDF.
Cities re-platform, prune, and quietly drop things: San Angelo moved from
cosatx.us to sanangelo.gov this year, and seven Miami OK meeting directories sat
empty for four days because a pipeline wedged. A copy that only exists on our
server has the same single point of failure, just ours instead of theirs.

So each agenda, minutes set, packet and released record gets its own Internet
Archive item with the source URL, the capture date and the chapter recorded in
its metadata. Once it is there it is permanent, citable, and outside anyone's
ability to withdraw.

Credentials
-----------
This reads Internet Archive S3 keys and never a password. Create them at
https://archive.org/account/s3.php while logged in, then either:

    ia configure            # prompts, writes ~/.config/ia.ini
    export IA_ACCESS_KEY=... IA_SECRET_KEY=...

Uploading publishes publicly and cannot be fully undone, so --dry-run first.
"""

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    from internetarchive import get_item, get_session
except ImportError:
    sys.exit("pip install internetarchive")

COLLECTION = "opensource"          # the open community collection
LICENSE = "https://creativecommons.org/publicdomain/mark/1.0/"


def creds():
    a, s = os.environ.get("IA_ACCESS_KEY"), os.environ.get("IA_SECRET_KEY")
    if a and s:
        return {"access": a, "secret": s}
    cfg = Path.home() / ".config" / "ia.ini"
    if cfg.exists():
        return None            # library reads it itself
    sys.exit(
        "No Internet Archive credentials.\n"
        "  Create S3 keys at https://archive.org/account/s3.php then run:\n"
        "     ia configure\n"
        "  or export IA_ACCESS_KEY and IA_SECRET_KEY.")


def identifier(cfg, kind, slug):
    """Stable, collision-proof, and readable in a citation."""
    return f"mwf-{cfg['key']}-{kind}-{slug}".lower().replace("_", "-")[:100]


def gather(cfg, src):
    """Everything worth preserving, with the metadata to make it findable."""
    items = []
    city, state = cfg["city"], cfg["state"]

    mpath = src / "site" / "data" / "meetings.json"
    if mpath.exists():
        for m in json.loads(mpath.read_text(encoding="utf-8"))["meetings"]:
            base = src / "site" / "meetings" / "files"
            for kind, suffix in (("agenda", "-agenda.pdf"), ("minutes", "-minutes.pdf")):
                f = base / f"{m['slug']}{suffix}"
                if not f.exists():
                    continue
                items.append({
                    "id": identifier(cfg, kind, m["slug"]),
                    "files": [f],
                    "md": {
                        "title": f"{m['title']} — {kind} ({city}, {state})",
                        "mediatype": "texts",
                        "collection": COLLECTION,
                        "date": m["date"],
                        "creator": f"City of {city}",
                        "subject": ["public records", "city government", city,
                                    state, kind, "Move Weight Foundation"],
                        "source": m.get("source", ""),
                        "licenseurl": LICENSE,
                        "description": (
                            f"{kind.capitalize()} for the {m['title']} of {city}, {state}, "
                            f"as published by the city. Mirrored by the Move Weight "
                            f"Foundation on {date.today().isoformat()} so the record "
                            f"survives independently of the city's website. "
                            f"Source: {m.get('source', 'city agenda portal')}"),
                    },
                })

    docs = src / "site" / "documents" / "files"
    if docs.is_dir():
        for f in sorted(docs.glob("*.pdf")):
            items.append({
                "id": identifier(cfg, "doc", f.stem),
                "files": [f],
                "md": {
                    "title": f"{f.stem.replace('-', ' ')} ({city}, {state})",
                    "mediatype": "texts",
                    "collection": COLLECTION,
                    "creator": f"City of {city}",
                    "subject": ["public records", "released records", city, state,
                                "Move Weight Foundation"],
                    "licenseurl": LICENSE,
                    "description": (
                        f"Public record released by the City of {city}, {state} under "
                        f"the state public records act. Mirrored by the Move Weight "
                        f"Foundation on {date.today().isoformat()}, unaltered and "
                        f"unredacted, so it survives independently of the city's site."),
                },
            })
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("chapter")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--delay", type=float, default=45.0,
                    help="seconds between item creations")
    a = ap.parse_args()

    cfg = json.loads((ROOT / "chapters" / f"{a.chapter}.json").read_text(encoding="utf-8"))
    src = Path(cfg.get("source_dir") or (ROOT.parent / f"expose{a.chapter}"))
    src = src if src.is_absolute() else (ROOT / src).resolve()

    items = gather(cfg, src)
    if a.limit:
        items = items[:a.limit]
    total_mb = sum(f.stat().st_size for i in items for f in i["files"]) / 1024 / 1024
    print(f"  {len(items)} items, {total_mb:.0f} MB")

    if a.dry_run:
        for i in items[:8]:
            print(f"    {i['id']}  <- {i['files'][0].name}")
        if len(items) > 8:
            print(f"    ... and {len(items) - 8} more")
        print("  dry run — nothing uploaded")
        return

    creds()
    ledger_path = src / "site" / "data" / "ia-mirror.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() \
        else {"items": {}}

    done = skipped = failed = 0
    for i in items:
        if i["id"] in ledger["items"]:
            skipped += 1
            continue
        try:
            item = get_item(i["id"])
            if item.exists:
                ledger["items"][i["id"]] = {"url": f"https://archive.org/details/{i['id']}",
                                            "status": "already-present"}
                skipped += 1
                continue
            item.upload([str(f) for f in i["files"]], metadata=i["md"],
                        retries=3, retries_sleep=10, verbose=False)
            ledger["items"][i["id"]] = {
                "url": f"https://archive.org/details/{i['id']}",
                "uploaded": date.today().isoformat()}
            done += 1
            print(f"    ok  {i['id']}", flush=True)
            # Internet Archive throttles *item creation* hard, especially for a
            # young account: uploading 26 items 1.5s apart got 19 of them
            # rejected as spam. Creating a new item is expensive on their side;
            # be a slow, obvious guest rather than a fast, suspicious one.
            time.sleep(a.delay)
        except Exception as exc:      # noqa: BLE001
            msg = str(exc)
            if "reduce your request rate" in msg or "appears to be spam" in msg:
                backoff = max(a.delay * 4, 300)
                print(f"    rate-limited on {i['id']} — backing off {backoff:.0f}s",
                      flush=True)
                time.sleep(backoff)
                try:
                    get_item(i["id"]).upload(
                        [str(f) for f in i["files"]], metadata=i["md"],
                        retries=3, retries_sleep=30, verbose=False)
                    ledger["items"][i["id"]] = {
                        "url": f"https://archive.org/details/{i['id']}",
                        "uploaded": date.today().isoformat()}
                    done += 1
                    print(f"    ok  {i['id']} (after backoff)", flush=True)
                    time.sleep(a.delay)
                    continue
                except Exception as exc2:             # noqa: BLE001
                    exc = exc2
            failed += 1
            print(f"    FAIL {i['id']}: {type(exc).__name__} {exc}", flush=True)
            # Save as we go: a run this slow must survive interruption.
            ledger_path.parent.mkdir(parents=True, exist_ok=True)
            ledger_path.write_text(json.dumps(ledger, indent=1), encoding="utf-8")

    ledger["updated"] = date.today().isoformat()
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, indent=1), encoding="utf-8")
    print(f"  uploaded {done}, already there {skipped}, failed {failed}")
    print(f"  ledger: {ledger_path}")


if __name__ == "__main__":
    main()
