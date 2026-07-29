#!/usr/bin/env python3
"""
Provision and deploy city chapters onto their state's container.

    python shared/deploy/provision.py --all --dns --site
    python shared/deploy/provision.py houston dallas --site
    python shared/deploy/provision.py --all --dry-run

Steps, each independently selectable so a re-run does not redo work:

    --dns      create the proxied Cloudflare A record for the subdomain
    --nginx    render and install the city vhost, reload nginx
    --site     push the built site to the container
    --traefik  rewrite the state's Traefik router rule to include every host
    --all      every chapter (otherwise name them)

Default with no step flags is --nginx --site, which is the pair you want after
a content change.

Why the transfer works the way it does
--------------------------------------
`pct push` moves one file per invocation and each one is an ssh round trip; a
chapter is ~30 files and there are eleven of them. So the site is tarred locally,
streamed to the node once, pushed into the container once, and unpacked there.

That also sidesteps a failure mode this project has hit before: when a container
fills its disk, `pct push` writes a ZERO-BYTE file and exits 0. A tarball either
extracts or it does not, and this script checks the file count afterwards, so a
full disk produces an error instead of a silently blank website.
"""

import argparse
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

ROOT = Path(__file__).resolve().parent.parent.parent
CHAPTERS = ROOT / "chapters"
NODE = os.environ.get("EXPOSE_NODE", "root@192.168.0.6")
ORIGIN_IP = "173.207.168.55"

STATE_HUB = {
    "oklahoma": ("exposeoklahoma.com", 170),
    "texas": ("exposetexas.org", 175),
    "mississippi": ("exposemississippi.com", 176),
}
# Hosts each state router must keep serving besides its city chapters: the apex
# and www of the state domain itself. Dropping these while rewriting the rule
# would take the state hub offline, which is exactly the kind of collateral a
# generated config invites.
STATE_EXTRA_HOSTS = {
    "oklahoma": ["exposeoklahoma.com", "www.exposeoklahoma.com"],
    "texas": ["exposetexas.org", "www.exposetexas.org"],
    "mississippi": ["exposemississippi.com", "www.exposemississippi.com"],
}

DRY = False


def run(cmd, check=True, capture=True, stdin=None, read_only=False):
    # A dry run still performs reads. Refusing to look at the Cloudflare token or
    # count files on disk would make --dry-run report a plan it cannot verify,
    # which is the opposite of what a dry run is for. Only writes are suppressed.
    if DRY and not read_only:
        print("    DRY  " + (cmd if isinstance(cmd, str) else " ".join(cmd)))
        return ""
    # encoding is pinned to UTF-8. Without it Python uses the Windows console
    # codepage to decode whatever comes back over ssh, and reading a vhost that
    # contains a single non-ASCII byte raises UnicodeDecodeError mid-deploy.
    r = subprocess.run(cmd, shell=isinstance(cmd, str), input=stdin,
                       capture_output=capture,
                       text=not isinstance(stdin, bytes),
                       encoding=None if isinstance(stdin, bytes) else "utf-8",
                       errors=None if isinstance(stdin, bytes) else "replace")
    if check and r.returncode != 0:
        err = (r.stderr or "").strip() if capture else ""
        raise SystemExit(f"  ! command failed ({r.returncode}): {cmd}\n    {err}")
    return (r.stdout or "") if capture else ""


def write_remote(path, payload):
    """Put bytes or text at `path` on the node, ssh or local."""
    data = payload if isinstance(payload, bytes) else payload.encode("utf-8")
    if NODE == "local":
        Path(path).write_bytes(data)
        return
    run(["ssh", NODE, f"cat > {path}"], stdin=data)


