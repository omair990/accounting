#!/usr/bin/env bash
# Render.com start phase.
#
# - Parses DATABASE_URL into the env vars Odoo expects.
# - On first boot (empty DB), bootstraps the schema with base + custom
#   modules, then exits the init pass. The next exec() starts HTTP.
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

# Odoo's full addons tree lives under both odoo-src/odoo/addons (core
# internals) and odoo-src/addons (user-facing apps). Then OCA, then this
# repo root for the custom modules.
ADDONS_PATH="odoo-src/odoo/addons,odoo-src/addons,oca/web,oca/account-financial-tools,oca/account-financial-reporting,oca/server-ux,oca/reporting-engine,."
HTTP_PORT="${PORT:-8069}"
ODOO_BIN="odoo-src/odoo-bin"

# --workers: Render Starter has 1 vCPU + 512MB RAM. Multi-process
#   doesn't help much there; keep 0 until you bump to standard ($25/mo,
#   2GB), then switch to 2. Override at deploy time with WORKERS env var.
# --limit-time-real / cpu: prevent runaway requests from holding the
#   single thread.
# --proxy-mode: trust X-Forwarded-* headers from Render's edge.
ODOO_WORKERS="${WORKERS:-0}"
ODOO_ARGS=(
    --addons-path="${ADDONS_PATH}"
    --db_host="${DB_HOST}"
    --db_port="${DB_PORT}"
    --db_user="${DB_USER}"
    --db_password="${DB_PASSWORD}"
    -d "${DB_NAME}"
    --db-filter="^${DB_NAME}\$"
    --workers="${ODOO_WORKERS}"
    --limit-time-cpu=600
    --limit-time-real=900
    --limit-memory-soft=1073741824
    --limit-memory-hard=1342177280
    --proxy-mode
    --without-demo=all
    --log-level=info
)

# ---- detect DB state -----------------------------------------------------------
# Three outcomes:
#   yes   — all four custom modules already installed; skip init
#   no    — schema or modules missing; run -i to install whatever's pending
# We check by module state, not just schema presence, so a previously failed
# init (e.g. a bad view that rolled back one module) is recovered automatically.
EXPECTED_MODULES="custom_accounting omran_dashboard omran_branding erp_lock"
INITIALIZED=$(EXPECTED_MODULES="$EXPECTED_MODULES" python - <<'PY'
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
    if not cur.fetchone()[0]:
        print("no"); sys.exit(0)
    expected = os.environ["EXPECTED_MODULES"].split()
    cur.execute(
        "SELECT COUNT(*) FROM ir_module_module "
        "WHERE name = ANY(%s) AND state = 'installed'",
        (expected,),
    )
    print("yes" if cur.fetchone()[0] == len(expected) else "no")
    c.close()
except Exception as e:
    print(f"probe-failed: {e}", file=sys.stderr)
    print("unknown")
PY
)

if [ "$INITIALIZED" = "no" ]; then
    echo "==> first boot: initialising database with base + custom modules"
    python "$ODOO_BIN" "${ODOO_ARGS[@]}" \
        -i base,web,custom_accounting,omran_dashboard,omran_branding,erp_lock \
        --stop-after-init
    echo "==> init complete"
elif [ "$INITIALIZED" = "yes" ]; then
    echo "==> database already initialised, skipping init"
else
    echo "==> probe failed, attempting init anyway (idempotent)"
    python "$ODOO_BIN" "${ODOO_ARGS[@]}" \
        -i base,web,custom_accounting,omran_dashboard,omran_branding,erp_lock \
        --stop-after-init || true
fi

# Refresh custom-module data files on every boot so views, menus, and reports
# match the deployed code. -u on an installed module is fast (~5–10s each)
# and safe; on a not-yet-installed module it logs and skips.
echo "==> update custom modules data files"
python "$ODOO_BIN" "${ODOO_ARGS[@]}" \
    -u custom_accounting,omran_dashboard,omran_branding,erp_lock \
    --stop-after-init || true

# Always (idempotent): make every user land on the OCIT Home dashboard.
# The omran_dashboard data file does this with noupdate=1 so it only fires
# on first install. Re-applying here on every boot keeps the production
# UX consistent regardless of init outcomes or admin-user creation order.
echo "==> normalize: set OCIT Home as default action for all users"
python "$ODOO_BIN" "${ODOO_ARGS[@]}" --no-http shell <<'PY' 2>&1 | tail -10 || true
action = env.ref('omran_dashboard.action_omran_dashboard', raise_if_not_found=False)
if action:
    users = env['res.users'].search([])
    users.write({'action_id': action.id})
    env.cr.commit()
    print(f"home action set for {len(users)} users")
else:
    print("WARNING: omran_dashboard.action_omran_dashboard not found")
PY

# Strip non-ERP modules ONCE per database, then never again. Gated by an
# ir.config_parameter sentinel so once a sysadmin has the install set they
# want, manual installs from the Apps UI aren't wiped on the next deploy.
# To re-run: delete the parameter `omran.modules_stripped` from Settings →
# Technical → Parameters → System Parameters.
echo "==> strip non-ERP modules (one-shot, sentinel-gated)"
python "$ODOO_BIN" "${ODOO_ARGS[@]}" --no-http shell <<'PY' 2>&1 | tail -40 || true
SENTINEL = 'omran.modules_stripped'
ICP = env['ir.config_parameter'].sudo()
if ICP.get_param(SENTINEL):
    print(f"sentinel '{SENTINEL}' set; skipping strip")
