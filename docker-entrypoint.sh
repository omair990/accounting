#!/bin/sh
# Wraps the official Odoo 17 entrypoint to support container platforms that
# expose the database as DATABASE_URL or as a $PORT env var.
set -e

# If DATABASE_URL is provided, decompose it into the env vars the official
# image's entrypoint already understands.
if [ -n "${DATABASE_URL:-}" ]; then
    eval "$(python3 - "$DATABASE_URL" <<'PY'
import sys, urllib.parse as up
u = up.urlparse(sys.argv[1])
def sh(k, v):
    v = "" if v is None else str(v)
    print(f"export {k}='{v.replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'")
sh("HOST", u.hostname)
sh("PORT", u.port or 5432)
sh("USER", up.unquote(u.username) if u.username else "")
sh("PASSWORD", up.unquote(u.password) if u.password else "")
db = (u.path or "").lstrip("/")
if db:
    sh("DB_NAME", db)
PY
)"
fi

# Some platforms (Heroku, Cloud Run, Render free tier) inject the public HTTP
# port as $PORT. Odoo defaults to 8069; honor $PORT if present.
EXTRA_ARGS=""
if [ -n "${PORT:-}" ] && [ "${PORT}" != "8069" ]; then
    EXTRA_ARGS="--http-port=${PORT}"
fi

# If a database name was extracted from DATABASE_URL, narrow Odoo to it.
if [ -n "${DB_NAME:-}" ]; then
    EXTRA_ARGS="${EXTRA_ARGS} -d ${DB_NAME} --db-filter=^${DB_NAME}$"
fi

# Defer to the base image's entrypoint, which handles config generation and
# waits for Postgres to be reachable.
if [ "$1" = "odoo" ] || [ "$1" = "odoo.py" ] || [ "${1#-}" != "$1" ]; then
    set -- /entrypoint.sh "$@" $EXTRA_ARGS
else
    set -- /entrypoint.sh "$@"
fi

exec "$@"
