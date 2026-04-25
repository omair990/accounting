FROM python:3.11-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libldap2-dev libsasl2-dev libssl-dev libffi-dev \
    libpq-dev libjpeg-dev libxml2-dev libxslt1-dev libxslt-dev \
    zlib1g-dev liblcms2-dev libwebp-dev libharfbuzz-dev libfribidi-dev \
    libtiff5-dev libopenjp2-7-dev libfreetype6-dev libtiff-dev \
    node-less npm \
    fonts-noto-cjk fonts-liberation fonts-freefont-ttf \
    xz-utils ca-certificates curl git \
    postgresql-client \
 && curl -fsSL https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3/wkhtmltox_0.12.6.1-3.bookworm_amd64.deb -o /tmp/wk.deb \
 && apt-get install -y --no-install-recommends /tmp/wk.deb \
 && rm /tmp/wk.deb \
 && rm -rf /var/lib/apt/lists/*

RUN useradd -ms /bin/bash odoo

WORKDIR /opt/odoo

# Clone Odoo Community + OCA repos at build time (pin to 17.0)
RUN git clone --depth 1 --branch 17.0 https://github.com/odoo/odoo.git         src/odoo \
 && git clone --depth 1 --branch 17.0 https://github.com/OCA/web.git           src/oca/web \
 && git clone --depth 1 --branch 17.0 https://github.com/OCA/account-financial-tools.git     src/oca/account-financial-tools \
 && git clone --depth 1 --branch 17.0 https://github.com/OCA/account-financial-reporting.git src/oca/account-financial-reporting \
 && git clone --depth 1 --branch 17.0 https://github.com/OCA/server-ux.git     src/oca/server-ux \
 && git clone --depth 1 --branch 17.0 https://github.com/OCA/reporting-engine.git src/oca/reporting-engine \
 && git clone --depth 1 https://github.com/JavierASU/custom_modern_theme_Odoo-17.git src/oca/custom_modern_theme

RUN pip install --no-cache-dir -r src/odoo/requirements.txt \
 && pip install --no-cache-dir freezegun num2words phonenumbers psycogreen gevent==23.9.1

# Copy your custom modules
COPY --chown=odoo:odoo ./custom /opt/odoo/custom

# Entrypoint
COPY --chown=odoo:odoo ./entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN mkdir -p /var/lib/odoo /var/log/odoo \
 && chown -R odoo:odoo /opt/odoo /var/lib/odoo /var/log/odoo

USER odoo
EXPOSE 8069 8072
VOLUME ["/var/lib/odoo"]

ENTRYPOINT ["/entrypoint.sh"]
CMD ["odoo"]
