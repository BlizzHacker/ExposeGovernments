#!/usr/bin/env python3
"""Aggregate public records requests (received + overdue delay-tracker) and
cross-city meetings/news feeds across all 14 Expose chapters and 3 state hubs.

Policy:
  - Always publish all RECEIVED public records requests (ORA, TPIA, MPRA, FOIA) with document links.
  - Unfiled/pending/queued requests wait until received — only SENT/OVERDUE requests are published
    publicly to draw completions due to delays.
  - Link-out only for third-party newsrooms; never republish article bodies.
  - Never emit another chapter's donation/GoFundMe URL inside cross-chapter feed blocks.
"""

from datetime import date, datetime, timezone
import html
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent.parent
CHAPTERS_DIR = ROOT / "chapters"
GEN = ROOT / "generated"
FEEDS_DIR = GEN / "feeds"

STATE_META = {
    "oklahoma": {
        "name": "Oklahoma",
        "abbr": "OK",
        "domain": "exposeoklahoma.com",
        "statute": "Oklahoma Open Records Act (ORA)",
    },
    "texas": {
        "name": "Texas",
        "abbr": "TX",
        "domain": "exposetexas.org",
        "statute": "Texas Public Information Act (TPIA)",
    },
    "mississippi": {
        "name": "Mississippi",
        "abbr": "MS",
        "domain": "exposemississippi.com",
        "statute": "Mississippi Public Records Act (MPRA)",
    },
}
STATE_ORDER = ("oklahoma", "texas", "mississippi")

SOUTHAVEN_RECEIVED = [
    ("sa-doc-synergy-fil", "2026-05-22", "City of Southaven / MDA", "Fee-in-Lieu Agreement for Project Synergy (MDA Approved)", "Ad valorem tax abatement agreement (Project Synergy / MZX Tech) approved by MDA and City of Southaven.", "https://southaven.exposemississippi.com/documents/files/ad-valorem-tax-agreement-project-synergy.pdf"),
    ("sa-doc-mous", "2026-05-22", "City of Southaven", "Request for Memoranda of Understanding (MOUs)", "Released MOUs concerning MZX Tech / Musk Foundation infrastructure and municipal commitments.", "https://southaven.exposemississippi.com/documents/files/request-for-mous-2026-05-22.pdf"),
    ("sa-doc-spd-donation", "2026-02-10", "City of Southaven", "Southaven Police Department Donation Agreement", "Executed $1,380,900 donation agreement with MZX Tech LLC for Southaven Police Department.", "https://southaven.exposemississippi.com/documents/files/spd-donation-agreement-2026-02-10.pdf"),
    ("sa-doc-water-4", "2026-05-22", "City of Southaven", "Water Bills Public Records Release #4", "Fourth municipal water billing records release for the Stanton Road industrial facility.", "https://southaven.exposemississippi.com/documents/files/water-bills-4-2026-05-22.pdf"),
    ("sa-doc-water-3", "2026-02-23", "City of Southaven", "Water Bills Public Records Release #3", "Third municipal water billing records release for the Stanton Road industrial facility.", "https://southaven.exposemississippi.com/documents/files/water-bills-3-2026-02-23.pdf"),
    ("sa-doc-water-explained", "2026-02-23", "City of Southaven", "Water Bills Explanatory Correspondence (Feb 23, 2026)", "Explanatory email correspondence from City of Southaven staff regarding municipal water billing.", "https://southaven.exposemississippi.com/documents/files/water-bills-explained-2026-02-23.pdf"),
    ("sa-doc-water-2", "2026-02-05", "City of Southaven", "Water Bills Public Records Release #2", "Second municipal water billing records release.", "https://southaven.exposemississippi.com/documents/files/water-bills-2-2026-02-05.pdf"),
    ("sa-doc-water-1", "2025-11-21", "City of Southaven", "Water Bills Public Records Release #1", "Initial municipal water billing records release.", "https://southaven.exposemississippi.com/documents/files/water-bills-1-2025-11-21.pdf"),
    ("sa-doc-zoning-ndas", "2026-02-03", "City of Southaven", "Zoning & Non-Disclosure Agreements (NDAs) Request", "Released zoning files and nondisclosure agreement records.", "https://southaven.exposemississippi.com/documents/files/zoning-and-ndas-2026-02-03.pdf"),
    ("sa-doc-sound-wall", "2026-01-14", "City of Southaven", "Sound Wall Public Records Release", "Records regarding acoustic barrier / sound wall plans and approvals.", "https://southaven.exposemississippi.com/documents/files/sound-wall-request-2026-01-14.pdf"),
    ("sa-doc-fire-permits", "2026-01-14", "City of Southaven Fire Dept", "Fire Department Permits Release", "Released fire department permits and inspection filings.", "https://southaven.exposemississippi.com/documents/files/fire-dept-permits-2026-01-14.pdf"),
    ("sa-doc-stateline-mou", "2025-12-23", "City of Southaven", "MOU for Stateline Road Improvements ($3.46M)", "December 23, 2025 Memorandum of Understanding with MZX Tech LLC for road improvements.", "https://southaven.exposemississippi.com/documents/files/mou-stateline-road-2025-12-23.pdf"),
]


