# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResPartner(models.Model):
    """Extend partner with accounting-specific fields."""
    _inherit = 'res.partner'

    # Default accounts for this partner
    property_account_receivable_id = fields.Many2one(
        'account.account', string='Account Receivable',
        domain="[('account_type_id.type', '=', 'receivable')]",
        help='Default receivable account for this customer.')
    property_account_payable_id = fields.Many2one(
        'account.account', string='Account Payable',
        domain="[('account_type_id.type', '=', 'payable')]",
        help='Default payable account for this vendor.')

    # Accounting classification
    customer_rank = fields.Integer(string='Customer Rank', default=0)
    supplier_rank = fields.Integer(string='Vendor Rank', default=0)

    # Credit management
    credit_limit = fields.Monetary(
        string='Credit Limit', currency_field='currency_id',
        help='Maximum outstanding receivable allowed.')
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id)

    # Computed accounting balances
    total_receivable = fields.Monetary(
        string='Total Receivable', compute='_compute_accounting_balances',
        currency_field='currency_id')
    total_payable = fields.Monetary(
        string='Total Payable', compute='_compute_accounting_balances',
        currency_field='currency_id')
    total_overdue = fields.Monetary(
        string='Total Overdue', compute='_compute_accounting_balances',
        currency_field='currency_id')

    # Payment terms
    payment_terms_note = fields.Text(string='Payment Terms Description')
    default_payment_days = fields.Integer(
        string='Default Payment Days', default=30,
        help='Default number of days for invoice due date.')

    def _compute_accounting_balances(self):
        today = fields.Date.context_today(self)
        for partner in self:
            # Receivable: posted invoices with residual
            receivable_moves = self.env['account.move'].search([
                ('partner_id', '=', partner.id),
                ('move_type', 'in', ('out_invoice', 'out_refund')),
                ('state', '=', 'posted'),
            ])
            partner.total_receivable = sum(receivable_moves.mapped('amount_residual'))

            # Payable: posted bills with residual
            payable_moves = self.env['account.move'].search([
                ('partner_id', '=', partner.id),
                ('move_type', 'in', ('in_invoice', 'in_refund')),
                ('state', '=', 'posted'),
            ])
            partner.total_payable = sum(payable_moves.mapped('amount_residual'))

            # Overdue
            overdue_moves = self.env['account.move'].search([
                ('partner_id', '=', partner.id),
                ('move_type', 'in', ('out_invoice', 'in_invoice')),
                ('state', '=', 'posted'),
                ('invoice_date_due', '<', today),
                ('amount_residual', '>', 0),
            ])
            partner.total_overdue = sum(overdue_moves.mapped('amount_residual'))

    def action_view_invoices(self):
        """Open customer invoices for this partner."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Invoices',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [
                ('partner_id', '=', self.id),
                ('move_type', 'in', ('out_invoice', 'out_refund')),
            ],
            'context': {'default_partner_id': self.id, 'default_move_type': 'out_invoice'},
        }

    def action_view_bills(self):
        """Open vendor bills for this partner."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bills',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [
                ('partner_id', '=', self.id),
                ('move_type', 'in', ('in_invoice', 'in_refund')),
            ],
            'context': {'default_partner_id': self.id, 'default_move_type': 'in_invoice'},
        }
