# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class AccountPartialReconcile(models.Model):
    """
    Partial Reconciliation — links a debit move line to a credit move line.
    Supports partial payments (amount can be less than either line's full amount).
    """
    _name = 'account.partial.reconcile'
    _description = 'Partial Reconciliation'

    debit_move_id = fields.Many2one(
        'account.move.line', string='Debit Move',
        required=True, ondelete='cascade', index=True)
    credit_move_id = fields.Many2one(
        'account.move.line', string='Credit Move',
        required=True, ondelete='cascade', index=True)
    amount = fields.Monetary(
        string='Amount', required=True, currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id)
    date = fields.Date(
        string='Date', default=fields.Date.context_today, required=True)
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company)

    # Exchange difference entry (for multi-currency)
    exchange_move_id = fields.Many2one(
        'account.move', string='Exchange Difference Entry')

    @api.constrains('amount')
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError("Reconciliation amount must be positive.")

    @api.constrains('debit_move_id', 'credit_move_id')
    def _check_same_account(self):
        """Both lines must belong to the same reconcilable account."""
        for rec in self:
            if rec.debit_move_id.account_id != rec.credit_move_id.account_id:
                raise ValidationError(
                    "Cannot reconcile lines from different accounts: '%s' vs '%s'."
                    % (rec.debit_move_id.account_id.name,
                       rec.credit_move_id.account_id.name))
            if not rec.debit_move_id.account_id.reconcile:
                raise ValidationError(
                    "Account '%s' does not allow reconciliation."
                    % rec.debit_move_id.account_id.name)


class AccountMoveLineReconcile(models.Model):
    """Add reconcile method to account.move.line."""
    _inherit = 'account.move.line'

    def reconcile(self):
        """
        Reconcile a set of move lines together.
        Automatically creates partial reconciliation records.
        Handles partial payments gracefully.
        """
        # Separate debit and credit lines
        debit_lines = self.filtered(lambda l: l.debit > 0 and l.amount_residual > 0)
        credit_lines = self.filtered(lambda l: l.credit > 0 and l.amount_residual > 0)

        if not debit_lines or not credit_lines:
            raise UserError(
                "Reconciliation requires at least one debit and one credit line "
                "with remaining residual amounts.")

        # Verify same account
        accounts = self.mapped('account_id')
        if len(accounts) > 1:
            raise UserError("All lines must belong to the same account for reconciliation.")
        if not accounts.reconcile:
            raise UserError("Account '%s' does not allow reconciliation." % accounts.name)

        # Match debit lines against credit lines
        reconcile_model = self.env['account.partial.reconcile']
        for debit_line in debit_lines:
            for credit_line in credit_lines:
                if debit_line.amount_residual <= 0 or credit_line.amount_residual <= 0:
                    continue
                # Determine the amount to reconcile
                amount = min(debit_line.amount_residual, credit_line.amount_residual)
                if amount <= 0:
                    continue
                reconcile_model.create({
                    'debit_move_id': debit_line.id,
                    'credit_move_id': credit_line.id,
                    'amount': amount,
                    'currency_id': debit_line.currency_id.id,
                })
                # Recompute residuals (triggers stored compute)
                (debit_line + credit_line).invalidate_recordset(
                    ['amount_residual', 'reconciled'])

    def unreconcile(self):
        """Remove all reconciliation records for these lines."""
        partials = self.env['account.partial.reconcile'].search([
            '|',
            ('debit_move_id', 'in', self.ids),
            ('credit_move_id', 'in', self.ids),
        ])
        partials.unlink()
