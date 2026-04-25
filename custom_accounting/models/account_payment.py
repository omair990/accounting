# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_is_zero

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    """
    Payment — money received from customers or sent to vendors.
    Automatically creates balanced journal entries and supports
    reconciliation with invoices (full and partial).
    """
    _name = 'account.payment'
    _description = 'Payment'
    _order = 'date desc, name desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company_auto = True

    # === Identity ===
    name = fields.Char(
        string='Number', readonly=True, copy=False, default='/',
        tracking=True, index='trigram')

    # === Type ===
    payment_type = fields.Selection([
        ('inbound', 'Receive Money'),
        ('outbound', 'Send Money'),
    ], string='Payment Type', required=True, tracking=True)
    partner_type = fields.Selection([
        ('customer', 'Customer'),
        ('supplier', 'Vendor'),
    ], string='Partner Type', required=True, tracking=True)

    # === Partner ===
    partner_id = fields.Many2one(
        'res.partner', string='Partner', required=True, tracking=True,
        index='btree_not_null')

    # === Amount ===
    amount = fields.Monetary(
        string='Amount', required=True, tracking=True,
        currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id, required=True)

    # === Date ===
    date = fields.Date(
        string='Payment Date', required=True,
        default=fields.Date.context_today, tracking=True, index=True)

    # === Journal ===
    journal_id = fields.Many2one(
        'account.journal', string='Journal', required=True,
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        tracking=True, check_company=True)

    # === Destination Account ===
    destination_account_id = fields.Many2one(
        'account.account', string='Destination Account',
        compute='_compute_destination_account', store=True, readonly=False,
        check_company=True)

    # === State ===
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('sent', 'Sent'),
        ('reconciled', 'Reconciled'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True,
        tracking=True, index=True, copy=False)

    # === Related Journal Entry ===
    move_id = fields.Many2one(
        'account.move', string='Journal Entry', readonly=True, copy=False,
        index=True)

    # === Reconciliation ===
    reconciled_invoice_ids = fields.Many2many(
        'account.move', string='Reconciled Invoices',
        compute='_compute_reconciled_invoices')
    reconciled_invoices_count = fields.Integer(
        compute='_compute_reconciled_invoices')
    is_reconciled = fields.Boolean(
        string='Is Reconciled', compute='_compute_is_reconciled', store=True)

    # === Communication ===
    memo = fields.Char(string='Memo', tracking=True)
    payment_reference = fields.Char(
        string='Payment Reference',
        help='Reference visible to the partner (bank transfer ref, check number).')

    # === Company ===
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company, required=True, readonly=True)

    # === Computed ===

    @api.depends('partner_type', 'partner_id', 'company_id')
    def _compute_destination_account(self):
        for payment in self:
            if payment.partner_type == 'customer':
                payment.destination_account_id = (
                    payment.partner_id.property_account_receivable_id or
                    payment.company_id.account_default_receivable_id)
            else:
                payment.destination_account_id = (
                    payment.partner_id.property_account_payable_id or
                    payment.company_id.account_default_payable_id)

    def _compute_reconciled_invoices(self):
        for payment in self:
            if payment.move_id:
                rec_lines = payment.move_id.line_ids.filtered(
                    lambda l: l.account_id.reconcile and
                    (l.matched_debit_ids or l.matched_credit_ids))
                invoices = self.env['account.move']
                for line in rec_lines:
                    for partial in (line.matched_debit_ids | line.matched_credit_ids):
                        counterpart = (partial.debit_move_id
                                       if partial.credit_move_id.id == line.id
                                       else partial.credit_move_id)
                        if counterpart.move_id.is_invoice:
                            invoices |= counterpart.move_id
                payment.reconciled_invoice_ids = invoices
                payment.reconciled_invoices_count = len(invoices)
            else:
                payment.reconciled_invoice_ids = False
                payment.reconciled_invoices_count = 0

    @api.depends('move_id.line_ids.reconciled', 'state')
    def _compute_is_reconciled(self):
        for payment in self:
            if payment.state != 'posted' or not payment.move_id:
                payment.is_reconciled = False
            else:
                rec_line = payment.move_id.line_ids.filtered(
                    lambda l: l.account_id == payment.destination_account_id)
                payment.is_reconciled = all(rec_line.mapped('reconciled'))

    # === Constraints ===

    @api.constrains('amount')
    def _check_amount(self):
        for payment in self:
            if float_is_zero(payment.amount, precision_rounding=payment.currency_id.rounding):
                raise ValidationError("Payment amount must be greater than zero.")
            if payment.amount < 0:
                raise ValidationError("Payment amount cannot be negative.")

    # === Actions ===

    def action_post(self):
        """Validate: create journal entry and post."""
        for payment in self:
            if payment.state != 'draft':
                raise UserError("Only draft payments can be posted.")
            if not payment.destination_account_id:
                raise UserError(
                    "No destination account found. Configure receivable/payable "
                    "account for partner '%s'." % payment.partner_id.name)

            move_vals = payment._prepare_move_vals()
            move = self.env['account.move'].create(move_vals)
            move.action_post()

            payment.write({
                'state': 'posted',
                'name': move.name,
                'move_id': move.id,
            })
            _logger.info("Payment %s posted for %s %.2f",
                         payment.name, payment.currency_id.name, payment.amount)
        return True

    def action_cancel(self):
        """Cancel the payment and its journal entry."""
        for payment in self:
            if payment.state not in ('posted', 'sent'):
                raise UserError("Only posted payments can be cancelled.")
            # Unreconcile first
            if payment.move_id:
                rec_lines = payment.move_id.line_ids.filtered(
                    lambda l: l.account_id.reconcile and l.reconciled)
                if rec_lines:
                    rec_lines.unreconcile()
                payment.move_id.action_cancel()
            payment.state = 'cancelled'
        return True

    def action_draft(self):
        """Reset to draft."""
        for payment in self:
            if payment.state != 'cancelled':
                raise UserError("Only cancelled payments can be reset.")
            payment.state = 'draft'
        return True

    def action_view_invoices(self):
        """View reconciled invoices."""
        self.ensure_one()
        invoices = self.reconciled_invoice_ids
        if len(invoices) == 1:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'res_id': invoices.id,
                'view_mode': 'form',
            }
        return {
            'type': 'ir.actions.act_window',
            'name': 'Invoices',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', invoices.ids)],
        }

    # === Move Generation ===

    def _prepare_move_vals(self):
        """Prepare journal entry values for this payment."""
        self.ensure_one()
        liquidity_account = (self.journal_id.default_account_id or
                             self.journal_id.payment_debit_account_id)
        if not liquidity_account:
            raise UserError(
                "No default account configured on journal '%s'."
                % self.journal_id.name)

        if self.payment_type == 'inbound':
            debit_account = liquidity_account
            credit_account = self.destination_account_id
        else:
            debit_account = self.destination_account_id
            credit_account = liquidity_account

        ref = self.memo or self.payment_reference or self.name
        return {
            'move_type': 'entry',
            'date': self.date,
            'journal_id': self.journal_id.id,
            'partner_id': self.partner_id.id,
            'ref': ref,
            'line_ids': [
                (0, 0, {
                    'account_id': debit_account.id,
                    'partner_id': self.partner_id.id,
                    'name': ref,
                    'debit': self.amount,
                    'credit': 0.0,
                    'date_maturity': self.date,
                }),
                (0, 0, {
                    'account_id': credit_account.id,
                    'partner_id': self.partner_id.id,
                    'name': ref,
                    'debit': 0.0,
                    'credit': self.amount,
                    'date_maturity': self.date,
                }),
            ],
        }

    def action_register_and_reconcile(self, invoice_ids):
        """
        Post the payment and reconcile against specified invoices.
        Supports partial payments.
        """
        self.ensure_one()
        self.action_post()
        if not self.move_id:
            return

        # Payment's receivable/payable line
        payment_line = self.move_id.line_ids.filtered(
            lambda l: l.account_id == self.destination_account_id)

        # Invoice receivable/payable lines
        invoices = self.env['account.move'].browse(invoice_ids)
        invoice_lines = invoices.mapped('line_ids').filtered(
            lambda l: l.account_id == self.destination_account_id
            and not l.reconciled
            and l.move_id.state == 'posted')

        if payment_line and invoice_lines:
            (payment_line + invoice_lines).reconcile()
