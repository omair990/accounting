#!/bin/bash
# Daily backup: pg_dump + filestore tarball + rotation (keep 14 days)
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/odoo}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)

mkdir -p "$BACKUP_DIR"

cd "$(dirname "$0")/.."

# 1. Database dump
docker compose exec -T db pg_dump -U "$ODOO_DB_USER" -Fc "$ODOO_DB_NAME" \
  > "$BACKUP_DIR/${ODOO_DB_NAME}_${STAMP}.dump"

# 2. Filestore
docker compose exec -T odoo tar czf - -C /var/lib/odoo filestore \
  > "$BACKUP_DIR/filestore_${STAMP}.tar.gz"

# 3. Rotate
find "$BACKUP_DIR" -name '*.dump'   -mtime +"$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -name '*.tar.gz' -mtime +"$RETENTION_DAYS" -delete

echo "Backup complete: $STAMP"
