// PharmaScope frontend — API client shared by every page.
//
// EDIT THIS before deploying: point it at your PythonAnywhere backend.
// Left as localhost for local development against `manage.py runserver`.
const API_BASE_URL = "http://127.0.0.1:8000";

const TOKEN_KEY = "ps_token";
const USER_KEY = "ps_user"; // { username, roles: [...] }

const Auth = {
  getToken() { return localStorage.getItem(TOKEN_KEY); },
  getUser() {
    try { return JSON.parse(localStorage.getItem(USER_KEY) || "null"); }
    catch { return null; }
  },
  isAuthenticated() { return !!this.getToken(); },
  hasRole(role) { return (this.getUser()?.roles || []).includes(role); },
  isRegulatorOrAbove() { return this.hasRole("regulator") || this.hasRole("data-team") || this.hasRole("admin"); },
  isDataTeam() { return this.hasRole("data-team") || this.hasRole("admin"); },

  async login(username, password) {
    const res = await fetch(`${API_BASE_URL}/api/v1/auth/login/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Login failed (HTTP ${res.status})`);
    }
    const data = await res.json();
    localStorage.setItem(TOKEN_KEY, data.token);
    localStorage.setItem(USER_KEY, JSON.stringify({ username: data.username, roles: data.roles }));
    return data;
  },

  async logout() {
    const token = this.getToken();
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    if (token) {
      try {
        await fetch(`${API_BASE_URL}/api/v1/auth/logout/`, {
          method: "POST",
          headers: { Authorization: `Token ${token}` },
        });
      } catch { /* token already cleared locally; ignore network errors */ }
    }
  },

  // Redirects to login.html if not signed in (or not in `role`, when given).
  // Call at the top of any protected page.
  requireAuth(role) {
    if (!this.isAuthenticated() || (role && !this.hasRole(role) && !this.isDataTeam())) {
      const next = encodeURIComponent(window.location.pathname);
      window.location.replace(`login.html?next=${next}`);
      return false;
    }
    return true;
  },
};

const Api = {
  base: API_BASE_URL,

  async get(path, params) {
    const url = new URL(API_BASE_URL + path);
    if (params) for (const [k, v] of Object.entries(params)) if (v) url.searchParams.set(k, v);
    const res = await fetch(url, { headers: this._headers() });
    if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
    return res.json();
  },

  async post(path, body) {
    const res = await fetch(API_BASE_URL + path, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...this._headers() },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => ({}));
      throw new Error(detail.detail || `${path} failed: ${res.status}`);
    }
    return res.json();
  },

  _headers() {
    const token = Auth.getToken();
    return token ? { Authorization: `Token ${token}` } : {};
  },
};