def esc(s):
    return html.escape(str(s or ""), quote=True)


def run_pct(ct, cmd):
    if ct in ("175", "176"):
        argv = ["ssh", "-n", "-o", "BatchMode=yes", "root@slimmer", f"pct exec {ct} -- bash -lc {json.dumps(cmd)}"]
    else:
        argv = ["pct", "exec", ct, "--", "bash", "-lc", cmd]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    return r.stdout if r.returncode == 0 else ""


def load_chapters():
    out = []
    for p in sorted(CHAPTERS_DIR.glob("*.json")):
        if p.stem.startswith("_"):
            continue
        cfg = json.loads(p.read_text(encoding="utf-8"))
        cfg.setdefault("key", p.stem)
        st = (cfg.get("state_key") or cfg.get("state", "")).lower().replace(" ", "")
        cfg["state_key"] = st
        out.append(cfg)
    return out


def days_since(iso_str):
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except Exception:
        try:
            d = date.fromisoformat(str(iso_str)[:10])
            return max(0, (date.today() - d).days)
        except Exception:
            return None


def collect_records():
    records = []
    # 1. Miami, OK (CT 170)
    raw = run_pct("170", "cat /var/www/exposemiamiok/data/foia/requests.json 2>/dev/null || echo '{}'")
    try:
        miami_db = json.loads(raw or "{}")
    except ValueError:
        miami_db = {}

    for r in miami_db.get("requests", []):
        st = r.get("status", "")
        if st not in ("fulfilled", "partial_response", "sent"):
            continue
        created = r.get("created_at", "")
        updates = r.get("updates", [])
        last_upd = updates[-1] if updates else {}
        raw_files = r.get("response_files", [])
        files = []
        for f in raw_files:
            u = str(f.get("url", ""))
            if u.startswith("/"):
                u = "https://miami.exposeoklahoma.com" + u
            elif u.startswith("https://exposemiamiok.com/"):
                u = "https://miami.exposeoklahoma.com/" + u[len("https://exposemiamiok.com/"):]
            files.append({"label": f.get("label", "PDF"), "url": u})
        if r.get("id") == "def17eeb2ea59c2f" and not files:
            files = [
                {"label": "Case 2026-0709 (Redacted PDF)", "url": "https://miami.exposeoklahoma.com/foia/responses/def17eeb2ea59c2f/incident-report-2026-0709-redacted.pdf"},
                {"label": "Case 2026-0775 (Redacted PDF)", "url": "https://miami.exposeoklahoma.com/foia/responses/def17eeb2ea59c2f/incident-report-2026-0775-redacted.pdf"},
                {"label": "Case 2026-0815 (Redacted PDF)", "url": "https://miami.exposeoklahoma.com/foia/responses/def17eeb2ea59c2f/incident-report-2026-0815-redacted-public.pdf"},
                {"label": "Redaction Statement (PDF)", "url": "https://miami.exposeoklahoma.com/foia/responses/def17eeb2ea59c2f/redaction-statement-personal-identifiers-2026-11-24.pdf"},
                {"label": "Stamped Request Form (PDF)", "url": "https://miami.exposeoklahoma.com/foia/responses/def17eeb2ea59c2f/request-def17eeb2ea59c2f-public.pdf"},
            ]
        desc = r.get("description", "").strip()
        if r.get("id") == "def17eeb2ea59c2f":
            desc = "All Miami Police Department incident reports for June 2026 involving use of force (Cases 2026-0709, 2026-0775, and 2026-0815)."
        records.append({
            "id": r["id"],
            "chapter": "miamiok",
            "city": "Miami",
            "state_key": "oklahoma",
            "state_abbr": "OK",
            "statute": "Oklahoma Open Records Act",
            "agency": r.get("recipient_name") or r.get("agency") or "City of Miami, OK",
            "status": st,
            "bucket": "received" if st in ("fulfilled", "partial_response") else "overdue",
            "created_at": created[:10],
            "updated_at": (last_upd.get("date") or created)[:10],
            "days_open": days_since(created),
            "title": desc[:140] + ("..." if len(desc) > 140 else ""),
            "summary": last_upd.get("note") or desc[:240],
            "page_url": "https://miami.exposeoklahoma.com/foia/review.html",
            "files": files,
        })

    # 2. Southaven, MS received releases
    for doc_id, dt_s, agency, title, summary, pdf_url in SOUTHAVEN_RECEIVED:
        records.append({
            "id": doc_id,
            "chapter": "mississippi",
            "city": "Southaven",
            "state_key": "mississippi",
            "state_abbr": "MS",
            "statute": "Mississippi Public Records Act",
            "agency": agency,
            "status": "fulfilled",
            "bucket": "received",
            "created_at": dt_s,
            "updated_at": dt_s,
            "days_open": 0,
            "title": title,
            "summary": summary,
            "page_url": "https://southaven.exposemississippi.com/documents/",
            "files": [{"label": "Download Released PDF", "url": pdf_url}],
        })

    # 3. Live dynamic ledgers on CT 175 (San Angelo) & CT 176 (Southaven)
    for ct, path, ch, city, st_key, abbr, stat, host in [
        ("175", "/var/www/exposesanangelo/data/tpia/requests.json", "sanangelo", "San Angelo", "texas", "TX", "Texas Public Information Act", "sanangelo.exposetexas.org"),
        ("176", "/var/www/exposemississippi/data/pra/requests.json", "mississippi", "Southaven", "mississippi", "MS", "Mississippi Public Records Act", "southaven.exposemississippi.com"),
    ]:
        raw_d = run_pct(ct, f"cat {path} 2>/dev/null || echo '[]'")
        try:
            arr = json.loads(raw_d or "[]")
            if isinstance(arr, dict):
                arr = arr.get("requests", [])
        except ValueError:
            arr = []
        for item in arr:
            st = item.get("status", "")
            if st not in ("fulfilled", "partial_response", "sent"):
                continue
            created = item.get("created_at") or item.get("filed_at") or ""
            records.append({
                "id": str(item.get("id", "")),
                "chapter": ch,
                "city": city,
                "state_key": st_key,
                "state_abbr": abbr,
                "statute": stat,
                "agency": item.get("agency") or item.get("recipient_name") or city,
                "status": st,
                "bucket": "received" if st in ("fulfilled", "partial_response") else "overdue",
                "created_at": str(created)[:10],
                "updated_at": str(item.get("updated_at") or created)[:10],
                "days_open": days_since(created),
                "title": (item.get("description") or item.get("records") or "Public records request")[:140],
                "summary": (item.get("note") or item.get("description") or "")[:240],
                "page_url": f"https://{host}/records/",
                "files": [
                    {
                        "label": f.get("label", "PDF"),
                        "url": (f"https://{host}" + str(f.get("url", ""))) if str(f.get("url", "")).startswith("/") else str(f.get("url", "")),
                    }
                    for f in item.get("response_files", [])
                ],
            })

    received = sorted([r for r in records if r["bucket"] == "received"], key=lambda r: r.get("updated_at") or "", reverse=True)
    overdue = sorted([r for r in records if r["bucket"] == "overdue"], key=lambda r: r.get("created_at") or "")
    return received + overdue