else:
    to_remove = [
        'website', 'website_sale', 'website_sale_product_configurator',
        'website_crm', 'website_crm_sms', 'website_sms',
        'website_mass_mailing', 'website_mass_mailing_sms',
        'website_mail', 'website_payment',
        'website_hr_recruitment', 'website_form_project', 'website_links',
        'website_event', 'website_event_crm', 'website_event_sale',
        'website_partner', 'website_blog', 'website_forum', 'website_slides',
        'test_website', 'test_website_modules', 'test_website_slides_full',
        'point_of_sale', 'pos_restaurant', 'pos_hr',
        'pos_loyalty', 'pos_mercury', 'pos_six', 'pos_adyen',
        'fleet', 'lunch', 'maintenance', 'survey',
        'event', 'event_sale',
        'mass_mailing', 'mass_mailing_sms', 'mass_mailing_crm',
        'mass_mailing_event', 'mass_mailing_event_track',
        'sms', 'membership', 'repair', 'project_todo', 'social_media',
    ]
    todo = env['ir.module.module'].search([
        ('name', 'in', to_remove), ('state', '=', 'installed'),
    ])
    if not todo:
        print("nothing to strip")
    else:
        names = todo.mapped('name')
        print(f"will uninstall: {names}")
        for name in names:
            try:
                m = env['ir.module.module'].with_context(
                    omran_force_uninstall=True,
                ).search([
                    ('name', '=', name), ('state', '=', 'installed'),
                ], limit=1)
                if not m:
                    print(f"  [GONE] {name}")
                    continue
                m.button_immediate_uninstall()
                env.cr.commit()
                print(f"  [OK] {name}")
            except Exception as e:
                env.cr.rollback()
                print(f"  [SKIP] {name}: {e!s:.150}")
        # Sweep stale ir.asset rows whose FILE path lives under a stripped
        # module's static dir. We must NOT match on bundle-include directives
        # like `('include', 'web._assets_helpers')` — those store path =
        # 'web._assets_helpers' (no slash, no `/static/`), and deleting them
        # breaks every SCSS bundle that depends on the helper variables.
        # Filter on `/static/` to ensure we only touch real file references.
        to_remove_set = set(to_remove)
        stale = [
            a.id for a in env['ir.asset'].search([])
            if '/static/' in (a.path or '')
            and (a.path or '').lstrip('/').split('/', 1)[0] in to_remove_set
        ]
        if stale:
            env['ir.asset'].browse(stale).unlink()
            env.cr.commit()
            print(f"  swept {len(stale)} stale ir.asset rows")
    ICP.set_param(SENTINEL, '1')
    env.cr.commit()
    print(f"sentinel '{SENTINEL}' set; future deploys will skip strip")
PY

# One-shot recovery: a previous version of the strip-sweep wiped ir.asset
# bundle-include rows (path='web._assets_helpers' and similar), so the
# web.assets_frontend / assets_backend bundles fail to compile and return
# 500. Recreate them by re-updating every installed module — `-u` reloads
# manifests, which re-creates ir.asset records owned by each module.
# Sentinel-gated so this heavy operation runs at most once per database.
RECOVERY_SENTINEL=$(python - <<'PY'
import os, sys
try:
    import psycopg2
    c = psycopg2.connect(
        host=os.environ["DB_HOST"], port=int(os.environ["DB_PORT"]),
        user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
        dbname=os.environ["DB_NAME"], connect_timeout=10,
    )
    cur = c.cursor()
    cur.execute(
        "SELECT to_regclass('public.ir_config_parameter') IS NOT NULL")
    if not cur.fetchone()[0]:
        print("missing"); sys.exit(0)
    cur.execute(
        "SELECT value FROM ir_config_parameter "
        "WHERE key = 'omran.assets_recovered_v1' LIMIT 1")
    row = cur.fetchone()
    print("set" if row and row[0] else "missing")
    c.close()
except Exception as e:
    print(f"probe-failed: {e}", file=sys.stderr)
    print("missing")
PY
)

if [ "$RECOVERY_SENTINEL" = "missing" ]; then
    echo "==> one-shot asset recovery: -u all to rebuild ir.asset rows"
    python "$ODOO_BIN" "${ODOO_ARGS[@]}" -u all --stop-after-init || true
    python "$ODOO_BIN" "${ODOO_ARGS[@]}" --no-http shell <<'PY' 2>&1 | tail -5 || true
env['ir.config_parameter'].sudo().set_param('omran.assets_recovered_v1', '1')
env.cr.commit()
print("asset recovery sentinel set")
PY
else
    echo "==> asset recovery already done, skipping"
fi

echo "==> starting Odoo HTTP on port ${HTTP_PORT}"
exec python "$ODOO_BIN" "${ODOO_ARGS[@]}" --http-port="${HTTP_PORT}"
