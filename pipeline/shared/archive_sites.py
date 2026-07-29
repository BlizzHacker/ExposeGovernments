#!/usr/bin/env python3
"""
Push every published page of every chapter into the Internet Archive.

    python3 shared/archive_sites.py --dry-run
    python3 shared/archive_sites.py                 # Wayback snapshots
    python3 shared/archive_sites.py --items         # + per-chapter IA items

Two different kinds of permanence, and the project needs both:

  Wayback snapshots  every page as it looked on a date, at a citable URL, with
                     no credentials required. This is what survives us losing a
                     server, a domain, or interest.
  IA items           a durable object per chapter holding its meeting index and
                     agenda text, with metadata, that can be cited and
                     downloaded whole.

Miami OK already has 510 meeting items from its own uploader. This does not
touch those; it covers the thirteen chapters that had nothing and the site pages
that were never archived anywhere.

On the account
--------------
Uploads land under whichever account's S3 keys are configured, and archive.org
files them under that uploader. The Foundation's archive account is
@move_weight_foundation_archive; the keys currently on the node belong to
`exposemiamiok`. Set IA_ACCESS_KEY / IA_SECRET_KEY, or point IA_CONFIG at an
ia.ini for the account you want. Nothing here assumes which one it is.

Save Page Now is rate limited and rejects bursts, so the sweep is paced. Being
slow is fine; the archive is forever.
"""

import argparse
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHAPTERS = ROOT / "chapters"

UA = ("Mozilla/5.0 (compatible; MoveWeightFoundation/1.0; "
      "+https://foundation.moveweight.com) archival-snapshot")
SAVE = "https://web.archive.org/save/"
AVAIL = "https://archive.org/wayback/available?url="

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


MANIFEST = ROOT / "generated" / "archive-manifest.json"


def get(url, timeout=90, method="GET"):
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method=method)
    with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
        return r.status, r.read().decode("utf-8", "replace")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Save Page Now answers with a 302 whose Location IS the new snapshot.

    urllib follows it by default, which throws away the one piece of information
    worth keeping and costs a second fetch of the archived page.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise _Redirected(newurl)


class _Redirected(Exception):
    def __init__(self, location):
        super().__init__(location)
        self.location = location


_OPENER = urllib.request.build_opener(_NoRedirect,
                                      urllib.request.HTTPSHandler(context=_CTX))


def load_manifest():
    if MANIFEST.exists():
        try:
            return json.loads(MANIFEST.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"generated_at": "", "snapshots": {}}


def save_manifest(m):
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    m["generated_at"] = date.today().isoformat()
    MANIFEST.write_text(json.dumps(m, indent=2, sort_keys=True), encoding="utf-8")


def hosts_and_pages():
    """Every chapter host and the pages it publishes, from the built sites."""
    out = {}
    for p in sorted(CHAPTERS.glob("*.json")):
        if p.stem.startswith("_"):
            continue
        cfg = json.loads(p.read_text(encoding="utf-8"))
        host = cfg.get("canonical_host") or cfg["domain"]
        site = (ROOT / cfg.get("source_dir", "") / "site").resolve()
        pages = ["/"]
        if site.is_dir():
            for f in sorted(site.rglob("*.html")):
                rel = f.relative_to(site).as_posix()
                # One snapshot per meeting page would be thousands of requests
                # against a rate-limited service to archive a table of links
                # whose targets are the city's, not ours.
                if rel.startswith(("meetings/", "transcripts/", "agenda-packets/")):
                    continue
                pages.append("/" if rel == "index.html" else "/" + rel)
        out[host] = (cfg, sorted(set(pages)))
    # The hubs and the Foundation itself are not chapters but are the front doors.
    for extra in ("foundation.moveweight.com", "exposeoklahoma.com",
                  "exposetexas.org", "exposemississippi.com"):
        out.setdefault(extra, (None, ["/"]))
    return out


def already_archived(url, within_days=30, manifest=None):
    """Skip anything the Wayback Machine captured recently.

    The local manifest is checked first and is authoritative. The availability
    API lags Save Page Now by hours - a page captured minutes ago still reports
    no snapshot - so trusting it alone means re-archiving the whole estate on
    every run and reporting successful captures as failures.

    Returns (is_current, snapshot_url, captured_date). The snapshot is handed
    back so a skipped page still gets recorded: the availability API already
    told us where the capture is, and discarding that left 50 of 145 pages
    archived but absent from our own index of them.
    """
    if manifest:
        rec = manifest.get("snapshots", {}).get(url)
        if rec:
            try:
                d = date.fromisoformat(rec["captured"])
                if (date.today() - d).days < within_days:
                    return True, rec.get("snapshot", ""), rec["captured"]
            except (ValueError, KeyError, TypeError):
                pass
    try:
        _, body = get(AVAIL + urllib.parse.quote(url, safe=""), timeout=45)
        snap = json.loads(body).get("archived_snapshots", {}).get("closest")
        if not snap or not snap.get("available"):
            return False, "", ""
        ts = snap.get("timestamp", "")
        if len(ts) < 8:
            return False, "", ""
        d = date(int(ts[:4]), int(ts[4:6]), int(ts[6:8]))
        return ((date.today() - d).days < within_days,
                snap.get("url") or f"https://web.archive.org/web/{ts}/{url}",
                d.isoformat())
    except Exception:  # noqa: BLE001 - if we cannot tell, archive it
        return False, "", ""


