# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError


class TestAccountMove(TransactionCase):
    """Test cases for journal entries and invoices."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create test account type
        cls.account_type_income = cls.env['account.account.type'].create({
            'name': 'Test Income',
            'code': 'test_income',
            'internal_group': 'income',
            'type': 'income',
        })
        cls.account_type_receivable = cls.env['account.account.type'].create({
            'name': 'Test Receivable',
            'code': 'test_receivable',
            'internal_group': 'asset',
            'type': 'receivable',
        })
        # Create test accounts
        cls.account_revenue = cls.env['account.account'].create({
            'code': '9001',
            'name': 'Test Revenue',
            'account_type_id': cls.account_type_income.id,
        })
        cls.account_receivable = cls.env['account.account'].create({
            'code': '9100',
            'name': 'Test Receivable',
            'account_type_id': cls.account_type_receivable.id,
            'reconcile': True,
        })
        # Create test journal
        cls.journal = cls.env['account.journal'].create({
            'name': 'Test Sales',
            'code': 'TST',
            'type': 'sale',
            'default_account_id': cls.account_revenue.id,
        })
        # Create test partner
        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Customer',
            'property_account_receivable_id': cls.account_receivable.id,
        })

    def test_create_journal_entry(self):
        """Test creating a balanced journal entry."""
        move = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'line_ids': [
                (0, 0, {
                    'account_id': self.account_receivable.id,
                    'debit': 1000.0,
                    'credit': 0.0,
                    'name': 'Test debit',
                }),
                (0, 0, {
                    'account_id': self.account_revenue.id,
                    'debit': 0.0,
                    'credit': 1000.0,
                    'name': 'Test credit',
                }),
            ],
        })
        self.assertEqual(move.state, 'draft')
        self.assertEqual(len(move.line_ids), 2)

    def test_post_balanced_entry(self):
        """Test posting a balanced entry succeeds."""
        move = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'line_ids': [
                (0, 0, {
                    'account_id': self.account_receivable.id,
                    'debit': 500.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'account_id': self.account_revenue.id,
                    'debit': 0.0,
                    'credit': 500.0,
                }),
            ],
        })
        move.action_post()
        self.assertEqual(move.state, 'posted')
        self.assertNotEqual(move.name, '/')

    def test_post_unbalanced_entry_fails(self):
        """Test that unbalanced entry cannot be posted."""
        move = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'line_ids': [
                (0, 0, {
                    'account_id': self.account_receivable.id,
                    'debit': 1000.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'account_id': self.account_revenue.id,
                    'debit': 0.0,
                    'credit': 800.0,
                }),
            ],
        })
        with self.assertRaises(UserError):
            move.action_post()

    def test_post_empty_entry_fails(self):
        """Test that entry with no lines cannot be posted."""
        move = self.env['account.move'].create({
            'journal_id': self.journal.id,
        })
        with self.assertRaises(UserError):
            move.action_post()

    def test_cancel_posted_entry(self):
        """Test cancelling a posted entry."""
        move = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'line_ids': [
                (0, 0, {
                    'account_id': self.account_receivable.id,
                    'debit': 200.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'account_id': self.account_revenue.id,
                    'debit': 0.0,
                    'credit': 200.0,
                }),
            ],
        })
        move.action_post()
        move.action_cancel()
        self.assertEqual(move.state, 'cancelled')

    def test_debit_credit_both_nonzero_fails(self):
        """Test that a line cannot have both debit and credit."""
        with self.assertRaises(ValidationError):
            self.env['account.move'].create({
                'journal_id': self.journal.id,
                'line_ids': [
                    (0, 0, {
                        'account_id': self.account_receivable.id,
                        'debit': 100.0,
                        'credit': 100.0,
                    }),
                ],
            })

    def test_account_code_validation(self):
        """Test that account code must be numeric and >= 4 digits."""
        with self.assertRaises(ValidationError):
            self.env['account.account'].create({
                'code': 'ABC',
                'name': 'Bad Account',
                'account_type_id': self.account_type_income.id,
            })
        with self.assertRaises(ValidationError):
            self.env['account.account'].create({
                'code': '123',
                'name': 'Short Code',
                'account_type_id': self.account_type_income.id,
            })
