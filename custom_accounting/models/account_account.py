# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class AccountAccountType(models.Model):
    """Account types define the nature of accounts for reporting purposes."""
    _name = 'account.account.type'
    _description = 'Account Type'
    _order = 'sequence, name'

    name = fields.Char(string='Type Name', required=True)
    code = fields.Char(string='Code', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    internal_group = fields.Selection([
        ('asset', 'Asset'),
        ('liability', 'Liability'),
        ('equity', 'Equity'),
        ('income', 'Income'),
        ('expense', 'Expense'),
    ], string='Internal Group', required=True,
        help='Used to classify accounts for financial statements')
    # Sub-classifications for detailed reporting
    type = fields.Selection([
        ('receivable', 'Receivable'),
        ('payable', 'Payable'),
        ('bank', 'Bank and Cash'),
        ('current_assets', 'Current Assets'),
        ('non_current_assets', 'Non-current Assets'),
        ('prepayments', 'Prepayments'),
        ('current_liabilities', 'Current Liabilities'),
        ('non_current_liabilities', 'Non-current Liabilities'),
        ('equity', 'Equity'),
        ('income', 'Income'),
        ('cost_of_revenue', 'Cost of Revenue'),
        ('expense', 'Expenses'),
        ('depreciation', 'Depreciation'),
        ('other_income', 'Other Income'),
    ], string='Type', required=True)

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Account type code must be unique.'),
    ]


class AccountAccount(models.Model):
    """Chart of Accounts — the foundation of the accounting system."""
    _name = 'account.account'
    _description = 'Account'
    _order = 'code'
    _inherit = ['mail.thread']

    name = fields.Char(string='Account Name', required=True, tracking=True)
    code = fields.Char(string='Code', required=True, size=10, tracking=True)
    account_type_id = fields.Many2one(
        'account.account.type', string='Account Type',
        required=True, tracking=True)
    internal_group = fields.Selection(
        related='account_type_id.internal_group',
        string='Internal Group', store=True, readonly=True)
    currency_id = fields.Many2one(
        'res.currency', string='Account Currency',
        help='Forces all moves for this account to have this currency.')
    reconcile = fields.Boolean(
        string='Allow Reconciliation', default=False,
        help='Check if you need to reconcile entries on this account (e.g., receivables, payables).')
    deprecated = fields.Boolean(
        string='Deprecated', default=False,
        help='Deprecated accounts cannot be used in new journal entries.')
    note = fields.Text(string='Internal Notes')
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company, required=True)
    active = fields.Boolean(default=True)

    # Computed fields for balance display
    current_balance = fields.Monetary(
        string='Current Balance', compute='_compute_current_balance',
        currency_field='company_currency_id')
    company_currency_id = fields.Many2one(
        related='company_id.currency_id', string='Company Currency', readonly=True)

    _sql_constraints = [
        ('code_company_unique',
         'UNIQUE(code, company_id)',
         'Account code must be unique per company.'),
    ]

    @api.depends('code')
    def _compute_current_balance(self):
        """Compute the current balance from all posted move lines."""
        for account in self:
            lines = self.env['account.move.line'].search([
                ('account_id', '=', account.id),
                ('move_id.state', '=', 'posted'),
            ])
            account.current_balance = sum(lines.mapped('debit')) - sum(lines.mapped('credit'))

    @api.constrains('code')
    def _check_code_format(self):
        """Ensure account code is numeric and at least 4 digits."""
        for record in self:
            if not record.code.isdigit():
                raise ValidationError("Account code must contain only digits.")
            if len(record.code) < 4:
                raise ValidationError("Account code must be at least 4 digits.")

    @api.constrains('deprecated')
    def _check_deprecated_usage(self):
        """Prevent deprecating accounts with unreconciled entries."""
        for record in self:
            if record.deprecated and record.reconcile:
                unreconciled = self.env['account.move.line'].search_count([
                    ('account_id', '=', record.id),
                    ('reconciled', '=', False),
                    ('move_id.state', '=', 'posted'),
                ])
                if unreconciled:
                    raise ValidationError(
                        "Cannot deprecate account '%s' — it has %d unreconciled entries."
                        % (record.name, unreconciled))

    def name_get(self):
        result = []
        for account in self:
            result.append((account.id, '%s %s' % (account.code, account.name)))
        return result

    @api.model
    def _name_search(self, name, domain=None, operator='ilike', limit=100, order=None):
        """Allow searching by code or name."""
        domain = domain or []
        if name:
            domain = ['|', ('code', '=ilike', name + '%'),
                      ('name', operator, name)] + domain
        return self._search(domain, limit=limit, order=order)