def collect_city_items(chapters):
    by_city = {}
    m_raw = run_pct(
        "170",
        "python3 -c 'import json,re;from datetime import datetime;"
        "d=json.load(open(\"/opt/miamiok-work/meetings_complete.json\"));"
        "ms=d if isinstance(d,list) else d.get(\"meetings\",[]);"
        "rows=[];\n"
        "for m in ms:\n"
        "  for f in (\"%B %d, %Y\",\"%b %d, %Y\",\"%Y-%m-%d\"):\n"
        "    try:\n"
        "      dt=datetime.strptime(re.sub(r\"\\s+\",\" \",str(m.get(\"date\") or \"\")).strip(),f).strftime(\"%Y-%m-%d\")\n"
        "      rows.append({\"date\":dt,\"title\":m.get(\"title\") or m.get(\"body\") or \"City Meeting\",\"url\":\"https://miami.exposeoklahoma.com/meetings/\"});break\n"
        "    except ValueError: pass\n"
        "rows.sort(key=lambda x:x[\"date\"],reverse=True);"
        "ln=json.load(open(\"/var/www/exposemiamiok/html/data/local-news-feeds.json\"));"
        "news=[{\"date\":str(it.get(\"published\") or \"\")[:10],\"title\":it.get(\"title\",\"\"),\"source\":it.get(\"source\",\"Local News\"),\"url\":it.get(\"link\") or \"https://miami.exposeoklahoma.com/local-news.html\"} for it in ln.get(\"items\",[])[:6]];"
        "print(json.dumps({\"meetings\":rows[:4],\"news\":news,\"count\":len(ms)}))'"
    )
    try:
        miami_feed = json.loads(m_raw or "{}")
    except ValueError:
        miami_feed = {"meetings": [], "news": [], "count": 538}

    for cfg in chapters:
        key = cfg["key"]
        host = cfg.get("canonical_host") or cfg["domain"]
        st = cfg["state_key"]
        city = cfg["city"]
        abbr = cfg.get("state_abbr", STATE_META[st]["abbr"])
        items = []
        m_count = 0

        if key == "miamiok":
            m_count = miami_feed.get("count", 538)
            for m in miami_feed.get("meetings", [])[:3]:
                items.append({"kind": "meeting", "date": m["date"], "city": city, "state_key": st, "state_abbr": abbr, "chapter": key, "host": host, "title": m["title"], "url": m["url"], "badge": "Meeting"})
            for n in miami_feed.get("news", [])[:3]:
                items.append({"kind": "news", "date": n["date"], "city": city, "state_key": st, "state_abbr": abbr, "chapter": key, "host": host, "title": n["title"], "source": n["source"], "url": n["url"], "badge": n["source"]})
        elif key in ("mississippi", "sanangelo"):
            folder = "exposemississippi" if key == "mississippi" else "exposesanangelo"
            mp = Path(f"/root/expose-work/{folder}/site/data/meetings.json")
            if mp.exists():
                md = json.loads(mp.read_text(encoding="utf-8"))
                ms = sorted(md.get("meetings", []), key=lambda x: x.get("date", ""), reverse=True)
                m_count = len(ms)
                for m in ms[:3]:
                    slug = m.get("slug", "")
                    url = f"https://{host}/meetings/{slug}.html" if slug else f"https://{host}/meetings/"
                    items.append({"kind": "meeting", "date": m.get("date", ""), "city": city, "state_key": st, "state_abbr": abbr, "chapter": key, "host": host, "title": m.get("title") or m.get("body") or "Public Meeting", "url": url, "badge": "Meeting"})
        else:
            src_dir = (ROOT / cfg.get("source_dir", "")).resolve()
            mp = src_dir / "generated" / "meetings.json"
            if not mp.exists():
                mp = src_dir / "site" / "data" / "meetings.json"
            if mp.exists():
                md = json.loads(mp.read_text(encoding="utf-8"))
                ms = sorted(md.get("meetings", []), key=lambda x: x.get("date", ""), reverse=True)
                m_count = md.get("count") or len(ms)
                for m in ms[:3]:
                    items.append({"kind": "meeting", "date": m.get("date", ""), "city": city, "state_key": st, "state_abbr": abbr, "chapter": key, "host": host, "title": m.get("title") or m.get("body") or "Public Meeting", "url": f"https://{host}/watch.html", "badge": "Meeting"})

        by_city[key] = {
            "key": key,
            "city": city,
            "state_key": st,
            "state_abbr": abbr,
            "host": host,
            "meetings_count": m_count,
            "items": items,
            "news_outlets": [{"name": n.get("name", ""), "url": n.get("url", ""), "note": n.get("note", "")} for n in cfg.get("news", [])[:3]],
            "records_url": f"https://{host}/foia/" if key == "miamiok" else f"https://{host}/records/",
            "news_url": f"https://{host}/local-news.html" if key == "miamiok" else f"https://{host}/news.html",
        }
    return by_city


