#!/bin/bash
# Usage: ./restore.sh <db_dump> <filestore_tar>
set -euo pipefail

DUMP="${1:?db dump file required}"
FS="${2:?filestore tar file required}"

cd "$(dirname "$0")/.."

echo "Stopping odoo..."
docker compose stop odoo

echo "Restoring database $ODOO_DB_NAME..."
docker compose exec -T db psql -U "$ODOO_DB_USER" -c "DROP DATABASE IF EXISTS $ODOO_DB_NAME;"
docker compose exec -T db psql -U "$ODOO_DB_USER" -c "CREATE DATABASE $ODOO_DB_NAME;"
docker compose exec -T db pg_restore -U "$ODOO_DB_USER" -d "$ODOO_DB_NAME" < "$DUMP"

echo "Restoring filestore..."
docker compose exec -T odoo tar xzf - -C /var/lib/odoo < "$FS"

echo "Starting odoo..."
docker compose start odoo
echo "Restore complete."
