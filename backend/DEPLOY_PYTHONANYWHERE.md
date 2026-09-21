# Deploying the backend to PythonAnywhere (free tier)

## Why this looks different from a normal Django deploy

PythonAnywhere's free tier gives you a 512MB disk quota. This project's
full dependency list includes numpy/pandas/shapely/rapidfuzz/topojson —
needed only by the one-time data-import management commands, not by the
live web app — and installing all of that blows the quota by itself
(numpy + pandas alone install to 150MB+).

So the split is:
- **`requirements.txt`** — the lean runtime set (Django, DRF, django-filter,
  django-cors-headers, python-decouple, whitenoise + their small transitive
  deps). This is all PythonAnywhere ever installs.
- **`requirements-etl.txt`** — numpy/pandas/shapely/rapidfuzz/topojson/xlrd.
  Only needed wherever you actually run `import_boundaries`/`import_outlets`
  (do this locally, not on PythonAnywhere).
- **`requirements-postgres.txt`** — dj-database-url/gunicorn/psycopg, only
  relevant to the Render/Postgres path (`config/settings/production.py`),
  not used here at all.
- **`db.sqlite3.seed`** — a pre-populated database (outlets, boundaries,
  the Regulator/Data Team groups) produced by running the importers
  locally once. PythonAnywhere copies this in instead of ever running the
  heavy importers itself.

## One-time setup

1. Clone the repo and check out this branch:
   ```
   git clone <your-repo-url> pharmascope
   cd pharmascope
   git checkout django-migration
   cd backend
   ```
2. Create a virtualenv and install **only the lean runtime deps**:
   ```
   mkvirtualenv --python=python3.12 pharmascope-env
   pip install -r requirements.txt
   ```
   If you already tried `pip install -r requirements.txt` before this file
   was split and hit a disk-quota error, recreate the virtualenv clean
   first so no partially-installed heavy packages are left taking up quota:
   ```
   deactivate
   rmvirtualenv pharmascope-env
   mkvirtualenv --python=python3.12 pharmascope-env
   pip install -r requirements.txt
   ```
3. Copy the seed database into place and apply any migrations newer than
   the seed:
   ```
   cp db.sqlite3.seed db.sqlite3
   python manage.py migrate
   python manage.py createsuperuser
   python manage.py collectstatic --noinput
   ```
4. In the **Web** tab, create a new web app: manual configuration,
   Python 3.12, pointed at the `pharmascope-env` virtualenv.
5. Set the WSGI file (PythonAnywhere gives you a path like
   `/var/www/<username>_pythonanywhere_com_wsgi.py`) to import this
   project's WSGI app:
   ```python
   import os, sys
   path = "/home/<username>/pharmascope/backend"
   if path not in sys.path:
       sys.path.append(path)
   os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.pythonanywhere"
   from django.core.wsgi import get_wsgi_application
   application = get_wsgi_application()
   ```
6. In the Web tab's **Environment variables** section, set:
   - `DJANGO_SECRET_KEY` — a real random secret, not the dev default.
   - `DJANGO_ALLOWED_HOSTS` — `<username>.pythonanywhere.com`
   - `DJANGO_CSRF_TRUSTED_ORIGINS` — `https://<username>.pythonanywhere.com`
   - `CORS_ALLOWED_ORIGINS` — your Vercel URL(s), e.g. `https://pharmascope.vercel.app`
   - `ORS_API_KEY` — only useful if you're on a paid plan (see note below).
7. Reload the web app from the Web tab.

## Refreshing the data later

If you re-run the importers locally against updated source data, just
copy the new `db.sqlite3` up (rename to `db.sqlite3.seed`, commit, `git
pull` on PythonAnywhere, `cp db.sqlite3.seed db.sqlite3`, reload) rather
than trying to run the importers on PythonAnywhere itself.

## Known free-tier limitations

- **Outbound internet is whitelisted.** Free accounts can only reach a
  fixed list of external domains. `openrouteservice.org` is very unlikely
  to be on it, so the road-routing calls in `siting/services/ors_client.py`
  will fail and the app will silently fall back to straight-line distance
  (this fallback is already built in — Find Pharmacy/Site Check keep
  working, just without real road distance/time). Upgrading to a paid
  plan lifts this restriction.
- **512MB disk quota total** — see above; this is why the dependency list
  is split and why the database is shipped pre-built rather than imported
  in place.
- **No git-push auto-deploy.** Redeploying means `git pull` in a
  PythonAnywhere Bash console, then hitting "Reload" on the Web tab (or
  scripting that via their API).

## Redeploying after a code change

```
cd ~/pharmascope
git pull
cd backend
pip install -r requirements.txt   # if requirements.txt changed
python manage.py migrate          # if there are new migrations
```
Then hit **Reload** on the Web tab.