def ssh(cmd, **kw):
    """Run a command on the Proxmox node.

    EXPOSE_NODE=local runs it directly, for the weekly timer that lives ON the
    node. Without this the timer would have to ssh to its own address, which
    means root holding a key to itself just so a cron job can reach `pct`.
    """
    # Proxmox takes a per-container config lock for pct operations. Pushing
    # eleven chapters into three containers back to back collides with it, and
    # with anything else touching the guest - a backup, another deploy - which
    # surfaces as "can't lock file '/run/lock/lxc/pve-config-175.lock' - got
    # timeout" and exit 4. It is transient by definition, so it is retried
    # rather than failing a whole weekly run.
    attempts = 4 if isinstance(cmd, str) and " pct " in f" {cmd} " else 1
    last = None
    for i in range(attempts):
        try:
            if NODE == "local":
                return run(cmd, **kw)
            return run(["ssh", "-o", "BatchMode=yes", NODE, cmd], **kw)
        except SystemExit as e:
            last = e
            if i == attempts - 1 or "lock" not in str(e).lower():
                raise
            time.sleep(5 * (i + 1))
    raise last


def load(key):
    p = CHAPTERS / f"{key}.json"
    if not p.exists():
        raise SystemExit(f"no chapter config for '{key}'")
    return json.loads(p.read_text(encoding="utf-8"))


def all_chapters():
    out = []
    for p in sorted(CHAPTERS.glob("*.json")):
        if p.stem.startswith("_"):
            continue
        out.append(json.loads(p.read_text(encoding="utf-8")))
    return out


def city_chapters():
    """Chapters that live as a subdomain on a shared state container.

    These are the ones whose nginx vhost and DNS record this script owns. It is
    deliberately NOT the set whose hosts belong in a Traefik rule (see
    step_traefik) nor the set whose sites get pushed (see deployable_chapters).
    """
    return [c for c in all_chapters() if c.get("infra", {}).get("shared_container")]


def deployable_chapters():
    """Every chapter whose built site this script can push.

    Any chapter carrying a `managed` value belongs to a different pipeline and is
    excluded. Two reasons, both learned the hard way:

      managed=legacy   Miami OK, generated by its own scripts. Pushing a template
                       build over it would destroy 522 meetings.
      managed=refresh  San Angelo and Southaven, built twice daily by refresh.sh
                       from ~50GB of source PDFs and OCR text this tree does not
                       have. I previously added them here so they would stop
                       serving a stale chapter bar - which fixed the bar and
                       started a fight instead: this deploy pushed a thinner
                       build (18 of 48 meetings searchable, and no
                       video-archive.html at all) and refresh.sh pushed it back
                       twelve hours later. The bar is fixed properly now, by
                       refresh.sh reading the same generated bar every other
                       chapter uses, so these two only need to be left alone.
    """
    return [c for c in all_chapters()
            if not c.get("managed")
            and c.get("infra", {}).get("web_root")
            and c.get("source_dir")]


def substitute(text, cfg):
    import re
    def dotted(path):
        cur = cfg
        for part in path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return None
        return cur
    return re.sub(r"\{\{([a-zA-Z0-9_.]+)\}\}",
                  lambda m: str(dotted(m.group(1)) if dotted(m.group(1)) is not None
                                else m.group(0)), text)


# ─── steps ─────────────────────────────────────────────────────────────
def cf_token():
    tok = os.environ.get("CF_DNS_API_TOKEN")
    if tok:
        return tok
    # Traefik already holds a token with access to every Expose zone. Reading it
    # beats keeping a second copy on a laptop.
    line = ssh("pct exec 107 -- cat /etc/traefik/cloudflare.env", read_only=True).strip()
    for part in line.splitlines():
        if "=" in part:
            return part.split("=", 1)[1].strip()
    raise SystemExit("no Cloudflare token: set CF_DNS_API_TOKEN")


