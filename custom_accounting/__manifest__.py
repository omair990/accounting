# -*- coding: utf-8 -*-
{
    'name': 'Custom Accounting',
    'version': '17.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Full double-entry accounting system with invoicing, payments, and financial reports',
    'description': """
        Custom Accounting Module
        ========================
        - Chart of Accounts management
        - Journal Entries (double-entry)
        - Customer Invoices and Vendor Bills
        - Payment registration and reconciliation
        - Bank and Cash journals
        - Tax configuration and computation
        - Financial Reports: GL, Trial Balance, P&L, Balance Sheet
        - Multi-currency support
        - Audit trail and access controls
    """,
    'author': 'Custom Development',
    'website': '',
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'data': [
        # Security
        'security/accounting_groups.xml',
        'security/ir.model.access.csv',
        'security/accounting_rules.xml',
        # Data
        'data/sequence_data.xml',
        'data/account_type_data.xml',
        'data/default_chart_of_accounts.xml',
        'data/default_journals.xml',
        'data/currency_data.xml',
        # Wizards (must load before views that reference them)
        'wizard/account_payment_register_views.xml',
        'wizard/account_report_wizard_views.xml',
        # Views
        'views/account_account_views.xml',
        'views/account_journal_views.xml',
        'views/account_move_views.xml',
        'views/account_invoice_views.xml',
        'views/account_payment_views.xml',
        'views/account_tax_views.xml',
        'views/res_partner_views.xml',
        'views/account_reconcile_views.xml',
        'views/account_dashboard_views.xml',
        # Data - Cron
        'data/cron_data.xml',
        # Reports
        'reports/report_general_ledger.xml',
        'reports/report_trial_balance.xml',
        'reports/report_profit_loss.xml',
        'reports/report_balance_sheet.xml',
        'reports/report_aged.xml',
        'reports/report_invoice_template.xml',
        # Menus
        'views/menu_items.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
}
