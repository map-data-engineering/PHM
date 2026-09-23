// PharmaScope frontend — API client shared by every page.
//
// For local development against `manage.py runserver`, temporarily swap
// this to "http://127.0.0.1:8000" — don't commit that swap.
const API_BASE_URL = "https://DET.pythonanywhere.com";

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

  // A stale token (e.g. the backend's database was reseeded, invalidating
  // every previously-issued token) must never lock a *public* endpoint —
  // DRF rejects an unrecognized Authorization header before it even checks
  // that the view is AllowAny. If a token is attached and the server comes
  // back 401/403, retry once with no Authorization header; if that
  // succeeds, the token was the problem, so drop it locally too (clears the
  // "signed in" state the nav bar would otherwise keep showing).
  async get(path, params) {
    const url = new URL(API_BASE_URL + path);
    if (params) for (const [k, v] of Object.entries(params)) if (v) url.searchParams.set(k, v);
    let res = await fetch(url, { headers: this._headers() });
    if (!res.ok && this._shouldRetryWithoutToken(res)) {
      const retry = await fetch(url);
      if (retry.ok) { this._dropStaleToken(); res = retry; }
    }
    if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
    return res.json();
  },

  async post(path, body) {
    const doPost = (headers) => fetch(API_BASE_URL + path, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...headers },
      body: JSON.stringify(body),
    });
    let res = await doPost(this._headers());
    if (!res.ok && this._shouldRetryWithoutToken(res)) {
      const retry = await doPost({});
      if (retry.ok) { this._dropStaleToken(); res = retry; }
    }
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

  _shouldRetryWithoutToken(res) {
    return (res.status === 401 || res.status === 403) && !!Auth.getToken();
  },

  _dropStaleToken() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },
};
