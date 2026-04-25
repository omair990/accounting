# -*- coding: utf-8 -*-
from odoo import models, fields


class ResCompany(models.Model):
    """Extend company with accounting configuration."""
    _inherit = 'res.company'

    # Fiscal configuration
    fiscalyear_last_day = fields.Integer(
        string='Last Day', default=31,
        help='Last day of the fiscal year.')
    fiscalyear_last_month = fields.Selection([
        ('1', 'January'), ('2', 'February'), ('3', 'March'),
        ('4', 'April'), ('5', 'May'), ('6', 'June'),
        ('7', 'July'), ('8', 'August'), ('9', 'September'),
        ('10', 'October'), ('11', 'November'), ('12', 'December'),
    ], string='Last Month', default='12',
        help='Last month of the fiscal year.')

    # Lock dates
    fiscalyear_lock_date = fields.Date(
        string='Fiscal Year Lock Date',
        help='No entries can be created or edited before this date for all users.')
    period_lock_date = fields.Date(
        string='Lock Date for Non-Advisers',
        help='Only users with Accounting Manager role can create/edit entries before this date.')

    # Default accounts
    account_default_receivable_id = fields.Many2one(
        'account.account', string='Default Receivable Account',
        domain="[('account_type_id.type', '=', 'receivable')]")
    account_default_payable_id = fields.Many2one(
        'account.account', string='Default Payable Account',
        domain="[('account_type_id.type', '=', 'payable')]")
    account_sale_tax_id = fields.Many2one(
        'account.tax', string='Default Sale Tax',
        domain="[('type_tax_use', '=', 'sale')]")
    account_purchase_tax_id = fields.Many2one(
        'account.tax', string='Default Purchase Tax',
        domain="[('type_tax_use', '=', 'purchase')]")

    # Currency gain/loss
    income_currency_exchange_account_id = fields.Many2one(
        'account.account', string='Exchange Gain Account')
    expense_currency_exchange_account_id = fields.Many2one(
        'account.account', string='Exchange Loss Account')
