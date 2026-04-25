# OCIT Accounting (Odoo 17)

Custom Odoo 17 ERP build for **Omran IT (OCIT)** — branded backend, custom
double-entry accounting module, business dashboard, and an uninstall lock to
prevent users from removing apps.

## Custom modules in this repo

| Module | What it does |
|---|---|
| `custom_accounting/` | Full double-entry accounting: chart of accounts, journals, invoices, payments, taxes, reports (GL, Trial Balance, P&L, Balance Sheet). |
| `omran_dashboard/` | "OCIT Home" landing dashboard with KPIs (revenue, pipeline, ops, HR). Set as default home action. |
| `omran_branding/` | Company colours, login-page customization, fonts, navbar restyle. |
| `erp_lock/` | Blocks UI-side module uninstalls (only superuser/CLI can uninstall). |

## What you also need (not committed)

This repo only contains the custom modules and deployment scripts. To run it,
clone the supporting trees alongside it:

```
git clone --depth 1 -b 17.0 https://github.com/odoo/odoo.git odoo
git clone --depth 1 https://github.com/OCA/web.git oca/web
git clone --depth 1 https://github.com/OCA/account-financial-tools.git oca/account-financial-tools
git clone --depth 1 https://github.com/OCA/account-financial-reporting.git oca/account-financial-reporting
git clone --depth 1 https://github.com/OCA/server-ux.git oca/server-ux
git clone --depth 1 https://github.com/OCA/reporting-engine.git oca/reporting-engine
```

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp odoo.conf.example odoo.conf
# edit odoo.conf — set db_user, db_password, db_name, admin_passwd

createdb my_accounting_db
.venv/bin/python odoo/odoo-bin -c odoo.conf -d my_accounting_db -i base --stop-after-init
.venv/bin/python odoo/odoo-bin -c odoo.conf
```

Open http://localhost:8069 and install `custom_accounting`, `omran_dashboard`,
`omran_branding`, `erp_lock` from Apps.

## Stripping non-ERP modules

`uninstall_non_erp.py` removes website / POS / mass-mailing / fleet / maintenance
modules and cleans up stale `ir.asset` and `ir.model.data` rows left behind by
incomplete uninstalls. Re-runnable.

```bash
.venv/bin/python odoo/odoo-bin shell -c odoo.conf -d my_accounting_db --no-http < uninstall_non_erp.py
```

## License

LGPL-3.0 (per individual module manifests).
