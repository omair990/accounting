# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError


class AccountReportWizard(models.TransientModel):
    """
    Wizard for generating financial reports with date range filtering.
    Used for: General Ledger, Trial Balance, P&L, Balance Sheet.
    """
    _name = 'account.report.wizard'
    _description = 'Financial Report Wizard'

    report_type = fields.Selection([
        ('general_ledger', 'General Ledger'),
        ('trial_balance', 'Trial Balance'),
        ('profit_loss', 'Profit and Loss'),
        ('balance_sheet', 'Balance Sheet'),
        ('aged_receivables', 'Aged Receivables'),
        ('aged_payables', 'Aged Payables'),
    ], string='Report Type', required=True)

    date_from = fields.Date(string='Start Date',
                            default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(string='End Date',
                          default=fields.Date.context_today)
    aged_as_of_date = fields.Date(
        string='As of Date',
        default=fields.Date.context_today,
        help='Aged-balance reports compute days outstanding as of this date.')
    account_ids = fields.Many2many(
        'account.account', string='Accounts',
        help='Leave empty to include all accounts.')
    partner_ids = fields.Many2many(
        'res.partner', string='Partners',
        help='Filter by partner (for GL and receivable/payable reports).')
    journal_ids = fields.Many2many(
        'account.journal', string='Journals',
        help='Filter by journal.')
    target_move = fields.Selection([
        ('posted', 'All Posted Entries'),
        ('all', 'All Entries'),
    ], string='Target Moves', default='posted', required=True)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for wizard in self:
            # Aged reports only use aged_as_of_date; skip the range check.
            if wizard.report_type in ('aged_receivables', 'aged_payables'):
                continue
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise UserError("Start date must be before end date.")

    def action_generate_report(self):
        """Generate the selected financial report."""
        self.ensure_one()
        data = {
            'report_type': self.report_type,
            'date_from': self.date_from,
            'date_to': self.date_to,
            'account_ids': self.account_ids.ids,
            'partner_ids': self.partner_ids.ids,
            'journal_ids': self.journal_ids.ids,
            'target_move': self.target_move,
        }

        data['aged_as_of_date'] = self.aged_as_of_date

        # Aged reports compute their own dataset and pass it through `data`,
        # so the template doesn't need a custom AbstractModel renderer.
        if self.report_type == 'aged_receivables':
            data.update(self._get_aged_data('receivable'))
            data['as_of'] = fields.Date.to_string(data['as_of']) if data.get('as_of') else ''
        elif self.report_type == 'aged_payables':
            data.update(self._get_aged_data('payable'))
            data['as_of'] = fields.Date.to_string(data['as_of']) if data.get('as_of') else ''

        report_map = {
            'general_ledger': 'custom_accounting.action_report_general_ledger',
            'trial_balance': 'custom_accounting.action_report_trial_balance',
            'profit_loss': 'custom_accounting.action_report_profit_loss',
            'balance_sheet': 'custom_accounting.action_report_balance_sheet',
            'aged_receivables': 'custom_accounting.action_report_aged_receivables',
            'aged_payables': 'custom_accounting.action_report_aged_payables',
        }

        report_action = self.env.ref(report_map[self.report_type])
        return report_action.report_action(self, data=data)

    def _get_report_lines(self):
        """
        Core method to fetch report data.
        Returns list of dicts with account-level aggregations.
        """
        self.ensure_one()
        domain = [('move_id.state', '=', 'posted')] if self.target_move == 'posted' else []
        domain += [
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ]
        if self.account_ids:
            domain += [('account_id', 'in', self.account_ids.ids)]
        if self.partner_ids:
            domain += [('partner_id', 'in', self.partner_ids.ids)]
        if self.journal_ids:
            domain += [('journal_id', 'in', self.journal_ids.ids)]

        move_lines = self.env['account.move.line'].search(domain)

        # Group by account
        report_data = {}
        for line in move_lines:
            account = line.account_id
            if account.id not in report_data:
                report_data[account.id] = {
                    'account_code': account.code,
                    'account_name': account.name,
                    'account_type': account.account_type_id.name,
                    'internal_group': account.internal_group,
                    'debit': 0.0,
                    'credit': 0.0,
                    'balance': 0.0,
                    'lines': [],
                }
            report_data[account.id]['debit'] += line.debit
            report_data[account.id]['credit'] += line.credit
            report_data[account.id]['balance'] += (line.debit - line.credit)
            report_data[account.id]['lines'].append({
                'date': line.date,
                'entry_name': line.move_name,
                'partner': line.partner_id.name or '',
                'label': line.name or '',
                'debit': line.debit,
                'credit': line.credit,
                'balance': line.debit - line.credit,
            })

        # Sort by account code
        return sorted(report_data.values(), key=lambda x: x['account_code'])

    def _get_trial_balance_data(self):
        """Get trial balance: debit/credit totals per account."""
        lines = self._get_report_lines()
        total_debit = sum(l['debit'] for l in lines)
        total_credit = sum(l['credit'] for l in lines)
        return {
            'lines': lines,
            'total_debit': total_debit,
            'total_credit': total_credit,
        }

    def _get_profit_loss_data(self):
        """Get P&L: income vs expense accounts."""
        lines = self._get_report_lines()
        income_lines = [l for l in lines if l['internal_group'] == 'income']
        expense_lines = [l for l in lines if l['internal_group'] == 'expense']
        total_income = abs(sum(l['balance'] for l in income_lines))
        total_expense = sum(l['balance'] for l in expense_lines)
        net_profit = total_income - total_expense
        return {
            'income_lines': income_lines,
            'expense_lines': expense_lines,
            'total_income': total_income,
            'total_expense': total_expense,
            'net_profit': net_profit,
        }

    def _get_balance_sheet_data(self):
        """Get Balance Sheet: assets, liabilities, equity."""
        lines = self._get_report_lines()
        assets = [l for l in lines if l['internal_group'] == 'asset']
        liabilities = [l for l in lines if l['internal_group'] == 'liability']
        equity = [l for l in lines if l['internal_group'] == 'equity']
        total_assets = sum(l['balance'] for l in assets)
        total_liabilities = abs(sum(l['balance'] for l in liabilities))
        total_equity = abs(sum(l['balance'] for l in equity))
        return {
            'asset_lines': assets,
            'liability_lines': liabilities,
            'equity_lines': equity,
            'total_assets': total_assets,
            'total_liabilities': total_liabilities,
            'total_equity': total_equity,
        }

    # Aged balance bucket boundaries (days). Edit here to retune.
    AGE_BUCKETS = (
        ('not_due', 'Not Due',     None, 0),
        ('b_0_30',  '0–30',        0,    30),
        ('b_31_60', '31–60',       31,   60),
        ('b_61_90', '61–90',       61,   90),
        ('b_90_p',  '90+',         91,   None),
    )

    def _get_aged_data(self, kind):
        """Aged receivables (kind='receivable') or payables (kind='payable').

        Returns a dict with per-partner aged buckets and overall totals,
        suitable for the QWeb template in reports/report_aged.xml.
        """
        self.ensure_one()
        as_of = self.aged_as_of_date or fields.Date.context_today(self)

        # Customer invoices vs vendor bills.
        if kind == 'receivable':
            move_types = ('out_invoice', 'out_refund')
            sign = 1.0
        else:  # payable
            move_types = ('in_invoice', 'in_refund')
            sign = -1.0  # vendor bills are credit balances

        moves = self.env['account.move'].search([
            ('move_type', 'in', move_types),
            ('state', '=', 'posted'),
            ('payment_state', 'in', ('not_paid', 'partial', 'in_payment')),
            ('invoice_date', '<=', as_of),
        ])

        # Bucket per partner.
        rows = {}
        bucket_codes = [b[0] for b in self.AGE_BUCKETS]
        for mv in moves:
            partner = mv.partner_id
            if not partner:
                continue
            residual = mv.amount_residual_signed * (1 if kind == 'receivable' else -1)
            if mv.move_type in ('out_refund', 'in_refund'):
                residual = -residual
            if abs(residual) < 0.005:
                continue

            due = mv.invoice_date_due or mv.invoice_date
            age_days = (as_of - due).days if due else 0

            bucket = 'b_90_p'
            for code, _label, lo, hi in self.AGE_BUCKETS:
                if code == 'not_due' and age_days < 0:
                    bucket = 'not_due'; break
                if lo is not None and hi is not None and lo <= age_days <= hi:
                    bucket = code; break
                if code == 'b_90_p' and age_days >= 91:
                    bucket = 'b_90_p'; break

            row = rows.setdefault(partner.id, {
                'partner_name': partner.display_name,
                'partner_id': partner.id,
                'total': 0.0,
                **{c: 0.0 for c in bucket_codes},
                'lines': [],
            })
            row[bucket] += residual
            row['total'] += residual
            row['lines'].append({
                'date': mv.invoice_date,
                'due': due,
                'name': mv.name,
                'days': age_days,
                'bucket': bucket,
                'residual': residual,
            })

        rows_list = sorted(rows.values(), key=lambda r: -abs(r['total']))

        totals = {c: sum(r[c] for r in rows_list) for c in bucket_codes}
        totals['total'] = sum(r['total'] for r in rows_list)

        # NOTE: keep this dict JSON-serialisable — it's passed to QWeb via
        # the report's `data` argument. Don't include recordsets here.
        return {
            'kind': kind,
            'as_of': as_of,
            'currency_symbol': (self.env.company.currency_id.symbol or ''),
            'buckets': list(self.AGE_BUCKETS),
            'rows': rows_list,
            'totals': totals,
        }
