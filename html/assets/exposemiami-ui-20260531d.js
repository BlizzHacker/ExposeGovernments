(function () {
  const navItems = [
    ["/", "Home"],
    ["/#resources", "City Resources"],
    ["/court-search/", "Court Search"],
    ["/#utilities", "Utilities"],
    ["/#media", "Media & Feed"],
    ["/#corruption", "Corruption Archive"],
    ["/#map", "Area Map"],
    ["/meetings/", "Transcripts"],
    ["/blog/", "Blog"],
    ["/ottawa-county.html", "Ottawa County"],
    ["/youtube.html", "YouTube"],
    ["/videos.html", "Videos"],
    ["https://www.facebook.com/profile.php?id=61590391534875", "Facebook"],
    ["/#about", "About"],
  ];

  function isActive(href) {
    const path = window.location.pathname;
    if (href === "/") return path === "/";
    return path === href || path.startsWith(href.replace(/\/index\.html$/, "/").replace(/\.html$/, ""));
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
    if (document.querySelector(".mw-unified-shell")) {
      const existing = document.querySelector(".mw-unified-shell");
      const drawer = existing.querySelector("#mw-drawer");
      const desktop = existing.querySelector(".dnav-inner");
      if (drawer && !drawer.children.length) fillNav(drawer, desktop);
      existing.querySelectorAll("#mw-drawer a").forEach((link) => link.addEventListener("click", closeDrawer));
      existing.querySelectorAll(".dnav-inner a").forEach((link) => {
        if (isActive(link.getAttribute("href") || "")) link.setAttribute("aria-current", "page");
      });
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

    fillNav(shell.querySelector("#mw-drawer"), shell.querySelector(".dnav-inner"));

    document.body.prepend(shell);
    shell.querySelector("#mw-ham").addEventListener("click", toggleDrawer);
    shell.querySelector("#mw-drawer-overlay").addEventListener("click", closeDrawer);
  }

  function fillNav(drawer, desktop) {
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
  }

  function hideOldNavigation() {
    document
      .querySelectorAll("body > header, body > nav.dnav, body > nav.drawer, body > .drawer-overlay, body > .nav")
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
