#!/bin/bash
# Obtain Let's Encrypt cert with certbot standalone, then copy into nginx/certs/
# Prereqs: stop the stack so port 80 is free. Run as root on the VPS.
set -euo pipefail

: "${DOMAIN:?DOMAIN env var required (e.g. erp.omran.com)}"
: "${EMAIL:?EMAIL env var required for Let's Encrypt registration}"

if ! command -v certbot >/dev/null; then
  apt-get update && apt-get install -y certbot
fi

cd "$(dirname "$0")/.."
docker compose stop nginx || true

certbot certonly --standalone -d "$DOMAIN" -m "$EMAIL" --agree-tos --non-interactive

mkdir -p nginx/certs
cp "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" nginx/certs/fullchain.pem
cp "/etc/letsencrypt/live/$DOMAIN/privkey.pem"   nginx/certs/privkey.pem

docker compose up -d nginx
echo "TLS installed for $DOMAIN. Add a cron job for renewal."