def render_record_card(r):
    if r["status"] == "fulfilled":
        badge_txt = "Received"
    elif r["status"] == "partial_response":
        badge_txt = "Partial Response"
    else:
        d = r.get("days_open")
        badge_txt = f"Overdue ({d}d awaiting)" if d is not None else "Awaiting Response"
    pill_style = (
        "background:rgba(34,197,94,.16);color:#86efac;border:1px solid rgba(34,197,94,.35)"
        if r["bucket"] == "received"
        else "background:rgba(245,158,11,.16);color:#fde68a;border:1px solid rgba(245,158,11,.35)"
    )
    file_links = ""
    if r.get("files"):
        fl = " &middot; ".join(
            f'<a href="{esc(f["url"])}" target="_blank" rel="noopener">{esc(f["label"])}</a>'
            for f in r["files"][:5]
        )
        file_links = f'<p class="dim" style="margin:.45rem 0 .2rem;font-size:.86rem"><strong>Documents:</strong> {fl}</p>'
    return (
        '<div class="card">'
        '<div style="display:flex;justify-content:space-between;gap:8px;align-items:center;margin-bottom:6px;flex-wrap:wrap">'
        f'<span class="eyebrow" style="margin:0">{esc(r["city"])}, {esc(r["state_abbr"])} &middot; {esc(r["updated_at"] or r["created_at"])}</span>'
        f'<span style="font-size:.74rem;padding:2px 8px;border-radius:999px;font-weight:700;{pill_style}">{esc(badge_txt)}</span></div>'
        f'<h3 style="margin:.2rem 0 .4rem">{esc(r["title"])}</h3>'
        f'<p class="dim" style="margin:0 0 .35rem;font-size:.88rem"><strong>Agency:</strong> {esc(r["agency"])} &middot; {esc(r["statute"])}</p>'
        f'<p style="margin:0 0 .45rem;font-size:.9rem">{esc(r["summary"][:260])}</p>'
        f'{file_links}'
        f'<a class="card-link" href="{esc(r["page_url"])}">View {esc(r["city"])} public records ledger &rarr;</a>'
        '</div>'
    )


