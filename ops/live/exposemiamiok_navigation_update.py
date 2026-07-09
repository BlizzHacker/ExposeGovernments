import re
from pathlib import Path

ROOT = Path("/var/www/exposemiamiok/html")
VERSION = "20260601-unified-menu-agenda6"

NAV_ITEMS = [
    ("/", "Home"),
    ("/search.html", "Search"),
    ("/local-news.html", "News"),
    ("/#resources", "City Resources"),
    ("/crime-watch.html", "Crime Watch"),
    ("/foia/", "FOIA"),
    ("/community-tools.html", "Tools"),
    ("/miami-oklahoma.html", "Miami OK"),
    ("/ottawa-county-guide.html", "Ottawa County"),
    ("/court-search/", "Court Search"),
    ("/#utilities", "Utilities"),
    ("/#media", "Media & Feed"),
    ("/#corruption", "Records Archive"),
    ("/#map", "Area Map"),
    ("/meetings/", "Transcripts"),
    ("/blog/", "Blog"),
    ("/ottawa-county.html", "Ottawa County"),
    ("/follow-the-money.html", "Finance"),
    ("/youtube.html", "YouTube"),
    ("/videos.html", "Videos"),
    ("https://www.facebook.com/profile.php?id=61590391534875", "Facebook"),
    ("/#about", "About"),
]

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

CSS_BLOCK = f"""
/* single unified menu: {VERSION} */
body .mw-unified-shell .mw-unified-nav.dnav {{
  display: none !important;
}}
body .mw-unified-shell .mw-unified-header {{
  border-bottom: 1px solid var(--mw-border) !important;
}}
body .mw-unified-shell .hdr-inner {{
  width: min(1500px, calc(100% - 28px)) !important;
  min-height: 92px !important;
}}
body .mw-unified-shell .ham {{
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 8px !important;
  width: auto !important;
  min-width: 106px !important;
  height: 46px !important;
  min-height: 46px !important;
  padding: 0 14px !important;
  border: 1px solid var(--mw-border) !important;
  border-radius: 8px !important;
  background: rgba(15, 23, 42, .86) !important;
  color: var(--mw-text) !important;
  box-shadow: none !important;
}}
body .mw-unified-shell .ham::after {{
  content: "Menu";
  font-size: .86rem !important;
  font-weight: 900 !important;
  letter-spacing: .02em !important;
}}
body .mw-unified-shell .ham.active::after {{
  content: "Close";
}}
body .mw-unified-shell .ham span {{
  width: 19px !important;
  height: 2px !important;
  background: currentColor !important;
}}
body .mw-unified-shell .drawer-overlay {{
  position: fixed !important;
  inset: 0 !important;
  background: rgba(2, 6, 23, .62) !important;
  z-index: 6000 !important;
  opacity: 0 !important;
  visibility: hidden !important;
  pointer-events: none !important;
  transition: opacity .18s ease, visibility .18s ease !important;
}}
body .mw-unified-shell .drawer-overlay.show {{
  opacity: 1 !important;
  visibility: visible !important;
  pointer-events: auto !important;
}}
body .mw-unified-shell .drawer {{
  position: fixed !important;
  top: 0 !important;
  right: 0 !important;
  left: auto !important;
  width: min(430px, calc(100vw - 22px)) !important;
  height: 100vh !important;
  padding: 124px 16px 24px !important;
  overflow-y: auto !important;
  transform: translateX(110%) !important;
  transition: transform .22s ease !important;
  z-index: 6001 !important;
  display: grid !important;
  align-content: start !important;
  grid-template-columns: 1fr !important;
  gap: 8px !important;
  visibility: hidden !important;
  pointer-events: none !important;
  background: rgba(15, 23, 42, .98) !important;
  border-left: 1px solid var(--mw-border) !important;
  box-shadow: -24px 0 60px rgba(0,0,0,.36) !important;
}}
body .mw-unified-shell .drawer.open {{
  transform: translateX(0) !important;
  visibility: visible !important;
  pointer-events: auto !important;
}}
html body .mw-unified-shell nav.drawer#mw-drawer {{
  right: 0 !important;
  left: auto !important;
  margin: 0 !important;
  transform: translate3d(110%, 0, 0) !important;
}}
html body .mw-unified-shell nav.drawer#mw-drawer.open {{
  right: 0 !important;
  left: auto !important;
  transform: translate3d(0, 0, 0) !important;
  visibility: visible !important;
  pointer-events: auto !important;
}}
body .mw-unified-shell .drawer a {{
  display: flex !important;
  align-items: center !important;
  justify-content: space-between !important;
  min-height: 46px !important;
  margin: 0 !important;
  padding: 10px 13px !important;
  border: 1px solid var(--mw-border) !important;
  border-radius: 8px !important;
  background: rgba(30, 41, 59, .62) !important;
  color: var(--mw-text) !important;
  font-size: .98rem !important;
  font-weight: 850 !important;
  line-height: 1.2 !important;
  text-decoration: none !important;
}}
body .mw-unified-shell .drawer a::after {{
  content: ">";
  color: var(--mw-muted) !important;
  font-weight: 900 !important;
}}
body .mw-unified-shell .drawer a:hover,
body .mw-unified-shell .drawer a[aria-current="page"] {{
  border-color: rgba(220, 38, 38, .72) !important;
  background: rgba(220, 38, 38, .18) !important;
  color: #fff !important;
}}
.mw-unified-shell .mw-nav-link,
.mw-unified-shell .mw-nav-button,
.mw-unified-shell .mw-nav-group,
.mw-unified-shell .mw-nav-menu,
.mw-unified-shell .mw-drawer-label {{
  display: none !important;
}}
@media (min-width: 760px) {{
  body .mw-unified-shell .drawer {{
    padding-top: 138px !important;
    grid-template-columns: 1fr 1fr !important;
    width: min(620px, calc(100vw - 40px)) !important;
  }}
  body .mw-unified-shell .drawer a {{
    min-height: 52px !important;
  }}
}}
@media (max-width: 899px) {{
  body .mw-unified-shell .mw-unified-header {{
    padding: 8px 10px !important;
  }}
  body .mw-unified-shell .hdr-inner {{
    min-height: 76px !important;
    width: min(100%, calc(100% - 8px)) !important;
    gap: 10px !important;
  }}
  body .mw-unified-shell .logo {{
    gap: 0 !important;
    flex: 0 1 auto !important;
    min-width: 0 !important;
  }}
  body .mw-unified-shell .logo > div {{
    display: none !important;
  }}
  body .mw-unified-shell .logo img {{
    width: 92px !important;
    height: 68px !important;
    min-width: 92px !important;
    min-height: 68px !important;
    flex-basis: 92px !important;
  }}
  body .mw-unified-shell .ham {{
    display: inline-flex !important;
    min-width: 92px !important;
    height: 44px !important;
  }}
  body .mw-unified-shell .drawer {{
    padding-top: 94px !important;
  }}
}}
@media (max-width: 700px) {{
  html,
  body {{
    max-width: 100vw !important;
    overflow-x: hidden !important;
  }}
  html body .mw-unified-shell nav.drawer#mw-drawer {{
    top: 92px !important;
    left: 0 !important;
    right: auto !important;
    width: 100vw !important;
    max-width: 100vw !important;
    height: calc(100vh - 92px) !important;
    padding: 10px 12px 18px !important;
    grid-template-columns: 1fr !important;
    transform: translate3d(0, -115%, 0) !important;
    border-left: 0 !important;
    border-top: 1px solid var(--mw-border) !important;
    box-shadow: 0 22px 60px rgba(0, 0, 0, .38) !important;
  }}
  html body .mw-unified-shell nav.drawer#mw-drawer.open {{
    left: 0 !important;
    right: auto !important;
    transform: translate3d(0, 0, 0) !important;
  }}
  body .mw-unified-shell .drawer-overlay {{
    top: 92px !important;
  }}
  body .mw-unified-shell .drawer a {{
    width: auto !important;
    min-height: 44px !important;
    font-size: .95rem !important;
  }}
}}
@media (max-width: 430px) {{
  body .mw-unified-shell .logo img {{
    width: 84px !important;
    height: 62px !important;
    min-width: 84px !important;
    min-height: 62px !important;
    flex-basis: 84px !important;
  }}
  body .mw-unified-shell .ham {{
    min-width: 82px !important;
    height: 42px !important;
    padding: 0 10px !important;
  }}
  body .mw-unified-shell .ham::after {{
    font-size: .8rem !important;
  }}
  body .mw-unified-shell .drawer {{
    width: 100vw !important;
    padding-top: 10px !important;
    padding-left: 10px !important;
    padding-right: 10px !important;
  }}
}}
/* end single unified menu */
"""


