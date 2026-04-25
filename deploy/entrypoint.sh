#!/bin/bash
set -e

: "${ODOO_DB_HOST:=db}"
: "${ODOO_DB_PORT:=5432}"
: "${ODOO_DB_USER:=odoo}"
: "${ODOO_DB_PASSWORD:?ODOO_DB_PASSWORD is required}"
: "${ODOO_ADMIN_PASSWD:?ODOO_ADMIN_PASSWD is required}"
: "${ODOO_WORKERS:=4}"
: "${ODOO_DB_NAME:=omran}"

# Wait for PostgreSQL
echo "Waiting for PostgreSQL at ${ODOO_DB_HOST}:${ODOO_DB_PORT}..."
until pg_isready -h "$ODOO_DB_HOST" -p "$ODOO_DB_PORT" -U "$ODOO_DB_USER" >/dev/null 2>&1; do
  sleep 1
done
echo "PostgreSQL is ready."

cat > /var/lib/odoo/odoo.conf <<EOF
[options]
admin_passwd = ${ODOO_ADMIN_PASSWD}
db_host = ${ODOO_DB_HOST}
db_port = ${ODOO_DB_PORT}
db_user = ${ODOO_DB_USER}
db_password = ${ODOO_DB_PASSWORD}
db_name = ${ODOO_DB_NAME}
dbfilter = ^${ODOO_DB_NAME}$
list_db = False

addons_path = /opt/odoo/src/odoo/addons,/opt/odoo/src/oca/web,/opt/odoo/src/oca/account-financial-tools,/opt/odoo/src/oca/account-financial-reporting,/opt/odoo/src/oca/server-ux,/opt/odoo/src/oca/reporting-engine,/opt/odoo/src/oca/custom_modern_theme,/opt/odoo/custom

data_dir = /var/lib/odoo
logfile = /var/log/odoo/odoo.log
log_level = info
log_handler = :INFO

proxy_mode = True
http_interface = 0.0.0.0
http_port = 8069
longpolling_port = 8072
gevent_port = 8072

workers = ${ODOO_WORKERS}
max_cron_threads = 2
limit_memory_soft = 2147483648
limit_memory_hard = 2684354560
limit_request = 8192
limit_time_cpu = 600
limit_time_real = 1200
limit_time_real_cron = 0

db_maxconn = 64
osv_memory_count_limit = 0

unaccent = True
without_demo = all
EOF

case "$1" in
  odoo)
    exec python /opt/odoo/src/odoo/odoo-bin -c /var/lib/odoo/odoo.conf "${@:2}"
    ;;
  shell)
    exec python /opt/odoo/src/odoo/odoo-bin shell -c /var/lib/odoo/odoo.conf "${@:2}"
    ;;
  *)
    exec "$@"
    ;;
esac
