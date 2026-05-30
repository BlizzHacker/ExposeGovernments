#!/usr/bin/env python3
"""
Rebuild meetings index page with complete agenda text and transcripts.
Shows: meeting name, date, duration, agenda text, transcript excerpt, video link.
"""
import json, re, html as htmlmod, subprocess
from pathlib import Path
from datetime import datetime

NAV_HTML = """<header style="background:var(--bg2);border-bottom:1px solid var(--border);padding:12px 16px;position:sticky;top:0;z-index:1000;box-shadow:0 2px 8px rgba(0,0,0,.3)">
  <div style="max-width:1200px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;gap:12px">
    <a href="/" style="display:flex;align-items:center;gap:10px;text-decoration:none;color:var(--text)">
      <img src="/images/logo-120.png" alt="ExposeMiamiOK" style="width:40px;height:40px;border-radius:8px">
      <div><div style="font-weight:800;font-size:1.1rem">ExposeMiamiOK</div><div style="font-size:.75rem;color:var(--text2)">Community Resources & Transparency</div></div>
    </a>
  </div>
</header>
<div style="background:#111;padding:10px 20px;border-bottom:1px solid #333;display:flex;flex-wrap:wrap;gap:12px;justify-content:center;position:sticky;top:64px;z-index:100">
  <a href="/" style="color:#c41e3a;text-decoration:none;font-weight:600;font-size:.9em;padding:4px 8px">\U0001F3E0 Home</a>
  <a href="/meetings/" style="color:#c41e3a;text-decoration:none;font-weight:600;font-size:.9em;padding:4px 8px">\U0001F4CB Meetings</a>
  <a href="/resources/" style="color:#c41e3a;text-decoration:none;font-weight:600;font-size:.9em;padding:4px 8px">\U0001F4C1 Resources</a>
  <a href="/blog/" style="color:#c41e3a;text-decoration:none;font-weight:600;font-size:.9em;padding:4px 8px">\U0001F4F0 Blog</a>
  <a href="/court-search/" style="color:#c41e3a;text-decoration:none;font-weight:600;font-size:.9em;padding:4px 8px">\u2696\uFE0F Court Search</a>
  <a href="/youtube.html" style="color:#c41e3a;text-decoration:none;font-weight:600;font-size:.9em;padding:4px 8px">\U0001F4FA YouTube</a>
  <a href="https://www.facebook.com/profile.php?id=61590391534875" target="_blank" style="color:#c41e3a;text-decoration:none;font-weight:600;font-size:.9em;padding:4px 8px">\U0001F4D8 Facebook</a>
</div>"""

# Load complete meetings data
meetings = json.loads(open('/opt/miamiok-work/meetings_complete.json').read())

# Build HTML
HTML_DIR = Path('/var/www/exposemiamiok/html')
MEETINGS_DIR = HTML_DIR / 'meetings'