def render_feed_card(item):
    src = f' &middot; {esc(item["source"])}' if item.get("source") else ""
    ext = ' target="_blank" rel="noopener"' if item.get("kind") == "news" else ""
    return (
        '<div class="card">'
        f'<span class="eyebrow" style="margin:0 0 4px;display:block">{esc(item["city"])}, {esc(item["state_abbr"])} &middot; {esc(item.get("date") or "Recent")}{src}</span>'
        f'<h3 style="margin:.2rem 0 .45rem;font-size:1.02rem"><a href="{esc(item["url"])}"{ext}>{esc(item["title"])}</a></h3>'
        f'<a class="card-link" href="https://{esc(item["host"])}/">Open {esc(item["city"])} chapter &rarr;</a>'
        '</div>'
    )


def render_records_section(state_key, records, heading=None, include_network_fallback=True):
    st_name = STATE_META[state_key]["name"]
    st_rec = [r for r in records if r["state_key"] == state_key and r["bucket"] == "received"]
    st_over = [r for r in records if r["state_key"] == state_key and r["bucket"] == "overdue"]
    net_rec = [r for r in records if r["state_key"] != state_key and r["bucket"] == "received"]

    parts = [
        f'<section id="published-records"><div class="wrap"><div class="section-head"><h2>{esc(heading or f"Published public records across {st_name}")}</h2>'
        "<p>Every public records response received by our chapters is published here with source documents. "
        "Pending requests wait until records are received &mdash; except overdue filings published below to document agency delays and prompt completion.</p></div>"
    ]
    if st_rec:
        parts.append(f'<h3>Records received in {esc(st_name)} ({len(st_rec)})</h3>')
        parts.append('<div class="cards">' + "".join(render_record_card(r) for r in st_rec[:12]) + '</div>')
    else:
        parts.append(
            f'<div class="callout"><span class="co-label">{esc(st_name)} public records releases</span>'
            f'<p class="mb0">No {esc(st_name)} agency responses have been finalized and published yet. '
            f'As soon as records arrive under the {esc(STATE_META[state_key]["statute"])}, they will appear here and on their city chapter.</p></div>'
        )
    if st_over:
        parts.append(f'<h3 style="margin-top:26px">Overdue &amp; awaiting agency response ({len(st_over)} published to draw completion)</h3>')
        parts.append('<div class="cards">' + "".join(render_record_card(r) for r in st_over[:10]) + '</div>')
    if include_network_fallback and net_rec:
        parts.append('<h3 style="margin-top:28px">Published public records from sister states</h3>')
        parts.append('<div class="cards">' + "".join(render_record_card(r) for r in net_rec[:4]) + '</div>')
    parts.append('</div></section>')
    return "\n".join(parts)


