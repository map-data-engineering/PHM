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
icia  (do this locally, not on PythonAnywhere).
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
   - `ORS_API_KEY` — a free key from openrouteservice.org; enables real
     road distance/time in Find Pharmacy and Site Check (see note below).
7. Reload the web app from the Web tab.

## Refreshing the data later

If you re-run the importers locally against updated source data, just
copy the new `db.sqlite3` up (rename to `db.sqlite3.seed`, commit, `git
pull` on PythonAnywhere, `cp db.sqlite3.seed db.sqlite3`, reload) rather
than trying to run the importers on PythonAnywhere itself.

**`db.sqlite3.seed` has zero user accounts** (only the empty
Regulator/Data Team groups) — it's built by re-running the importers
locally, not by dumping the live server's data. So every time you
`cp db.sqlite3.seed db.sqlite3`, any login you'd previously created on
the server (superuser or otherwise) is gone, and the next login attempt
fails with "invalid credentials" — that's not a bug, just re-run:
```
python manage.py createsuperuser
```
A superuser bypasses the Regulator/Data Team group checks entirely
(see `common/permissions.py`), so one such account is enough to use
every page, including Site Check.

## Loading health facility data (Site Check's rule 1.3)

Site Check's public-health-facility distance rule reports "unknown" until
a health facility dataset is imported — this is expected, not a bug, and
is called out explicitly in the tool's own output. Once you have a CSV
(name, type/level, ownership, lat, lon columns — names are auto-detected,
or pass `--name-col`/`--type-col`/etc. to point at the right ones), import
it locally (it needs no heavy dependencies, so this works fine on
PythonAnywhere too):
```
python manage.py import_health_facilities path/to/facilities.csv
```
Review the per-tier counts and any "skipped" rows it reports — a generic
type string like "Hospital" (no tier keyword) won't auto-classify and
needs either a clearer source column or a manual fix in Django Admin
(Facilities → Health facilities) afterward.

## Known free-tier limitations

- **Outbound internet is whitelisted.** Free accounts can only reach a
  fixed list of external domains — but `openrouteservice.org` (and
  `api.openrouteservice.org`) is confirmed on that list
  (pythonanywhere.com/whitelist/), so road-routing works fine on the
  free tier once `ORS_API_KEY` is set. If it's still falling back to
  straight-line after setting the key and reloading, check the Web
  tab's error log for the `ORS routing unavailable` warning — that
  line names the actual failure (bad key, timeout, etc.), rather than
  guessing.
- **512MB disk quota total** — see above; this is why the dependency list
  is split and why the database is shipped pre-built rather than imported
  in place.
- **No git-push auto-deploy.** Redeploying means `git pull` in a
  PythonAnywhere Bash console, then hitting "Reload" on the Web tab (or
  scripting that via their API).

## Redeploying after a code change

Every new Bash console starts with **no virtualenv active** — PythonAnywhere
doesn't persist that across sessions the way it does inside the running web
app. If a `manage.py` command fails with `ModuleNotFoundError` for something
in `requirements.txt` (e.g. `decouple`), or the traceback shows Python
importing from `/usr/local/lib/python3.13/...` instead of
`~/.virtualenvs/pharmascope-env/...`, that's the tell — activate it first:
```
workon pharmascope-env
```
Your prompt should then show `(pharmascope-env)` at the start. With that
active:
```
cd ~/pharmascope
git pull
cd backend
pip install -r requirements.txt   # if requirements.txt changed
python manage.py migrate          # if there are new migrations
```
Then hit **Reload** on the Web tab.