CSS = """
:root { --bg: #0a0a0f; --card: #12121a; --text: #e4e4e7; --text2: #a1a1aa; --accent: #ef4444; --border: #27272a; --green: #22c55e; }
@media (prefers-color-scheme: light) { :root { --bg: #fff; --card: #f4f4f5; --text: #18181b; --text2: #52525b; --border: #e4e4e7; } }
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--text); font-family: system-ui, -apple-system, sans-serif; margin: 0; line-height: 1.6; }
.page { max-width: 1200px; margin: 0 auto; padding: 1.5rem 1rem; }
h1 { font-size: 1.8rem; margin-bottom: 0.25rem; }
.subtitle { color: var(--text2); margin-bottom: 1.5rem; }
.stats { display: flex; gap: 1.5rem; flex-wrap: wrap; margin-bottom: 1.5rem; }
.stat { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem 1.25rem; text-align: center; }
.stat .num { font-size: 1.8rem; font-weight: 700; color: var(--accent); }
.stat .label { font-size: 0.8rem; color: var(--text2); }
.filters { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1.5rem; }
.filters input, .filters select { background: var(--card); border: 1px solid var(--border); color: var(--text); padding: 0.5rem 1rem; border-radius: 8px; font-size: 0.9rem; }
.filters input { flex: 1; min-width: 200px; }
.meeting { background: var(--card); border: 1px solid var(--border); border-radius: 12px; margin-bottom: 1rem; overflow: hidden; }
.meeting-header { padding: 1rem 1.5rem; cursor: pointer; display: flex; justify-content: space-between; align-items: center; gap: 1rem; }
.meeting-header:hover { background: rgba(255,255,255,0.02); }
.meeting-title { font-weight: 600; font-size: 1rem; flex: 1; }
.meeting-date { color: var(--text2); font-size: 0.85rem; white-space: nowrap; }
.meeting-duration { color: var(--text2); font-size: 0.85rem; white-space: nowrap; }
.badges { display: flex; gap: 0.4rem; }
.badge { padding: 0.15rem 0.5rem; border-radius: 12px; font-size: 0.7rem; font-weight: 600; white-space: nowrap; }
.badge-transcript { background: rgba(34,197,94,0.2); color: var(--green); }
.badge-agenda { background: rgba(239,68,68,0.2); color: var(--accent); }
.badge-minutes { background: rgba(59,130,246,0.2); color: #3b82f6; }
.badge-video { background: rgba(168,85,247,0.2); color: #a855f7; }
.meeting-body { display: none; padding: 0 1.5rem 1.5rem; }
.meeting.open .meeting-body { display: block; }
.meeting-body h3 { font-size: 0.95rem; color: var(--accent); margin: 1rem 0 0.5rem; }
.meeting-body .text-block { background: rgba(0,0,0,0.2); border: 1px solid var(--border); border-radius: 8px; padding: 1rem;  font-size: 0.85rem; line-height: 1.5; color: var(--text2); white-space: pre-wrap; }
.meeting-body .links { display: flex; gap: 0.75rem; flex-wrap: wrap; margin-top: 1rem; }
.meeting-body .links a { color: var(--accent); text-decoration: none; font-size: 0.85rem; padding: 0.3rem 0.75rem; border: 1px solid var(--accent); border-radius: 6px; }
.meeting-body .links a:hover { background: var(--accent); color: #fff; }
.expand-icon { font-size: 1.2rem; color: var(--text2); transition: transform 0.2s; }
.meeting.open .expand-icon { transform: rotate(180deg); }
.load-more { text-align: center; padding: 1rem; }
.load-more button { background: var(--accent); color: #fff; border: none; padding: 0.75rem 2rem; border-radius: 8px; cursor: pointer; font-size: 1rem; }
"""

JS = """
function toggleMeeting(el) {
    el.closest('.meeting').classList.toggle('open');
}
function filterMeetings() {
    const q = document.getElementById('search').value.toLowerCase();
    const type = document.getElementById('type-filter').value;
    document.querySelectorAll('.meeting').forEach(m => {
        const text = m.textContent.toLowerCase();
        const matchSearch = !q || text.includes(q);
        const matchType = !type || m.dataset.types.includes(type);
        m.style.display = (matchSearch && matchType) ? '' : 'none';
    });
}
let shown = 50;
function loadMore() {
    const all = document.querySelectorAll('.meeting');
    for (let i = shown; i < Math.min(shown + 50, all.length); i++) {
        all[i].style.display = '';
    }
    shown += 50;
    if (shown >= all.length) document.getElementById('load-more').style.display = 'none';
}
"""

# Count stats
total = len(meetings)
with_transcript = sum(1 for m in meetings if m.get('transcript'))
with_agenda = sum(1 for m in meetings if m.get('agenda_text'))
with_minutes = sum(1 for m in meetings if m.get('minutes_text'))
with_video = sum(1 for m in meetings if m.get('video_url') and m['video_url'] != 'None')

# Build meeting cards
cards = []
for m in meetings:
    clip_id = m.get('clip_id', '')
    name = htmlmod.escape(m.get('name', 'Unknown'))
    date = htmlmod.escape(m.get('date', ''))
    duration = htmlmod.escape(m.get('duration', ''))
    
    has_transcript = bool(m.get('transcript'))
    has_agenda = bool(m.get('agenda_text'))
    has_minutes = bool(m.get('minutes_text'))
    has_video = m.get('video_url') and m['video_url'] != 'None'
    
    types = []
    badges = ''
    if has_transcript:
        badges += '<span class="badge badge-transcript">Transcript</span>'
        types.append('transcript')
    if has_agenda:
        badges += '<span class="badge badge-agenda">Agenda</span>'
        types.append('agenda')
    if has_minutes:
        badges += '<span class="badge badge-minutes">Minutes</span>'
        types.append('minutes')
    if has_video:
        badges += '<span class="badge badge-video">Video</span>'
        types.append('video')
    
    # Body content
    body = ''
    
    if has_agenda:
        agenda_text = htmlmod.escape(m['agenda_text'])
        body += f'<h3>📋 Full Agenda</h3><div class="text-block">{agenda_text}</div>'
    
    if has_transcript:
        transcript = htmlmod.escape(m['transcript'])
        source = m.get('transcript_source', '')
        body += f'<h3>📝 Transcript <small style="color:var(--text2);font-weight:400">({source})</small></h3><div class="text-block">{transcript}</div>'
    
    if has_minutes:
        minutes_text = htmlmod.escape(m['minutes_text'])
        body += f'<h3>📄 Minutes</h3><div class="text-block">{minutes_text}</div>'
    
    # Links
    links = ''
    if has_video:
        links += f'<a href="{htmlmod.escape(m["video_url"])}" target="_blank">▶ Watch Video</a>'
    if m.get('agenda_url'):
        links += f'<a href="{htmlmod.escape(m["agenda_url"])}" target="_blank">📋 Agenda PDF</a>'
    if m.get('minutes_url'):
        links += f'<a href="{htmlmod.escape(m["minutes_url"])}" target="_blank">📄 Minutes PDF</a>'
    
    if links:
        body += f'<div class="links">{links}</div>'
    
    card = f"""<div class="meeting" data-types="{','.join(types)}" data-date="{date}">
<div class="meeting-header" onclick="toggleMeeting(this)">
<span class="meeting-title">{name}</span>
<span class="meeting-date">{date}</span>
<span class="meeting-duration">{duration}</span>
<div class="badges">{badges}</div>
<span class="expand-icon">▼</span>
</div>
<div class="meeting-body">{body}</div>
</div>"""
    cards.append(card)