def render_state_feed_section(state_key, by_city, records):
    st_name = STATE_META[state_key]["name"]
    state_cities = [c for c in by_city.values() if c["state_key"] == state_key]
    feed_items = []
    for c in state_cities:
        feed_items.extend(c["items"])
    for r in records:
        if r["state_key"] == state_key and r["bucket"] == "received":
            feed_items.append({
                "kind": "record",
                "date": r.get("updated_at") or r.get("created_at"),
                "city": r["city"],
                "state_key": r["state_key"],
                "state_abbr": r["state_abbr"],
                "chapter": r["chapter"],
                "host": by_city[r["chapter"]]["host"],
                "title": f"Records Received: {r['title']}",
                "source": r["statute"],
                "url": r["page_url"],
            })
    feed_items.sort(key=lambda x: x.get("date") or "", reverse=True)
    picked, per_city = [], {}
    for it in feed_items:
        ch = it["chapter"]
        if per_city.get(ch, 0) < 3:
            picked.append(it)
            per_city[ch] = per_city.get(ch, 0) + 1
        if len(picked) >= 12:
            break

    sister_cards = []
    for other_st in STATE_ORDER:
        if other_st == state_key:
            continue
        meta = STATE_META[other_st]
        other_cities = sorted([c for c in by_city.values() if c["state_key"] == other_st], key=lambda c: -c["meetings_count"])
        total_m = sum(c["meetings_count"] for c in other_cities)
        rec_n = sum(1 for r in records if r["state_key"] == other_st and r["bucket"] == "received")
        city_links = " &middot; ".join(f'<a href="https://{esc(c["host"])}/">{esc(c["city"])}</a>' for c in other_cities)
        sister_cards.append(
            '<div class="card">'
            '<span class="eyebrow" style="margin:0 0 4px;display:block">Sister State Hub</span>'
            f'<h3><a href="https://{esc(meta["domain"])}/">{esc(meta["name"])} ({esc(meta["domain"])})</a></h3>'
            f'<p>{len(other_cities)} chapters, {total_m:,} meetings indexed'
            + (f', {rec_n} published public records releases' if rec_n else '')
            + f'.</p><p class="dim" style="font-size:.88rem">{city_links}</p>'
            f'<a class="card-link" href="https://{esc(meta["domain"])}/">Open {esc(meta["name"])} hub &rarr;</a>'
            '</div>'
        )

    return (
        f'<section id="state-feed"><div class="wrap"><div class="section-head">'
        f'<h2>Latest news, meetings &amp; public records across {esc(st_name)}</h2>'
        f'<p>Live cross-city feed pulling recent public meetings, local newsroom dispatches, and released public records from every {esc(st_name)} chapter.</p></div>'
        '<div class="cards">' + "".join(render_feed_card(it) for it in picked) + '</div>'
        '<h3 style="margin-top:30px">Interlinked across the Expose network</h3>'
        '<div class="cards">' + "".join(sister_cards) + '</div>'
        '</div></section>'
    )


