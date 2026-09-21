import dj_database_url
from decouple import Csv, config

from .base import *  # noqa: F401,F403

DEBUG = False

CSRF_TRUSTED_ORIGINS = config("DJANGO_CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

DATABASES = {
    "default": dj_database_url.config(default=config("DATABASE_URL")),
}

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
