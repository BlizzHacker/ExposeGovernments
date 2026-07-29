import hashlib
import re
import sys
from pathlib import Path

ROOT = Path("/var/www/exposemiamiok/html")
VERSION = "20260728-nav-restore"

# The one navigation. This script used to carry its own copy and overwrite the
# corrected one every hour; see /opt/nav_constants.py for why the list is what
# it is. Deliberately not wrapped in try/except: writing a stale nav to 800
# pages silently is worse than a cron failure that gets logged.
sys.path.insert(0, "/opt")
from nav_constants import NAV_ITEMS  # noqa: E402


def _js_nav_items():
    """Render NAV_ITEMS as the JS array literal UI_JS expects."""
    rows = "\n".join(
        '    [{}, {}],'.format(_js_str(href), _js_str(label))
        for href, label in NAV_ITEMS
    )
    return "const navItems = [\n" + rows + "\n  ]"


def _js_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


FALLBACK_NAV_HTML = "".join(f'<a href="{href}">{label}</a>' for href, label in NAV_ITEMS)

UI_JS = r"""(function () {
  const navItems = [
    ["/", "Home"],
    ["/search.html", "Search"],
    ["/local-news.html", "News"],
    ["/#resources", "City Resources"],
    ["/crime-watch.html", "Crime Watch"],
    ["/foia/", "FOIA"],
    ["/community-tools.html", "Tools"],
    ["/miami-oklahoma.html", "Miami OK"],
    ["/ottawa-county-guide.html", "Ottawa County"],
    ["/court-search/", "Court Search"],
    ["/#utilities", "Utilities"],
    ["/#media", "Media & Feed"],
    ["/#corruption", "Records Archive"],
    ["/#map", "Area Map"],
    ["/meetings/", "Transcripts"],
    ["/blog/", "Blog"],
    ["/ottawa-county.html", "Ottawa County"],
    ["/follow-the-money.html", "Finance"],
    ["/youtube.html", "YouTube"],
    ["/videos.html", "Videos"],
    ["https://www.facebook.com/profile.php?id=61590391534875", "Facebook"],
    ["/#about", "About"],
  ];

  function normalizedPath() {
    return window.location.pathname.replace(/\/index\.html$/, "/");
  }

  function isActive(href) {
    const path = normalizedPath();
    if (!href || href.startsWith("http")) return false;
    if (href === "/") return path === "/";
    if (href === "/follow-the-money.html" && (path.startsWith("/finance-transcripts") || path.startsWith("/agenda-packets"))) return true;
    if (href.includes("#")) return path === "/" && href.startsWith("/#");
    const base = href.replace(/\/index\.html$/, "/").replace(/\.html$/, "");
    return path === href || (base !== "/" && path.startsWith(base));
  }

  function closeDrawer() {
    document.getElementById("mw-drawer")?.classList.remove("open");
    document.getElementById("mw-drawer-overlay")?.classList.remove("show");
    document.getElementById("mw-ham")?.classList.remove("active");
  }

  function toggleDrawer() {
    document.getElementById("mw-drawer")?.classList.toggle("open");
    document.getElementById("mw-drawer-overlay")?.classList.toggle("show");
    document.getElementById("mw-ham")?.classList.toggle("active");
  }

  function makeLink(href, label) {
    const link = document.createElement("a");
    link.href = href;
    link.textContent = label;
    if (href.startsWith("http")) {
      link.target = "_blank";
      link.rel = "noopener";
    }
    if (isActive(href)) link.setAttribute("aria-current", "page");
    return link;
  }

  function fillLinks(container) {
    container.innerHTML = "";
    for (const [href, label] of navItems) {
      const link = makeLink(href, label);
      link.addEventListener("click", closeDrawer);
      container.appendChild(link);
    }
  }

  function buildHeader() {
    if (document.querySelector(".mw-unified-shell")) {
      const existing = document.querySelector(".mw-unified-shell");
      const tagline = existing.querySelector(".logo p");
      if (tagline) tagline.textContent = "Public Records & Civic Tools";
      const drawer = existing.querySelector("#mw-drawer");
      const desktop = existing.querySelector(".dnav-inner");
      if (drawer) fillLinks(drawer);
      if (desktop) fillLinks(desktop);
      existing.querySelector("#mw-ham")?.addEventListener("click", toggleDrawer);
      existing.querySelector("#mw-drawer-overlay")?.addEventListener("click", closeDrawer);
      return;
    }

    const shell = document.createElement("div");
    shell.className = "mw-unified-shell";
    shell.innerHTML = `
      <header class="hdr mw-unified-header">
        <div class="hdr-inner">
          <a class="logo" href="/" aria-label="ExposeMiamiOK home">
            <img src="/images/logo-header.png" alt="">
            <div>
              <h1>ExposeMiamiOK</h1>
              <p>Public Records & Civic Tools</p>
            </div>
          </a>
          <button class="ham" id="mw-ham" type="button" aria-label="Open navigation"><span></span><span></span><span></span></button>
        </div>
      </header>
      <div class="drawer-overlay" id="mw-drawer-overlay"></div>
      <nav class="drawer" id="mw-drawer" aria-label="Mobile navigation"></nav>
      <nav class="dnav mw-unified-nav" aria-label="Primary navigation"><div class="dnav-inner"></div></nav>
    `;

    fillLinks(shell.querySelector("#mw-drawer"));
    fillLinks(shell.querySelector(".dnav-inner"));

    document.body.prepend(shell);
    shell.querySelector("#mw-ham").addEventListener("click", toggleDrawer);
    shell.querySelector("#mw-drawer-overlay").addEventListener("click", closeDrawer);
  }

  function hideOldNavigation() {
    document
      .querySelectorAll("body > header, body > .hdr, body > nav.dnav, body > nav.drawer, body > .drawer-overlay, body > .nav")
      .forEach((node) => {
        if (!node.closest(".mw-unified-shell")) node.classList.add("mw-retired-ui");
      });
  }

  function init() {
    hideOldNavigation();
    buildHeader();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
"""