def render_city_network_section(cfg, by_city, records):
    key = cfg["key"]
    st = cfg["state_key"]
    st_name = STATE_META[st]["name"]
    st_dom = STATE_META[st]["domain"]
    same_state = [c for c in by_city.values() if c["state_key"] == st and c["key"] != key]

    picked = []
    for c in sorted(same_state, key=lambda x: -x["meetings_count"]):
        picked.extend(c["items"][:2])
    for r in records:
        if r["bucket"] == "received" and r["chapter"] != key:
            picked.append({
                "kind": "record",
                "date": r.get("updated_at") or r.get("created_at"),
                "city": r["city"],
                "state_key": r["state_key"],
                "state_abbr": r["state_abbr"],
                "chapter": r["chapter"],
                "host": by_city[r["chapter"]]["host"],
                "title": f"Records Received: {r['title']}",
                "source": r["statute"],
                "url": r["page_url"],
            })
            if len(picked) >= 9:
                break
    picked.sort(key=lambda x: x.get("date") or "", reverse=True)
    picked = picked[:6]

    sister_links = " &middot; ".join(
        f'<a href="https://{esc(c["host"])}/">{esc(c["city"])}</a>'
        for c in sorted(same_state, key=lambda x: x["city"])
    )
    hub_links = " &middot; ".join(
        f'<a href="https://{esc(STATE_META[s]["domain"])}/">{esc(STATE_META[s]["name"])}</a>'
        for s in STATE_ORDER
    )
    return (
        f'<section id="network-feed"><div class="wrap"><div class="section-head">'
        f'<h2>Across {esc(st_name)} &amp; sister Expose cities</h2>'
        f'<p>Live meetings, local dispatches, and published public records from our other {esc(st_name)} chapters '
        f'({sister_links}) and the <a href="https://{esc(st_dom)}/">{esc(st_name)} Hub</a> &middot; '
        f'State hubs: {hub_links} &middot; <a href="https://foundation.moveweight.com/">Move Weight Foundation</a>.</p></div>'
        '<div class="cards">' + "".join(render_feed_card(it) for it in picked) + '</div>'
        '</div></section>'
    )


def render_miami_network_block(by_city, records):
    ok_cities = [c for c in by_city.values() if c["state_key"] == "oklahoma" and c["key"] != "miamiok"]
    items = []
    for c in sorted(ok_cities, key=lambda x: -x["meetings_count"]):
        items.extend(c["items"][:2])
    for r in records:
        if r["state_key"] != "oklahoma" and r["bucket"] == "received":
            items.append({
                "kind": "record",
                "date": r.get("updated_at") or r.get("created_at"),
                "city": r["city"],
                "state_key": r["state_key"],
                "state_abbr": r["state_abbr"],
                "chapter": r["chapter"],
                "host": by_city[r["chapter"]]["host"],
                "title": f"Records Received: {r['title']}",
                "source": r["statute"],
                "url": r["page_url"],
            })
            if len(items) >= 8:
                break
    items.sort(key=lambda x: x.get("date") or "", reverse=True)
    cards = []
    for it in items[:6]:
        src = f' &middot; {esc(it["source"])}' if it.get("source") else ""
        cards.append(
            '<div class="card">'
            f'<div style="font-size:.76rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.05em;margin-bottom:.3rem">'
            f'{esc(it["city"])}, {esc(it["state_abbr"])} &middot; {esc(it.get("date") or "Recent")}{src}</div>'
            f'<h3 style="margin:.15rem 0 .45rem;font-size:1rem"><a href="{esc(it["url"])}">{esc(it["title"])}</a></h3>'
            f'<a class="card-link" href="https://{esc(it["host"])}/">Open {esc(it["city"])} chapter &rarr;</a>'
            '</div>'
        )
    return (
        "<!-- NETWORK FEED START -->\n"
        '<section id="network-feed" class="section" style="margin:1.5rem 0">\n'
        '  <p style="margin:0 0 .35rem;color:#fbbf24;font-weight:800;text-transform:uppercase;letter-spacing:.08em;font-size:.78rem">Across Oklahoma &amp; the Expose Network</p>\n'
        '  <h2 style="margin:.1rem 0 .5rem">Live meetings, news &amp; public records from sister cities</h2>\n'
        '  <p style="margin:0 0 1rem;color:#cbd5e1;font-size:.94rem">Interlinked across '
        '<a href="https://exposeoklahoma.com/" style="color:#fbbf24">ExposeOklahoma</a> '
        '(<a href="https://okc.exposeoklahoma.com/" style="color:#fbbf24">OKC</a> &middot; '
        '<a href="https://tulsa.exposeoklahoma.com/" style="color:#fbbf24">Tulsa</a> &middot; '
        '<a href="https://claremore.exposeoklahoma.com/" style="color:#fbbf24">Claremore</a>), '
        '<a href="https://exposetexas.org/" style="color:#fbbf24">ExposeTexas</a>, '
        '<a href="https://exposemississippi.com/" style="color:#fbbf24">ExposeMississippi</a>, and '
        '<a href="https://foundation.moveweight.com/" style="color:#fbbf24">Move Weight Foundation</a>.</p>\n'
        '  <div class="grid">' + "".join(cards) + '</div>\n'
        '</section>\n'
        "<!-- NETWORK FEED END -->\n"
    )


