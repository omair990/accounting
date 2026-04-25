# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError


class TestAccountPayment(TransactionCase):
    """Test cases for payment processing."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Account types
        cls.type_bank = cls.env['account.account.type'].create({
            'name': 'Test Bank', 'code': 'test_bank',
            'internal_group': 'asset', 'type': 'bank',
        })
        cls.type_receivable = cls.env['account.account.type'].create({
            'name': 'Test AR', 'code': 'test_ar',
            'internal_group': 'asset', 'type': 'receivable',
        })
        # Accounts
        cls.bank_account = cls.env['account.account'].create({
            'code': '8100', 'name': 'Test Bank',
            'account_type_id': cls.type_bank.id,
        })
        cls.receivable_account = cls.env['account.account'].create({
            'code': '8200', 'name': 'Test AR',
            'account_type_id': cls.type_receivable.id,
            'reconcile': True,
        })
        # Journal
        cls.bank_journal = cls.env['account.journal'].create({
            'name': 'Test Bank Journal', 'code': 'TBK',
            'type': 'bank',
            'default_account_id': cls.bank_account.id,
        })
        # Partner
        cls.customer = cls.env['res.partner'].create({
            'name': 'Test Payment Customer',
            'property_account_receivable_id': cls.receivable_account.id,
        })

    def test_create_payment(self):
        """Test basic payment creation."""
        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.customer.id,
            'amount': 500.0,
            'journal_id': self.bank_journal.id,
        })
        self.assertEqual(payment.state, 'draft')
        self.assertEqual(payment.amount, 500.0)

    def test_post_payment_creates_journal_entry(self):
        """Test that posting a payment creates a balanced journal entry."""
        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.customer.id,
            'amount': 1000.0,
            'journal_id': self.bank_journal.id,
        })
        payment.action_post()
        self.assertEqual(payment.state, 'posted')
        self.assertTrue(payment.move_id)
        self.assertEqual(payment.move_id.state, 'posted')
        # Verify balanced
        total_debit = sum(payment.move_id.line_ids.mapped('debit'))
        total_credit = sum(payment.move_id.line_ids.mapped('credit'))
        self.assertEqual(total_debit, total_credit)

    def test_zero_amount_payment_fails(self):
        """Test that zero or negative payment is rejected."""
        with self.assertRaises(ValidationError):
            self.env['account.payment'].create({
                'payment_type': 'inbound',
                'partner_type': 'customer',
                'partner_id': self.customer.id,
                'amount': 0.0,
                'journal_id': self.bank_journal.id,
            })

    def test_cancel_payment(self):
        """Test cancelling a posted payment."""
        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.customer.id,
            'amount': 250.0,
            'journal_id': self.bank_journal.id,
        })
        payment.action_post()
        payment.action_cancel()
        self.assertEqual(payment.state, 'cancelled')
