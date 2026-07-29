#!/bin/bash
# Per-area public submission addresses on moveweight.net.
#
#     sh shared/deploy/mail_areas.sh            # create / repair
#     sh shared/deploy/mail_areas.sh --list     # show what exists
#
# Austin asked for an address he could post publicly so Mississippi citizens can
# send documents in. This creates one per area rather than a single shared inbox,
# because the address tells you which chapter a submission belongs to before
# anyone opens it - and a resident in Southaven should not have to write to a
# generic address to reach the people covering Southaven.
#
# Shape:
#   <state>@moveweight.net    a real mailbox, keeps a local copy, and forwards
#                             to foia@ and team@moveweight.com
#   <city>@moveweight.net     an alias on its state's mailbox
#
# Aliases rather than fourteen mailboxes: fourteen passwords to hold and fourteen
# maildirs to watch, to deliver mail to the same two people, is cost with no
# benefit. The alias still gives each chapter its own postable address.
#
# Forwarding to foia@ AND team@ is deliberate. foia@ is the records desk and
# team@ is the one connected to the nonprofit's banking and general contact, so a
# document submission reaching only one of them depends on which person happens
# to be looking.
#
# Run on the Proxmox node. Hestia's CLI is not on PATH under `pct exec`, so every
# call is by absolute path.
set -u

CT=160
V=/usr/local/hestia/bin
DOMAIN=moveweight.net
# One destination per v-add-mail-account-forward call. Hestia stores them as a
# comma list but rejects a comma list as INPUT - passing both at once silently
# fails and leaves the address with no forward at all, which looks identical to
# success until a citizen's document goes nowhere.
FWD_LIST="foia@moveweight.com team@moveweight.com"

# state -> cities that alias onto it
STATES="mississippi texas oklahoma"
mississippi_cities="southaven jackson olivebranch"
texas_cities="sanangelo houston dallas austin sanantonio lubbock abilene"
oklahoma_cities="miami okc tulsa claremore"

h() { ssh root@192.168.0.6 "pct exec $CT -- $*"; }

if [ "${1:-}" = "--list" ]; then
  echo "== $DOMAIN accounts"
  h "$V/v-list-mail-accounts admin $DOMAIN plain" 2>/dev/null \
    | awk -F'\t' '{printf "  %-16s fwd=%-46s aliases=%s\n", $1, $3, $2}'
  exit 0
fi

echo "== per-area submission addresses on $DOMAIN"
for st in $STATES; do
  eval "cities=\$${st}_cities"

  # The mailbox. A password is required by Hestia even though nobody signs in as
  # these - mail is read wherever it forwards to. Generated, printed once, and
  # recorded in the same credentials file as every other mailbox.
  if h "$V/v-list-mail-account admin $DOMAIN $st plain" >/dev/null 2>&1; then
    echo "  ok   $st@$DOMAIN exists"
  else
    PW=$(ssh root@192.168.0.6 "head -c 18 /dev/urandom | base64 | tr -d '=+/' | cut -c1-16")
    if h "$V/v-add-mail-account admin $DOMAIN $st '$PW'" 2>&1 | grep -qi error; then
      echo "  !!   $st@$DOMAIN could not be created"
      continue
    fi
    ssh root@192.168.0.6 "pct exec $CT -- sh -c \"printf '%s %s@%s %s\\n' $DOMAIN $st $DOMAIN '$PW' >> /etc/exim4/domain-mailbox-passwords.txt\""
    echo "  NEW  $st@$DOMAIN created"
  fi

  # Forward to both desks, keeping the local copy.
  for f in $FWD_LIST; do
    h "$V/v-add-mail-account-forward admin $DOMAIN $st $f" >/dev/null 2>&1
  done
  got=$(h "$V/v-list-mail-account admin $DOMAIN $st plain" 2>/dev/null | awk -F'	' '{print $3}')
  case "$got" in
    *foia@moveweight.com*team@moveweight.com*) echo "       -> $got" ;;
    *) echo "  !!   $st@$DOMAIN forward incomplete: '$got'" ;;
  esac

  for c in $cities; do
    if h "$V/v-add-mail-account-alias admin $DOMAIN $st $c" 2>&1 | grep -qiE "error|exist"; then
      echo "       ..  $c@$DOMAIN already aliased"
    else
      echo "       +   $c@$DOMAIN -> $st@$DOMAIN"
    fi
  done
done

echo
echo "== verifying exim accepts these addresses"
for a in mississippi southaven jackson olivebranch texas oklahoma; do
  r=$(ssh root@192.168.0.6 "pct exec $CT -- exim -bt $a@$DOMAIN 2>&1 | head -3" | tr '\n' ' ')
  case "$r" in
    *deliver*|*router*|*"is undeliverable"*) : ;;
  esac
  printf "  %-24s %s\n" "$a@$DOMAIN" "$(echo "$r" | cut -c1-96)"
done
