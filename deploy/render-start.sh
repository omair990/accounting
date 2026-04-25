#!/usr/bin/env bash
# Render.com start phase — runs every container boot.
#
# Reads DATABASE_URL (Render injects this from the linked Postgres service),
# decomposes it into the flags Odoo expects, and execs Odoo on $PORT.
set -euo pipefail

if [ -z "${DATABASE_URL:-}" ]; then
    echo "FATAL: DATABASE_URL is not set" >&2
    exit 1
fi

# Parse DATABASE_URL into individual fields. Using python so we get correct
# percent-decoding of the password.
eval "$(python - <<'PY'
import os, urllib.parse as up
u = up.urlparse(os.environ['DATABASE_URL'])
def emit(key, val):
    val = "" if val is None else str(val)
    val = val.replace("'", "'\\''")
    print(f"export {key}='{val}'")
emit("DB_HOST", u.hostname)
emit("DB_PORT", u.port or 5432)
emit("DB_USER", up.unquote(u.username) if u.username else "")
emit("DB_PASSWORD", up.unquote(u.password) if u.password else "")
emit("DB_NAME", (u.path or "").lstrip("/"))
PY
)"

# Addons: OCA repos cloned in build phase + this repo's custom modules at root.
ADDONS_PATH="oca/web,oca/account-financial-tools,oca/account-financial-reporting,oca/server-ux,oca/reporting-engine,."

# Render injects $PORT for the public HTTP listener. Odoo's default is 8069.
HTTP_PORT="${PORT:-8069}"

echo "==> starting Odoo on port ${HTTP_PORT}, db=${DB_NAME}"

exec python -m odoo \
    --http-port="${HTTP_PORT}" \
    --addons-path="${ADDONS_PATH}" \
    --db_host="${DB_HOST}" \
    --db_port="${DB_PORT}" \
    --db_user="${DB_USER}" \
    --db_password="${DB_PASSWORD}" \
    -d "${DB_NAME}" \
    --db-filter="^${DB_NAME}\$" \
    --workers=0 \
    --proxy-mode \
    --without-demo=all \
    --logfile=/dev/stdout
