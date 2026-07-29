#!/usr/bin/env python3
"""
Build a chapter's meeting index from whatever portal its city happens to run.

    python3 shared/ingest_meetings.py houston
    python3 shared/ingest_meetings.py --all --since 2025-01-01

Eleven cities run six different agenda systems between them. Writing six scripts
would mean six places to fix the same bug, so this is one script with one adapter
per vendor and a single output shape:

    {"date","time","body","title","agenda_url","minutes_url","packet_url",
     "video_url","source_url"}

What it writes into the chapter's source tree:

    generated/meetings.json          machine-readable index
    src/pages/69-meetings.html       the archive page fragment, rendered by build.py

Going through build.py rather than emitting finished HTML is deliberate: the
meetings page then gets the same shell, chapter bar, nav and canonical tags as
every other page, and there is exactly one place where a page is assembled.

Nothing here logs in, submits a form, or touches a page the city has not already
published. It is a reader, and a slow one on purpose.

Requires: nothing outside the standard library.
"""

import argparse
import html as htmlmod
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHAPTERS = ROOT / "chapters"

UA = ("Mozilla/5.0 (compatible; MoveWeightFoundation/1.0; "
      "+https://foundation.moveweight.com) public-records-archive")
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# FlareSolverr on LXC 112 (192.168.0.146). Only used when a city's own site
# refuses an ordinary GET - see the fallback ladder in fetch(). Override with
# EXPOSE_FLARESOLVERR, or set it empty to disable the tier entirely.
FLARESOLVERR = os.environ.get("EXPOSE_FLARESOLVERR",
                              "http://192.168.0.146:8191/v1")

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def fetch(url, timeout=45, session=False):
    """GET a page.

    `session=True` builds an opener that keeps cookies and follows redirects.
    Swagit hands out a session cookie on first hit and serves a 508-byte stub to
    anything that does not send it back, which looks exactly like an empty
    archive rather than like a failure.
    """
    handlers = [urllib.request.HTTPSHandler(context=_CTX)]
    if session:
        import http.cookiejar
        handlers.append(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    opener = urllib.request.build_opener(*handlers)

    def get(agent):
        req = urllib.request.Request(url, headers={
            "User-Agent": agent,
            "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        with opener.open(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace")

    # Identify honestly first. Some city sites sit behind a WAF that answers 403
    # to every non-browser agent indiscriminately - claremore.com does, and the
    # same URL loads fine in a browser from the same machine. Falling back to a
    # browser agent on 403 keeps the polite identification as the default while
    # not letting a blanket bot filter erase a city's public meeting calendar.
    # This never sends a request the public site would refuse a resident.
    try:
        return get(UA)
    except urllib.error.HTTPError as e:
        if e.code != 403:
            raise
    try:
        return get(BROWSER_UA)
    except urllib.error.HTTPError as e:
        if e.code != 403:
            raise
    # Still refused. claremore.com sits behind bot management that fingerprints
    # the TLS handshake, not the headers: the identical URL with the identical
    # user-agent returns 200 to curl and 403 to urllib from the same machine.
    #
    # FlareSolverr drives a real browser, so it gets through both the fingerprint
    # check and an actual JS challenge, which curl cannot. It is tried first and
    # curl is kept as the last resort for when FlareSolverr is not reachable.
    # Either way this is one GET of a page the city publishes to the public.
    try:
        return _flaresolverr(url, timeout)
    except Exception:  # noqa: BLE001 - fall through to the simpler transport
        return _curl(url, timeout)


def _flaresolverr(url, timeout):
    """Fetch through the FlareSolverr instance on the home network.

    Returns the document body. FlareSolverr hands back a rendered page, so a JSON
    endpoint arrives wrapped in the browser's <pre> viewer and has to be unwrapped
    or every JSON adapter downstream chokes on a leading '<html>'.
    """
    endpoint = FLARESOLVERR
    if not endpoint:
        raise RuntimeError("no FlareSolverr endpoint configured")
    body = json.dumps({"cmd": "request.get", "url": url,
                       "maxTimeout": max(timeout, 60) * 1000}).encode()
    req = urllib.request.Request(endpoint, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout + 60) as r:
        d = json.loads(r.read().decode())
    if d.get("status") != "ok":
        raise RuntimeError(f"flaresolverr: {d.get('message')}")
    html = (d.get("solution") or {}).get("response") or ""
    m = re.search(r"<pre[^>]*>(.*?)</pre>", html, re.S)
    if m and "<html" in html[:200].lower():
        return htmlmod.unescape(m.group(1))
    return html


def _curl(url, timeout):
    import shutil
    exe = shutil.which("curl")
    if not exe:
        raise RuntimeError("403 and neither FlareSolverr nor curl available")
    r = subprocess.run(
        [exe, "-sS", "-L", "--compressed", "-m", str(timeout),
         "-A", BROWSER_UA, url],
        capture_output=True, text=True, timeout=timeout + 15)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError(f"curl fallback failed: {r.stderr.strip()[:160]}")
    return r.stdout


def fetch_json(url, timeout=45):
    return json.loads(fetch(url, timeout))


def esc(s):
    return htmlmod.escape(str(s or ""), quote=True)


def iso(d):
    """Normalise the many date shapes these portals emit to YYYY-MM-DD."""
    if not d:
        return ""
    s = str(d).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%Y %I:%M %p"):
        try:
            return datetime.strptime(s[:len(fmt) + 4] if "T" in fmt else s,
                                     fmt).date().isoformat()
        except ValueError:
            continue
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", s)
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    # Word dates: Granicus writes "July 22, 2026 - 5:00 PM", Swagit "Jul 24, 2026".
    m = re.search(r"([A-Z][a-z]{2,8})\.?\s+(\d{1,2}),?\s+(\d{4})", s)
    if m:
        for fmt in ("%B %d %Y", "%b %d %Y"):
            try:
                return datetime.strptime(
                    f"{m.group(1)} {m.group(2)} {m.group(3)}", fmt).date().isoformat()
            except ValueError:
                continue
    return ""


# ─── adapters ──────────────────────────────────────────────────────────
# Each returns a list of the common dict shape. An adapter that cannot reach its
# portal raises; the caller records the failure on the automation page rather
# than pretending the archive is current.

def from_primegov(portal, since):
    """OKC and San Antonio. Public JSON API, agenda and video in one record."""
    client = portal["client"]
    base = f"https://{client}.primegov.com"
    out = []
    for year in range(int(since[:4]), date.today().year + 1):
        try:
            rows = fetch_json(f"{base}/api/v2/PublicPortal/"
                              f"ListArchivedMeetings?year={year}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            raise
        for m in rows:
            d = iso(m.get("dateTime") or m.get("date"))
            if not d or d < since:
                continue
            agenda = packet = ""
            for doc in m.get("documentList") or []:
                link = (f"{base}/Portal/viewer?id={doc.get('id')}"
                        f"&type={doc.get('compileOutputType')}")
                name = (doc.get("templateName") or "").lower()
                if "packet" in name and not packet:
                    packet = link
                elif not agenda:
                    agenda = link
            out.append({
                "date": d, "time": m.get("time", ""),
                "body": m.get("title", "") or "Meeting", "title": m.get("title", ""),
                "agenda_url": agenda, "minutes_url": "", "packet_url": packet,
                "video_url": m.get("videoUrl") or "",
                "source_url": f"{base}/Portal/Meeting?meetingId={m.get('id')}",
            })
    return out


def from_legistar(portal, since):
    """Austin and Dallas. OData; the richest of the six by a distance."""
    client = portal["client"]
    q = urllib.parse.quote(f"EventDate ge datetime'{since}'", safe="")
    url = (f"https://webapi.legistar.com/v1/{client}/events"
           f"?$filter={q}&$orderby=EventDate%20desc")
    out = []
    for e in fetch_json(url):
        d = iso(e.get("EventDate"))
        if not d:
            continue
        out.append({
            "date": d, "time": e.get("EventTime") or "",
            "body": e.get("EventBodyName") or "Meeting",
            "title": e.get("EventBodyName") or "",
            "agenda_url": e.get("EventAgendaFile") or "",
            "minutes_url": e.get("EventMinutesFile") or "",
            "packet_url": "",
            "video_url": e.get("EventVideoPath") or "",
            "source_url": e.get("EventInSiteURL") or "",
        })
    return out


def from_civicclerk(portal, since):
    """Abilene. OData over the portal's own API.

    Two things this used to get wrong, and both are worth stating because they
    made the chapter look like the city published nothing.

    **The API caps every response at 15 rows.** `$top` is accepted and ignored,
    so a request for 250 returns the most recent fifteen and no error. Abilene
    sat at 15 indexed meetings for weeks, which read as a small city with a quiet
    council rather than as a paging bug. Page with `$skip` until a page comes
    back empty or older than `since`.

    **The documents are in `publishedFiles`, not `agendaFile`.** `agendaFile` and
    `minutesFile` are present on every event and are empty stubs - fileName null,
    date 0001-01-01 - so a reader of the schema concludes there are no documents.
    The real ones are in `publishedFiles[]`, typed "Agenda", "Agenda Packet" and
    "Minutes", and each carries a `fileId`.

    The download URL was verified rather than guessed, which is what the previous
    version was right to be cautious about: the `url` field on those entries is a
    relative `stream/CLIENT/<uuid>.pdf` that 404s on the API host and returns a
    viewer shell on the portal host. `GetMeetingFileStream(fileId=...)` is the
    form that answers 200 with application/pdf.
    """
    client = portal["client"]
    base = f"https://{client}.api.civicclerk.com/v1"

    def doc(files, want):
        for f in files or []:
            if (f.get("type") or "").lower() == want and f.get("fileId"):
                return (f"{base}/Meetings/GetMeetingFileStream"
                        f"(fileId={f['fileId']},plainText=false)")
        return ""

    out, skip = [], 0
    while skip < 3000:  # a hard stop; no chapter has 200 pages of history
        page = fetch_json(
            f"{base}/Events?$skip={skip}&$orderby=startDateTime%20desc"
        ).get("value", [])
        if not page:
            break
        oldest = None
        for e in page:
            d = iso(e.get("startDateTime") or e.get("eventDate"))
            if not d:
                continue
            oldest = d if oldest is None else min(oldest, d)
            if d < since:
                continue
            files = e.get("publishedFiles")
            out.append({
                "date": d, "time": "",
                "body": e.get("categoryName") or e.get("meetingTypeName") or "Meeting",
                "title": e.get("eventName") or "",
                "agenda_url": doc(files, "agenda"),
                "packet_url": doc(files, "agenda packet"),
                "minutes_url": doc(files, "minutes"),
                # No video field on this vendor's events for Abilene - checked
                # youtubeVideoId, externalMediaUrl and mediaStreamPath across 90
                # events and all three are empty. That is the city, not a bug.
                "video_url": e.get("youtubeVideoId") and
                             f"https://www.youtube.com/watch?v={e['youtubeVideoId']}" or "",
                "source_url": f"https://{client}.portal.civicclerk.com/event/{e.get('id')}/overview",
            })
        # Ordered newest first, so once a whole page predates the window there is
        # nothing older worth asking for.
        if oldest is not None and oldest < since:
            break
        skip += len(page)
    return out


def from_civicplus(portal, since):
    """Lubbock and Olive Branch. AgendaCenter exposes stable ViewFile paths."""
    base = "https://" + portal["client"].strip("/")
    page = fetch(f"{base}/AgendaCenter")

    # Parsed row by row rather than by pattern-matching URLs out of the whole
    # page. Two earlier attempts got this wrong in opposite directions: building
    # the minutes URL from the agenda's id made every minutes link a guess that
    # 404'd, and then grouping by date collapsed Lubbock's 114 meetings into 51,
    # because several bodies meet on the same day.
    #
    # One <tr class="catAgendaRow"> is one meeting. It carries the date, the
    # agenda link, the meeting's real name, and a <td class="minutes"> that is
    # either empty or holds the minutes link for THAT meeting.
    out = []
    for row in re.findall(r'<tr[^>]+class="catAgendaRow".*?</tr>', page, re.S):
        am = re.search(r'href="(/AgendaCenter/ViewFile/Agenda/_(\d{8})-\d+)"', row)
        if not am:
            continue
        stamp = am.group(2)
        d = f"{stamp[4:8]}-{stamp[0:2]}-{stamp[2:4]}"
        if d < since:
            continue
        mm = re.search(r'href="(/AgendaCenter/ViewFile/Minutes/_[\d-]+)"', row)
        title = ""
        tm = re.search(r"<p>\s*<a[^>]*>(.*?)</a>", row, re.S)
        if tm:
            title = _text(tm.group(1))
        out.append({
            "date": d, "time": "", "body": title or "Meeting", "title": title,
            "agenda_url": base + am.group(1),
            "minutes_url": base + mm.group(1) if mm else "",
            "packet_url": "", "video_url": "",
            "source_url": f"{base}/AgendaCenter",
        })
    return out


TAGS = re.compile(r"<[^>]+>")


def _text(fragment):
    """Visible text of an HTML fragment, with &nbsp; collapsed to a space.

    Granicus writes its dates as "July&nbsp;22,&nbsp;2026", so anything that
    strips tags without decoding entities produces a date no parser recognises.
    """
    t = TAGS.sub(" ", fragment)
    t = htmlmod.unescape(t).replace("\xa0", " ")
    return re.sub(r"\s+", " ", t).strip()


def from_granicus(portal, since):
    """Tulsa. ViewPublisher is a 9 MB HTML table of listingRow entries."""
    url = portal["portal_url"]
    page = fetch(url, timeout=120)
    host = urllib.parse.urlsplit(url).netloc
    view = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get(
        "view_id", ["4"])[0]
    out, seen = [], set()
    for row in re.findall(r'<tr class="listingRow">(.*?)</tr>', page, re.S):
        cid = re.search(r"clip_id=(\d+)", row)
        if not cid or cid.group(1) in seen:
            continue
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if not cells:
            continue
        name = _text(cells[0]) if cells else "Meeting"
        d = ""
        for c in cells[:3]:
            d = iso(_text(c).split(" - ")[0])
            if d:
                break
        if not d or d < since:
            continue
        seen.add(cid.group(1))
        out.append({
            "date": d, "time": "", "body": name or "Meeting", "title": name,
            "agenda_url": f"https://{host}/AgendaViewer.php?view_id={view}&clip_id={cid.group(1)}",
            "minutes_url": "", "packet_url": "",
            "video_url": f"https://{host}/MediaPlayer.php?view_id={view}&clip_id={cid.group(1)}",
            "source_url": url,
        })
    return out


def from_swagit(portal, since):
    """Houston.

    Houston's NovusAgenda instance has no browsable list at all - Meetings.aspx
    is a date-picker that only answers a postback, so there is nothing to read.
    Its Swagit archive, on the other hand, publishes every recorded meeting with
    a title and a date in plain HTML. That is the honest index for this city.
    """
    url = portal["portal_url"]
    host = "https://" + urllib.parse.urlsplit(url).netloc
    page = fetch(url, timeout=120, session=True)
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        vid = re.search(r'href="/videos/(\d+)"', row)
        if not vid:
            continue
        cells = [_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) < 2:
            continue
        d = iso(_parse_swagit_date(cells[1]))
        if not d or d < since:
            continue
        out.append({
            "date": d, "time": "", "body": cells[0] or "Meeting", "title": cells[0],
            "agenda_url": "", "minutes_url": "", "packet_url": "",
            "video_url": f"{host}/videos/{vid.group(1)}",
            "source_url": f"{host}/videos/{vid.group(1)}",
        })
    return out


def _parse_swagit_date(s):
    """'Jul 24, 2026' -> ISO."""
    try:
        return datetime.strptime(s.strip(), "%b %d, %Y").date().isoformat()
    except ValueError:
        pass
    try:
        return datetime.strptime(s.strip(), "%B %d, %Y").date().isoformat()
    except ValueError:
        return ""


def from_novus(portal, since):
    """Houston. NovusAgenda's public list page."""
    base = portal["portal_url"].rstrip("/")
    page = fetch(f"{base}/Meetings.aspx")
    out = []
    for mid, d in re.findall(
            r"MeetingID=(\d+)[^>]*>.{0,400}?(\d{1,2}/\d{1,2}/\d{4})", page, re.S):
        di = iso(d)
        if not di or di < since:
            continue
        out.append({
            "date": di, "time": "", "body": "Meeting", "title": "",
            "agenda_url": f"{base}/DisplayAgendaPDF.ashx?MeetingID={mid}",
            "minutes_url": "", "packet_url": "", "video_url": "",
            "source_url": f"{base}/Meetings.aspx",
        })
    return out


# A city's public calendar carries the library book club alongside the Council.
# Only entries naming a governing body are indexed: publishing "Movie Night at
# the Museum" as a public meeting would make the archive useless for the one
# thing it is for.
GOV_BODY = re.compile(
    r"\b(council|commission|board|authority|trust|committee|aldermen|"
    r"planning|zoning|budget|utility|hearing)\b", re.I)


def from_wordpress(portal, since):
    """Jackson MS publishes meetings as a custom post type."""
    base = portal["api"].rstrip("/")
    out = []
    for ptype in ("agendameeting", "posts"):
        try:
            rows = fetch_json(f"{base}/{ptype}?per_page=100&orderby=date&order=desc")
        except Exception:  # noqa: BLE001 - a missing post type is normal
            continue
        if not isinstance(rows, list) or not rows:
            continue
        for p in rows:
            d = iso(p.get("date"))
            if not d or d < since:
                continue
            title = htmlmod.unescape(
                TAGS.sub("", (p.get("title") or {}).get("rendered", ""))).strip()
            if ptype == "posts" and not GOV_BODY.search(title):
                continue
            out.append({
                "date": d, "time": "", "body": "Meeting", "title": title,
                "agenda_url": "", "minutes_url": "", "packet_url": "",
                "video_url": "", "source_url": p.get("link") or "",
            })
        if out:
            break
    return out


def from_tribe_events(portal, since):
    """Claremore.

    claremore.com runs The Events Calendar, so every public meeting is an event
    - and so is every library book club. The GOV_BODY filter is what makes the
    result a meeting archive rather than a what's-on listing.
    """
    base = portal["api"].rstrip("/").replace("/wp/v2", "")
    out, page = [], 1
    while page <= 6:
        try:
            d = fetch_json(f"https://{urllib.parse.urlsplit(base).netloc}"
                           f"/wp-json/tribe/events/v1/events"
                           f"?per_page=50&page={page}&start_date={since}")
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                break
            raise
        events = d.get("events") or []
        if not events:
            break
        for e in events:
            title = htmlmod.unescape(TAGS.sub("", e.get("title") or "")).strip()
            if not GOV_BODY.search(title):
                continue
            di = iso(e.get("start_date"))
            if not di or di < since:
                continue
            out.append({
                "date": di, "time": (e.get("start_date") or "")[11:16],
                "body": title, "title": title,
                "agenda_url": "", "minutes_url": "", "packet_url": "",
                "video_url": "", "source_url": e.get("url") or "",
            })
        page += 1
    return out


ADAPTERS = {
    "primegov": from_primegov, "legistar": from_legistar,
    "civicclerk": from_civicclerk, "civicplus": from_civicplus,
    "granicus": from_granicus, "novus": from_novus, "wordpress": from_wordpress,
    "swagit": from_swagit, "tribe_events": from_tribe_events,
}


# ─── page ──────────────────────────────────────────────────────────────
FRAGMENT = """<!--meta
out: meetings/index.html
nav: /meetings/
requires: meetings
title: {city} meeting archive
description: Every {city} public meeting we have indexed - {n} of them, back to {first} - with the city's own agenda, minutes and video for each.
-->

<section class="hero">
  <div class="wrap">
    <span class="eyebrow">Meetings &middot; {city}, {abbr}</span>
    <h1>{n} meetings, indexed</h1>
    <p class="lede">
      Every public meeting this chapter has found in {city}'s own portal, newest first,
      each one linked to the agenda, minutes and recording the City published for it.
      Refreshed automatically every week - see <a href="/automation.html">what is stale</a>.
    </p>
    <p class="dim">
      Source: {vendor} at <a href="{portal}" rel="noopener">{portal}</a>.
      Last pulled {generated}.
    </p>
    {searchnote}
  </div>
</section>

<section>
  <div class="wrap">
    <div class="tablewrap">
      <table class="datatable">
        <thead><tr><th>Date</th><th>Body</th><th>Agenda</th><th>Minutes</th><th>Video</th></tr></thead>
        <tbody>
{rows}
        </tbody>
      </table>
    </div>
  </div>
</section>

<section>
  <div class="wrap narrow">
    <div class="callout gold">
      <span class="co-label">These are the City's documents, on the City's servers</span>
      <p class="mb0">
        This page is an index, not a mirror. Each link goes to {city}'s own copy so you are
        reading the authoritative version. When a document disappears from the City's site -
        and they do - <a href="/tips.html">tell us</a>, because the City still holds the file
        whether or not it publishes it, and that makes it a records request.
      </p>
    </div>
  </div>
</section>
"""


def render_fragment(cfg, meetings, generated):
    rows = []
    for m in meetings:
        def link(url, label):
            return f'<a href="{esc(url)}" rel="noopener">{label}</a>' if url \
                else '<span class="dim">&mdash;</span>'
        body = esc(m.get("title") or m.get("body") or "Meeting")
        if m.get("source_url"):
            body = f'<a href="{esc(m["source_url"])}" rel="noopener">{body}</a>'
        rows.append(
            "          <tr>"
            f'<td class="mono">{esc(m["date"])}</td>'
            f"<td>{body}</td>"
            f'<td>{link(m.get("agenda_url"), "Agenda")}</td>'
            f'<td>{link(m.get("minutes_url"), "Minutes")}</td>'
            f'<td>{link(m.get("video_url"), "Video")}</td>'
            "</tr>")
    # Say plainly whether the agenda text behind these links is searchable here.
    # Two of the eleven cities publish every meeting but serve the document only
    # behind a sign-in, so their archive is a catalogue rather than a corpus.
    # A reader who searches and finds nothing deserves to know it is the portal,
    # not an empty city.
    vendor = cfg.get("portal", {}).get("vendor", "")
    if vendor in ("legistar", "civicplus", "granicus"):
        note = ('<div class="callout"><span class="co-label">These agendas are '
                'searchable</span><p class="mb0">The text of each agenda below is '
                'indexed, so you can search a phrase and land on the meeting that '
                'carried it. <a href="/search.html">Search the archive &rarr;</a>'
                '</p></div>')
    elif vendor == "primegov":
        note = ('<div class="callout gold"><span class="co-label">Why you cannot '
                'search these agendas here</span><p class="mb0">'
                + cfg["city"] + ' publishes every meeting on its portal but serves '
                'the agenda document itself only to a signed-in account. We index '
                'what is public - the date, the body and the link - and cannot '
                'index the text. That is the City&rsquo;s choice, not a gap in this '
                'archive, and it is the kind of thing worth asking about.</p></div>')
    else:
        note = ""

    return FRAGMENT.format(
        searchnote=note,
        city=cfg["city"], abbr=cfg["state_abbr"], n=len(meetings),
        first=meetings[-1]["date"] if meetings else "",
        vendor=cfg.get("portal", {}).get("vendor", ""),
        portal=cfg.get("portal", {}).get("portal_url", ""),
        generated=generated, rows="\n".join(rows))


# ─── driver ────────────────────────────────────────────────────────────
def ingest(key, since, quiet=False):
    cfg = json.loads((CHAPTERS / f"{key}.json").read_text(encoding="utf-8"))
    portal = cfg.get("portal") or {}
    vendor = portal.get("vendor")
    if vendor not in ADAPTERS:
        raise SystemExit(f"{key}: no adapter for vendor '{vendor}'")

    meetings = ADAPTERS[vendor](portal, since)
    meetings = [m for m in meetings if m.get("date")]
    meetings.sort(key=lambda m: m["date"], reverse=True)

    src = (ROOT / cfg["source_dir"]).resolve()
    (src / "generated").mkdir(parents=True, exist_ok=True)
    (src / "src" / "pages").mkdir(parents=True, exist_ok=True)
    generated = datetime.now().astimezone().isoformat(timespec="seconds")

    (src / "generated" / "meetings.json").write_text(
        json.dumps({"generated_at": generated, "chapter": key, "vendor": vendor,
                    "count": len(meetings), "meetings": meetings},
                   indent=2), encoding="utf-8")

    if meetings:
        (src / "src" / "pages" / "69-meetings.html").write_text(
            render_fragment(cfg, meetings, generated[:10]), encoding="utf-8")
        # The feature flag is flipped by data arriving, never by a human deciding
        # the page looks ready. That is what keeps an empty archive off the nav.
        if not cfg["features"].get("meetings"):
            cfg["features"]["meetings"] = True
            cfg["nav"] = _with_meetings(cfg["nav"])
            (CHAPTERS / f"{key}.json").write_text(
                json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if not quiet:
        print(f"  {key:12s} {vendor:11s} {len(meetings):5d} meetings"
              + (f"  {meetings[-1]['date']} .. {meetings[0]['date']}" if meetings else ""))
    return len(meetings)


def _with_meetings(nav):
    if any(e["href"] == "/meetings/" for e in nav):
        return nav
    out, ins = [], {"href": "/meetings/", "label": "Meetings"}
    for e in nav:
        if e["href"] == "/watch.html" and ins:
            out.append(ins)
            ins = None
        out.append(e)
    if ins:
        out.insert(len(out) - 1, ins)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--since", default=(date.today() - timedelta(days=730)).isoformat(),
                    help="earliest meeting date to index (default: two years back)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    keys = args.keys
    if args.all:
        keys = []
        for p in sorted(CHAPTERS.glob("*.json")):
            if p.stem.startswith("_"):
                continue
            cfg = json.loads(p.read_text(encoding="utf-8"))
            if (cfg.get("portal") or {}).get("vendor") in ADAPTERS:
                keys.append(p.stem)
    if not keys:
        raise SystemExit("name chapters, or pass --all")

    failed = 0
    for k in keys:
        try:
            ingest(k, args.since, args.quiet)
        except Exception as e:  # noqa: BLE001 - one city's outage is not the others'
            failed += 1
            print(f"  {k:12s} FAILED: {type(e).__name__}: {e}")
    return failed


if __name__ == "__main__":
    sys.exit(main())
