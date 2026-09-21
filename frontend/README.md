# PharmaScope frontend (static, deploys to Vercel)

Plain HTML/CSS/JS — no build step, no framework, matching the rest of this
project's stated approach. Calls the Django backend (hosted separately, e.g.
on PythonAnywhere) over its REST API.

## Before deploying

Edit `shared/api.js` and change:
```js
const API_BASE_URL = "http://127.0.0.1:8000";
```
to your deployed backend's URL, e.g. `https://<username>.pythonanywhere.com`.

On the backend side, make sure `CORS_ALLOWED_ORIGINS` (an env var, see
`backend/DEPLOY_PYTHONANYWHERE.md`) includes the Vercel URL you deploy to.

## Deploying to Vercel

This is a zero-config static site — from the `frontend/` directory:
```
npx vercel --prod
```
or connect the repo in the Vercel dashboard and set **Root Directory** to
`frontend/` with no build command (static output = the directory itself).

## Local development

```
python -m http.server 5500
```
then open `http://127.0.0.1:5500/`. Leave `API_BASE_URL` pointed at your
local `python manage.py runserver` (default `http://127.0.0.1:8000`) —
the Django dev settings already allow all CORS origins for convenience.

## Auth model

Session cookies don't travel reliably cross-origin (Vercel domain vs.
backend domain), so this frontend uses token auth instead:
`login.html` → `POST /api/v1/auth/login/` → token stored in
`localStorage` → sent as `Authorization: Token <token>` on every
subsequent request (see `shared/api.js`). Public pages (Registry, Find
Pharmacy) need no token at all. `site-check.html` and `data-quality.html`
redirect to `login.html` if there's no token in storage.
