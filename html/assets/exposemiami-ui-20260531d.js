(function () {
  const navItems = [
    ["/", "Home"],
    ["/resources/", "Resources"],
    ["/meetings/", "Transcripts"],
    ["/court-search/", "Court Search"],
    ["/blog/", "Blog"],
    ["/youtube.html", "YouTube"],
    ["/videos.html", "Videos"],
    ["/ottawa-county.html", "Ottawa County"],
  ];

  function isActive(href) {
    const path = window.location.pathname;
    if (href === "/") return path === "/";
    return path === href || path.startsWith(href.replace(/\.html$/, ""));
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

  function buildHeader() {
    if (document.querySelector(".mw-unified-shell")) return;

    const shell = document.createElement("div");
    shell.className = "mw-unified-shell";
    shell.innerHTML = `
      <header class="hdr mw-unified-header">
        <div class="hdr-inner">
          <a class="logo" href="/" aria-label="ExposeMiamiOK home">
            <img src="/images/logo-120.png" alt="">
            <div>
              <h1>ExposeMiamiOK</h1>
              <p>Community Resources & Transparency</p>
            </div>
          </a>
          <button class="ham" id="mw-ham" type="button" aria-label="Open navigation"><span></span><span></span><span></span></button>
        </div>
      </header>
      <div class="drawer-overlay" id="mw-drawer-overlay"></div>
      <nav class="drawer" id="mw-drawer" aria-label="Mobile navigation"></nav>
      <nav class="dnav mw-unified-nav" aria-label="Primary navigation"><div class="dnav-inner"></div></nav>
    `;

    const drawer = shell.querySelector("#mw-drawer");
    const desktop = shell.querySelector(".dnav-inner");

    for (const [href, label] of navItems) {
      const mobile = document.createElement("a");
      mobile.href = href;
      mobile.textContent = label;
      mobile.addEventListener("click", closeDrawer);
      drawer.appendChild(mobile);

      const link = document.createElement("a");
      link.href = href;
      link.textContent = label;
      if (isActive(href)) link.setAttribute("aria-current", "page");
      desktop.appendChild(link);
    }

    document.body.prepend(shell);
    shell.querySelector("#mw-ham").addEventListener("click", toggleDrawer);
    shell.querySelector("#mw-drawer-overlay").addEventListener("click", closeDrawer);
  }

  function hideOldNavigation() {
    document
      .querySelectorAll("body > header, body > nav.dnav, body > nav.drawer, body > .drawer-overlay")
      .forEach((node) => {
        if (!node.closest(".mw-unified-shell")) node.classList.add("mw-retired-ui");
      });
  }

  document.addEventListener("DOMContentLoaded", function () {
    hideOldNavigation();
    buildHeader();
  });
})();