def render_foundation_network_block(by_city, records):
    rec = [r for r in records if r["bucket"] == "received"]
    over = [r for r in records if r["bucket"] == "overdue"]
    cards = []
    for r in rec[:6]:
        file_html = ""
        if r.get("files"):
            f0 = r["files"][0]
            file_html = f' <a href="{esc(f0["url"])}" target="_blank" rel="noopener" class="flink" style="margin-left:10px">PDF &rarr;</a>'
        cards.append(
            '        <div class="feature-card">\n'
            f'          <h4>{esc(r["city"])}, {esc(r["state_abbr"])} &mdash; {esc(r["updated_at"])}</h4>\n'
            f'          <p>{esc(r["title"])}</p>\n'
            f'          <a href="{esc(r["page_url"])}" class="flink">View record &rarr;</a>{file_html}\n'
            '        </div>'
        )
    return (
        '<section id="published-records">\n'
        '  <div class="container">\n'
        '    <div class="section-eyebrow">Published Public Records</div>\n'
        f'    <h2>{len(rec)} received releases published &middot; {len(over)} overdue requests tracked</h2>\n'
        '    <p class="section-sub">Every public records response received across Oklahoma, Texas, and Mississippi '
        'is published directly on its city chapter and state hub. Overdue requests are published to document agency delays.</p>\n'
        '    <div class="feature-grid">\n' + "\n".join(cards) + '\n    </div>\n'
        '  </div>\n'
        '</section>'
    )


def main():
    GEN.mkdir(parents=True, exist_ok=True)
    FEEDS_DIR.mkdir(parents=True, exist_ok=True)

    chapters = load_chapters()
    records = collect_records()
    by_city = collect_city_items(chapters)
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    foia_payload = {
        "generated_at": now_iso,
        "received_count": sum(1 for r in records if r["bucket"] == "received"),
        "overdue_count": sum(1 for r in records if r["bucket"] == "overdue"),
        "records": records,
    }
    feed_payload = {
        "generated_at": now_iso,
        "states": STATE_META,
        "chapters": by_city,
    }
    (GEN / "network-foias.json").write_text(json.dumps(foia_payload, indent=2) + "\n", encoding="utf-8")
    (GEN / "network-feed.json").write_text(json.dumps(feed_payload, indent=2) + "\n", encoding="utf-8")

    for st in STATE_ORDER:
        rec_html = render_records_section(st, records)
        feed_html = render_state_feed_section(st, by_city, records)
        (FEEDS_DIR / f"state-hub-{st}.html").write_text(rec_html + "\n" + feed_html + "\n", encoding="utf-8")

    for cfg in chapters:
        key = cfg["key"]
        (FEEDS_DIR / f"city-feed-{key}.html").write_text(render_city_network_section(cfg, by_city, records) + "\n", encoding="utf-8")
        (FEEDS_DIR / f"city-records-{key}.html").write_text(
            render_records_section(cfg["state_key"], records, heading=f"Public records received &amp; overdue across {STATE_META[cfg['state_key']]['name']}", include_network_fallback=True) + "\n",
            encoding="utf-8",
        )

    miami_block = render_miami_network_block(by_city, records)
    (FEEDS_DIR / "miami-network-block.html").write_text(miami_block, encoding="utf-8")
    (FEEDS_DIR / "foundation-network-block.html").write_text(render_foundation_network_block(by_city, records) + "\n", encoding="utf-8")

    subprocess.run(["pct", "push", "170", str(FEEDS_DIR / "miami-network-block.html"), "/var/www/exposemiamiok/ops/miami/network-feed-block.html", "--perms", "0644"], check=True)
    subprocess.run(["pct", "push", "170", str(GEN / "network-foias.json"), "/var/www/exposemiamiok/data/foia/network-foias.json", "--perms", "0640"], check=True)
    subprocess.run(["pct", "push", "170", str(GEN / "network-feed.json"), "/var/www/exposemiamiok/html/data/network-feed.json", "--perms", "0644"], check=True)

    print(f"network feeds built: {foia_payload['received_count']} received + {foia_payload['overdue_count']} overdue records across {len(by_city)} chapters")


if __name__ == "__main__":
    main()