# Build page
page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>All Meetings | ExposeMiamiOK</title>
<style>{CSS}</style>
</head>
<body>
<div class="page">
<a href="/" style="color:var(--accent);text-decoration:none;font-size:0.9rem">← Back to Home</a>
<h1>🏛️ All City Meetings</h1>
<p class="subtitle">Complete archive with full agendas, transcripts, and minutes from miamiok.gov</p>

<div class="stats">
<div class="stat"><div class="num">{total}</div><div class="label">Total Meetings</div></div>
<div class="stat"><div class="num">{with_transcript}</div><div class="label">With Transcripts</div></div>
<div class="stat"><div class="num">{with_agenda}</div><div class="label">With Full Agendas</div></div>
<div class="stat"><div class="num">{with_minutes}</div><div class="label">With Minutes</div></div>
<div class="stat"><div class="num">{with_video}</div><div class="label">With Video</div></div>
</div>

<div class="filters">
<input type="text" id="search" placeholder="Search meetings..." oninput="filterMeetings()">
<select id="type-filter" onchange="filterMeetings()">
<option value="">All Meetings</option>
<option value="transcript">Has Transcript</option>
<option value="agenda">Has Full Agenda</option>
<option value="minutes">Has Minutes</option>
<option value="video">Has Video</option>
</select>
</div>

{chr(10).join(cards[:50])}
</div>

<div id="load-more" class="load-more">
<button onclick="loadMore()">Load More Meetings ({total - 50} remaining)</button>
</div>

<div style="display:none" id="remaining-cards">
{chr(10).join(cards[50:])}
</div>

<footer style="text-align:center;padding:2rem;color:var(--text2);font-size:0.8rem;">
Data from <a href="https://www.miamiok.gov" target="_blank" style="color:var(--accent)">miamiok.gov</a> · ExposeMiamiOK.com
</footer>

<script>
{JS}
// Move remaining cards into main container on load more
function loadMore() {{
    const remaining = document.getElementById('remaining-cards');
    const container = document.querySelector('.page');
    const cards = remaining.querySelectorAll('.meeting');
    const limit = Math.min(50, cards.length);
    for (let i = 0; i < limit; i++) {{
        container.appendChild(cards[0]);
        cards[0].style.display = '';
    }}
    if (remaining.querySelectorAll('.meeting').length === 0) {{
        document.getElementById('load-more').style.display = 'none';
    }} else {{
        document.querySelector('#load-more button').textContent = 'Load More Meetings (' + remaining.querySelectorAll('.meeting').length + ' remaining)';
    }}
}}
</script>
</body></html>"""

# Write meetings index page
(HTML_DIR / 'meetings' / 'index.html').write_text(page)
print(f'Meetings page rebuilt: {len(cards)} meetings')
print(f'  Transcripts: {with_transcript}/{total}')
print(f'  Full Agendas: {with_agenda}/{total}')
print(f'  Minutes: {with_minutes}/{total}')

# Git push
subprocess.run(['git', 'add', '-A'], cwd=str(HTML_DIR), capture_output=True)
subprocess.run(['git', 'commit', '-m', f'Rebuild meetings page: {with_transcript} transcripts, {with_agenda} full agendas, {with_minutes} minutes'], cwd=str(HTML_DIR), capture_output=True)
subprocess.run(['git', 'push', 'origin', 'main'], cwd=str(HTML_DIR), capture_output=True)
print('Pushed to GitHub')
