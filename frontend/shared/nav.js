// Injects the site header into <div id="site-nav"></div>. Plain DOM writes,
// no templating engine — consistent with the rest of this frontend.
(function () {
  function render() {
    const mount = document.getElementById("site-nav");
    if (!mount) return;
    const user = Auth.getUser();
    const authed = Auth.isAuthenticated();

    mount.innerHTML = `
      <header class="site-nav">
        <div class="brand"><a href="index.html">PharmaScope</a></div>
        <nav>
          <a href="registry.html">Registry</a>
          <a href="find-pharmacy.html">Find Pharmacy</a>
          ${authed ? '<a href="site-check.html">Site Check</a>' : ""}
          ${authed ? '<a href="data-quality.html">Data Quality</a>' : ""}
        </nav>
        <div class="user">
          ${authed
            ? `${escapeHtml(user?.username || "")} &middot; <a href="#" id="nav-signout">Sign out</a>`
            : '<a href="login.html">Sign in</a>'}
        </div>
      </header>`;

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
