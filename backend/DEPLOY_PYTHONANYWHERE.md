# Deploying the backend to PythonAnywhere (free tier)

## One-time setup

1. Create a PythonAnywhere account, open a **Bash console** there, and clone the repo:
   ```
   git clone <your-repo-url> pharmascope
   cd pharmascope/backend
   ```
2. Create a virtualenv and install dependencies:
   ```
   mkvirtualenv --python=python3.12 pharmascope-env
   pip install -r requirements.txt
   ```
3. In the **Web** tab, create a new web app: manual configuration, Python 3.12, and point it at this virtualenv.
4. Set the WSGI file (PythonAnywhere gives you a path like
   `/var/www/<username>_pythonanywhere_com_wsgi.py`) to import this project's WSGI app:
   ```python
   import os, sys
   path = "/home/<username>/pharmascope/backend"
   if path not in sys.path:
       sys.path.append(path)
   os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.pythonanywhere"
   from django.core.wsgi import get_wsgi_application
   application = get_wsgi_application()
   ```
5. In the Web tab's **Environment variables** section (or a `.env` loaded some other way), set:
   - `DJANGO_SECRET_KEY` — a real random secret, not the dev default.
   - `DJANGO_ALLOWED_HOSTS` — `<username>.pythonanywhere.com`
   - `DJANGO_CSRF_TRUSTED_ORIGINS` — `https://<username>.pythonanywhere.com`
   - `CORS_ALLOWED_ORIGINS` — your Vercel URL(s), e.g. `https://pharmascope.vercel.app`
   - `ORS_API_KEY` — only useful if you're on a paid plan (see note below).
6. Run migrations and import the data:
   ```
   python manage.py migrate
   python manage.py import_boundaries
   python manage.py import_outlets
   python manage.py createsuperuser
   python manage.py collectstatic --noinput
   ```
7. Reload the web app from the Web tab.

## Known free-tier limitations

- **Outbound internet is whitelisted.** Free accounts can only reach a
  fixed list of external domains. `openrouteservice.org` is very unlikely
  to be on it, so the road-routing calls in `siting/services/ors_client.py`
  will fail and the app will silently fall back to straight-line distance
  (this fallback is already built in — Find Pharmacy/Site Check keep
  working, just without real road distance/time). Upgrading to a paid
  plan lifts this restriction.
- **No PostgreSQL.** This settings module uses SQLite instead, which is
  fine for this app's scale (~5k rows, infrequent writes) but doesn't
  scale to high write concurrency.
- **No git-push auto-deploy.** Redeploying means `git pull` in a
  PythonAnywhere Bash console, then hitting "Reload" on the Web tab (or
  scripting that via their API).

## Redeploying after a code change

```
cd ~/pharmascope
git pull
cd backend
pip install -r requirements.txt   # if requirements changed
python manage.py migrate          # if there are new migrations
```
Then hit **Reload** on the Web tab.
