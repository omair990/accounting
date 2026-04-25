# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from odoo.tools import float_is_zero, float_compare


class AccountMoveLine(models.Model):
    """
    Journal Item — individual debit/credit line within a journal entry.
    Supports tax computation, reconciliation, and multi-currency.
    """
    _name = 'account.move.line'
    _description = 'Journal Item'
    _order = 'date desc, move_name desc, id'
    _check_company_auto = True

    # === Parent ===
    move_id = fields.Many2one(
        'account.move', string='Journal Entry',
        required=True, ondelete='cascade', index=True, auto_join=True)
    move_name = fields.Char(
        related='move_id.name', string='Entry Number', store=True, index=True)
    move_type = fields.Selection(related='move_id.move_type', store=True)

    # === Core Accounting ===
    account_id = fields.Many2one(
        'account.account', string='Account', required=True,
        index=True, check_company=True,
        domain="[('deprecated', '=', False), ('company_id', '=', company_id)]")
    name = fields.Char(string='Label', tracking=True)
    debit = fields.Monetary(
        string='Debit', default=0.0, currency_field='currency_id')
    credit = fields.Monetary(
        string='Credit', default=0.0, currency_field='currency_id')
    balance = fields.Monetary(
        string='Balance', compute='_compute_balance',
        store=True, currency_field='currency_id')

    # === Invoice line data ===
    quantity = fields.Float(string='Quantity', default=1.0, digits='Product Unit of Measure')
    price_unit = fields.Float(string='Unit Price', digits='Product Price')
    price_subtotal = fields.Monetary(
        string='Subtotal', compute='_compute_price',
        store=True, currency_field='currency_id')
    discount = fields.Float(string='Discount (%)', digits='Discount', default=0.0)

    # === Multi-currency ===
    currency_id = fields.Many2one(
        related='move_id.currency_id', string='Currency',
        store=True, readonly=True)
    amount_currency = fields.Monetary(
        string='Amount in Currency',
        currency_field='currency_id',
        help='Amount in the entry currency if different from company currency.')

    # === Tax ===
    tax_ids = fields.Many2many(
        'account.tax', string='Taxes',
        help='Taxes applied to this line.',
        domain="[('company_id', '=', company_id)]")
    is_tax_line = fields.Boolean(
        string='Is Tax Line', default=False, readonly=True)
    tax_line_id = fields.Many2one(
        'account.tax', string='Originating Tax', readonly=True)
    tax_base_amount = fields.Monetary(
        string='Tax Base', currency_field='currency_id',
        help='Base amount on which this tax was computed.')

    # === Relationships ===
    partner_id = fields.Many2one(
        related='move_id.partner_id', string='Partner',
        store=True, index='btree_not_null')
    journal_id = fields.Many2one(
        related='move_id.journal_id', string='Journal', store=True, index=True)
    company_id = fields.Many2one(
        related='move_id.company_id', string='Company', store=True)
    date = fields.Date(related='move_id.date', string='Date', store=True, index=True)

    # === Reconciliation ===
    reconciled = fields.Boolean(
        string='Reconciled', compute='_compute_reconciled', store=True)
    amount_residual = fields.Monetary(
        string='Residual Amount', compute='_compute_amount_residual',
        store=True, currency_field='currency_id')
    matched_debit_ids = fields.One2many(
        'account.partial.reconcile', 'credit_move_id', string='Matched Debits')
    matched_credit_ids = fields.One2many(
        'account.partial.reconcile', 'debit_move_id', string='Matched Credits')
    full_reconcile_id = fields.Many2one(
        'account.partial.reconcile', string='Full Reconcile',
        compute='_compute_reconciled', store=True)

    # === Display ===
    date_maturity = fields.Date(string='Due Date', index=True)
    sequence = fields.Integer(default=10)
    display_type = fields.Selection([
        ('line_section', 'Section'),
        ('line_note', 'Note'),
    ], string='Display Type', default=False)

    # === Computed ===

    @api.depends('debit', 'credit')
    def _compute_balance(self):
        for line in self:
            line.balance = line.debit - line.credit

    @api.depends('quantity', 'price_unit', 'discount', 'tax_ids')
    def _compute_price(self):
        for line in self:
            subtotal = line.quantity * line.price_unit
            if line.discount:
                subtotal *= (1 - line.discount / 100.0)
            line.price_subtotal = subtotal

    @api.depends('debit', 'credit', 'matched_debit_ids.amount',
                 'matched_credit_ids.amount', 'account_id.reconcile')
    def _compute_amount_residual(self):
        for line in self:
            if not line.account_id.reconcile:
                line.amount_residual = 0.0
                continue
            matched_amount = (
                sum(line.matched_debit_ids.mapped('amount')) +
                sum(line.matched_credit_ids.mapped('amount')))
            if line.debit:
                line.amount_residual = line.debit - matched_amount
            elif line.credit:
                line.amount_residual = line.credit - matched_amount
            else:
                line.amount_residual = 0.0

    @api.depends('amount_residual', 'account_id.reconcile')
    def _compute_reconciled(self):
        for line in self:
            if not line.account_id.reconcile:
                line.reconciled = False
                line.full_reconcile_id = False
            else:
                line.reconciled = (
                    float_is_zero(line.amount_residual,
                                  precision_rounding=line.currency_id.rounding or 0.01)
                    and (line.debit > 0 or line.credit > 0))
                line.full_reconcile_id = False

    # === Constraints ===

    @api.constrains('debit', 'credit')
    def _check_debit_credit(self):
        for line in self:
            if line.display_type:
                continue
            if line.debit < 0 or line.credit < 0:
                raise ValidationError(
                    "Debit and credit must be positive values (line: %s)."
                    % (line.name or line.account_id.display_name))
            if float_compare(line.debit, 0, precision_rounding=0.01) > 0 and \
               float_compare(line.credit, 0, precision_rounding=0.01) > 0:
                raise ValidationError(
                    "A journal item cannot have both debit and credit "
                    "(account: %s)." % line.account_id.display_name)

    # === Onchange ===

    @api.onchange('quantity', 'price_unit', 'discount', 'tax_ids')
    def _onchange_price_unit(self):
        """Recompute debit/credit from price when editing invoice lines."""
        if self.move_id.is_invoice and self.price_unit and not self.is_tax_line:
            subtotal = self.quantity * self.price_unit
            if self.discount:
                subtotal *= (1 - self.discount / 100.0)

            if self.move_id.move_type in ('out_invoice', 'out_refund'):
                self.credit = subtotal
                self.debit = 0.0
            else:
                self.debit = subtotal
                self.credit = 0.0

    @api.onchange('debit')
    def _onchange_debit(self):
        if self.debit:
            self.credit = 0.0

    @api.onchange('credit')
    def _onchange_credit(self):
        if self.credit:
            self.debit = 0.0

    # === Tax Line Generation ===

    def _compute_tax_lines(self):
        """
        Compute and create tax lines for this set of move lines.
        Called when posting an invoice to auto-generate tax journal items.
        """
        move = self.mapped('move_id')
        move.ensure_one()

        # Remove existing tax lines
        existing_tax_lines = move.line_ids.filtered(lambda l: l.is_tax_line)
        if existing_tax_lines:
            existing_tax_lines.unlink()

        # Compute new tax lines
        tax_lines_vals = []
        for line in self.filtered(lambda l: l.tax_ids and not l.is_tax_line):
            base_amount = line.debit or line.credit
            tax_results = line.tax_ids.compute_all(base_amount, line.quantity)
            for tax_data in tax_results.get('taxes', []):
                tax = self.env['account.tax'].browse(tax_data['tax_id'])
                tax_account = tax.account_id
                if not tax_account:
                    continue

                if move.move_type in ('out_invoice', 'out_refund'):
                    tax_lines_vals.append({
                        'move_id': move.id,
                        'account_id': tax_account.id,
                        'name': tax_data['tax_name'],
                        'debit': 0.0,
                        'credit': tax_data['tax_amount'],
                        'is_tax_line': True,
                        'tax_line_id': tax.id,
                        'tax_base_amount': base_amount,
                        'partner_id': move.partner_id.id,
                    })
                else:
                    tax_lines_vals.append({
                        'move_id': move.id,
                        'account_id': tax_account.id,
                        'name': tax_data['tax_name'],
                        'debit': tax_data['tax_amount'],
                        'credit': 0.0,
                        'is_tax_line': True,
                        'tax_line_id': tax.id,
                        'tax_base_amount': base_amount,
                        'partner_id': move.partner_id.id,
                    })

        if tax_lines_vals:
            self.env['account.move.line'].create(tax_lines_vals)
