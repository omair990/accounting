{
    'name': 'OCIT Dashboard',
    'version': '17.0.1.0.0',
    'category': 'Dashboards',
    'summary': 'Stats dashboard landing page for OCIT ERP',
    'depends': ['base', 'web', 'mail', 'account', 'sale_management', 'purchase', 'stock', 'hr', 'project', 'crm'],
    'data': [
        'security/ir.model.access.csv',
        'views/dashboard_views.xml',
        'data/home_action.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'omran_dashboard/static/src/scss/dashboard.scss',
        ],
    },
    'license': 'LGPL-3',
    'installable': True,
    'application': True,
    'auto_install': False,
}
