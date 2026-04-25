#!/usr/bin/env bash
# Render.com build phase.
#
# Clones the Odoo 17 source tree (full, including ./addons) and the OCA
# dependency repos, then installs Python deps. We do NOT pip-install Odoo
# because its sdist only ships the `odoo/` core — not the `addons/` tree
# at the source root, which is where `web`, `account`, `sale`, etc. live.
set -euo pipefail

ODOO_BRANCH="17.0"

echo "==> clone Odoo $ODOO_BRANCH source"
if [ ! -d odoo-src ]; then
    git clone --depth 1 -b "$ODOO_BRANCH" https://github.com/odoo/odoo.git odoo-src
    rm -rf odoo-src/.git
fi

echo "==> pip install Odoo's own requirements"
pip install --upgrade pip
pip install -r odoo-src/requirements.txt

echo "==> pip install this repo's extras"
pip install -r requirements.txt

echo "==> clone OCA modules"
mkdir -p oca
cd oca
for repo in web account-financial-tools account-financial-reporting server-ux reporting-engine; do
    if [ ! -d "$repo" ]; then
        git clone --depth 1 -b "$ODOO_BRANCH" "https://github.com/OCA/$repo.git" "$repo"
        rm -rf "$repo/.git"
    fi
done
cd ..

echo "==> build done"
