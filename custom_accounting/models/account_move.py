# -*- coding: utf-8 -*-
import logging
from odoo import models, fields, api, Command
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    """
    Journal Entry — the core accounting document.
    Handles journal entries, customer invoices, vendor bills, and credit notes.
    """
    _name = 'account.move'
    _description = 'Journal Entry'
    _order = 'date desc, name desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _check_company_auto = True

    # === Identity ===
    name = fields.Char(
        string='Number', readonly=True, copy=False, default='/',
        tracking=True, index='trigram')
    ref = fields.Char(string='Reference', copy=False, tracking=True, index='trigram')
    date = fields.Date(
        string='Accounting Date', required=True,
        default=fields.Date.context_today, tracking=True,
        index=True, copy=False)

    # === Type ===
    move_type = fields.Selection([
        ('entry', 'Journal Entry'),
        ('out_invoice', 'Customer Invoice'),
        ('out_refund', 'Customer Credit Note'),
        ('in_invoice', 'Vendor Bill'),
        ('in_refund', 'Vendor Credit Note'),
    ], string='Type', required=True, default='entry', readonly=True,
        tracking=True, index=True,
        change_default=True)

    # === State ===
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True,
        index=True, copy=False)

    # === Relationships ===
    journal_id = fields.Many2one(
        'account.journal', string='Journal', required=True,
        check_company=True, tracking=True,
        domain="[('company_id', '=', company_id)]")
    partner_id = fields.Many2one(
        'res.partner', string='Partner',
        tracking=True, index='btree_not_null',
        change_default=True)
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id,
        required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company, required=True,
        readonly=True, index=True)
    company_currency_id = fields.Many2one(
        related='company_id.currency_id', string='Company Currency',
        readonly=True)
    line_ids = fields.One2many(
        'account.move.line', 'move_id', string='Journal Items',
        copy=True)

    # === Invoice-specific ===
    invoice_date = fields.Date(string='Invoice/Bill Date', copy=False)
    invoice_date_due = fields.Date(
        string='Due Date', tracking=True, copy=False, index=True)
    invoice_origin = fields.Char(
        string='Source Document', tracking=True,
        help='Reference to the document that generated this invoice.')
    invoice_payment_term = fields.Integer(
        string='Payment Term (Days)', default=30,
        help='Number of days for payment.')
    narration = fields.Html(string='Terms & Conditions')

    # === Amounts (Computed) ===
    amount_untaxed = fields.Monetary(
        string='Untaxed Amount', compute='_compute_amounts',
        store=True, currency_field='currency_id', tracking=True)
    amount_tax = fields.Monetary(
        string='Tax', compute='_compute_amounts',
        store=True, currency_field='currency_id')
    amount_total = fields.Monetary(
        string='Total', compute='_compute_amounts',
        store=True, currency_field='currency_id', tracking=True)
    amount_residual = fields.Monetary(
        string='Amount Due', compute='_compute_amount_residual',
        store=True, currency_field='currency_id')
    amount_total_in_currency_signed = fields.Monetary(
        string='Total in Company Currency',
        compute='_compute_amounts', store=True,
        currency_field='company_currency_id')

    # === Payment Status ===
    payment_state = fields.Selection([
        ('not_paid', 'Not Paid'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('reversed', 'Reversed'),
        ('invoicing_legacy', 'Invoicing App Legacy'),
    ], string='Payment Status', compute='_compute_payment_state',
        store=True, tracking=True)

    # === Overdue ===
    is_overdue = fields.Boolean(
        string='Overdue', compute='_compute_is_overdue',
        search='_search_is_overdue', store=False)
    days_overdue = fields.Integer(
        string='Days Overdue', compute='_compute_is_overdue')

    # === Display helpers ===
    is_invoice = fields.Boolean(
        compute='_compute_is_invoice', store=True)
    display_type = fields.Selection(
        related='move_type', string='Display Type')

    # === Counts ===
    payment_count = fields.Integer(
        compute='_compute_payment_count', string='Payment Count')

    @api.depends('move_type')
    def _compute_is_invoice(self):
        for move in self:
            move.is_invoice = move.move_type in (
                'out_invoice', 'out_refund', 'in_invoice', 'in_refund')

    @api.depends('line_ids.debit', 'line_ids.credit', 'line_ids.is_tax_line',
                 'line_ids.amount_currency', 'move_type')
    def _compute_amounts(self):
        for move in self:
            if move.move_type == 'entry':
                move.amount_untaxed = sum(move.line_ids.mapped('debit'))
                move.amount_tax = 0.0
                move.amount_total = move.amount_untaxed
            else:
                product_lines = move.line_ids.filtered(
                    lambda l: not l.is_tax_line and
                    l.account_id.account_type_id.type not in ('receivable', 'payable'))
                tax_lines = move.line_ids.filtered(lambda l: l.is_tax_line)

                if move.move_type in ('out_invoice', 'out_refund'):
                    move.amount_untaxed = sum(product_lines.mapped('credit'))
                    move.amount_tax = sum(tax_lines.mapped('credit'))
                else:
                    move.amount_untaxed = sum(product_lines.mapped('debit'))
                    move.amount_tax = sum(tax_lines.mapped('debit'))

                move.amount_total = move.amount_untaxed + move.amount_tax
            move.amount_total_in_currency_signed = move.amount_total

    @api.depends('line_ids.amount_residual', 'line_ids.account_id.account_type_id.type')
    def _compute_amount_residual(self):
        for move in self:
            if move.move_type in ('out_invoice', 'out_refund', 'in_invoice', 'in_refund'):
                payment_lines = move.line_ids.filtered(
                    lambda l: l.account_id.account_type_id.type in ('receivable', 'payable'))
                move.amount_residual = abs(sum(payment_lines.mapped('amount_residual')))
            else:
                move.amount_residual = 0.0

    @api.depends('amount_residual', 'amount_total', 'state', 'move_type')
    def _compute_payment_state(self):
        for move in self:
            if move.state != 'posted' or not move.is_invoice:
                move.payment_state = 'not_paid'
            elif float_is_zero(move.amount_residual, precision_rounding=move.currency_id.rounding):
                move.payment_state = 'paid'
            elif float_compare(move.amount_residual, move.amount_total,
                               precision_rounding=move.currency_id.rounding) < 0:
                move.payment_state = 'partial'
            else:
                move.payment_state = 'not_paid'

    @api.depends('invoice_date_due', 'amount_residual', 'state')
    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for move in self:
            if (move.state == 'posted' and move.invoice_date_due
                    and move.invoice_date_due < today
                    and not float_is_zero(move.amount_residual,
                                         precision_rounding=move.currency_id.rounding)):
                move.is_overdue = True
                move.days_overdue = (today - move.invoice_date_due).days
            else:
                move.is_overdue = False
                move.days_overdue = 0

    def _search_is_overdue(self, operator, value):
        today = fields.Date.context_today(self)
        if (operator == '=' and value) or (operator == '!=' and not value):
            return [
                ('state', '=', 'posted'),
                ('invoice_date_due', '<', today),
                ('amount_residual', '>', 0),
            ]
        return ['|', ('state', '!=', 'posted'),
                '|', ('invoice_date_due', '>=', today),
                ('amount_residual', '=', 0)]

    def _compute_payment_count(self):
        for move in self:
            reconciled_lines = move.line_ids.filtered(
                lambda l: l.account_id.reconcile and
                (l.matched_debit_ids or l.matched_credit_ids))
            move.payment_count = len(reconciled_lines.mapped(
                'matched_debit_ids.credit_move_id.move_id') |
                reconciled_lines.mapped(
                    'matched_credit_ids.debit_move_id.move_id')) - (1 if reconciled_lines else 0)

    # === Onchange ===

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        """Set default receivable/payable account and payment terms from partner."""
        if self.partner_id:
            if self.move_type in ('out_invoice', 'out_refund'):
                self.invoice_payment_term = self.partner_id.default_payment_days or 30
            elif self.move_type in ('in_invoice', 'in_refund'):
                self.invoice_payment_term = self.partner_id.default_payment_days or 30

    @api.onchange('invoice_date', 'invoice_payment_term')
    def _onchange_invoice_date(self):
        """Auto-compute due date from invoice date + payment terms."""
        if self.invoice_date and self.invoice_payment_term:
            from datetime import timedelta
            self.invoice_date_due = self.invoice_date + timedelta(
                days=self.invoice_payment_term)

    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        """Set currency from journal if specified."""
        if self.journal_id and self.journal_id.currency_id:
            self.currency_id = self.journal_id.currency_id

    # === CRUD ===

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            move_type = vals.get('move_type', 'entry')
            if move_type != 'entry' and not vals.get('invoice_date'):
                vals['invoice_date'] = vals.get('date', fields.Date.context_today(self))
            # Auto-compute due date
            if move_type != 'entry' and vals.get('invoice_date') and not vals.get('invoice_date_due'):
                from datetime import timedelta
                payment_days = vals.get('invoice_payment_term', 30)
                invoice_date = vals['invoice_date']
                if isinstance(invoice_date, str):
                    invoice_date = fields.Date.from_string(invoice_date)
                vals['invoice_date_due'] = invoice_date + timedelta(days=payment_days)
        moves = super().create(vals_list)
        return moves

    def write(self, vals):
        # Prevent editing posted entries (except specific fields)
        if self.filtered(lambda m: m.state == 'posted'):
            allowed_posted_fields = {'narration', 'ref', 'invoice_date_due'}
            if not set(vals.keys()).issubset(allowed_posted_fields | {'state'}):
                for move in self.filtered(lambda m: m.state == 'posted'):
                    if not set(vals.keys()).issubset(allowed_posted_fields | {'state'}):
                        raise UserError(
                            "You cannot modify a posted entry '%s'. "
                            "Reset it to draft first." % move.name)
        return super().write(vals)

    def unlink(self):
        """Prevent deleting posted entries."""
        for move in self:
            if move.state == 'posted':
                raise UserError(
                    "You cannot delete a posted journal entry '%s'. "
                    "You should cancel it first." % move.name)
        return super().unlink()

    # === Actions / Workflow ===

    def action_post(self):
        """Validate and post the journal entry."""
        for move in self:
            if move.state != 'draft':
                raise UserError("Only draft entries can be posted.")
            move._check_lock_date()
            move._validate_move()
            # Generate receivable/payable line for invoices if missing
            if move.is_invoice:
                move._generate_receivable_payable_line()
            # Assign sequence number
            if move.name == '/':
                move.name = move.journal_id._get_next_entry_number()
            move.state = 'posted'
            _logger.info("Posted journal entry %s (ID: %d)", move.name, move.id)
        return True

    def action_cancel(self):
        """Cancel a posted entry."""
        for move in self:
            if move.state == 'cancelled':
                raise UserError("Entry '%s' is already cancelled." % move.name)
            if move.state == 'posted':
                reconciled = move.line_ids.filtered(lambda l: l.reconciled)
                if reconciled:
                    raise UserError(
                        "Cannot cancel '%s' — it has reconciled lines. "
                        "Unreconcile payments first." % move.name)
            move.state = 'cancelled'
            _logger.info("Cancelled journal entry %s (ID: %d)", move.name, move.id)
        return True

    def action_draft(self):
        """Reset cancelled entry to draft."""
        for move in self:
            if move.state != 'cancelled':
                raise UserError("Only cancelled entries can be reset to draft.")
            move.state = 'draft'
        return True

    def action_view_payments(self):
        """Open related payments for this invoice."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Payments',
            'res_model': 'account.payment',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.partner_id.id),
                       ('state', '=', 'posted')],
        }

    # === Validation ===

    def _check_lock_date(self):
        """Check company and journal lock dates."""
        self.ensure_one()
        company = self.company_id
        if company.fiscalyear_lock_date and self.date <= company.fiscalyear_lock_date:
            raise UserError(
                "The fiscal year is locked until %s. You cannot post entries "
                "dated %s." % (company.fiscalyear_lock_date, self.date))
        if company.period_lock_date and self.date <= company.period_lock_date:
            if not self.env.user.has_group('custom_accounting.group_account_manager'):
                raise UserError(
                    "The period is locked until %s for non-managers."
                    % company.period_lock_date)
        if self.journal_id.lock_date and self.date <= self.journal_id.lock_date:
            raise UserError(
                "Journal '%s' is locked until %s."
                % (self.journal_id.name, self.journal_id.lock_date))

    def _validate_move(self):
        """Ensure the journal entry is valid for posting."""
        self.ensure_one()
        if not self.line_ids:
            raise UserError("Cannot post entry with no lines.")

        # Check balanced (debit == credit)
        precision = self.currency_id.rounding or 0.01
        total_debit = sum(self.line_ids.mapped('debit'))
        total_credit = sum(self.line_ids.mapped('credit'))
        if float_compare(total_debit, total_credit, precision_rounding=precision) != 0:
            raise UserError(
                "Entry is not balanced.\n"
                "Total Debit: %.2f\n"
                "Total Credit: %.2f\n"
                "Difference: %.2f"
                % (total_debit, total_credit, abs(total_debit - total_credit)))

        # Check deprecated accounts
        deprecated = self.line_ids.filtered(lambda l: l.account_id.deprecated)
        if deprecated:
            raise UserError(
                "Cannot use deprecated accounts: %s"
                % ', '.join(deprecated.mapped('account_id.display_name')))

        # All lines must have an account
        no_account = self.line_ids.filtered(lambda l: not l.account_id)
        if no_account:
            raise UserError("All journal items must have an account.")

    def _generate_receivable_payable_line(self):
        """
        For invoices: ensure a receivable/payable counterpart line exists
        that balances the entry.
        """
        self.ensure_one()
        existing_rp = self.line_ids.filtered(
            lambda l: l.account_id.account_type_id.type in ('receivable', 'payable'))
        if existing_rp:
            return  # Already has a receivable/payable line

        # Determine the account
        if self.move_type in ('out_invoice', 'out_refund'):
            account = (self.partner_id.property_account_receivable_id or
                       self.company_id.account_default_receivable_id)
            if not account:
                raise UserError(
                    "No receivable account configured for partner '%s' or company."
                    % self.partner_id.name)
        else:
            account = (self.partner_id.property_account_payable_id or
                       self.company_id.account_default_payable_id)
            if not account:
                raise UserError(
                    "No payable account configured for partner '%s' or company."
                    % self.partner_id.name)

        # Calculate total of existing lines
        total_debit = sum(self.line_ids.mapped('debit'))
        total_credit = sum(self.line_ids.mapped('credit'))

        if self.move_type in ('out_invoice', 'out_refund'):
            # Customer invoice: lines are credits (income), counterpart is debit (receivable)
            rp_debit = total_credit - total_debit
            rp_credit = 0.0
        else:
            # Vendor bill: lines are debits (expense), counterpart is credit (payable)
            rp_debit = 0.0
            rp_credit = total_debit - total_credit

        if rp_debit > 0 or rp_credit > 0:
            self.env['account.move.line'].create({
                'move_id': self.id,
                'account_id': account.id,
                'partner_id': self.partner_id.id,
                'name': self.name or '/',
                'debit': rp_debit,
                'credit': rp_credit,
                'date_maturity': self.invoice_date_due,
            })

    # === Helper Methods ===

    def _get_invoice_line_account(self):
        """Get default account for invoice lines based on type."""
        self.ensure_one()
        if self.move_type in ('out_invoice', 'out_refund'):
            return self.journal_id.default_account_id
        elif self.move_type in ('in_invoice', 'in_refund'):
            return self.journal_id.default_account_id
        return False

    def name_get(self):
        result = []
        for move in self:
            name = move.name or '/'
            if move.ref:
                name = '%s (%s)' % (name, move.ref)
            result.append((move.id, name))
        return result

    # === Scheduled Actions ===

    @api.model
    def _cron_check_overdue_invoices(self):
        """
        Scheduled action: find overdue invoices and create activities
        for the responsible accountant to follow up.
        """
        today = fields.Date.context_today(self)
        overdue_invoices = self.search([
            ('move_type', 'in', ('out_invoice', 'in_invoice')),
            ('state', '=', 'posted'),
            ('invoice_date_due', '<', today),
            ('amount_residual', '>', 0),
            ('payment_state', '!=', 'paid'),
        ])
        _logger.info("Cron: found %d overdue invoices", len(overdue_invoices))

        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        for invoice in overdue_invoices:
            # Don't create duplicate activities
            existing = self.env['mail.activity'].search([
                ('res_model', '=', 'account.move'),
                ('res_id', '=', invoice.id),
                ('activity_type_id', '=', activity_type.id if activity_type else False),
                ('summary', 'like', 'Overdue'),
            ], limit=1)
            if not existing and activity_type:
                days_late = (today - invoice.invoice_date_due).days
                invoice.activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary='Overdue: %d days past due (%.2f remaining)'
                            % (days_late, invoice.amount_residual),
                    note='Invoice %s for partner %s is %d days overdue. '
                         'Amount due: %.2f'
                         % (invoice.name, invoice.partner_id.name,
                            days_late, invoice.amount_residual),
                    date_deadline=today,
                )
        return True
