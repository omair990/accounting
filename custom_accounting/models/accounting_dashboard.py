"""Accounting dashboard — 4-card layout (Sales / Purchases / Bank / Tax Returns).

Replicates the visual structure of Odoo Enterprise's accounting home, using
only Community-available data sources. No Enterprise code or assets.
"""
from odoo import api, fields, models


class AccountingDashboard(models.TransientModel):
    _name = "accounting.dashboard"
    _description = "Accounting Dashboard"

    # ---- Sales card (receivables aging) -------------------------------------
    receivable_due = fields.Monetary(
        currency_field="currency_id", compute="_compute_data",
        help="Customer invoices that are already past their due date.")
    receivable_w1 = fields.Monetary(currency_field="currency_id", compute="_compute_data")
    receivable_w2 = fields.Monetary(currency_field="currency_id", compute="_compute_data")
    receivable_w3 = fields.Monetary(currency_field="currency_id", compute="_compute_data")
    receivable_w4 = fields.Monetary(currency_field="currency_id", compute="_compute_data")
    receivable_not_due = fields.Monetary(currency_field="currency_id", compute="_compute_data")
    # Bar percentages (0-100) for visual proportions in the chart.
    bar_pct_due = fields.Float(compute="_compute_data")
    bar_pct_w1 = fields.Float(compute="_compute_data")
    bar_pct_w2 = fields.Float(compute="_compute_data")
    bar_pct_w3 = fields.Float(compute="_compute_data")
    bar_pct_w4 = fields.Float(compute="_compute_data")
    bar_pct_not_due = fields.Float(compute="_compute_data")
    # Human labels for the 4 weekly buckets (e.g., "27 Apr - 3 May").
    label_w1 = fields.Char(compute="_compute_data")
    label_w2 = fields.Char(compute="_compute_data")
    label_w3 = fields.Char(compute="_compute_data")
    label_w4 = fields.Char(compute="_compute_data")

    # ---- Purchases card -----------------------------------------------------
    bills_draft_count = fields.Integer(compute="_compute_data")

    # ---- Bank card ----------------------------------------------------------
    bank_journal_count = fields.Integer(compute="_compute_data")

    # ---- Tax Returns checklist ----------------------------------------------
    company_data_set = fields.Boolean(compute="_compute_data")
    periods_set = fields.Boolean(compute="_compute_data")
    coa_reviewed = fields.Boolean(compute="_compute_data")

    currency_id = fields.Many2one("res.currency", compute="_compute_data")

    @api.depends_context("uid", "company")
    def _compute_data(self):
        company = self.env.company
        today = fields.Date.context_today(self)
        Move = self.env["account.move"].sudo()

        # Receivables: posted out_invoices not fully paid.
        invs = Move.search([
            ("company_id", "=", company.id),
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("payment_state", "in", ("not_paid", "partial", "in_payment")),
        ])
        due_now = w1 = w2 = w3 = w4 = not_due = 0.0
        for inv in invs:
            res = inv.amount_residual_signed
            if abs(res) < 0.005:
                continue
            due = inv.invoice_date_due or inv.invoice_date or today
            delta = (due - today).days
            if delta < 0:
                due_now += res
            elif delta <= 7:
                w1 += res
            elif delta <= 14:
                w2 += res
            elif delta <= 21:
                w3 += res
            elif delta <= 28:
                w4 += res
            else:
                not_due += res

        amounts = (due_now, w1, w2, w3, w4, not_due)
        peak = max((abs(a) for a in amounts), default=0) or 1.0
        pct = lambda a: round((abs(a) / peak) * 100.0, 1)

        bills = Move.search_count([
            ("company_id", "=", company.id),
            ("move_type", "=", "in_invoice"),
            ("state", "=", "draft"),
        ])
        bank_count = self.env["account.journal"].search_count([
            ("type", "=", "bank"),
            ("company_id", "=", company.id),
        ])
        coa_count = self.env["account.account"].search_count([
            ("company_id", "=", company.id),
        ])
        # Treat fiscal lock date as a "periods configured" signal in Community.
        periods = bool(getattr(company, "fiscalyear_lock_date", False)) or \
            bool(getattr(company, "tax_lock_date", False))

        # Human labels for the 4 weekly buckets, e.g. "27 Apr - 3 May".
        from datetime import timedelta
        def fmt(start, end):
            return f"{start.strftime('%-d %b')} - {end.strftime('%-d %b')}"
        w1_start = today + timedelta(days=1)
        w1_end = today + timedelta(days=7)
        w2_start = today + timedelta(days=8)
        w2_end = today + timedelta(days=14)
        w3_start = today + timedelta(days=15)
        w3_end = today + timedelta(days=21)
        w4_start = today + timedelta(days=22)
        w4_end = today + timedelta(days=28)

        for r in self:
            r.currency_id = company.currency_id.id
            r.receivable_due = due_now
            r.receivable_w1 = w1
            r.receivable_w2 = w2
            r.receivable_w3 = w3
            r.receivable_w4 = w4
            r.receivable_not_due = not_due
            r.bar_pct_due = pct(due_now)
            r.bar_pct_w1 = pct(w1)
            r.bar_pct_w2 = pct(w2)
            r.bar_pct_w3 = pct(w3)
            r.bar_pct_w4 = pct(w4)
            r.bar_pct_not_due = pct(not_due)
            r.label_w1 = fmt(w1_start, w1_end)
            r.label_w2 = fmt(w2_start, w2_end)
            r.label_w3 = fmt(w3_start, w3_end)
            r.label_w4 = fmt(w4_start, w4_end)
            r.bills_draft_count = bills
            r.bank_journal_count = bank_count
            r.company_data_set = bool(company.name and company.email)
            r.periods_set = periods
            r.coa_reviewed = coa_count > 5

    # ---- Open the dashboard -------------------------------------------------
    @api.model
    def action_open_accounting_dashboard(self):
        rec = self.create({})
        return {
            "type": "ir.actions.act_window",
            "name": "Accounting Dashboard",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": rec.id,
            "target": "current",
            "context": {"create": False, "edit": False, "delete": False},
        }

    # ---- Drill-downs --------------------------------------------------------
    def _act(self, name, model, view_mode, domain=None, context=None):
        return {
            "type": "ir.actions.act_window",
            "name": name, "res_model": model,
            "view_mode": view_mode,
            "domain": domain or [],
            "context": context or {},
            "target": "current",
        }

    def action_open_invoices_due(self):
        today = fields.Date.context_today(self)
        return self._act("Overdue invoices", "account.move", "list,form", domain=[
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("payment_state", "in", ("not_paid", "partial", "in_payment")),
            ("invoice_date_due", "<", today),
        ])

    def action_open_invoices_open(self):
        return self._act("Open invoices", "account.move", "list,form", domain=[
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("payment_state", "in", ("not_paid", "partial", "in_payment")),
        ])

    def action_open_bills_draft(self):
        return self._act("Draft bills", "account.move", "list,form", domain=[
            ("move_type", "=", "in_invoice"),
            ("state", "=", "draft"),
        ])

    def action_open_bank_journals(self):
        return self._act(
            "Bank journals", "account.journal", "list,form",
            domain=[("type", "=", "bank")],
        )

    def action_open_chart_of_accounts(self):
        return self._act("Chart of accounts", "account.account", "list,form")

    def action_create_invoice(self):
        return self._act("New invoice", "account.move", "form",
            context={"default_move_type": "out_invoice"})

    def action_create_bill(self):
        return self._act("New bill", "account.move", "form",
            context={"default_move_type": "in_invoice"})

    def action_open_review_queue(self):
        """Same target as the Review menu — invoices/bills awaiting validation."""
        return self._act("Review queue", "account.move", "list,form", domain=[
            ("state", "=", "draft"),
            ("move_type", "in", ("out_invoice", "in_invoice")),
        ])

    def action_open_company_settings(self):
        return self._act("Company settings", "res.company", "form",
            domain=[("id", "=", self.env.company.id)])
