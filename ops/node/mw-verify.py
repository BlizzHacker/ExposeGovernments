#!/usr/bin/env python3
"""Assert the invariants the Expose estate kept losing silently.

    python3 /opt/mw-verify.py            # full run
    python3 /opt/mw-verify.py --quick    # skip the settle test (the slow one)

Runs on the Proxmox host so it can see inside every chapter container as well
as the public sites. Exits non-zero if any check fails, so systemd marks the
unit failed rather than logging a wall of green nobody reads.

Every check here exists because the thing it checks actually broke, and broke
without any dashboard noticing:

  nav source     Miami's navigation lived in FIVE places - nav_constants.py,
                 the page HTML, exposemiami-ui.js, and two hourly generators
                 that rewrote the others. Fixes reverted within the hour.
  settle         Two writers rebuilt the same nav markup with different
                 whitespace and rewrote each other's output on 770 pages every
                 hour, forever, without either converging.
  asset stamps   ?v= was a hand-typed constant, so editing an asset did not
                 change the URL and returning readers kept the cached copy.
  stacking       .chapterbar opens a stacking context, so the chapter picker
                 opened underneath the header; the shell had been pinned at
                 z-index 2147483000 to win an arms race.
  timers         mw-standardize.timer read enabled AND active while its next
                 elapse was "infinity" - it had not fired for six hours.
"""

import argparse
import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

MIAMI_CT = "170"
CHAPTER_CTS = {"170": "Oklahoma", "175": "Texas", "176": "Mississippi"}
MIAMI_HOST = "https://miami.exposeoklahoma.com"
ASSETS = "/var/www/exposemiamiok/html/assets"

# Bar must outrank the header, or its dropdown opens behind it.
MIN_BAR_Z = 9000

HOSTS = [
    "foundation.moveweight.com",
    "exposeoklahoma.com", "miami.exposeoklahoma.com", "okc.exposeoklahoma.com",
    "tulsa.exposeoklahoma.com", "claremore.exposeoklahoma.com",
    "exposetexas.org", "sanangelo.exposetexas.org", "houston.exposetexas.org",
    "dallas.exposetexas.org", "austin.exposetexas.org",
    "sanantonio.exposetexas.org", "lubbock.exposetexas.org",
    "abilene.exposetexas.org",
    "exposemississippi.com", "southaven.exposemississippi.com",
    "jackson.exposemississippi.com", "olivebranch.exposemississippi.com",
]

# name -> (container, kind). Timers must have a future elapse; cron must exist.
SCHEDULES = [
    ("170", "timer", "mw-standardize.timer"),
    ("170", "timer", "miami-refresh.timer"),
    ("170", "cron", "exposemiamiok-automation"),
]

failures = []
notes = []


def fail(check, detail):
    failures.append((check, detail))
    print(f"  FAIL  {check}: {detail}")


def ok(check, detail=""):
    print(f"  ok    {check}{(': ' + detail) if detail else ''}")


def pct(ct, script):
    """Run python inside a container and return stdout."""
    r = subprocess.run(["pct", "exec", ct, "--", "python3", "-c", script],
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f"pct exec {ct} failed: {r.stderr.strip()[:300]}")
    return r.stdout