def update_css():
    path = ROOT / "assets" / "exposemiami-theme.css"
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"/\* grouped navigation: .*?/\* end grouped navigation \*/\n?", "", text, flags=re.S)
    text = re.sub(r"/\* compact full navigation: .*?/\* end compact full navigation \*/\n?", "", text, flags=re.S)
    text = re.sub(r"/\* single unified menu: .*?/\* end single unified menu \*/\n?", "", text, flags=re.S)
    path.write_text(text.rstrip() + "\n\n" + CSS_BLOCK, encoding="utf-8")


def update_html(path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    original = text
    text = re.sub(
        r'(<nav\b[^>]*class="[^"]*\bdnav\b[^"]*"[^>]*>\s*<div class="dnav-inner">\s*)(.*?)(\s*</div>\s*</nav>)',
        lambda match: match.group(1) + FALLBACK_NAV_HTML + match.group(3),
        text,
        flags=re.S,
    )
    text = re.sub(r"/assets/exposemiami-ui\.js\?v=[^\"']+", f"/assets/exposemiami-ui.js?v={VERSION}", text)
    text = text.replace('/assets/exposemiami-ui.js"', f'/assets/exposemiami-ui.js?v={VERSION}"')
    text = re.sub(r"/assets/exposemiami-theme\.css\?v=[^\"']+", f"/assets/exposemiami-theme.css?v={VERSION}", text)
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
    changed = 0
    checked = 0
    for path in ROOT.rglob("*.html"):
        checked += 1
        if update_html(path):
            changed += 1
    update_sitemap()
    print(f"full menu updated checked={checked} changed={changed} version={VERSION}")


if __name__ == "__main__":
    main()