def ia_keys():
    """S3 keys for authenticated Save Page Now.

    Authentication here only buys rate limit. A Wayback capture is not owned by
    whoever requested it - unlike an item upload, which is filed under the
    uploader - so using whichever keys are on the box carries none of the
    account-attribution problem that `--items` does.
    """
    ak = os.environ.get("IA_ACCESS_KEY")
    sk = os.environ.get("IA_SECRET_KEY")
    if ak and sk:
        return ak, sk
    for p in (Path(os.environ.get("IA_CONFIG", "")),
              Path.home() / ".config" / "internetarchive" / "ia.ini",
              Path("/root/.config/internetarchive/ia.ini")):
        if p and p.is_file():
            vals = {}
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                if "=" in line:
                    k, _, v = line.partition("=")
                    vals[k.strip()] = v.strip()
            if vals.get("access") and vals.get("secret"):
                return vals["access"], vals["secret"]
    return None, None


def save_auth(url, keys, delay, poll_max=240):
    """Capture one page through the SPN2 API. Returns (snapshot_url, error).

    Anonymous /save/ is throttled to roughly one page every two minutes, which
    turns a 146-page sweep into a three-hour run that outlives its own timeout.
    Authenticated SPN2 answers with a job id immediately and is polled.
    """
    body = urllib.parse.urlencode({"url": url, "skip_first_archive": "1"}).encode()
    req = urllib.request.Request(
        "https://web.archive.org/save", data=body,
        headers={"User-Agent": UA, "Accept": "application/json",
                 "Authorization": f"LOW {keys[0]}:{keys[1]}",
                 "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=90, context=_CTX) as r:
            job = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        time.sleep(delay * (6 if e.code == 429 else 1))
        return "", f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        time.sleep(delay)
        return "", type(e).__name__

    jid = job.get("job_id")
    if not jid:
        # SPN says no before it starts: usually the daily quota or a blocked host.
        return "", (job.get("message") or "no job_id")[:90]

    waited = 0
    while waited < poll_max:
        time.sleep(delay)
        waited += delay
        try:
            _, body = get(f"https://web.archive.org/save/status/{jid}", timeout=60)
            st = json.loads(body)
        except Exception:  # noqa: BLE001 - a failed poll is not a failed capture
            continue
        if st.get("status") == "success":
            ts = st.get("timestamp", "")
            return (f"https://web.archive.org/web/{ts}/{url}" if ts else ""), \
                   ("" if ts else "success without timestamp")
        if st.get("status") == "error":
            return "", (st.get("message") or "error")[:90]
    return "", f"still pending after {poll_max}s"


def save(url, delay):
    """Capture one page anonymously. Returns (snapshot_url, error).

    A capture we cannot cite is not evidence, so the snapshot URL is the return
    value rather than a status code.
    """
    try:
        req = urllib.request.Request(SAVE + url, headers={"User-Agent": UA})
        with _OPENER.open(req, timeout=180) as r:
            # A 200 means SPN rendered the interstitial rather than redirecting;
            # the capture still happened but it does not hand us the URL.
            body = r.read().decode("utf-8", "replace")
            time.sleep(delay)
            m = re.search(r"/web/(\d{14})/", body)
            return (f"https://web.archive.org/web/{m.group(1)}/{url}"
                    if m else ""), ("" if m else "no snapshot url in response")
    except _Redirected as e:
        time.sleep(delay)
        return e.location, ""
    except urllib.error.HTTPError as e:
        # 429 is the one to respect rather than retry into.
        time.sleep(delay * (6 if e.code == 429 else 2))
        return "", f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        time.sleep(delay)
        return "", type(e).__name__


def sweep(dry, delay, force, quiet=False, anon=False):
    manifest = load_manifest()
    snaps = manifest.setdefault("snapshots", {})
    keys = (None, None) if anon else ia_keys()
    if not dry:
        print("  mode: " + ("anonymous /save/ (slow, ~1 page per 2 min)"
                            if not keys[0] else "authenticated SPN2"))
    # Failures are recorded per URL, not just counted. A run that says "10
    # failed" and does not say which ten cannot be acted on, and the only way I
    # found them the first time was diffing the manifest against the page list.
    fails = manifest.setdefault("failures", {})
    saved = skipped = failed = 0
    for host, (cfg, pages) in hosts_and_pages().items():
        hs = hf = hk = 0
        first_err = ""
        for path in pages:
            url = f"https://{host}{path}"
            if not force:
                current, snap_url, when = already_archived(url, manifest=manifest)
                if current:
                    if snap_url:
                        snaps[url] = {"captured": when, "snapshot": snap_url}
                    hk += 1
                    continue
            if dry:
                hs += 1
                continue
            snap, err = (save_auth(url, keys, delay) if keys[0]
                         else save(url, delay))
            # SPN returns a bare "Job failed." that is usually transient - the
            # same two URLs that failed twice captured cleanly in 13s on a third
            # attempt. One retry costs seconds and closes a permanent gap.
            if not snap and keys[0] and "Job failed" in err:
                time.sleep(delay * 2)
                snap, err = save_auth(url, keys, delay)
            if snap:
                snaps[url] = {"captured": date.today().isoformat(), "snapshot": snap}
                fails.pop(url, None)
                hs += 1
            else:
                fails[url] = {"when": date.today().isoformat(), "error": err}
                hf += 1
                first_err = first_err or err
        saved += hs
        skipped += hk
        failed += hf
        # Flushed per host: a sweep of 146 pages at 6s apart runs for a quarter
        # of an hour, and an interrupted run must not lose what it captured.
        if not dry:
            save_manifest(manifest)
        if not quiet:
            print(f"  {host:36s} {hs:3d} archived  {hk:3d} already current"
                  + (f"  {hf} failed ({first_err})" if hf else ""))
    print(f"\n  {saved} pages archived, {skipped} already current, {failed} failed")
    if failed and not dry:
        print("  failures:")
        for u, f in sorted(fails.items()):
            if f.get("when") == date.today().isoformat():
                print(f"    {u}  -  {f['error']}")
    if not dry:
        print(f"  manifest: {MANIFEST}")
    return failed


# ─── per-chapter IA items ──────────────────────────────────────────────
def item_complete(ident, expected):
    """Whether the item holds every file it is supposed to.

    Not "does the item exist": a partial upload leaves a real item that looks
    fine from outside. Lubbock's meetings.json landed and its agenda index did
    not, so an existence check would have marked it done forever and the agenda
    text would never have reached the archive.

    The metadata endpoint answers immediately - unlike the search index, which
    lags by hours and reports a just-created item as absent.
    """
    want = {Path(f).name for f in expected}
    try:
        # Retried once: a single slow metadata call made Houston look incomplete
        # when it was fine, which would have re-uploaded it for no reason.
        try:
            _, body = get(f"https://archive.org/metadata/{ident}", timeout=45)
        except Exception:  # noqa: BLE001
            time.sleep(3)
            _, body = get(f"https://archive.org/metadata/{ident}", timeout=60)
        d = json.loads(body)
        if not d.get("metadata"):
            # No item at all: it needs everything, not nothing. Returning an
            # empty gap set here printed "needs []" against the five chapters
            # that were entirely absent.
            return False, want
        have = {f["name"] for f in d.get("files", [])}
        return want <= have, want - have
    except Exception:  # noqa: BLE001 - if we cannot tell, try the upload
        return False, want


def upload_items(dry, quiet=False, gap=90.0):
    """Create one Internet Archive item per chapter.

    `gap` is the pause between item CREATIONS, which is a different and much
    tighter limit than uploading files into an item that already exists. At two
    seconds, six of eleven landed and the last four failed consecutively -
    the signature of a creation rate limit rather than bad data. Skipping items
    that already exist makes a re-run cheap, so being slow costs nothing.
    """
    try:
        from internetarchive import get_item, upload  # noqa: F401
    except ImportError:
        print("  ! the `internetarchive` package is not installed here")
        return 1

    # Deliberately NOT falling back to ia_keys(). That helper finds the ia.ini on
    # the box, which belongs to `exposemiamiok`; an item is filed under whoever
    # uploads it, so a silent fallback would scatter the Foundation's collection
    # across two accounts and take a support ticket to undo. The Wayback sweep
    # can use whatever keys it finds because captures are not owned. Items cannot.
    ak = os.environ.get("IA_ACCESS_KEY")
    sk = os.environ.get("IA_SECRET_KEY")
    if not dry and not (ak and sk):
        print("  ! set IA_ACCESS_KEY and IA_SECRET_KEY for the account that should\n"
              "    own these items. Refusing to guess - uploads are attributed to\n"
              "    the uploader and cannot be reassigned without a support request.")
        return 1
    n = skipped = bad = 0
    for p in sorted(CHAPTERS.glob("*.json")):
        if p.stem.startswith("_"):
            continue
        cfg = json.loads(p.read_text(encoding="utf-8"))
        src = (ROOT / cfg.get("source_dir", "")).resolve()
        meetings = src / "generated" / "meetings.json"
        if not meetings.exists():
            continue

        host = cfg.get("canonical_host") or cfg["domain"]
        ident = f"moveweight-{cfg['key']}-meetings"
        files = [str(meetings)]
        agendas = src / "generated" / "agendas" / "index.json"
        if agendas.exists():
            files.append(str(agendas))

        md = {
            "title": f"{cfg['city']}, {cfg['state_abbr']} - public meeting index "
                     f"({date.today().isoformat()})",
            "collection": "opensource",
            "mediatype": "texts",
            "creator": "Move Weight Foundation",
            "subject": ["public records", "open government", cfg["city"],
                        cfg["state"], cfg["county"]],
            "description": (
                f"Machine-readable index of public meetings for {cfg['city']}, "
                f"{cfg['county']}, {cfg['state']}, compiled by the Move Weight "
                f"Foundation from the city's own agenda portal "
                f"({cfg.get('portal', {}).get('portal_url', '')}). Published at "
                f"https://{host}/ . Each record carries the meeting date, body, "
                f"and links to the city's own agenda, minutes and video. "
                f"The Foundation does not rehost the city's documents; this is "
                f"the index and the extracted text used to make them searchable."),
            "licenseurl": "https://creativecommons.org/publicdomain/zero/1.0/",
            "source": f"https://{host}/",
        }
        # Checked before the dry branch so a dry run reports what would actually
        # happen rather than listing every chapter as pending.
        done, gaps = item_complete(ident, files)
        if done:
            if not quiet:
                print(f"  --   {ident} complete")
            skipped += 1
            continue
        if dry:
            print(f"    DRY  {ident}  needs {sorted(gaps)}")
            n += 1
            continue

        # Two attempts. A transient DNS failure on the node killed two uploads
        # outright, and a single retry is the whole fix.
        for attempt in (1, 2):
            try:
                upload(ident, files=files, metadata=md,
                       access_key=ak, secret_key=sk, verbose=False)
                print(f"  ok   https://archive.org/details/{ident}")
                n += 1
                time.sleep(gap)
                break
            except Exception as e:  # noqa: BLE001 - one chapter must not stop the rest
                msg = str(e)
                # Archive.org answers a too-fast run with "Please reduce your
                # request rate" and calls the account spam. Pushing on after that
                # deepens the flag against a real charity's account, so stop and
                # let the operator come back later.
                if "reduce your request rate" in msg or "appears to be spam" in msg:
                    bad += 1
                    print(f"  !    {ident}: rate limited by archive.org")
                    print("\n  ! archive.org is rate limiting this account. Stopping.\n"
                          "    Wait several hours, then re-run - completed items are\n"
                          "    skipped, so it resumes where it left off.")
                    print(f"\n  {n} uploaded, {skipped} complete already, {bad} failed")
                    return bad
                if attempt == 1:
                    time.sleep(gap * 3)
                    continue
                bad += 1
                print(f"  !    {ident}: {type(e).__name__}: {msg[:160]}")
    print(f"\n  {n} uploaded, {skipped} complete already, {bad} failed")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--items", action="store_true",
                    help="also upload a per-chapter IA item")
    ap.add_argument("--no-pages", action="store_true",
                    help="skip the Wayback sweep")
    ap.add_argument("--delay", type=float, default=6.0,
                    help="seconds between Save Page Now calls")
    ap.add_argument("--force", action="store_true",
                    help="re-archive even if a recent snapshot exists")
    # 90s, not 20s. Creating eleven items at a 2s gap got the account flagged as
    # spam by archive.org; being slow here is cheaper than being explained to a
    # human at info@archive.org.
    ap.add_argument("--item-gap", type=float, default=90.0,
                    help="seconds between Internet Archive item creations")
    ap.add_argument("--anon", action="store_true",
                    help="force anonymous Save Page Now even if keys exist")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    rc = 0
    if not args.no_pages:
        print("== Wayback snapshots")
        rc |= sweep(args.dry_run, args.delay, args.force, args.quiet, args.anon)
    if args.items:
        print("\n== per-chapter Internet Archive items")
        rc |= upload_items(args.dry_run, args.quiet, args.item_gap)
    return rc


if __name__ == "__main__":
    sys.exit(main())
