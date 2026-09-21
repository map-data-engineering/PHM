"""Settings for the free-tier PythonAnywhere deployment.

Differs from production.py (which targets Render + Postgres) in two ways
the free tier forces on us:
  - SQLite instead of Postgres (PythonAnywhere's free tier has no managed
    Postgres; SQLite is a fine fit here at ~5k read-heavy rows).
  - No SECURE_SSL_REDIRECT — PythonAnywhere terminates TLS at its own
    reverse proxy and free-tier accounts don't reliably forward
    X-Forwarded-Proto, so forcing a redirect here risks a redirect loop.
    HTTPS on *.pythonanywhere.com is already provided by the platform.

The frontend (Vercel, a separate static site) talks to this API
cross-origin via CORS + token auth — see accounts/api_urls.py and
CORS_ALLOWED_ORIGINS below.
"""
from decouple import Csv, config

from .base import *  # noqa: F401,F403

DEBUG = False

CSRF_TRUSTED_ORIGINS = config("DJANGO_CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
    }
}

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
