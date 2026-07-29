#!/bin/bash
# Full refresh for one chapter, in the only order that works:
#   ingest -> OCR -> build -> search index -> push -> verify
#
# Order matters. ingest_agendas.py regenerates every meeting fragment from the
# source PDF, which wipes OCR text, so OCR must run AFTER ingest and BEFORE build.
# Getting this backwards silently drops ~60% of San Angelo's searchable agenda text.
#
#   sh refresh.sh sanangelo
set -e
KEY="${1:?usage: sh refresh.sh <chapter>}"
W=/root/expose-work
cd "$W/expose-template"

case "$KEY" in
  mississippi) CT=176; NAME=exposemississippi ;;
  sanangelo)   CT=175; NAME=exposesanangelo ;;
  *) echo "unknown or legacy chapter: $KEY"; exit 1 ;;
esac

echo "== ingest =="
python3 shared/ingest_agendas.py "$KEY" 2>&1 | tail -2
echo "== ocr =="
python3 shared/ocr_agendas.py "$KEY" 2>&1 | tail -2
echo "== video =="
python3 shared/ingest_videos.py "$KEY" 2>&1 | tail -1
echo "== transcripts =="
python3 shared/ingest_transcripts.py "$KEY" 2>&1 | tail -1
echo "== build =="
python3 build.py "$KEY" --quiet
python3 shared/build_search_index.py "$KEY" --quiet
echo "== push =="
tar czf /tmp/$NAME.tgz -C "$W/$NAME/site" .
pct push $CT /tmp/$NAME.tgz /tmp/s.tgz
pct exec $CT -- bash -c "
  tar xzf /tmp/s.tgz --no-same-owner -C /var/www/$NAME/html &&
  mkdir -p /var/www/$NAME/html/records/generated &&
  chown -R www-data:www-data /var/www/$NAME/html &&
  rm -f /tmp/s.tgz" 2>&1 | grep -v 'time stamp' || true
rm -f /tmp/$NAME.tgz
# Internet Archive rejects bursts of new items from a young account as spam —
# 26 at once got 19 refused even at 60s spacing. But this runs twice a day and
# the ledger makes it resumable, so a small batch per run walks the whole
# backlog in a few days without ever looking like a burst.
echo "== mirror to archive.org =="
python3 shared/archive_to_ia.py "$KEY" --limit 6 --delay 90 2>&1 | tail -3

echo "== state =="
python3 - "$KEY" "$NAME" <<'PY'
import json, sys
d = json.load(open(f"/root/expose-work/{sys.argv[2]}/site/data/meetings.json"))
ms = d["meetings"]
print(f"  {len(ms)} meetings, "
      f"{sum(1 for m in ms if m['chars'] > 200)} with searchable text, "
      f"{sum(1 for m in ms if m.get('minutes_archived'))} with minutes archived")
PY
