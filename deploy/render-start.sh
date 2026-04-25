#!/usr/bin/env bash
# Render.com start phase.
#
# - Parses DATABASE_URL into the env vars Odoo expects.
# - On first boot (empty DB), initialises the schema with base + custom
#   modules, then exits. The next exec() starts the HTTP server.
# - On subsequent boots, the init step is skipped via a fast probe.
set -euo pipefail

if [ -z "${DATABASE_URL:-}" ]; then
    echo "FATAL: DATABASE_URL is not set" >&2
    exit 1
fi

# ---- decompose DATABASE_URL ---------------------------------------------------
eval "$(python - <<'PY'
import os, urllib.parse as up
u = up.urlparse(os.environ['DATABASE_URL'])
def emit(k, v):
    v = "" if v is None else str(v)
    v = v.replace("'", "'\\''")
    print(f"export {k}='{v}'")
emit("DB_HOST", u.hostname)
emit("DB_PORT", u.port or 5432)
emit("DB_USER", up.unquote(u.username) if u.username else "")
emit("DB_PASSWORD", up.unquote(u.password) if u.password else "")
emit("DB_NAME", (u.path or "").lstrip("/"))
PY
)"

ADDONS_PATH="oca/web,oca/account-financial-tools,oca/account-financial-reporting,oca/server-ux,oca/reporting-engine,."
HTTP_PORT="${PORT:-8069}"

ODOO_ARGS=(
    --addons-path="${ADDONS_PATH}"
    --db_host="${DB_HOST}"
    --db_port="${DB_PORT}"
    --db_user="${DB_USER}"
    --db_password="${DB_PASSWORD}"
    -d "${DB_NAME}"
    --db-filter="^${DB_NAME}\$"
    --workers=0
    --proxy-mode
    --without-demo=all
)

# ---- detect empty DB ----------------------------------------------------------
INITIALIZED=$(python - <<'PY'
import os, sys
try:
    import psycopg2
    c = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        dbname=os.environ["DB_NAME"],
        connect_timeout=10,
    )
    cur = c.cursor()
    cur.execute("SELECT to_regclass('public.ir_module_module') IS NOT NULL")
    print("yes" if cur.fetchone()[0] else "no")
    c.close()
except Exception as e:
    print(f"probe-failed: {e}", file=sys.stderr)
    print("unknown")
PY
)

if [ "$INITIALIZED" = "no" ]; then
    echo "==> first boot: initialising database with base + custom modules"
    python -m odoo "${ODOO_ARGS[@]}" \
        -i base,web,custom_accounting,omran_dashboard,omran_branding,erp_lock \
        --stop-after-init
    echo "==> init complete"
elif [ "$INITIALIZED" = "yes" ]; then
    echo "==> database already initialised, skipping init"
else
    echo "==> probe failed, attempting init anyway (idempotent)"
    python -m odoo "${ODOO_ARGS[@]}" \
        -i base,web,custom_accounting,omran_dashboard,omran_branding,erp_lock \
        --stop-after-init || true
fi

echo "==> starting Odoo HTTP on port ${HTTP_PORT}"
exec python -m odoo "${ODOO_ARGS[@]}" --http-port="${HTTP_PORT}"
