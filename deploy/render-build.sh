#!/usr/bin/env bash
# Render.com build phase — runs once per deploy.
#   1. install Python deps (Odoo itself comes from a git+ pin in requirements.txt)
#   2. clone OCA dependency trees into ./oca
set -euo pipefail

echo "==> pip install"
pip install --upgrade pip
pip install -r requirements.txt

echo "==> clone OCA modules"
mkdir -p oca
cd oca
for repo in web account-financial-tools account-financial-reporting server-ux reporting-engine; do
    if [ ! -d "$repo" ]; then
        git clone --depth 1 -b 17.0 "https://github.com/OCA/$repo.git" "$repo"
        rm -rf "$repo/.git"
    fi
done
cd ..

echo "==> build done"
