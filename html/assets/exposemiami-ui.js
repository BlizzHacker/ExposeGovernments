(function () {
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
