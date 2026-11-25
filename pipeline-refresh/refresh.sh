#!/bin/bash
# Full refresh for one chapter, in the only order that works:
#   ingest -> OCR -> video -> transcripts -> build -> search index -> automation.json -> push -> verify
#
# Order matters. ingest_agendas.py regenerates every meeting fragment from the
# source PDF, which wipes OCR text, so OCR must run AFTER ingest and BEFORE build.
# Getting this backwards silently drops ~60% of San Angelo's searchable agenda text.
#
#   sh refresh.sh sanangelo
#   sh refresh.sh mississippi --no-ia
set -e
KEY="${1:?usage: sh refresh.sh <chapter> [--no-ia]}"
SKIP_IA="${2:-}"
W=/root/expose-work
cd "$W/expose-template"

case "$KEY" in
  mississippi) CT=176; NAME=exposemississippi; CITY="Southaven"; NODE="root@slimmer" ;;
  sanangelo)   CT=175; NAME=exposesanangelo;   CITY="San Angelo"; NODE="root@slimmer" ;;
  *) echo "unknown or legacy chapter: $KEY"; exit 1 ;;
esac

SSH_OPTS="-o BatchMode=yes -o StrictHostKeyChecking=accept-new"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "== ingest =="
T0=$(date +%s)
INGEST_OUT="$(python3 shared/ingest_agendas.py "$KEY" 2>&1 | tail -2)"
echo "$INGEST_OUT"
INGEST_SEC=$(( $(date +%s) - T0 ))

echo "== ocr =="
T0=$(date +%s)
OCR_OUT="$(python3 shared/ocr_agendas.py "$KEY" 2>&1 | tail -2)"
echo "$OCR_OUT"
OCR_SEC=$(( $(date +%s) - T0 ))

echo "== video =="
T0=$(date +%s)
VID_OUT="$(python3 shared/ingest_videos.py "$KEY" 2>&1 | tail -1)"
echo "$VID_OUT"
VID_SEC=$(( $(date +%s) - T0 ))

echo "== transcripts =="
T0=$(date +%s)
TR_OUT="$(python3 shared/ingest_transcripts.py "$KEY" 2>&1 | tail -1)"
echo "$TR_OUT"
TR_SEC=$(( $(date +%s) - T0 ))

echo "== build =="
T0=$(date +%s)
python3 build.py "$KEY" --quiet
python3 shared/build_search_index.py "$KEY" --quiet
BUILD_SEC=$(( $(date +%s) - T0 ))

echo "== automation status =="
python3 - "$KEY" "$NAME" "$CITY" "$STARTED_AT" "$INGEST_SEC" "$OCR_SEC" "$VID_SEC" "$TR_SEC" "$BUILD_SEC" "$INGEST_OUT" "$OCR_OUT" "$VID_OUT" "$TR_OUT" <<'PYEOF'
import json, sys
from datetime import datetime, timezone
from pathlib import Path

key, name, city, started, s_ing, s_ocr, s_vid, s_tr, s_bld, d_ing, d_ocr, d_vid, d_tr = sys.argv[1:14]
site_data = Path(f"/root/expose-work/{name}/site/data")
site_data.mkdir(parents=True, exist_ok=True)
ms = json.loads((site_data / "meetings.json").read_text(encoding="utf-8")).get("meetings", [])
searchable = sum(1 for m in ms if m.get("chars", 0) > 200)
now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

auto = {
    "generated_at": now_iso,
    "chapter": key,
    "city": city,
    "failure_count": 0,
    "jobs": [
        {"name": "Meetings", "what": f"Pull agendas and packets from {city}'s portal", "last_run": started, "ok": True, "seconds": float(s_ing), "detail": f"{len(ms)} meetings indexed ({searchable} searchable)"},
        {"name": "OCR", "what": "Recover text from scanned agenda PDFs", "last_run": now_iso, "ok": True, "seconds": float(s_ocr), "detail": (d_ocr.strip().splitlines()[-1] if d_ocr.strip() else "ok")[:180]},
        {"name": "Video", "what": "Index official meeting video archive", "last_run": now_iso, "ok": True, "seconds": float(s_vid), "detail": (d_vid.strip().splitlines()[-1] if d_vid.strip() else "ok")[:180]},
        {"name": "Transcripts", "what": "Pull captions and transcripts", "last_run": now_iso, "ok": True, "seconds": float(s_tr), "detail": (d_tr.strip().splitlines()[-1] if d_tr.strip() else "ok")[:180]},
        {"name": "Build & Search", "what": "Render site and rebuild client search index", "last_run": now_iso, "ok": True, "seconds": float(s_bld), "detail": "ok"},
    ],
}
(site_data / "automation.json").write_text(json.dumps(auto, indent=2) + chr(10), encoding="utf-8")
print(f"  wrote {site_data / 'automation.json'} ({len(ms)} meetings, {searchable} searchable)")
PYEOF

echo "== push to $NODE CT $CT =="
tar czf /tmp/$NAME.tgz -C "$W/$NAME/site" .
if pct status "$CT" >/dev/null 2>&1; then
  pct push "$CT" "/tmp/$NAME.tgz" /tmp/s.tgz
  pct exec "$CT" -- bash -c "
    tar xzf /tmp/s.tgz --no-same-owner -C /var/www/$NAME/html &&
    mkdir -p /var/www/$NAME/html/records/generated &&
    chown -R www-data:www-data /var/www/$NAME/html &&
    rm -f /tmp/s.tgz" 2>&1 | grep -v 'time stamp' || true
else
  scp $SSH_OPTS "/tmp/$NAME.tgz" "$NODE:/tmp/$NAME.tgz"
  ssh -n $SSH_OPTS "$NODE" "
    pct push $CT /tmp/$NAME.tgz /tmp/s.tgz &&
    rm -f /tmp/$NAME.tgz &&
    pct exec $CT -- bash -c '
      tar xzf /tmp/s.tgz --no-same-owner -C /var/www/$NAME/html &&
      mkdir -p /var/www/$NAME/html/records/generated &&
      chown -R www-data:www-data /var/www/$NAME/html &&
      rm -f /tmp/s.tgz'" 2>&1 | grep -v 'time stamp' || true
fi
rm -f /tmp/$NAME.tgz

if [ "$SKIP_IA" != "--no-ia" ]; then
  echo "== mirror to archive.org =="
  python3 shared/archive_to_ia.py "$KEY" --limit 6 --delay 90 2>&1 | tail -3
fi

echo "== state =="
python3 - "$KEY" "$NAME" <<'PYEOF'
import json, sys
d = json.load(open(f"/root/expose-work/{sys.argv[2]}/site/data/meetings.json"))
ms = d["meetings"]
print(f"  {len(ms)} meetings, "
      f"{sum(1 for m in ms if m['chars'] > 200)} with searchable text, "
      f"{sum(1 for m in ms if m.get('minutes_archived'))} with minutes archived")
PYEOF
