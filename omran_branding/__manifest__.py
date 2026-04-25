{
    'name': 'Omran Branding',
    'version': '17.0.1.0.0',
    'category': 'Themes/Backend',
    'summary': 'Company branding, login page and color scheme for Omran IT',
    'depends': ['base', 'web', 'mail'],
    'data': [
        'data/company_data.xml',
        'data/system_parameter_data.xml',
        'views/fonts.xml',
        'views/webclient_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'omran_branding/static/src/scss/riyal_font.scss',
            'omran_branding/static/src/scss/variables.scss',
            'omran_branding/static/src/scss/branding.scss',
            'omran_branding/static/src/scss/components.scss',
            'omran_branding/static/src/scss/navbar.scss',
            'omran_branding/static/src/scss/legibility.scss',
            'omran_branding/static/src/scss/dashboard_action.scss',
        ],
        'web.assets_frontend': [
            'omran_branding/static/src/scss/riyal_font.scss',
            'omran_branding/static/src/scss/variables.scss',
            'omran_branding/static/src/scss/login.scss',
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
    'application': False,
    'auto_install': True,
}
