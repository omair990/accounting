# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class AccountPaymentRegister(models.TransientModel):
    """
    Wizard to register a payment directly from an invoice.
    Handles partial and full payments with auto-reconciliation.
    """
    _name = 'account.payment.register'
    _description = 'Register Payment Wizard'

    # === Source invoice info ===
    invoice_ids = fields.Many2many(
        'account.move', string='Invoices')
    partner_id = fields.Many2one(
        'res.partner', string='Partner', compute='_compute_from_invoices', store=True)
    amount_residual = fields.Monetary(
        string='Amount Due', compute='_compute_from_invoices',
        store=True, currency_field='currency_id')

    # === Payment info ===
    amount = fields.Monetary(
        string='Amount to Pay', currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id)
    payment_type = fields.Selection([
        ('inbound', 'Receive Money'),
        ('outbound', 'Send Money'),
    ], string='Payment Type', compute='_compute_from_invoices', store=True)
    partner_type = fields.Selection([
        ('customer', 'Customer'),
        ('supplier', 'Vendor'),
    ], compute='_compute_from_invoices', store=True)
    journal_id = fields.Many2one(
        'account.journal', string='Journal',
        domain="[('type', 'in', ('bank', 'cash'))]", required=True)
    payment_date = fields.Date(
        string='Payment Date', default=fields.Date.context_today, required=True)
    memo = fields.Char(string='Memo')

    @api.model
    def default_get(self, fields_list):
        """Pre-fill wizard from active invoice(s)."""
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids', [])
        active_model = self.env.context.get('active_model')

        if active_model == 'account.move' and active_ids:
            invoices = self.env['account.move'].browse(active_ids).filtered(
                lambda m: m.state == 'posted' and m.amount_residual > 0)
            if not invoices:
                raise UserError("No posted invoices with outstanding balance selected.")
            res['invoice_ids'] = [(6, 0, invoices.ids)]
            res['amount'] = sum(invoices.mapped('amount_residual'))
        return res

    @api.depends('invoice_ids')
    def _compute_from_invoices(self):
        for wizard in self:
            invoices = wizard.invoice_ids
            if invoices:
                wizard.partner_id = invoices[0].partner_id
                wizard.amount_residual = sum(invoices.mapped('amount_residual'))
                if invoices[0].move_type in ('out_invoice', 'out_refund'):
                    wizard.payment_type = 'inbound'
                    wizard.partner_type = 'customer'
                else:
                    wizard.payment_type = 'outbound'
                    wizard.partner_type = 'supplier'
            else:
                wizard.partner_id = False
                wizard.amount_residual = 0
                wizard.payment_type = 'inbound'
                wizard.partner_type = 'customer'

    def action_create_payment(self):
        """Create and post the payment, then reconcile with invoices."""
        self.ensure_one()

        if self.amount <= 0:
            raise UserError("Payment amount must be greater than zero.")
        if self.amount > self.amount_residual:
            raise UserError(
                "Payment amount (%.2f) exceeds the amount due (%.2f)."
                % (self.amount, self.amount_residual))

        # Create payment
        payment = self.env['account.payment'].create({
            'payment_type': self.payment_type,
            'partner_type': self.partner_type,
            'partner_id': self.partner_id.id,
            'amount': self.amount,
            'currency_id': self.currency_id.id,
            'date': self.payment_date,
            'journal_id': self.journal_id.id,
            'memo': self.memo or ', '.join(self.invoice_ids.mapped('name')),
        })

        # Post and reconcile
        payment.action_register_payment_for_invoices(self.invoice_ids.ids)

        # Return action to view the payment
        return {
            'type': 'ir.actions.act_window',
            'name': 'Payment',
            'res_model': 'account.payment',
            'res_id': payment.id,
            'view_mode': 'form',
            'target': 'current',
        }
