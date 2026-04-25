# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class AccountJournal(models.Model):
    """Journals group transactions by type (sales, purchases, bank, cash, misc)."""
    _name = 'account.journal'
    _description = 'Accounting Journal'
    _order = 'sequence, type, code'
    _inherit = ['mail.thread']

    name = fields.Char(string='Journal Name', required=True, tracking=True)
    code = fields.Char(
        string='Short Code', required=True, size=5,
        help='Used in sequence generation for entry references.')
    type = fields.Selection([
        ('sale', 'Sales'),
        ('purchase', 'Purchase'),
        ('cash', 'Cash'),
        ('bank', 'Bank'),
        ('general', 'Miscellaneous'),
    ], string='Type', required=True, tracking=True)
    sequence = fields.Integer(string='Sequence', default=10)

    # Default accounts for automatic line generation
    default_account_id = fields.Many2one(
        'account.account', string='Default Account',
        help='Default account used for journal items in this journal.',
        tracking=True)
    # For bank/cash journals
    payment_debit_account_id = fields.Many2one(
        'account.account', string='Outstanding Receipts Account',
        help='Account for unreconciled incoming payments.')
    payment_credit_account_id = fields.Many2one(
        'account.account', string='Outstanding Payments Account',
        help='Account for unreconciled outgoing payments.')
    suspense_account_id = fields.Many2one(
        'account.account', string='Suspense Account',
        help='Bank statement lines without a match go here temporarily.')

    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        help='Leave empty to use company currency.')
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company, required=True)
    active = fields.Boolean(default=True)
    color = fields.Integer(string='Color Index', default=0)

    # Sequence for entry numbering
    sequence_id = fields.Many2one(
        'ir.sequence', string='Entry Sequence',
        help='Sequence used for numbering journal entries in this journal.')

    # Lock date — prevent entries before this date
    lock_date = fields.Date(
        string='Lock Date',
        help='No entries allowed before this date in this journal.')

    _sql_constraints = [
        ('code_company_unique',
         'UNIQUE(code, company_id)',
         'Journal code must be unique per company.'),
    ]

    @api.constrains('type', 'default_account_id')
    def _check_default_account(self):
        """Validate that default account matches journal type."""
        type_group_map = {
            'sale': 'income',
            'purchase': 'expense',
            'bank': 'asset',
            'cash': 'asset',
        }
        for journal in self:
            if journal.default_account_id and journal.type in type_group_map:
                expected = type_group_map[journal.type]
                if journal.default_account_id.internal_group != expected:
                    raise ValidationError(
                        "Default account for a '%s' journal should be of group '%s'."
                        % (journal.type, expected))

    def _get_next_entry_number(self):
        """Generate the next sequence number for a journal entry."""
        self.ensure_one()
        if self.sequence_id:
            return self.sequence_id.next_by_id()
        # Fallback: use journal code + date-based numbering
        prefix = self.code.upper()
        year = fields.Date.context_today(self).strftime('%Y')
        last_move = self.env['account.move'].search([
            ('journal_id', '=', self.id),
            ('name', 'like', '%s/%s/' % (prefix, year)),
        ], order='name desc', limit=1)
        if last_move and last_move.name:
            last_num = int(last_move.name.split('/')[-1])
            next_num = last_num + 1
        else:
            next_num = 1
        return '%s/%s/%04d' % (prefix, year, next_num)