def cf(method, path, token, body=None):
    import urllib.request
    req = urllib.request.Request(
        "https://api.cloudflare.com/client/v4" + path, method=method,
        headers={"Authorization": "Bearer " + token,
                 "Content-Type": "application/json"},
        data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def step_dns(cfg, token, zones):
    host = cfg["canonical_host"]
    domain = cfg["domain"]
    zid = zones.get(domain)
    if not zid:
        print(f"  ! {host}: zone {domain} not visible to this token")
        return
    existing = cf("GET", f"/zones/{zid}/dns_records?name={host}", token)
    if existing.get("result"):
        rec = existing["result"][0]
        if rec["type"] == "A" and rec["content"] == ORIGIN_IP and rec["proxied"]:
            print(f"  ok   dns  {host} -> {ORIGIN_IP} (proxied, already correct)")
            return
        print(f"  ..   dns  {host} exists as {rec['type']} {rec['content']} "
              f"proxied={rec['proxied']} — left alone, fix by hand")
        return
    if DRY:
        print(f"    DRY  create A {host} -> {ORIGIN_IP} proxied")
        return
    # Proxied, because public TLS for these domains is Cloudflare's edge
    # certificate. Traefik's cert resolver is not what terminates them, and an
    # unproxied record would serve a certificate error to every visitor.
    cf("POST", f"/zones/{zid}/dns_records", token,
       {"type": "A", "name": host, "content": ORIGIN_IP, "proxied": True,
        "ttl": 1, "comment": "Move Weight Foundation chapter"})
    print(f"  NEW  dns  {host} -> {ORIGIN_IP} (proxied)")


def step_nginx(cfg):
    key, vmid = cfg["key"], cfg["infra"]["vmid"]
    tmpl = (ROOT / "shared" / "deploy" / "city.nginx.tmpl").read_text(encoding="utf-8")
    conf = substitute(tmpl.replace("{{hosts_nginx}}", " ".join(cfg["hosts"])), cfg)
    root = cfg["infra"]["web_root"]
    ssh(f"pct exec {vmid} -- mkdir -p {root}")
    if DRY:
        print(f"    DRY  install /etc/nginx/sites-available/expose{key} on {vmid}")
    else:
        write_remote(f"/tmp/expose{key}.nginx", conf)
        ssh(f"pct push {vmid} /tmp/expose{key}.nginx "
            f"/etc/nginx/sites-available/expose{key}")
        ssh(f"pct exec {vmid} -- ln -sf /etc/nginx/sites-available/expose{key} "
            f"/etc/nginx/sites-enabled/expose{key}")
        ssh(f"rm -f /tmp/expose{key}.nginx")
    out = ssh(f"pct exec {vmid} -- nginx -t", check=False)
    ssh(f"pct exec {vmid} -- systemctl reload nginx")
    print(f"  ok   nginx {key} -> ct {vmid} ({cfg['hosts'][0]})")


def step_site(cfg):
    key, vmid = cfg["key"], cfg["infra"]["vmid"]
    site = (ROOT / cfg["source_dir"] / "site").resolve()
    if not site.is_dir():
        raise SystemExit(f"  ! {key}: nothing built at {site} — run build.py first")
    files = [p for p in site.rglob("*") if p.is_file()]
    root = cfg["infra"]["web_root"]

    if DRY:
        print(f"    DRY  ship {len(files)} files -> {vmid}:{root}")
        return

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for p in files:
            tar.add(p, arcname=p.relative_to(site).as_posix())
    data = buf.getvalue()

    remote = f"/tmp/expose{key}-site.tgz"
    write_remote(remote, data)
    ssh(f"pct push {vmid} {remote} {remote}")
    ssh(f"pct exec {vmid} -- mkdir -p {root}")
    ssh(f"pct exec {vmid} -- tar xzf {remote} -C {root}")
    ssh(f"pct exec {vmid} -- chown -R www-data:www-data {root}")
    ssh(f"pct exec {vmid} -- rm -f {remote}")
    ssh(f"rm -f {remote}")

    # A container that has filled its disk makes pct push write a zero-byte file
    # and still exit 0, which historically produced a live site of empty pages.
    # Count what landed instead of trusting the exit code.
    n = ssh(f"pct exec {vmid} -- sh -c 'find {root} -type f | wc -l'").strip()
    try:
        landed = int(n)
    except ValueError:
        landed = -1
    if landed < len(files):
        raise SystemExit(f"  ! {key}: shipped {len(files)} files but {landed} are on "
                         f"disk. Check free space on ct {vmid} before retrying.")
    print(f"  ok   site  {key}: {len(files)} files -> {vmid}:{root}")


# State hub web roots. The apex of each state domain serves its own directory,
# separate from any city vhost, so exposetexas.org keeps working no matter which
# chapter happens to host the generated hub page.
STATE_HUB_ROOT = {
    "oklahoma": (170, "/var/www/exposeoklahoma-state/html"),
    "texas": (175, "/var/www/exposetexas-state/html"),
    "mississippi": (176, "/var/www/exposemississippi-state/html"),
}


def _state_vhost(state, vmid, root):
    """Make sure the apex has a vhost of its own.

    Mississippi did not have one: southaven's vhost claimed
    exposemississippi.com alongside its own subdomain, so the state hub page was
    pushed to a directory nothing served and the apex kept rendering Southaven's
    homepage. Oklahoma and Texas already had theirs, and this is a no-op there.
    """
    name = "expose" + state + "-state"
    hosts = STATE_EXTRA_HOSTS[state]
    tmpl = (ROOT / "shared" / "deploy" / "state.nginx.tmpl").read_text(encoding="utf-8")
    conf = (tmpl.replace("{{hosts_nginx}}", " ".join(hosts))
                .replace("{{domain}}", STATE_HUB[state][0])
                .replace("{{root}}", root)
                .replace("{{name}}", name))
    write_remote(f"/tmp/{name}.nginx", conf)
    ssh(f"pct push {vmid} /tmp/{name}.nginx /etc/nginx/sites-available/{name}")
    ssh(f"pct exec {vmid} -- ln -sf /etc/nginx/sites-available/{name} "
        f"/etc/nginx/sites-enabled/{name}")
    ssh(f"rm -f /tmp/{name}.nginx")

    _strip_apex_from_other_vhosts(vmid, name, hosts)
    ssh(f"pct exec {vmid} -- nginx -t", check=False)
    ssh(f"pct exec {vmid} -- systemctl reload nginx")


def _strip_apex_from_other_vhosts(vmid, keep, hosts):
    """Remove the apex hostnames from every vhost except the state hub's.

    Southaven's hand-written vhost listed exposemississippi.com next to its own
    subdomain. Two server blocks answering to one name is resolved by load order
    rather than by intent, so the apex has to belong to exactly one of them.

    The edit reads each file out, changes it here, and writes it back, rather
    than running an in-container sed. Escaping a regex through
    ssh -> pct exec -> sh -> sed is four layers of quoting over the file that
    decides whether every site in the container resolves.
    """
    import re as _re
    listing = ssh(f"pct exec {vmid} -- ls /etc/nginx/sites-available",
                  read_only=True).split()
    for f in listing:
        if f == keep:
            continue
        path = f"/etc/nginx/sites-available/{f}"
        conf = ssh(f"pct exec {vmid} -- cat {path}", read_only=True, check=False)
        if not conf or "server_name" not in conf:
            continue
        # Rewrite the directive as a list of names rather than substituting a
        # pattern. A regex with a backreference over this file already went wrong
        # once and wrote a literal 0x01 byte where "server_name" had been, which
        # left nginx refusing to load the container's entire config. Splitting
        # the names and reassembling the line cannot fail that way: the worst
        # case is that nothing changes.
        def _rewrite(m):
            names = [n for n in m.group(1).split() if n not in hosts]
            return "server_name " + " ".join(names) + ";" if names else m.group(0)

        new = _re.sub(r"server_name\s+([^;]+);", _rewrite, conf)
        if new == conf:
            continue
        # Belt and braces: never ship a vhost that lost its server_name.
        if new.count("server_name") != conf.count("server_name") \
                or _re.search(r"server_name\s*;", new):
            print(f"  ..   hub   {f}: rewrite looked wrong, left alone")
            continue
        write_remote(f"/tmp/{f}.vhost", new)
        ssh(f"pct push {vmid} /tmp/{f}.vhost {path}")
        ssh(f"rm -f /tmp/{f}.vhost")
        print(f"  ok   hub   {f}: apex hostname removed, now owned by {keep}")


# Miami OK is managed=legacy: its pages come from its own generators and
# /opt/mw-standardize.py stamps the shared bar onto them on a 15-minute timer.
# That standardiser reads the bar from a file rather than holding its own copy,
# so the file has to be kept current here.
LEGACY_BAR_TARGETS = {"miamiok": (170, "/opt/expose-chapterbar.html")}


def step_bars():
    src_dir = ROOT / "generated" / "chapterbars"
    for key, (vmid, dest) in LEGACY_BAR_TARGETS.items():
        src = src_dir / f"{key}.html"
        if not src.exists():
            print(f"  ..   bar   {key}: not generated - run shared/make_chapterbars.py")
            continue
        html = src.read_bytes()
        if DRY:
            print(f"    DRY  bar {key}: {len(html)} bytes -> {vmid}:{dest}")
            continue
        write_remote(f"/tmp/{key}-bar.html", html)
        ssh(f"pct push {vmid} /tmp/{key}-bar.html {dest}")
        ssh(f"rm -f /tmp/{key}-bar.html")
        _legacy_bar_css(key, vmid)
        # Stamp it now rather than waiting up to 15 minutes for the timer.
        ssh(f"pct exec {vmid} -- python3 /opt/mw-standardize.py --quiet", check=False)
        print(f"  ok   bar   {key}: {len(html)} bytes -> {vmid}:{dest}")


# Miami OK carries four stylesheets and its pages do not agree on which to use:
# 751 link exposemiami-theme.css and 10 - including the homepage - link
# theme.css. Patching only the first left the front page with v3 bar markup and
# no rules for it. Both get the shared block.
LEGACY_THEMES = {
    "miamiok": (170, ["/var/www/exposemiamiok/html/assets/exposemiami-theme.css",
                      "/var/www/exposemiamiok/html/assets/theme.css"]),
}
CSS_START = "/* MW:CHAPTERBAR:START */"
CSS_END = "/* MW:CHAPTERBAR:END */"


def _legacy_bar_css(key, vmid):
    """Keep the legacy chapter's stylesheet carrying the current bar rules.

    Miami OK has its own hand-maintained stylesheet. It was given the v3 bar
    markup while its CSS still knew only the v1 classes, so the picker rendered
    as an unstyled disclosure - correct HTML, broken-looking page. The shared
    rules are injected between markers and replaced wholesale on each run; the
    rest of that stylesheet is never touched.
    """
    import re as _re

    target = LEGACY_THEMES.get(key)
    css_src = ROOT / "shared" / "chapterbar.css"
    if not target or not css_src.exists():
        return
    vmid_css, paths = target
    block = CSS_START + "\n" + css_src.read_text(encoding="utf-8").rstrip() \
        + "\n" + CSS_END
    for path in paths:
        _inject_css(key, vmid_css, path, block)


def _inject_css(key, vmid_css, path, block):
    import re as _re
    cur = ssh(f"pct exec {vmid_css} -- cat {path}", read_only=True, check=False)
    if not cur:
        print(f"  ..   bar   {key}: could not read {path}")
        return
    if CSS_START in cur:
        new_css = _re.sub(_re.escape(CSS_START) + r".*?" + _re.escape(CSS_END),
                          lambda _: block, cur, flags=_re.S)
    else:
        # The first run also retires the v1 rules. Left in place, the old
        # .cb-links styling keeps applying to markup that no longer contains
        # those elements.
        old_block = _re.compile(
            r"/\* .{0,4} CHAPTER BAR \(mw-chapterbar\).*?(?=\n/\* |\Z)", _re.S)
        new_css = old_block.sub("", cur)
        new_css = new_css.rstrip() + "\n\n" + block + "\n"
    if new_css == cur:
        return
    if DRY:
        print(f"    DRY  bar {key}: stylesheet -> {len(new_css):,} bytes")
        return
    write_remote(f"/tmp/{key}-theme.css", new_css)
    ssh(f"pct push {vmid_css} /tmp/{key}-theme.css {path}")
    ssh(f"rm -f /tmp/{key}-theme.css")
    print(f"  ok   bar   {key}: stylesheet updated ({len(new_css):,} bytes)")


def _relabel_bar_for_apex(html, state):
    """Make the chapter bar say the STATE on the state's front door.

    The hub page is built inside whichever chapter hosts it, so its bar came out
    saying "San Antonio, TX" - which is true of the file and false of the page a
    reader is looking at when they type exposetexas.org. The same reason the
    current-chapter dot has to go: on the apex, the reader is not in any chapter.
    """
    import re as _re
    label = {"oklahoma": "Oklahoma", "texas": "Texas",
             "mississippi": "Mississippi"}[state]
    t = html.decode("utf-8")
    t = _re.sub(r'(<span class="cb-here">)[^<]*(</span>)',
                lambda m: m.group(1) + label + " statewide" + m.group(2), t, count=1)
    t = t.replace(' class="cur" aria-current="page"', "", 1)
    return t.encode("utf-8")


# Files the apex web root actually holds. Everything else on that page is a link
# into a chapter site and has to be absolutised - see _absolutise_apex_links.
APEX_LOCAL = ("/assets/", "/favicon", "/robots.txt", "/sitemap.xml", "/cdn-cgi/")


def _absolutise_apex_links(html, host):
    """Point the apex page's relative links at the chapter it was built from.

    The state apex serves a single index.html out of its own web root, but the
    page came from a chapter build and carries that chapter's nav, footer and
    donate banner - twenty-one relative links, every one of which 404'd.
    "Fund a public records request" was among them, which is the broken link
    Austin reported.

    Rewriting to the host chapter is the honest fix: those pages exist there, the
    content is chapter-appropriate, and a reader who lands on the state front
    door and clicks "File a records request" gets a real records page for a real
    city in their state instead of a 404. Anything the apex genuinely serves -
    the stylesheet, the favicon - is left alone.

    Donate is the exception. Every chapter now runs its own GoFundMe, so
    inheriting the host chapter's donate button would quietly bill every
    state-level donation to whichever city happens to host the hub - San Antonio
    for Texas, purely because it has the largest archive. A reader at the state
    front door has not chosen a city yet, so they are sent to the Foundation's
    chapter list to pick one.
    """
    import re as _re

    def repl(m):
        pre, path = m.group(1), m.group(2)
        if path.startswith(APEX_LOCAL) or path.startswith("//"):
            return m.group(0)
        return f'{pre}https://{host}{path}"'

    out = _re.sub(r'((?:href|src)=")(/[^"]*)"', repl, html.decode("utf-8"))

    # Runs after the rewrite above, so it catches the donate link whether the
    # chapter pointed at its own campaign or at the local funding explainer.
    out = _re.sub(
        r'<a href="[^"]*">Fund a public records request',
        '<a href="https://foundation.moveweight.com/#chapter-directory">'
        'Fund a public records request', out)

    return out.encode("utf-8")


def _push_assets(assets_dir, vmid, root):
    """Ship a built chapter's assets/ alongside a page copied out of it."""
    if not assets_dir.is_dir():
        return
    files = [f for f in assets_dir.iterdir() if f.is_file()]
    if not files or DRY:
        if DRY:
            print(f"    DRY  assets: {len(files)} files -> {vmid}:{root}/assets")
        return
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for f in files:
            tar.add(f, arcname="assets/" + f.name)
        # The shell links /favicon.svg at the ROOT. The apex serves out of its
        # own web root, so shipping only assets/ left it 404ing on every load.
        fav = assets_dir.parent / "favicon.svg"
        if fav.exists():
            tar.add(fav, arcname="favicon.svg")
    write_remote("/tmp/hub-assets.tgz", buf.getvalue())
    ssh(f"pct push {vmid} /tmp/hub-assets.tgz /tmp/hub-assets.tgz")
    ssh(f"pct exec {vmid} -- tar xzf /tmp/hub-assets.tgz -C {root}")
    ssh(f"pct exec {vmid} -- chown -R www-data:www-data {root}")
    ssh(f"pct exec {vmid} -- rm -f /tmp/hub-assets.tgz")
    ssh("rm -f /tmp/hub-assets.tgz")


def step_hub(state):
    """Publish the generated state hub page at the state domain's apex.

    make_state_hubs.py writes the hub as a `state.html` fragment inside whichever
    chapter can build it; this copies the BUILT page to the apex web root as
    index.html. The canonical inside it still points at that chapter's copy,
    which is deliberate - one page, one canonical, two addresses.
    """
    vmid, root = STATE_HUB_ROOT[state]
    # Which chapter hosts this hub is decided by make_state_hubs.py and written
    # to generated/state-hubs.json. Do not re-derive it: an earlier version took
    # the first chapter in the state with a built state.html, so a chapter that
    # hosted the hub in a previous run and still had a stale copy on disk won on
    # filename order - and the apex published a map two revisions old while the
    # current one sat unused.
    manifest = ROOT / "generated" / "state-hubs.json"
    try:
        host_key = json.loads(manifest.read_text(encoding="utf-8"))[state]
    except (OSError, ValueError, KeyError):
        print(f"  ..   hub   {state}: no entry in {manifest.name} "
              "- run shared/make_state_hubs.py first")
        return
    cfg = next((c for c in all_chapters() if c["key"] == host_key), None)
    src = (ROOT / cfg["source_dir"] / "site" / "state.html").resolve() if cfg else None
    if src is None or not src.exists():
        print(f"  ..   hub   {state}: {host_key} has no built state.html "
              "- run build.py first")
        return
    if DRY:
        print(f"    DRY  hub {state}: {src} -> {vmid}:{root}/index.html")
        return
    host = cfg.get("canonical_host") or cfg["domain"]
    html = _absolutise_apex_links(_relabel_bar_for_apex(src.read_bytes(), state),
                                  host)
    ssh(f"pct exec {vmid} -- mkdir -p {root}")
    _state_vhost(state, vmid, root)
    # The apex has its own web root, so it needs its own copy of the stylesheet
    # the hub page links. Without this it kept serving a theme.css from whenever
    # the hub was first published - which meant the state front doors rendered
    # the new chapter bar with none of its rules.
    _push_assets(src.parent / "assets", vmid, root)
    write_remote(f"/tmp/{state}-hub.html", html)
    ssh(f"pct push {vmid} /tmp/{state}-hub.html {root}/index.html")
    ssh(f"pct exec {vmid} -- chown -R www-data:www-data {root}")
    ssh(f"rm -f /tmp/{state}-hub.html")
    print(f"  ok   hub   {state}: {len(html):,} bytes -> {vmid}:{root}/index.html")


def step_traefik(state):
    """Rewrite one state's router rule to cover every chapter it serves.

    The host list comes from EVERY chapter in the state, not just the ones this
    script provisions. Miami OK, San Angelo and Southaven predate the shared
    container and are flagged differently; a rule built only from the chapters
    being deployed would have silently dropped all three live sites off their
    routers the first time this ran. The dry run is what caught it, which is the
    argument for having one.
    """
    domain, vmid = STATE_HUB[state]
    name = "expose" + state
    hosts = list(STATE_EXTRA_HOSTS[state])
    for cfg in all_chapters():
        if cfg.get("state_key") != state:
            continue
        for h in cfg.get("hosts", []) + [cfg.get("canonical_host", "")]:
            if h and h not in hosts:
                hosts.append(h)
    rule = " || ".join(f"Host(`{h}`)" for h in hosts)
    ip = {"oklahoma": "192.168.0.170", "texas": "192.168.0.175",
          "mississippi": "192.168.0.176"}[state]
    # ASCII ONLY, deliberately. Traefik's file provider aborts the ENTIRE
    # configuration when any one file in conf.d is not valid UTF-8 - not just
    # that file, all of it. An em-dash in this comment, written from a Windows
    # shell as a cp1252 byte, took all 128 routers on the node offline at once.
    # There is no reason for a generated config comment to contain a character
    # that can fail, so it does not.
    conf = f"""# {domain} - generated by shared/deploy/provision.py
# One router for the whole state: the hub at the apex plus every city chapter,
# all served from ct {vmid}. Regenerate rather than hand-editing, or the next
# chapter silently 404s because somebody forgot a Host() clause.
#
# Keep this file ASCII. See the note in provision.py step_traefik().
http:
  routers:
    {name}-rtr:
      rule: "{rule}"
      entryPoints: [websecure]
      middlewares: [{name}-headers]
      service: {name}-svc
      tls:
        certResolver: myresolver

  middlewares:
    {name}-headers:
      headers:
        customRequestHeaders:
          X-Forwarded-Proto: "https"
          X-Forwarded-Port: "443"

  services:
    {name}-svc:
      loadBalancer:
        passHostHeader: true
        servers:
          - url: "http://{ip}"
"""
    try:
        conf.encode("ascii")
    except UnicodeEncodeError as e:
        raise SystemExit(
            f"  ! refusing to write {name}.yml: non-ASCII at position {e.start}. "
            "Traefik drops every router on the node if one conf.d file is not "
            "valid UTF-8, so this file is held to ASCII.")

    if DRY:
        print(f"    DRY  traefik {state}: {len(hosts)} hosts")
        print("         " + rule)
        return
    write_remote(f"/tmp/{name}.yml", conf.encode("utf-8"))
    # The backup goes OUTSIDE conf.d. Traefik's file provider loads every file in
    # that directory whatever its extension, so a "<name>.yml.bak" defines a
    # SECOND router with the same name, Traefik resolves the duplicate by keeping
    # one of them, and the stale copy can win. That is exactly what happened the
    # first time this ran: eleven new hosts 404'd while the old rule stayed live.
    ssh("pct exec 107 -- mkdir -p /etc/traefik/backups")
    ssh(f"pct exec 107 -- sh -c 'cp /etc/traefik/conf.d/{name}.yml "
        f"/etc/traefik/backups/{name}.yml.$(date +%Y%m%d-%H%M%S) 2>/dev/null || true'",
        check=False)
    ssh(f"pct push 107 /tmp/{name}.yml /etc/traefik/conf.d/{name}.yml")
    ssh(f"rm -f /tmp/{name}.yml")
    # Traefik watches conf.d and reloads on its own; no restart, which would drop
    # every other site on the node for a second.
    print(f"  ok   traefik {state}: {len(hosts)} hosts -> {ip}")


def main():
    global DRY
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dns", action="store_true")
    ap.add_argument("--nginx", action="store_true")
    ap.add_argument("--site", action="store_true")
    ap.add_argument("--traefik", action="store_true")
    ap.add_argument("--bars", action="store_true",
                    help="deploy the generated chapter bar to legacy chapters")
    ap.add_argument("--hubs", action="store_true",
                    help="publish the generated state hub page at each state apex")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    DRY = args.dry_run

    # --site reaches every deployable chapter; --nginx/--dns only the ones whose
    # vhost and DNS this script owns.
    site_only = args.site and not (args.nginx or args.dns or args.traefik)
    chapters = ((deployable_chapters() if site_only else city_chapters())
                if args.all else [load(k) for k in args.keys])
    if not chapters:
        raise SystemExit("name chapters, or pass --all")

    steps = {"dns": args.dns, "nginx": args.nginx, "site": args.site,
             "traefik": args.traefik, "hubs": args.hubs, "bars": args.bars}
    if not any(steps.values()):
        steps["nginx"] = steps["site"] = True

    if steps["dns"]:
        token = cf_token()
        zl = cf("GET", "/zones?per_page=50", token)
        zones = {z["name"]: z["id"] for z in zl.get("result", [])}
        print(f"\n== dns ({len(zones)} zones visible)")
        for cfg in chapters:
            step_dns(cfg, token, zones)

    if steps["nginx"]:
        print("\n== nginx")
        for cfg in chapters:
            step_nginx(cfg)

    if steps["site"]:
        print("\n== site")
        for cfg in chapters:
            step_site(cfg)

    if steps["bars"]:
        print("\n== chapter bars")
        step_bars()

    if steps["hubs"]:
        print("\n== state hubs")
        for state in STATE_HUB:
            step_hub(state)

    if steps["traefik"]:
        print("\n== traefik")
        touched = {c.get("state_key") for c in chapters}
        for state in [s for s in STATE_HUB if s in touched]:
            step_traefik(state)

    print("\n  done")


if __name__ == "__main__":
    main()
