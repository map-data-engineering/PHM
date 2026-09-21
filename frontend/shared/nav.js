// Injects the site header into <div id="site-nav"></div>. Plain DOM writes,
// no templating engine — consistent with the rest of this frontend.
(function () {
  function render() {
    const mount = document.getElementById("site-nav");
    if (!mount) return;
    const user = Auth.getUser();
    const authed = Auth.isAuthenticated();
    const page = window.location.pathname.split("/").pop() || "index.html";
    const active = (href) => (href === page ? " active" : "");

    mount.innerHTML = `
      <nav class="navbar navbar-expand-lg navbar-dark bg-brand-navy site-navbar">
        <div class="container-fluid px-3 px-lg-4">
          <a class="navbar-brand fw-bold" href="index.html">PharmaScope</a>
          <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navMain">
            <span class="navbar-toggler-icon"></span>
          </button>
          <div class="collapse navbar-collapse" id="navMain">
            <ul class="navbar-nav me-auto">
              <li class="nav-item"><a class="nav-link${active("index.html")}" href="index.html">Home</a></li>
              <li class="nav-item"><a class="nav-link${active("registry.html")}" href="registry.html">Registry</a></li>
              <li class="nav-item"><a class="nav-link${active("find-pharmacy.html")}" href="find-pharmacy.html">Find Pharmacy</a></li>
              ${authed ? `<li class="nav-item"><a class="nav-link${active("site-check.html")}" href="site-check.html">Site Check</a></li>` : ""}
              ${authed ? `<li class="nav-item"><a class="nav-link${active("data-quality.html")}" href="data-quality.html">Data Quality</a></li>` : ""}
            </ul>
            <div class="d-flex align-items-center gap-2 small text-white-50">
              ${authed
                ? `<span class="text-info-emphasis">${escapeHtml(user?.username || "")}</span><a class="link-light ms-2" href="#" id="nav-signout">Sign out</a>`
                : '<a class="btn btn-sm btn-primary" href="login.html">Sign in</a>'}
            </div>
          </div>
        </div>
      </nav>`;

    const signout = document.getElementById("nav-signout");
    if (signout) {
      signout.addEventListener("click", async (e) => {
        e.preventDefault();
        await Auth.logout();
        window.location.href = "index.html";
      });
    }
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  document.addEventListener("DOMContentLoaded", render);
})();
