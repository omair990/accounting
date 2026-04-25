# -*- coding: utf-8 -*-
"""
REST API Controller for Mobile/External Integration.

These endpoints expose accounting data via JSON for mobile apps,
third-party integrations, or custom dashboards.

Authentication: Uses Odoo session authentication by default.
For token-based auth, consider pairing with the 'auth_api_key' module.

All endpoints return JSON with consistent structure:
{
    "success": true/false,
    "data": {...} or [...],
    "error": "message" (only on failure)
}
"""
import json
from odoo import http
from odoo.http import request, Response


class AccountingApiController(http.Controller):
    """RESTful API for the Custom Accounting module."""

    def _json_response(self, data=None, error=None, status=200):
        """Standardized JSON response."""
        body = {'success': error is None}
        if data is not None:
            body['data'] = data
        if error:
            body['error'] = error
        return Response(
            json.dumps(body, default=str),
            content_type='application/json',
            status=status,
        )

    # === INVOICES ===

    @http.route('/api/v1/invoices', type='http', auth='user', methods=['GET'], csrf=False)
    def get_invoices(self, **kwargs):
        """
        GET /api/v1/invoices
        Query params: state, partner_id, date_from, date_to, limit, offset
        """
        domain = [('move_type', 'in', ('out_invoice', 'out_refund'))]

        if kwargs.get('state'):
            domain.append(('state', '=', kwargs['state']))
        if kwargs.get('partner_id'):
            domain.append(('partner_id', '=', int(kwargs['partner_id'])))
        if kwargs.get('date_from'):
            domain.append(('invoice_date', '>=', kwargs['date_from']))
        if kwargs.get('date_to'):
            domain.append(('invoice_date', '<=', kwargs['date_to']))

        limit = int(kwargs.get('limit', 50))
        offset = int(kwargs.get('offset', 0))

        invoices = request.env['account.move'].search(
            domain, limit=limit, offset=offset, order='invoice_date desc')
        total = request.env['account.move'].search_count(domain)

        data = {
            'total': total,
            'limit': limit,
            'offset': offset,
            'records': [{
                'id': inv.id,
                'name': inv.name,
                'partner': inv.partner_id.name,
                'partner_id': inv.partner_id.id,
                'date': inv.invoice_date,
                'due_date': inv.invoice_date_due,
                'amount_total': inv.amount_total,
                'amount_residual': inv.amount_residual,
                'state': inv.state,
                'payment_state': inv.payment_state,
                'is_overdue': inv.is_overdue,
                'currency': inv.currency_id.name,
            } for inv in invoices],
        }
        return self._json_response(data)

    @http.route('/api/v1/invoices/<int:invoice_id>', type='http', auth='user', methods=['GET'], csrf=False)
    def get_invoice_detail(self, invoice_id, **kwargs):
        """GET /api/v1/invoices/<id> — Full invoice detail with lines."""
        invoice = request.env['account.move'].browse(invoice_id)
        if not invoice.exists():
            return self._json_response(error='Invoice not found', status=404)

        lines = [{
            'id': line.id,
            'account': line.account_id.name,
            'description': line.name,
            'quantity': line.quantity,
            'price_unit': line.price_unit,
            'debit': line.debit,
            'credit': line.credit,
            'taxes': [{'id': t.id, 'name': t.name} for t in line.tax_ids],
        } for line in invoice.line_ids]

        data = {
            'id': invoice.id,
            'name': invoice.name,
            'move_type': invoice.move_type,
            'partner': {'id': invoice.partner_id.id, 'name': invoice.partner_id.name},
            'date': invoice.invoice_date,
            'due_date': invoice.invoice_date_due,
            'amount_untaxed': invoice.amount_untaxed,
            'amount_tax': invoice.amount_tax,
            'amount_total': invoice.amount_total,
            'amount_residual': invoice.amount_residual,
            'state': invoice.state,
            'payment_state': invoice.payment_state,
            'lines': lines,
        }
        return self._json_response(data)

    # === PAYMENTS ===

    @http.route('/api/v1/payments', type='http', auth='user', methods=['GET'], csrf=False)
    def get_payments(self, **kwargs):
        """GET /api/v1/payments — List payments with filters."""
        domain = []
        if kwargs.get('payment_type'):
            domain.append(('payment_type', '=', kwargs['payment_type']))
        if kwargs.get('state'):
            domain.append(('state', '=', kwargs['state']))
        if kwargs.get('partner_id'):
            domain.append(('partner_id', '=', int(kwargs['partner_id'])))

        limit = int(kwargs.get('limit', 50))
        offset = int(kwargs.get('offset', 0))

        payments = request.env['account.payment'].search(
            domain, limit=limit, offset=offset, order='date desc')

        data = {
            'total': request.env['account.payment'].search_count(domain),
            'records': [{
                'id': p.id,
                'name': p.name,
                'payment_type': p.payment_type,
                'partner': p.partner_id.name,
                'amount': p.amount,
                'date': p.date,
                'journal': p.journal_id.name,
                'state': p.state,
                'currency': p.currency_id.name,
            } for p in payments],
        }
        return self._json_response(data)

    @http.route('/api/v1/payments', type='json', auth='user', methods=['POST'], csrf=False)
    def create_payment(self, **kwargs):
        """
        POST /api/v1/payments — Create a new payment.
        Body: {payment_type, partner_id, amount, journal_id, date, memo}
        """
        try:
            vals = {
                'payment_type': kwargs.get('payment_type', 'inbound'),
                'partner_type': kwargs.get('partner_type', 'customer'),
                'partner_id': int(kwargs['partner_id']),
                'amount': float(kwargs['amount']),
                'journal_id': int(kwargs['journal_id']),
                'date': kwargs.get('date'),
                'memo': kwargs.get('memo', ''),
            }
            payment = request.env['account.payment'].create(vals)

            if kwargs.get('auto_post'):
                payment.action_post()

            return {'success': True, 'payment_id': payment.id, 'name': payment.name}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # === DASHBOARD / SUMMARY ===

    @http.route('/api/v1/dashboard', type='http', auth='user', methods=['GET'], csrf=False)
    def get_dashboard(self, **kwargs):
        """GET /api/v1/dashboard — Summary stats for mobile dashboard."""
        Move = request.env['account.move']

        # Outstanding receivables
        receivables = Move.search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', '!=', 'paid'),
        ])
        total_receivable = sum(receivables.mapped('amount_residual'))

        # Outstanding payables
        payables = Move.search([
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('payment_state', '!=', 'paid'),
        ])
        total_payable = sum(payables.mapped('amount_residual'))

        # Overdue
        overdue = Move.search([('is_overdue', '=', True)])
        total_overdue = sum(overdue.mapped('amount_residual'))

        # Draft invoices
        draft_count = Move.search_count([
            ('move_type', 'in', ('out_invoice', 'in_invoice')),
            ('state', '=', 'draft'),
        ])

        data = {
            'total_receivable': total_receivable,
            'total_payable': total_payable,
            'total_overdue': total_overdue,
            'overdue_count': len(overdue),
            'draft_invoices_count': draft_count,
            'receivable_invoices_count': len(receivables),
            'payable_bills_count': len(payables),
        }
        return self._json_response(data)

    # === ACCOUNTS ===

    @http.route('/api/v1/accounts', type='http', auth='user', methods=['GET'], csrf=False)
    def get_accounts(self, **kwargs):
        """GET /api/v1/accounts — Chart of accounts listing."""
        domain = [('deprecated', '=', False)]
        if kwargs.get('group'):
            domain.append(('internal_group', '=', kwargs['group']))

        accounts = request.env['account.account'].search(domain, order='code')
        data = [{
            'id': a.id,
            'code': a.code,
            'name': a.name,
            'type': a.account_type_id.name,
            'group': a.internal_group,
            'balance': a.current_balance,
        } for a in accounts]
        return self._json_response(data)

    # === PARTNERS ===

    @http.route('/api/v1/partners', type='http', auth='user', methods=['GET'], csrf=False)
    def get_partners(self, **kwargs):
        """GET /api/v1/partners — Customers and vendors."""
        domain = []
        if kwargs.get('type') == 'customer':
            domain.append(('customer_rank', '>', 0))
        elif kwargs.get('type') == 'vendor':
            domain.append(('supplier_rank', '>', 0))

        partners = request.env['res.partner'].search(domain, order='name')
        data = [{
            'id': p.id,
            'name': p.name,
            'email': p.email,
            'phone': p.phone,
            'total_receivable': p.total_receivable,
            'total_payable': p.total_payable,
            'total_overdue': p.total_overdue,
        } for p in partners]
        return self._json_response(data)
