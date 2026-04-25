# Omran IT ERP — Production Deployment

Production-ready Odoo 17 Community stack: Odoo + PostgreSQL + Nginx (TLS).

## Contents

- `Dockerfile` — builds Odoo 17 + OCA + custom_accounting + custom_modern_theme, with wkhtmltopdf for PDFs.
- `docker-compose.yml` — orchestrates Odoo (app) + Postgres 16 + Nginx.
- `entrypoint.sh` — renders `odoo.conf` from env vars at container start; 4 workers + gevent longpolling by default.
- `nginx/odoo.conf` — reverse proxy with TLS, websocket support, gzip, static caching.
- `scripts/backup.sh` — daily pg_dump + filestore tarball, 14-day retention.
- `scripts/restore.sh` — restore from a backup pair.
- `scripts/tls-letsencrypt.sh` — obtain + install Let's Encrypt cert.
- `.env.example` — secrets template.

## Project layout expected

This `deploy/` directory must live at the root of the Omran project repo so the Dockerfile can `COPY ./custom` (your `custom_accounting` and `erp_lock` modules).

```
Oddo/
├── custom_accounting/
├── erp_lock/
└── deploy/             ← you are here
    ├── Dockerfile
    ├── docker-compose.yml
    └── ...
```

Before building, create `deploy/custom/` and move your custom modules in, OR symlink them:

```
cd deploy
mkdir -p custom
ln -s ../../custom_accounting custom/custom_accounting
ln -s ../../erp_lock          custom/erp_lock
```

## Quick deploy on a VPS (Ubuntu 22.04+)

```bash
# 1. Install Docker
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

# 2. Clone your project
git clone <your-repo> /opt/omran-erp
cd /opt/omran-erp/deploy

# 3. Configure secrets
cp .env.example .env
# EDIT .env — set strong random values for ODOO_DB_PASSWORD and ODOO_ADMIN_PASSWD

# 4. Prep custom modules (see layout above)
mkdir -p custom
cp -r ../custom_accounting ../erp_lock custom/

# 5. Build + start (first time takes ~10 min to clone + install deps)
docker compose up -d --build

# 6. Watch logs
docker compose logs -f odoo

# 7. TLS (once DNS points at the server)
sudo DOMAIN=erp.omran.com EMAIL=admin@omran.com bash scripts/tls-letsencrypt.sh

# 8. Initialize the database on first run (one-time)
docker compose exec odoo python /opt/odoo/src/odoo/odoo-bin \
  -c /var/lib/odoo/odoo.conf -d omran \
  -i base,account,custom_accounting,erp_lock,crm,sale_management,purchase,stock,mrp,hr,hr_attendance,hr_holidays,hr_recruitment,hr_expense,hr_skills,project,hr_timesheet,contacts,calendar,account_financial_report,web_responsive,web_chatter_position,web_refresher,web_no_bubble,web_environment_ribbon,web_theme_classic,custom_modern_theme \
  --without-demo=all --stop-after-init
```

## Capacity guidance

- **4 workers / 4 GB RAM / 2 vCPU** — handles ~50 concurrent active ERP users comfortably.
- **8 workers / 8 GB RAM / 4 vCPU** — ~150 concurrent.
- **Sizing rule** — workers ≈ (vCPU × 2) + 1. Each worker uses 200–500 MB RAM.
- **Past ~200 concurrent**, split PostgreSQL onto its own server (add `DATABASE_URL` pointer; remove the `db:` service).
- **Past ~500 concurrent**, use horizontal scaling: multiple Odoo containers behind the Nginx upstream, shared filestore via S3 (`s3_filestore` OCA module), and managed PostgreSQL.

## Backups

Add to root's crontab on the VPS:
```
0 2 * * * cd /opt/omran-erp/deploy && source .env && bash scripts/backup.sh >> /var/log/odoo-backup.log 2>&1
```
Copy backups off-host (rsync to another server or `aws s3 sync` to object storage).

## Hardening checklist

- [ ] Strong `ODOO_ADMIN_PASSWD` (32+ chars) — this is the master password for `/web/database/manager`.
- [ ] `list_db = False` and `dbfilter = ^omran$` (already set in entrypoint) — prevents DB manager enumeration.
- [ ] Ufw firewall: only 22/80/443 open inbound.
- [ ] Fail2ban on SSH + nginx auth logs.
- [ ] Off-host backups + test a restore at least once.
- [ ] Cert auto-renewal cron: `0 3 * * * certbot renew --deploy-hook "docker compose -f /opt/omran-erp/deploy/docker-compose.yml restart nginx"`
- [ ] Monitor disk on the filestore volume; attachments grow.
- [ ] Monitor Postgres size + set up PITR if data is critical.

## What this does NOT give you

- Multi-tenant SaaS (per-client DB routing, billing). That's option C / a different architecture.
- Enterprise-only modules (Studio, Documents, Sign, Planning, etc.). Those require a paid subscription.
- HA / zero-downtime. Single node = single point of failure. Add a second node + managed Postgres + shared storage for HA.
- GDPR/SOC2/etc. compliance. Those are organizational, not technical, tasks.