# UI_JS ships a hardcoded copy of the list; replace it with the real one.
UI_JS = re.sub(r"const navItems = \[.*?\n  \]", lambda _m: _js_nav_items(),
                UI_JS, count=1, flags=re.S)
if '"/#corruption"' in UI_JS:
    raise SystemExit("navItems substitution failed - refusing to publish the old nav")


CSS_BLOCK = r"""
/* single unified menu: 20260728-nav-restore
   ---------------------------------------------------------------------------
   Replaces "20260601-unified-menu-agenda6", the seventh layer of nav patches on
   this stylesheet and the one that made the site look broken:

   * it set .dnav { display:none } at TOP LEVEL, so the desktop navigation bar
     was hidden at every width - a 1272px desktop had no visible navigation at
     all, only a button;
   * .ham was display:inline-flex with no flex-direction, so its three bars laid
     out in a row and the button read "- - - Menu" instead of showing an icon;
   * at >=760px the drawer became grid-template-columns:1fr 1fr at 620px wide,
     so opening the menu threw a two-column slab of oversized buttons across
     half the screen.

   The earlier layers already define a proper desktop bar (offsets ~13151 and
   ~15628); removing the override above is what brings it back. This layer only
   adds what those layers lack: the bar wraps instead of clipping, because 18
   labels do not fit on one 1200px line.

   Desktop (>=900px): the real nav bar. No hamburger.
   Mobile  (<900px):  hamburger icon, single-column sheet from the right.
   --------------------------------------------------------------------------- */

/* The shell was pinned at z-index:2147483000 by the "MENU LOCK 20260601"
   block above, which put it above everything on the page forever - including
   the chapter bar's own dropdown, which opened behind the donate banner and
   the nav rows. Page content here tops out around 200; the chapter bar sits at
   9000 because its panel must cover the header. */
body .mw-unified-shell {
  z-index: 5000 !important;
}

/* Header sits above the drawer so the button that opened it can close it. */
body .mw-unified-shell .mw-unified-header {
  border-bottom: 1px solid var(--mw-border) !important;
  position: relative !important;
  z-index: 6002 !important;
}
body .mw-unified-shell .hdr-inner {
  width: min(1500px, calc(100% - 28px)) !important;
  min-height: 92px !important;
}

/* -- the hamburger: three stacked bars, becoming an X when open ------------ */
body .mw-unified-shell .ham {
  display: inline-flex !important;
  flex-direction: column !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 5px !important;
  width: 46px !important;
  min-width: 46px !important;
  height: 46px !important;
  min-height: 46px !important;
  padding: 0 !important;
  border: 1px solid var(--mw-border) !important;
  border-radius: 8px !important;
  background: rgba(15, 23, 42, .86) !important;
  color: var(--mw-text) !important;
  box-shadow: none !important;
  cursor: pointer !important;
}
body .mw-unified-shell .ham::after { content: none !important; }
body .mw-unified-shell .ham span {
  display: block !important;
  width: 20px !important;
  height: 2px !important;
  border-radius: 2px !important;
  background: currentColor !important;
  transition: transform .18s ease, opacity .18s ease !important;
}
body .mw-unified-shell .ham.active span:nth-child(1) {
  transform: translateY(7px) rotate(45deg) !important;
}
body .mw-unified-shell .ham.active span:nth-child(2) { opacity: 0 !important; }
body .mw-unified-shell .ham.active span:nth-child(3) {
  transform: translateY(-7px) rotate(-45deg) !important;
}
@media (prefers-reduced-motion: reduce) {
  body .mw-unified-shell .ham span { transition: none !important; }
}

/* -- desktop: the real navigation bar -------------------------------------- */
@media (min-width: 900px) {
  body .mw-unified-shell .mw-unified-nav.dnav {
    display: block !important;
    height: auto !important;
    overflow: visible !important;
  }
  body .mw-unified-shell .mw-unified-nav.dnav .dnav-inner {
    height: auto !important;
    flex-wrap: wrap !important;
    justify-content: center !important;
    padding: 3px 0 !important;
  }
  body .mw-unified-shell .mw-unified-nav.dnav .dnav-inner > a {
    height: 38px !important;
    min-height: 38px !important;
    padding: 0 11px !important;
    font-size: .78rem !important;
  }
  body .mw-unified-shell .ham { display: none !important; }
  /* Nothing left hanging if the viewport grows while the sheet is open. */
  html body .mw-unified-shell nav.drawer#mw-drawer,
  body .mw-unified-shell .drawer-overlay { display: none !important; }
}

/* -- mobile: one column, from the right ------------------------------------ */
body .mw-unified-shell .drawer-overlay {
  position: fixed !important;
  inset: 0 !important;
  background: rgba(2, 6, 23, .62) !important;
  z-index: 6000 !important;
  opacity: 0 !important;
  visibility: hidden !important;
  pointer-events: none !important;
  transition: opacity .18s ease, visibility .18s ease !important;
}
body .mw-unified-shell .drawer-overlay.show {
  opacity: 1 !important;
  visibility: visible !important;
  pointer-events: auto !important;
}
html body .mw-unified-shell nav.drawer#mw-drawer {
  position: fixed !important;
  top: 0 !important;
  right: 0 !important;
  left: auto !important;
  margin: 0 !important;
  width: min(340px, calc(100vw - 34px)) !important;
  max-width: none !important;
  height: 100vh !important;
  padding: 100px 14px 24px !important;
  overflow-y: auto !important;
  display: grid !important;
  align-content: start !important;
  grid-template-columns: 1fr !important;
  gap: 6px !important;
  transform: translate3d(110%, 0, 0) !important;
  transition: transform .22s ease !important;
  z-index: 6001 !important;
  visibility: hidden !important;
  pointer-events: none !important;
  background: rgba(15, 23, 42, .98) !important;
  border-left: 1px solid var(--mw-border) !important;
  border-top: 0 !important;
  box-shadow: -24px 0 60px rgba(0, 0, 0, .36) !important;
}
html body .mw-unified-shell nav.drawer#mw-drawer.open {
  transform: translate3d(0, 0, 0) !important;
  visibility: visible !important;
  pointer-events: auto !important;
}
body .mw-unified-shell .drawer a {
  display: flex !important;
  align-items: center !important;
  justify-content: space-between !important;
  min-height: 42px !important;
  margin: 0 !important;
  padding: 8px 12px !important;
  border: 1px solid var(--mw-border) !important;
  border-radius: 8px !important;
  background: rgba(30, 41, 59, .62) !important;
  color: var(--mw-text) !important;
  font-size: .92rem !important;
  font-weight: 700 !important;
  line-height: 1.2 !important;
  text-decoration: none !important;
}
body .mw-unified-shell .drawer a::after {
  content: "\203A" !important;
  color: var(--mw-muted) !important;
  font-weight: 900 !important;
}
body .mw-unified-shell .drawer a:hover,
body .mw-unified-shell .drawer a[aria-current="page"] {
  border-color: rgba(220, 38, 38, .72) !important;
  background: rgba(220, 38, 38, .18) !important;
  color: #fff !important;
}

/* Leftovers from the navigation systems this one replaced. */
.mw-unified-shell .mw-nav-link,
.mw-unified-shell .mw-nav-button,
.mw-unified-shell .mw-nav-group,
.mw-unified-shell .mw-nav-menu,
.mw-unified-shell .mw-drawer-label {
  display: none !important;
}

@media (max-width: 899px) {
  body .mw-unified-shell .mw-unified-nav.dnav { display: none !important; }
  body .mw-unified-shell .mw-unified-header { padding: 8px 10px !important; }
  body .mw-unified-shell .hdr-inner {
    min-height: 76px !important;
    width: min(100%, calc(100% - 8px)) !important;
    gap: 10px !important;
  }
  body .mw-unified-shell .logo {
    gap: 0 !important;
    flex: 0 1 auto !important;
    min-width: 0 !important;
  }
  body .mw-unified-shell .logo > div { display: none !important; }
  body .mw-unified-shell .logo img {
    width: 92px !important;
    height: 68px !important;
    min-width: 92px !important;
    min-height: 68px !important;
    flex-basis: 92px !important;
  }
  body .mw-unified-shell .ham { display: inline-flex !important; }
  html body .mw-unified-shell nav.drawer#mw-drawer { padding-top: 88px !important; }
}

@media (max-width: 430px) {
  html, body { max-width: 100vw !important; overflow-x: hidden !important; }
  body .mw-unified-shell .logo img {
    width: 84px !important;
    height: 62px !important;
    min-width: 84px !important;
    min-height: 62px !important;
    flex-basis: 84px !important;
  }
  body .mw-unified-shell .ham {
    width: 42px !important;
    min-width: 42px !important;
    height: 42px !important;
    min-height: 42px !important;
  }
  html body .mw-unified-shell nav.drawer#mw-drawer {
    width: min(300px, calc(100vw - 24px)) !important;
    padding-top: 82px !important;
  }
}
/* end single unified menu */
"""


