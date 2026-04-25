################################################################################
# OCIT Accounting — Odoo 17 production image
#
# Built on the official Odoo 17 image, with:
#   - OCA dependencies cloned from upstream (web, account-financial-*, server-ux,
#     reporting-engine) at the 17.0 branch
#   - Custom modules from this repo (custom_accounting, omran_dashboard,
#     omran_branding, erp_lock)
#   - Extra Python dependencies from requirements.txt
#
# Database is provided at runtime via env vars. Either form works:
#   - DATABASE_URL=postgres://user:pass@host:5432/dbname
#   - HOST=... PORT=5432 USER=... PASSWORD=... (Odoo image defaults)
#
# Default HTTP port: 8069 (override at runtime with -e PORT=… if your
# platform injects a $PORT env var; the entrypoint honors it).
################################################################################

FROM odoo:17

USER root

# git is needed to fetch OCA dependencies during build.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# ---- OCA dependencies ----------------------------------------------------------
# Cloned shallow from the 17.0 branch. Pin to specific commits in your fork if
# you need reproducible builds.
RUN set -eux; \
    mkdir -p /mnt/extra-addons; \
    cd /mnt/extra-addons; \
    for repo in web account-financial-tools account-financial-reporting server-ux reporting-engine; do \
        git clone --depth 1 -b 17.0 "https://github.com/OCA/$repo.git" "$repo"; \
        rm -rf "$repo/.git"; \
    done

# ---- Custom modules from this repo --------------------------------------------
COPY --chown=odoo:odoo custom_accounting  /mnt/extra-addons/custom_accounting
COPY --chown=odoo:odoo omran_dashboard    /mnt/extra-addons/omran_dashboard
COPY --chown=odoo:odoo omran_branding     /mnt/extra-addons/omran_branding
COPY --chown=odoo:odoo erp_lock           /mnt/extra-addons/erp_lock

RUN chown -R odoo:odoo /mnt/extra-addons

# ---- Extra Python dependencies -------------------------------------------------
# Skip the `odoo` line — the base image already has Odoo installed.
COPY requirements.txt /tmp/requirements.txt
RUN set -eux; \
    grep -vE '^(odoo[ @=]|#|\s*$)' /tmp/requirements.txt > /tmp/req-clean.txt || true; \
    pip install --no-cache-dir -r /tmp/req-clean.txt; \
    rm -f /tmp/requirements.txt /tmp/req-clean.txt

# ---- Entrypoint shim: DATABASE_URL → HOST/USER/PASSWORD/PORT ------------------
COPY docker-entrypoint.sh /usr/local/bin/ocit-entrypoint.sh
RUN chmod +x /usr/local/bin/ocit-entrypoint.sh

USER odoo

EXPOSE 8069 8071 8072

ENTRYPOINT ["/usr/local/bin/ocit-entrypoint.sh"]
CMD ["odoo"]
