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
    ], string='Report Type', required=True)

    date_from = fields.Date(string='Start Date', required=True)
    date_to = fields.Date(string='End Date', required=True,
                          default=fields.Date.context_today)
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
            if wizard.date_from > wizard.date_to:
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

        report_map = {
            'general_ledger': 'custom_accounting.action_report_general_ledger',
            'trial_balance': 'custom_accounting.action_report_trial_balance',
            'profit_loss': 'custom_accounting.action_report_profit_loss',
            'balance_sheet': 'custom_accounting.action_report_balance_sheet',
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
