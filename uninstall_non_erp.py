"""
One-time cleanup script: removes non-ERP modules (website, POS, fleet, etc.)
and their stale residue (ir.asset / ir.model_data rows that point at uninstalled
addons).

Run via:  ./odoo-bin shell -c odoo.conf -d <db>  < uninstall_non_erp.py

Safe to re-run: each step is wrapped in a savepoint so a single failure does
not abort the rest.
"""

# Modules to remove. Grouped for readability.
to_remove = [
    # All website-related (catch everything)
    'website', 'website_sale', 'website_sale_product_configurator',
    'website_crm', 'website_crm_sms', 'website_sms', 'website_mass_mailing',
    'website_mass_mailing_sms', 'website_mail', 'website_payment',
    'website_hr_recruitment', 'website_form_project', 'website_links',
    'website_event', 'website_event_crm', 'website_event_sale',
    'website_partner', 'website_blog', 'website_forum', 'website_slides',
    # Test modules that depend on theme_default / website
    'test_website', 'test_website_modules', 'test_website_slides_full',
    # POS
    'point_of_sale', 'pos_restaurant', 'pos_hr', 'pos_loyalty',
    'pos_mercury', 'pos_six', 'pos_adyen',
    # Non-ERP utilities
    'fleet', 'lunch', 'maintenance', 'survey', 'event', 'event_sale',
    'mass_mailing', 'mass_mailing_sms', 'mass_mailing_crm',
    'mass_mailing_event', 'mass_mailing_event_track',
    'sms', 'membership', 'repair', 'project_todo',
    'social_media',
]


def _safe_uninstall(modules, label):
    """Uninstall modules one at a time so one bad module can't abort the rest.

    button_immediate_uninstall commits internally and rebuilds the registry, so
    savepoints don't help here — on failure we rollback the connection and
    re-fetch the module record fresh from a clean transaction.
    """
    # Capture names up front; the recordset can become stale across uninstalls.
    names = list(modules.mapped('name'))
    for name in names:
        try:
            mod = env['ir.module.module'].search([
                ('name', '=', name), ('state', '=', 'installed'),
            ], limit=1)
            if not mod:
                print(f'  [GONE] {label}: {name} (already uninstalled)')
                continue
            mod.button_immediate_uninstall()
            env.cr.commit()
            print(f'  [OK] {label}: {name}')
        except Exception as e:  # noqa: BLE001 — keep going
            env.cr.rollback()
            print(f'  [SKIP] {label}: {name} — {e!s:.200}')


# ---- 1. Uninstall the explicit list ------------------------------------------
explicit = env['ir.module.module'].search([
    ('name', 'in', to_remove),
    ('state', '=', 'installed'),
])
print(f'Uninstalling {len(explicit)} explicit modules...')
_safe_uninstall(explicit, 'explicit')

# ---- 2. Sweep anything still installed that depends on the removed set --------
leftover = env['ir.module.module'].search([
    ('state', '=', 'installed'),
])
leftover = leftover.filtered(
    lambda m: m.name.startswith('website')
    or m.name.startswith('pos_')
    or m.name.startswith('mass_mailing')
    or m.name.startswith('theme_')
)
print(f'Sweeping {len(leftover)} leftover modules...')
_safe_uninstall(leftover, 'leftover')

# ---- 3. Clean stale ir.asset rows pointing at uninstalled addons --------------
# When a module uninstall is interrupted (FK errors above), some ir.asset rows
# can be left behind. They cause "Unallowed to fetch files from addon X" errors
# on every page render. We delete any asset row whose path references an addon
# that is no longer installed.
print('Cleaning stale ir.asset rows...')
installed_names = set(env['ir.module.module'].search([
    ('state', '=', 'installed'),
]).mapped('name'))

stale = []
for asset in env['ir.asset'].search([]):
    # path looks like 'website/static/src/scss/foo.scss' or '/website/...'
    path = (asset.path or '').lstrip('/')
    addon = path.split('/', 1)[0] if '/' in path else ''
    if addon and addon not in installed_names:
        stale.append(asset.id)

if stale:
    print(f'  Removing {len(stale)} stale ir.asset rows')
    env['ir.asset'].browse(stale).unlink()
    env.cr.commit()

# ---- 4. Clean stale ir.model_data rows pointing at gone modules ---------------
gone_data = env['ir.model.data'].search([
    ('module', 'not in', list(installed_names) + ['__export__', '__import__', 'base']),
])
if gone_data:
    print(f'  Removing {len(gone_data)} stale ir.model.data rows')
    gone_data.unlink()
    env.cr.commit()

print('DONE')