def update_css():
    path = ROOT / "assets" / "exposemiami-theme.css"
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"/\* grouped navigation: .*?/\* end grouped navigation \*/\n?", "", text, flags=re.S)
    text = re.sub(r"/\* compact full navigation: .*?/\* end compact full navigation \*/\n?", "", text, flags=re.S)
    text = re.sub(r"/\* single unified menu: .*?/\* end single unified menu \*/\n?", "", text, flags=re.S)
    path.write_text(text.rstrip() + "\n\n" + CSS_BLOCK, encoding="utf-8")


def asset_ver(name):
    """sha256[:8] of the built asset - the same scheme mw-standardize.py uses.

    A hand-typed VERSION meant editing an asset did not change the URL a page
    asked for, so a returning reader kept the copy already in their cache. It
    also meant this script and mw-standardize stamped different values and
    rewrote each other's every hour.
    """
    return hashlib.sha256((ROOT / "assets" / name).read_bytes()).hexdigest()[:8]


def update_html(path, js_ver, css_ver):
    text = path.read_text(encoding="utf-8", errors="ignore")
    original = text
    # mw-standardize.py owns the nav markup. This used to rewrite .dnav-inner
    # here from the same NAV_ITEMS but joined with "" instead of one indented
    # anchor per line, so the two rewrote each other's formatting on 770 pages
    # every hour without either ever settling. Assets here, HTML there.
    text = re.sub(r"/assets/exposemiami-ui\.js(\?v=[\w.-]*)?",
                  "/assets/exposemiami-ui.js?v=" + js_ver, text)
    text = re.sub(r"/assets/exposemiami-theme\.css(\?v=[\w.-]*)?",
                  "/assets/exposemiami-theme.css?v=" + css_ver, text)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def update_sitemap():
    path = ROOT / "sitemap.xml"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    today = "2026-06-01"
    urls = [
        "https://exposemiamiok.com/search.html",
        "https://exposemiamiok.com/local-news.html",
        "https://exposemiamiok.com/follow-the-money.html",
        "https://exposemiamiok.com/automation-status.html",
        "https://exposemiamiok.com/agenda-packets/",
        "https://exposemiamiok.com/agenda-packets/miami-city-council-2026-06-02.html",
    ]
    for url in urls:
        if url not in text:
            text = text.replace("</urlset>", f"  <url><loc>{url}</loc><lastmod>{today}</lastmod></url>\n</urlset>")
    path.write_text(text, encoding="utf-8")


def main():
    (ROOT / "assets" / "exposemiami-ui.js").write_text(UI_JS, encoding="utf-8")
    update_css()
    # Hash after writing, so the stamp describes what is actually on disk.
    js_ver = asset_ver("exposemiami-ui.js")
    css_ver = asset_ver("exposemiami-theme.css")
    changed = 0
    checked = 0
    for path in ROOT.rglob("*.html"):
        checked += 1
        if update_html(path, js_ver, css_ver):
            changed += 1
    update_sitemap()
    print(f"full menu updated checked={checked} changed={changed} "
          f"nav_items={len(NAV_ITEMS)} js={js_ver} css={css_ver}")


if __name__ == "__main__":
    main()
