# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class AccountTax(models.Model):
    """Tax definitions for sales and purchases."""
    _name = 'account.tax'
    _description = 'Tax'
    _order = 'sequence, name'

    name = fields.Char(string='Tax Name', required=True)
    type_tax_use = fields.Selection([
        ('sale', 'Sales'),
        ('purchase', 'Purchases'),
        ('none', 'None'),
    ], string='Tax Scope', required=True, default='sale')
    amount_type = fields.Selection([
        ('percent', 'Percentage'),
        ('fixed', 'Fixed Amount'),
    ], string='Tax Computation', required=True, default='percent')
    amount = fields.Float(
        string='Amount', required=True,
        help='For percentage: enter 15 for 15%. For fixed: enter the fixed amount.')
    sequence = fields.Integer(string='Sequence', default=1)
    active = fields.Boolean(default=True)

    # Accounts for tax postings
    account_id = fields.Many2one(
        'account.account', string='Tax Account (Invoices)',
        help='Account for tax amount on invoices.')
    refund_account_id = fields.Many2one(
        'account.account', string='Tax Account (Credit Notes)',
        help='Account for tax amount on credit notes.')

    # Display
    description = fields.Char(
        string='Label on Invoices',
        help='Short text displayed on invoice lines.')
    price_include = fields.Boolean(
        string='Included in Price', default=False,
        help='If checked, the tax is already included in the unit price.')
    include_base_amount = fields.Boolean(
        string='Affect Base of Subsequent Taxes', default=False)

    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company, required=True)

    @api.constrains('amount', 'amount_type')
    def _check_amount(self):
        for tax in self:
            if tax.amount_type == 'percent' and (tax.amount < 0 or tax.amount > 100):
                raise ValidationError("Percentage tax must be between 0 and 100.")

    def compute_tax(self, base_amount, quantity=1.0):
        """
        Compute tax amount for a given base.
        Returns dict: {'tax_amount': float, 'base': float, 'total': float}
        """
        self.ensure_one()
        if self.amount_type == 'percent':
            if self.price_include:
                # Price includes tax: extract tax from the total
                tax_amount = base_amount - (base_amount / (1 + self.amount / 100))
                base = base_amount - tax_amount
            else:
                tax_amount = base_amount * (self.amount / 100)
                base = base_amount
        else:
            # Fixed amount per unit
            tax_amount = self.amount * quantity
            base = base_amount

        return {
            'tax_id': self.id,
            'tax_name': self.name,
            'base': round(base, 2),
            'tax_amount': round(tax_amount, 2),
            'total': round(base + tax_amount, 2),
        }

    def compute_all(self, base_amount, quantity=1.0):
        """
        Compute all taxes in self (handles tax groups/stacking).
        Returns: {'base': float, 'taxes': [list of tax dicts], 'total_included': float}
        """
        taxes = []
        total_tax = 0.0
        current_base = base_amount
        for tax in self.sorted(key=lambda t: t.sequence):
            result = tax.compute_tax(current_base, quantity)
            taxes.append(result)
            total_tax += result['tax_amount']
            if tax.include_base_amount:
                current_base += result['tax_amount']

        return {
            'base': round(base_amount, 2),
            'taxes': taxes,
            'total_tax': round(total_tax, 2),
            'total_included': round(base_amount + total_tax, 2),
        }
