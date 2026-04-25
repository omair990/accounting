# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError, ValidationError


class TestReconciliation(TransactionCase):
    """Test cases for payment reconciliation."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.type_receivable = cls.env['account.account.type'].create({
            'name': 'Reconcile AR', 'code': 'rec_ar',
            'internal_group': 'asset', 'type': 'receivable',
        })
        cls.type_income = cls.env['account.account.type'].create({
            'name': 'Reconcile Income', 'code': 'rec_income',
            'internal_group': 'income', 'type': 'income',
        })
        cls.type_bank = cls.env['account.account.type'].create({
            'name': 'Reconcile Bank', 'code': 'rec_bank',
            'internal_group': 'asset', 'type': 'bank',
        })
        cls.receivable = cls.env['account.account'].create({
            'code': '7100', 'name': 'Reconcile AR',
            'account_type_id': cls.type_receivable.id,
            'reconcile': True,
        })
        cls.income = cls.env['account.account'].create({
            'code': '7200', 'name': 'Reconcile Income',
            'account_type_id': cls.type_income.id,
        })
        cls.bank = cls.env['account.account'].create({
            'code': '7300', 'name': 'Reconcile Bank',
            'account_type_id': cls.type_bank.id,
        })
        cls.journal = cls.env['account.journal'].create({
            'name': 'Reconcile Journal', 'code': 'REC',
            'type': 'general',
        })
        cls.partner = cls.env['res.partner'].create({
            'name': 'Reconcile Partner',
        })

    def test_full_reconciliation(self):
        """Test reconciling a debit and credit line of equal amounts."""
        # Create invoice-like entry: Debit AR 1000, Credit Income 1000
        move1 = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'partner_id': self.partner.id,
            'line_ids': [
                (0, 0, {'account_id': self.receivable.id, 'debit': 1000, 'credit': 0}),
                (0, 0, {'account_id': self.income.id, 'debit': 0, 'credit': 1000}),
            ],
        })
        move1.action_post()

        # Create payment-like entry: Debit Bank 1000, Credit AR 1000
        move2 = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'partner_id': self.partner.id,
            'line_ids': [
                (0, 0, {'account_id': self.bank.id, 'debit': 1000, 'credit': 0}),
                (0, 0, {'account_id': self.receivable.id, 'debit': 0, 'credit': 1000}),
            ],
        })
        move2.action_post()

        # Get the AR lines and reconcile
        ar_lines = (move1.line_ids + move2.line_ids).filtered(
            lambda l: l.account_id == self.receivable)
        ar_lines.reconcile()

        # Both lines should now be fully reconciled
        for line in ar_lines:
            self.assertTrue(line.reconciled)
            self.assertEqual(line.amount_residual, 0.0)

    def test_partial_reconciliation(self):
        """Test partial reconciliation (payment less than invoice)."""
        # Invoice: Debit AR 1000
        move1 = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'line_ids': [
                (0, 0, {'account_id': self.receivable.id, 'debit': 1000, 'credit': 0}),
                (0, 0, {'account_id': self.income.id, 'debit': 0, 'credit': 1000}),
            ],
        })
        move1.action_post()

        # Payment: Credit AR 600 (partial)
        move2 = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'line_ids': [
                (0, 0, {'account_id': self.bank.id, 'debit': 600, 'credit': 0}),
                (0, 0, {'account_id': self.receivable.id, 'debit': 0, 'credit': 600}),
            ],
        })
        move2.action_post()

        ar_lines = (move1.line_ids + move2.line_ids).filtered(
            lambda l: l.account_id == self.receivable)
        ar_lines.reconcile()

        debit_line = ar_lines.filtered(lambda l: l.debit > 0)
        credit_line = ar_lines.filtered(lambda l: l.credit > 0)

        # Debit line has 400 remaining, credit line is fully reconciled
        self.assertEqual(debit_line.amount_residual, 400.0)
        self.assertFalse(debit_line.reconciled)
        self.assertEqual(credit_line.amount_residual, 0.0)
        self.assertTrue(credit_line.reconciled)

    def test_reconcile_different_accounts_fails(self):
        """Test that reconciling lines from different accounts raises error."""
        move = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'line_ids': [
                (0, 0, {'account_id': self.receivable.id, 'debit': 100, 'credit': 0}),
                (0, 0, {'account_id': self.income.id, 'debit': 0, 'credit': 100}),
            ],
        })
        move.action_post()
        with self.assertRaises(UserError):
            move.line_ids.reconcile()
