#!/bin/bash
# Miami's publish chain. The fetch that writes /opt/meetings_manifest.json was
# already running; nothing ran the merge and page rebuild behind it, so the
# manifest sat a week ahead of the published archive and the site quietly fell
# 70 days out of date while every dashboard on it looked healthy.
#
#   rebuild_meetings.py       manifest + scrapes -> meetings_complete.json
#   rebuild_all.py            one page per meeting
#   rebuild_meetings_page.py  the index
#   sync_nav_js.py            nav_constants.py -> the UI script's copy
#   mw-standardize.py         chapter bar, donate banner, canonical tags
set -u
cd /opt || exit 1
echo "== merge"
python3 rebuild_meetings.py 2>&1 | tail -5
echo "== per-meeting pages"
python3 rebuild_all.py 2>&1 | tail -3
echo "== index"
python3 rebuild_meetings_page.py 2>&1 | tail -3
echo "== records request status"
python3 records_status.py 2>&1 | tail -1
echo "== nav (script copy)"
# /assets/exposemiami-ui.js carries its own navItems array and rewrites both
# navs on DOMContentLoaded, so it overrides whatever the HTML says. Regenerate
# it from nav_constants.py BEFORE standardising, or the page ships one nav and
# the reader sees another.
python3 sync_nav_js.py 2>&1 | tail -1
echo "== standardise"
python3 mw-standardize.py 2>&1 | tail -1
echo "== published state"
python3 - <<'PY'
import json, re
from datetime import datetime, date
d = json.load(open('/opt/miamiok-work/meetings_complete.json'))
ms = d if isinstance(d, list) else d.get('meetings', [])
def iso(s):
    s = re.sub(r'\s+', ' ', str(s or '')).strip()
    for f in ('%B %d, %Y', '%b %d, %Y', '%Y-%m-%d'):
        try: return datetime.strptime(s, f).date()
        except ValueError: pass
    return None
ds = sorted(x for x in (iso(m.get('date')) for m in ms) if x)
if ds:
    print(f"  {len(ms)} meetings, newest {ds[-1]} ({(date.today()-ds[-1]).days}d ago)")
PY