def pct_sh(ct, cmd, timeout=600):
    r = subprocess.run(["pct", "exec", ct, "--", "bash", "-lc", cmd],
                       capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def http(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "mw-verify"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        return f"ERR {type(e).__name__}", b""


# ── 1. one nav source, and the built JS matches it ────────────────────────────
def check_nav_source():
    print("\n[nav] single source of truth")
    probe = (
        "import sys, json, re, pathlib, hashlib;"
        "sys.path.insert(0,'/opt');"
        "from nav_constants import NAV_ITEMS;"
        "js=pathlib.Path('%s/exposemiami-ui.js').read_text(errors='replace');"
        "m=re.search(r'const navItems = \\[(.*?)\\n  \\]', js, re.S);"
        "arr=re.findall(r'\\[\"([^\"]*)\", \"([^\"]*)\"\\]', m.group(1)) if m else [];"
        "print(json.dumps({'nav':[list(x) for x in NAV_ITEMS],'js':[list(x) for x in arr]}))"
        % ASSETS
    )
    data = json.loads(pct(MIAMI_CT, probe))
    nav = [tuple(x) for x in data["nav"]]
    js = [tuple(x) for x in data["js"]]

    if not js:
        fail("nav/js-array", "could not parse navItems out of exposemiami-ui.js")
    elif js != nav:
        only_js = [x for x in js if x not in nav]
        only_nav = [x for x in nav if x not in js]
        fail("nav/js-matches-source",
             f"js has {len(js)} items, nav_constants has {len(nav)}; "
             f"js-only={only_js[:3]} source-only={only_nav[:3]}")
    else:
        ok("nav/js-matches-source", f"{len(nav)} items")

    hrefs = [h for h, _ in nav]
    labels = [l for _, l in nav]
    dup_h = sorted({h for h in hrefs if hrefs.count(h) > 1})
    dup_l = sorted({l for l in labels if labels.count(l) > 1})
    if dup_h:
        fail("nav/no-duplicate-href", str(dup_h))
    else:
        ok("nav/no-duplicate-href")
    if dup_l:
        fail("nav/no-duplicate-label", str(dup_l))
    else:
        ok("nav/no-duplicate-label")
    return nav


# ── 2. every nav target resolves ──────────────────────────────────────────────
def check_nav_targets(nav):
    print("\n[nav] targets resolve")
    bad = []
    for href, label in nav:
        path = href.split("#")[0] or "/"
        code, body = http(MIAMI_HOST + path)
        if code != 200 or len(body) < 500:
            bad.append(f"{label} {href} -> {code}/{len(body)}b")
    if bad:
        fail("nav/targets-200", "; ".join(bad))
    else:
        ok("nav/targets-200", f"{len(nav)}/{len(nav)}")


# ── 3. no NEW hardcoded nav copy has appeared ─────────────────────────────────
def check_no_new_copies():
    print("\n[nav] no new hardcoded copies")
    probe = r'''
import pathlib, re, json
SOURCE = "/opt/nav_constants.py"
# A nav pair is ["/path" or "https://...", "Label"] where the label is prose.
# Deliberately narrow: the job runners spell commands as ["python3", "/opt/x.py"]
# and an earlier version of this check flagged every one of them.
pair = re.compile(r'\[\s*"(?:/[^"]*|https?://[^"]*)"\s*,\s*"[A-Z][^"/]*"\s*\]')
out = []
for d in ("/usr/local/bin", "/opt"):
    for p in pathlib.Path(d).glob("*.py"):
        if str(p) == SOURCE:          # the one place the list is allowed to live
            continue
        try:
            t = p.read_text(errors="replace")
        except OSError:
            continue
        if "exposemiami-ui.js" not in t and "dnav-inner" not in t:
            continue
        if "from nav_constants import" in t:
            continue
        if len(pair.findall(t)) >= 8:
            out.append(str(p))
print(json.dumps(out))
'''
    rogue = json.loads(pct(MIAMI_CT, probe))
    retired = "/usr/local/bin/exposemiamiok_navigation_grouped_update.py"
    live = [r for r in rogue if r != retired]
    if live:
        fail("nav/no-extra-copies",
             f"script(s) carrying their own nav list: {live}")
    else:
        ok("nav/no-extra-copies")

    # The retired generator may keep its list, but only while it cannot run.
    rc, out, _ = pct_sh(
        MIAMI_CT,
        f"test -f {retired} && grep -c RETIRED-20260728 {retired} || echo absent")
    state = out.strip()
    if state == "absent":
        ok("nav/retired-generator", "removed")
    elif state.isdigit() and int(state) > 0:
        rc2, out2, _ = pct_sh(
            MIAMI_CT, "grep -rl navigation_grouped_update /etc/cron.d "
                      "/usr/local/bin/exposemiamiok_auto_update.py 2>/dev/null || true")
        if out2.strip():
            fail("nav/retired-generator",
                 f"guarded but still referenced by: {out2.split()}")
        else:
            ok("nav/retired-generator", "guarded and unscheduled")
    else:
        fail("nav/retired-generator",
             "present, UNGUARDED - running it restores the old nav on every page")


# ── 4. asset stamps are content-derived ───────────────────────────────────────
def check_asset_stamps():
    print("\n[assets] cache-busting stamps match file contents")
    probe = (
        "import hashlib, pathlib, json;"
        "A=pathlib.Path('%s');"
        "print(json.dumps({n: hashlib.sha256((A/n).read_bytes()).hexdigest()[:8]"
        " for n in ('exposemiami-ui.js','exposemiami-theme.css')}))" % ASSETS
    )
    want = json.loads(pct(MIAMI_CT, probe))
    code, body = http(MIAMI_HOST + "/")
    if code != 200:
        fail("assets/homepage", f"homepage returned {code}")
        return
    html = body.decode("utf-8", "replace")
    for name, key in (("exposemiami-ui.js", "js"), ("exposemiami-theme.css", "css")):
        m = re.search(re.escape(name) + r"\?v=([\w.-]+)", html)
        if not m:
            fail(f"assets/{key}-stamped", f"{name} has no ?v= on the homepage")
        elif m.group(1) != want[name]:
            fail(f"assets/{key}-stamped",
                 f"page asks for {m.group(1)}, file hashes to {want[name]}")
        else:
            ok(f"assets/{key}-stamped", want[name])


# ── 5. the two writers converge ───────────────────────────────────────────────
def _writer_round():
    rc, out, err = pct_sh(
        MIAMI_CT,
        "python3 /usr/local/bin/exposemiamiok_navigation_update.py "
        "&& cd /opt && python3 mw-standardize.py", timeout=900)
    if rc != 0:
        return None, None, (err or out).strip()[-200:]
    m_nav = re.search(r"changed=(\d+)", out)
    m_std = re.search(r"updated (\d+) pages", out)
    return (int(m_nav.group(1)) if m_nav else -1,
            int(m_std.group(1)) if m_std else -1, None)


def check_settle():
    print("\n[writers] navigation_update and mw-standardize both settle")
    # Two rounds, and only the SECOND has to be zero. The first legitimately
    # has work whenever an hourly generator has regenerated pages since the
    # last standardise - demanding zero on the first pass just flags normal
    # healing as a fight. What must never happen is the pair failing to
    # converge, which is what a non-zero second round means.
    first_nav, first_std, err = _writer_round()
    if err:
        fail("writers/run", err)
        return
    nav_changed, std_changed, err = _writer_round()
    if err:
        fail("writers/run", err)
        return
    if nav_changed != 0 or std_changed != 0:
        fail("writers/settled",
             f"second round still changing: navigation_update={nav_changed}, "
             f"mw-standardize={std_changed} - they are rewriting each other")
    else:
        detail = "both 0 on the second round"
        if first_nav or first_std:
            detail += f" (first round healed {first_nav}/{first_std})"
        ok("writers/settled", detail)


# ── 6. stacking: the bar outranks the header on every chapter ─────────────────
def check_stacking():
    print("\n[css] chapter bar outranks the header")
    probe = r'''
import pathlib, re, json
RULE = re.compile(r"(?<![-\w])\.chapterbar\s*\{([^}]*)\}")
COMMENT = re.compile(r"/\*.*?\*/", re.S)
out = {}
for css in sorted(pathlib.Path("/var/www").rglob("*.css")):
    try:
        t = css.read_text(errors="replace")
    except OSError:
        continue
    rules = RULE.findall(t)
    if not rules:
        continue
    body = COMMENT.sub("", rules[-1])
    z = re.search(r"z-index:\s*(\d+)", body)
    pos = re.search(r"position:\s*(\w+)", body)
    out[str(css)] = [int(z.group(1)) if z else None, pos.group(1) if pos else None]
print(json.dumps(out))
'''
    total = 0
    bad = []
    for ct in CHAPTER_CTS:
        for path, (z, pos) in json.loads(pct(ct, probe)).items():
            total += 1
            if z is None or z < MIN_BAR_Z or pos != "relative":
                bad.append(f"CT{ct} {path.split('/')[3]} z={z} position={pos}")
    if bad:
        fail("css/chapterbar-stacking", "; ".join(bad))
    else:
        ok("css/chapterbar-stacking", f"{total} stylesheets at z>={MIN_BAR_Z}")

    # Miami only: the shell must sit below the bar, not at max int.
    probe2 = (
        "import pathlib, re;"
        "t=pathlib.Path('%s/exposemiami-theme.css').read_text(errors='replace');"
        "ms=re.findall(r'\\.mw-unified-shell\\s*\\{([^}]*)\\}', t);"
        "zs=[int(m.group(1)) for m in (re.search(r'z-index:\\s*(\\d+)', b) for b in ms) if m];"
        "print(zs[-1] if zs else 'none')" % ASSETS
    )
    shell_z = pct(MIAMI_CT, probe2).strip()
    if shell_z == "none" or not shell_z.isdigit():
        fail("css/shell-z", f"could not read shell z-index ({shell_z})")
    elif int(shell_z) >= MIN_BAR_Z:
        fail("css/shell-z",
             f"shell z-index {shell_z} >= chapter bar {MIN_BAR_Z}; "
             "the picker will open behind the header")
    else:
        ok("css/shell-z", f"shell {shell_z} < bar {MIN_BAR_Z}")


# ── 7. schedulers are actually scheduled ──────────────────────────────────────
def _next_elapse(ct, name):
    """The timer's next fire time, or "" if systemd is not reporting one.

    Reads TimersCalendar as well as NextElapseUSecRealtime: for a calendar timer
    the computed next_elapse stays populated in TimersCalendar even at moments
    when the realtime property reads empty.
    """
    rc, out, _ = pct_sh(
        ct, f"systemctl show {name} -p NextElapseUSecRealtime -p TimersCalendar")
    m = re.search(r"NextElapseUSecRealtime=(.+)", out)
    if m and m.group(1).strip() and m.group(1).strip() != "infinity":
        return m.group(1).strip()
    m = re.search(r"next_elapse=([^;}]+)", out)
    if m and m.group(1).strip() and "infinity" not in m.group(1):
        return m.group(1).strip()
    return ""


def check_schedules():
    print("\n[systemd] schedulers armed")
    for ct, kind, name in SCHEDULES:
        if kind == "timer":
            # Sampled twice. While a timer's own service is mid-run systemd
            # briefly reports no next elapse, and a single sample landing in
            # that window called a perfectly healthy 15-minute timer dead.
            elapse = _next_elapse(ct, name)
            if not elapse:
                time.sleep(8)
                elapse = _next_elapse(ct, name)
            if elapse:
                ok(f"systemd/{name}", elapse)
            else:
                fail(f"systemd/{name}",
                     "no future elapse - the timer will never fire again "
                     "(enabled+active is not enough)")
        else:
            rc, out, _ = pct_sh(ct, f"test -f /etc/cron.d/{name} && echo present")
            if "present" in out:
                ok(f"cron/{name}")
            else:
                fail(f"cron/{name}", "missing")


# ── 8. donate links go somewhere ──────────────────────────────────────────────
def check_donate_links():
    """What a reader's donate button actually does, on the served page.

    This deliberately reads the live HTML, not the configs. A config-based
    version of this check passed green while Southaven's button still pointed at
    /about.html#funding: the URL is baked into a pre-rendered donate_banner, and
    the two refresh-managed chapters are built from a separate tree with its own
    chapters/*.json, so a correct config in the weekly tree proves nothing about
    what shipped.

    Delegates to /opt/mw-check-donate.py, which also verifies each campaign page
    returns 200, that no chapter links a neighbour's campaign, and that the hubs
    do not bill one city for a general donation.
    """
    print("\n[donate] buttons on the served pages")
    r = subprocess.run(["python3", "/opt/mw-check-donate.py"],
                       capture_output=True, text=True, timeout=600)
    out = (r.stdout or "").strip()
    if r.returncode == 0:
        chapters = out.count("\n  ok   ")
        ok("donate/live-buttons", f"{chapters} checks passed")
    else:
        bad_lines = [l.strip() for l in out.splitlines() if l.strip().startswith("BAD")]
        fail("donate/live-buttons", "; ".join(bad_lines)[:400]
             or (r.stderr or "").strip()[:200])


# ── 8b. every PAGE of a chapter funds that chapter ────────────────────────────
# (container, webroot, that chapter's campaign slug)
CHAPTER_SITES = [
    ("170", "/var/www/exposemiamiok/html", "miami-ok"),
    ("170", "/var/www/exposeokc/html", "oklahoma-city"),
    ("170", "/var/www/exposetulsa/html", "tulsa"),
    ("170", "/var/www/exposeclaremore/html", "claremore"),
    ("175", "/var/www/exposesanangelo/html", "san-angelo"),
    ("175", "/var/www/exposehouston/html", "houston"),
    ("175", "/var/www/exposedallas/html", "dallas"),
    ("175", "/var/www/exposeaustin/html", "austin"),
    ("175", "/var/www/exposesanantonio/html", "san-antonio"),
    ("175", "/var/www/exposelubbock/html", "lubbock"),
    ("175", "/var/www/exposeabilene/html", "abilene"),
    ("176", "/var/www/exposemississippi/html", "southaven"),
    ("176", "/var/www/exposejackson/html", "jackson"),
    ("176", "/var/www/exposeolivebranch/html", "olive-branch"),
]
SLUG_PREFIX = "fund-public-records-access-in-"


def check_donate_pages():
    """No page may fund a different chapter than the one it belongs to.

    The homepage check passed while 23 of OKC's 36 pages - everything under
    meetings/ and transcripts/ - carried MIAMI's campaign. They were stale
    deployed artifacts from before per-chapter campaigns existed, and nothing
    regenerated them, so no rebuild would ever have corrected it. Per-area
    attribution is the entire reason these campaigns are separate, and it was
    quietly wrong on the second-largest chapter.
    """
    print("\n[donate] every page funds its own chapter")
    total = wrong = 0
    detail = []
    for ct, root, slug in CHAPTER_SITES:
        rc, out, err = pct_sh(
            ct, f"python3 /opt/mw-scan-donate.py {root} {SLUG_PREFIX}{slug}",
            timeout=300)
        if rc != 0:
            fail("donate/per-page", f"scan failed in CT{ct} {root}: "
                                    f"{(err or out).strip()[:150]}")
            return
        m = re.search(r"pages=(\d+)", out)
        total += int(m.group(1)) if m else 0
        bad = re.search(r"-> (\d+) page\(s\) fund another chapter", out)
        if bad:
            wrong += int(bad.group(1))
            detail.append(f"{root.split('/')[3]}={bad.group(1)}")
    if wrong:
        fail("donate/per-page", f"{wrong} page(s) fund another chapter: "
                               f"{', '.join(detail)}")
    else:
        ok("donate/per-page", f"{total:,} pages across {len(CHAPTER_SITES)} chapters")


# ── 9. every chapter is reachable ─────────────────────────────────────────────
def check_hosts():
    print("\n[http] every chapter answers")
    bad = []
    for h in HOSTS:
        code, body = http(f"https://{h}/")
        if code != 200 or len(body) < 500:
            bad.append(f"{h} -> {code}")
    if bad:
        fail("http/chapters-200", "; ".join(bad))
    else:
        ok("http/chapters-200", f"{len(HOSTS)}/{len(HOSTS)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true",
                    help="skip the settle test, which runs both writers")
    args = ap.parse_args()

    print("mw-verify: Expose estate invariants")
    nav = check_nav_source()
    check_nav_targets(nav)
    check_no_new_copies()
    check_asset_stamps()
    if not args.quick:
        check_settle()
    check_stacking()
    check_schedules()
    check_donate_links()
    if not args.quick:
        # Walks ~1,500 files across three containers; the hourly pass skips it.
        check_donate_pages()
    check_hosts()

    print()
    for n in notes:
        print(f"  note  {n}")

    # A verdict on disk, so a failure is answerable without re-running the
    # checks - and so "when did this last actually pass?" has an answer. The
    # timer that died earlier looked healthy precisely because nothing recorded
    # its last real success.
    status = {
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "quick" if args.quick else "full",
        "ok": not failures,
        "failures": [{"check": c, "detail": d} for c, d in failures],
        "notes": notes,
    }
    try:
        pathlib.Path("/opt/mw-verify-status.json").write_text(
            json.dumps(status, indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        print(f"  warn  could not write status file: {e}")

    if failures:
        print(f"\nFAILED: {len(failures)} check(s)")
        for c, d in failures:
            print(f"  - {c}: {d}")
        return 1
    print("\nAll invariants hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
