"""The one Miami navigation. Imported by every generator; injected and kept
current on every page by mw-standardize.py.

Why this was rewritten (2026-07-28)
-----------------------------------
Miami had two navigations running at once and neither was complete.

* 12 top-level pages carried no site nav at all - including the homepage,
  City Desk, Follow the Money, Videos and Tips - while 749 sub-pages had one.
  The flagship pages were the ones a reader could not navigate from.
* The nav that did exist had been edited in place on deployed pages but not
  here, so this file and the live site disagreed: "Corruption Archive" here,
  "Records Archive" there. Anything regenerating from this file put the old
  label back.
* **"Records Archive" pointed at /#corruption, an anchor that does not exist on
  the homepage** - a dead link on 757 pages. It now points at /foia/, which is
  the records archive.
* **"Ottawa County" appeared twice**, once for the guide and once for the
  directory, with no way to tell which was which.

The label change is not only about a dead link. This Foundation's own pages say
plainly that a chapter is opened on structural risk and that nothing here is an
accusation. A permanent nav item reading "Corruption Archive" says the opposite
on every page of the site.

Every href below was checked live before it was written down.
"""

NAV_CSS = """
.mw-unified-shell{position:sticky;top:0;z-index:5000}
"""

# (href, label). Order is the reading order: what the city is doing, then the
# records that show it, then the archives, then the project itself.
NAV_ITEMS = [
    ("/", "Home"),
    ("/city-desk.html", "City Desk"),
    ("/meetings/", "Meetings"),
    ("/videos.html", "Videos"),
    ("/foia/", "Records Archive"),
    ("/follow-the-money.html", "Follow the Money"),
    ("/crime-watch.html", "Crime Watch"),
    ("/court-search/", "Court Search"),
    ("/local-news.html", "News"),
    ("/ottawa-county-guide.html", "Ottawa County"),
    ("/ottawa-county.html", "County Directory"),
    ("/#utilities", "Utilities"),
    ("/#map", "Area Map"),
    ("/blog/", "Blog"),
    ("/search.html", "Search"),
    ("/tips.html", "Send a tip"),
    ("/automation-status.html", "What is stale"),
    ("/#about", "About"),
]

DRAWER_LINKS = "\n".join(f'    <a href="{href}">{label}</a>' for href, label in NAV_ITEMS)
DESKTOP_LINKS = "\n".join(f'      <a href="{href}">{label}</a>' for href, label in NAV_ITEMS)

HEADER_HTML = f"""<div class="mw-unified-shell">
  <header class="hdr mw-unified-header">
    <div class="hdr-inner">
      <a class="logo" href="/" aria-label="ExposeMiamiOK home">
        <img src="/images/logo-header.png" alt="">
        <div>
          <h1>ExposeMiamiOK</h1>
          <p>Community Resources &amp; Transparency</p>
        </div>
      </a>
      <button class="ham" id="mw-ham" type="button" aria-label="Open navigation"><span></span><span></span><span></span></button>
    </div>
  </header>
  <div class="drawer-overlay" id="mw-drawer-overlay"></div>
  <nav class="drawer" id="mw-drawer" aria-label="Mobile navigation">
{DRAWER_LINKS}
  </nav>
  <nav class="dnav mw-unified-nav" aria-label="Primary navigation"><div class="dnav-inner">
{DESKTOP_LINKS}
  </div></nav>
</div>"""
