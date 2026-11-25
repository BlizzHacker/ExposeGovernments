#!/bin/bash
# Sync FOIA queue files from /opt to web root
# Runs every 5 minutes via cron

python3 -c "
import json, os, requests

# Fetch live data from FOIA API
try:
    r = requests.get('http://127.0.0.1:5060/api/foia/requests', timeout=10)
    data = r.json()

    sent = []
    pending = []
    rejected = []
    for req in data.get('requests', []):
        if req['status'] in ('sent', 'partial_response', 'fulfilled'):
            sent.append(req)
        elif req['status'] == 'pending_review':
            pending.append(req)
        elif req['status'] == 'rejected':
            rejected.append(req)

    webdir = '/var/www/exposemiamiok/html/api'
    os.makedirs(webdir, exist_ok=True)

    with open(f'{webdir}/foia-sent.json', 'w') as f:
        json.dump(sent, f, indent=2, default=str)

    # Also update the main queue files
    os.makedirs('/opt/foia-review-queue', exist_ok=True)
    with open('/opt/foia-review-queue/sent.json', 'w') as f:
        json.dump(sent, f, indent=2, default=str)

    print(f'FOIA sync: {len(sent)} sent, {len(pending)} pending, {len(rejected)} rejected')
except Exception as e:
    print(f'FOIA sync error: {e}')
"
