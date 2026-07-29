#!/bin/sh
# Install the Expose weekly refresh on the Proxmox node.
#
#     sh shared/deploy/install_weekly.sh
#
# Ships the template to /opt/expose-template on the node and installs a systemd
# timer that runs the refresh every Sunday, then deploys whatever changed.
#
# It runs ON THE NODE rather than in a container because the deploy step needs
# `pct`, and because a job that keeps eleven chapters current should not depend
# on one chapter's container being up.
#
# EXPOSE_NODE=local is what tells provision.py to run pct directly instead of
# ssh'ing to its own address.
set -eu

NODE="${EXPOSE_NODE:-root@192.168.0.6}"
DEST=/opt/expose-template
HERE="$(cd "$(dirname "$0")/../.." && pwd)"

echo "== packing $HERE"
# Only what the refresh needs. The built sites are regenerated on the node, so
# shipping them would be shipping derived files to the machine that derives them.
# --exclude must precede the members it filters; GNU tar treats it positionally
# and silently ignores it otherwise, which is how __pycache__ ends up on a server.
#
# Code and research ship straight in. Chapter configs go to a staging directory
# and are merged, because the node owns `features` and `nav` - see
# merge_chapters.py. Overwriting them here un-publishes every meetings archive.
tar czf - -C "$HERE" \
    --exclude='__pycache__' --exclude='*.pyc' \
    build.py new_chapter.py scaffold_chapters.py \
    shared research \
  | ssh "$NODE" "mkdir -p $DEST && tar xzf - -C $DEST"

# make_maps.py reads the state boundary GeoJSON from the template's parent
# directory. Without it the weekly Maps job fails and both hubs keep publishing
# last week's pin set.
if [ -f "$HERE/../states.json" ]; then
  ssh "$NODE" "cat > $(dirname $DEST)/states.json" < "$HERE/../states.json"
  echo "   states.json shipped"
else
  echo "   ! states.json not found next to the template - maps will not regenerate"
fi

# San Angelo and Southaven are template-built but their page fragments are
# hand-written and live only on the workstation - unlike the eleven newer
# chapters, whose fragments are generated on the node by the ingest. Without
# these the node cannot build them, so the weekly run reported "nothing built"
# and they silently stopped being deployed at all.
for c in exposesanangelo exposemississippi; do
  if [ -d "$HERE/../$c/src" ]; then
    tar czf - -C "$HERE/.." --exclude='__pycache__' "$c/src" \
      | ssh "$NODE" "mkdir -p $(dirname $DEST) && tar xzf - -C $(dirname $DEST)"
    echo "   $c/src shipped"
  fi
done

tar czf - -C "$HERE" --exclude='__pycache__' chapters \
  | ssh "$NODE" "rm -rf $DEST/.staged && mkdir -p $DEST/.staged && tar xzf - -C $DEST/.staged"
ssh "$NODE" "mkdir -p $DEST/chapters && cd $DEST && python3 shared/deploy/merge_chapters.py $DEST/.staged/chapters && rm -rf $DEST/.staged"

# Compile everything with the NODE's interpreter before trusting it. The
# workstation runs 3.12 and the node runs 3.11, and a backslash inside an
# f-string expression is legal on the former and a SyntaxError on the latter -
# so a chapter bar that built perfectly here broke every rebuild there, and the
# only symptom was a weekly run reporting failures after the fact.
echo "== syntax check against the node's python"
if ! ssh "$NODE" "cd $DEST && python3 -m compileall -q . " ; then
  echo "  ! the node's python cannot compile this tree - not enabling the timer"
  exit 1
fi
ssh "$NODE" "find $DEST -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true"

echo "== installing unit + timer"
ssh "$NODE" "cat > /etc/systemd/system/expose-weekly.service" <<UNIT
[Unit]
Description=Expose chapters weekly refresh (agendas, links, search, deploy)
After=network-online.target pve-guests.service
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$DEST
Environment=EXPOSE_NODE=local
Environment=PYTHONUNBUFFERED=1
# --deploy is what makes the refresh visible. Without it the node would rebuild
# eleven sites every week into a directory nobody serves.
ExecStart=/usr/bin/python3 $DEST/shared/weekly.py --all --deploy
# One city portal being slow must not wedge the timer forever.
TimeoutStartSec=3600
Nice=10
IOSchedulingClass=idle

[Install]
WantedBy=multi-user.target
UNIT

ssh "$NODE" "cat > /etc/systemd/system/expose-weekly.timer" <<'TIMER'
[Unit]
Description=Run the Expose chapter refresh weekly

[Timer]
# Sunday 03:40. Deliberately not on the hour: every other timer on this node
# fires at :00, and eleven chapters pulling city portals at once is enough load
# without competing with backups.
OnCalendar=Sun *-*-* 03:40:00
RandomizedDelaySec=900
# A node that was down on Sunday should still refresh when it comes back, rather
# than waiting a week and publishing a stale archive the whole time.
Persistent=true

[Install]
WantedBy=timers.target
TIMER

ssh "$NODE" "systemctl daemon-reload && systemctl enable --now expose-weekly.timer"
ssh "$NODE" "systemctl list-timers expose-weekly.timer --no-pager"

echo
echo "  installed. Run it now with:"
echo "      ssh $NODE systemctl start expose-weekly.service"
echo "  Watch it with:"
echo "      ssh $NODE journalctl -u expose-weekly -f"
