from datetime import date, datetime, time, timedelta

from odoo import api, fields, models


class OmranDashboard(models.TransientModel):
    _name = "omran.dashboard"
    _description = "OCIT ERP Dashboard"

    currency_id = fields.Many2one("res.currency", compute="_compute_stats")

    # Finance
    revenue_month = fields.Monetary(currency_field="currency_id", compute="_compute_stats")
    revenue_today = fields.Monetary(currency_field="currency_id", compute="_compute_stats")
    outstanding_receivable = fields.Monetary(currency_field="currency_id", compute="_compute_stats")
    invoices_draft_count = fields.Integer(compute="_compute_stats")
    invoices_overdue_count = fields.Integer(compute="_compute_stats")

    # Sales / CRM
    sales_open_count = fields.Integer(compute="_compute_stats")
    sales_month_value = fields.Monetary(currency_field="currency_id", compute="_compute_stats")
    pipeline_value = fields.Monetary(currency_field="currency_id", compute="_compute_stats")
    open_opportunities = fields.Integer(compute="_compute_stats")

    # Purchase
    purchase_open_count = fields.Integer(compute="_compute_stats")
    purchase_month_value = fields.Monetary(currency_field="currency_id", compute="_compute_stats")

    # Inventory
    product_count = fields.Integer(compute="_compute_stats")

    # HR
    employee_count = fields.Integer(compute="_compute_stats")
    leaves_pending = fields.Integer(compute="_compute_stats")

    # Projects
    active_projects = fields.Integer(compute="_compute_stats")
    open_tasks = fields.Integer(compute="_compute_stats")

    # Partners
    customer_count = fields.Integer(compute="_compute_stats")
    vendor_count = fields.Integer(compute="_compute_stats")

    # Derived percentages (for progress bars)
    paid_ratio_pct = fields.Float(compute="_compute_stats", string="Paid %")
    cash_in_target_pct = fields.Float(compute="_compute_stats")
    pipeline_conversion_pct = fields.Float(compute="_compute_stats")

    @api.depends_context("uid", "company")
    def _compute_stats(self):
        company = self.env.company
        today = fields.Date.context_today(self)
        month_start = today.replace(day=1)

        # pre-compute shared bits
        AM = self.env["account.move"].sudo()
        SO = self.env["sale.order"].sudo() if "sale.order" in self.env else None
        PO = self.env["purchase.order"].sudo() if "purchase.order" in self.env else None
        Lead = self.env["crm.lead"].sudo() if "crm.lead" in self.env else None
        Prod = self.env["product.product"].sudo()
        Emp = self.env["hr.employee"].sudo() if "hr.employee" in self.env else None
        Leave = self.env["hr.leave"].sudo() if "hr.leave" in self.env else None
        Proj = self.env["project.project"].sudo() if "project.project" in self.env else None
        Task = self.env["project.task"].sudo() if "project.task" in self.env else None
        Partner = self.env["res.partner"].sudo()

        # Revenue month / today — posted customer invoices, amount_total_signed
        rev_domain_common = [
            ("company_id", "=", company.id),
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
        ]
        rev_month = sum(AM.search(rev_domain_common + [("invoice_date", ">=", month_start)]).mapped("amount_total_signed"))
        rev_today = sum(AM.search(rev_domain_common + [("invoice_date", "=", today)]).mapped("amount_total_signed"))

        # Outstanding receivable: open + partial customer invoices
        outstanding = sum(AM.search([
            ("company_id", "=", company.id),
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("payment_state", "in", ("not_paid", "partial", "in_payment")),
        ]).mapped("amount_residual_signed"))

        drafts = AM.search_count([
            ("company_id", "=", company.id),
            ("move_type", "in", ("out_invoice", "in_invoice")),
            ("state", "=", "draft"),
        ])
        overdue = AM.search_count([
            ("company_id", "=", company.id),
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("payment_state", "in", ("not_paid", "partial")),
            ("invoice_date_due", "<", today),
        ])

        so_open = so_val = 0
        if SO is not None:
            so_open = SO.search_count([("company_id", "=", company.id), ("state", "in", ("sale", "done"))])
            so_val = sum(SO.search([
                ("company_id", "=", company.id),
                ("state", "in", ("sale", "done")),
                ("date_order", ">=", month_start),
            ]).mapped("amount_total"))

        pipe_val = lead_open = 0
        if Lead is not None:
            leads = Lead.search([("type", "=", "opportunity"), ("probability", "<", 100), ("active", "=", True), ("company_id", "=", company.id)])
            pipe_val = sum(leads.mapped("expected_revenue"))
            lead_open = len(leads)

        po_open = po_val = 0
        if PO is not None:
            po_open = PO.search_count([("company_id", "=", company.id), ("state", "in", ("purchase", "done"))])
            po_val = sum(PO.search([
                ("company_id", "=", company.id),
                ("state", "in", ("purchase", "done")),
                ("date_order", ">=", datetime.combine(month_start, time.min)),
            ]).mapped("amount_total"))

        prod_count = Prod.search_count([("sale_ok", "=", True)])

        emp_count = leave_pending = 0
        if Emp is not None:
            emp_count = Emp.search_count([("company_id", "=", company.id), ("active", "=", True)])
        if Leave is not None:
            leave_pending = Leave.search_count([("state", "=", "confirm")])

        proj_active = task_open = 0
        if Proj is not None:
            proj_active = Proj.search_count([("company_id", "=", company.id), ("active", "=", True)])
        if Task is not None:
            task_open = Task.search_count([("company_id", "=", company.id), ("stage_id.fold", "=", False)])

        cust_count = Partner.search_count([("customer_rank", ">", 0)])
        vend_count = Partner.search_count([("supplier_rank", ">", 0)])

        # Display the dashboard in Saudi Riyal regardless of company currency
        sar = self.env.ref("base.SAR", raise_if_not_found=False)
        display_currency = sar or company.currency_id
        conversion_rate = 1.0
        if sar and company.currency_id != sar:
            conversion_rate = company.currency_id._convert(
                1.0, sar, company, fields.Date.context_today(self), round=False
            ) if hasattr(company.currency_id, "_convert") else 1.0

        # Derived ratios (clamped 0–100)
        total_invoiced = rev_month + outstanding if (rev_month + outstanding) else 1
        paid_pct = max(0.0, min(100.0, (rev_month / total_invoiced) * 100.0))
        cash_target_pct = max(0.0, min(100.0, (rev_month / 100000.0) * 100.0))  # naive target SAR 100k
        pipe_conv = max(0.0, min(100.0, (so_val / pipe_val * 100.0) if pipe_val else 0.0))

        for rec in self:
            rec.paid_ratio_pct = paid_pct
            rec.cash_in_target_pct = cash_target_pct
            rec.pipeline_conversion_pct = pipe_conv
            rec.currency_id = display_currency.id
            rec.revenue_month = rev_month
            rec.revenue_today = rev_today
            rec.outstanding_receivable = outstanding
            rec.invoices_draft_count = drafts
            rec.invoices_overdue_count = overdue
            rec.sales_open_count = so_open
            rec.sales_month_value = so_val
            rec.pipeline_value = pipe_val
            rec.open_opportunities = lead_open
            rec.purchase_open_count = po_open
            rec.purchase_month_value = po_val
            rec.product_count = prod_count
            rec.employee_count = emp_count
            rec.leaves_pending = leave_pending
            rec.active_projects = proj_active
            rec.open_tasks = task_open
            rec.customer_count = cust_count
            rec.vendor_count = vend_count

    @api.model
    def action_open_dashboard(self):
        rec = self.create({})
        return {
            "type": "ir.actions.act_window",
            "name": "OCIT Dashboard",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": rec.id,
            "target": "current",
            "context": {"create": False, "edit": False, "delete": False},
        }

    # ---- Drill-down actions: each KPI on the dashboard opens a filtered list
    # ----------------------------------------------------------------------
    # Helper: build an act_window result with a domain. Models that aren't
    # installed return False (the calling button will simply do nothing).

    def _act_window(self, name, model, view_mode, domain=None, context=None):
        if model not in self.env:
            return False
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": model,
            "view_mode": view_mode,
            "domain": domain or [],
            "context": context or {},
            "target": "current",
        }

    # Finance ---------------------------------------------------------------
    def action_open_revenue_month(self):
        first = fields.Date.context_today(self).replace(day=1)
        return self._act_window(
            "Revenue this month", "account.move", "list,form",
            domain=[
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("invoice_date", ">=", first),
            ],
        )

    def action_open_outstanding(self):
        return self._act_window(
            "Outstanding receivables", "account.move", "list,form",
            domain=[
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("payment_state", "in", ("not_paid", "partial", "in_payment")),
            ],
        )

    def action_open_overdue_invoices(self):
        today = fields.Date.context_today(self)
        return self._act_window(
            "Overdue invoices", "account.move", "list,form",
            domain=[
                ("move_type", "=", "out_invoice"),
                ("state", "=", "posted"),
                ("payment_state", "in", ("not_paid", "partial")),
                ("invoice_date_due", "<", today),
            ],
        )

    def action_open_draft_invoices(self):
        return self._act_window(
            "Draft invoices and bills", "account.move", "list,form",
            domain=[
                ("move_type", "in", ("out_invoice", "in_invoice")),
                ("state", "=", "draft"),
            ],
        )

    # Sales / CRM -----------------------------------------------------------
    def action_open_open_sales(self):
        return self._act_window(
            "Open sales orders", "sale.order", "list,form",
            domain=[("state", "in", ("sale", "done"))],
        )

    def action_open_pipeline(self):
        return self._act_window(
            "Open opportunities", "crm.lead", "kanban,list,form",
            domain=[
                ("type", "=", "opportunity"),
                ("probability", "<", 100),
                ("active", "=", True),
            ],
        )

    # Purchase --------------------------------------------------------------
    def action_open_open_purchases(self):
        return self._act_window(
            "Open purchase orders", "purchase.order", "list,form",
            domain=[("state", "in", ("purchase", "done"))],
        )

    # Inventory / partners --------------------------------------------------
    def action_open_products(self):
        return self._act_window(
            "Products", "product.product", "kanban,list,form",
            domain=[("sale_ok", "=", True)],
        )

    def action_open_customers(self):
        return self._act_window(
            "Customers", "res.partner", "kanban,list,form",
            domain=[("customer_rank", ">", 0)],
        )

    # HR --------------------------------------------------------------------
    def action_open_employees(self):
        return self._act_window(
            "Active employees", "hr.employee", "kanban,list,form",
            domain=[("active", "=", True)],
        )

    def action_open_pending_leaves(self):
        return self._act_window(
            "Pending leave requests", "hr.leave", "list,form",
            domain=[("state", "=", "confirm")],
        )

    # Project ---------------------------------------------------------------
    def action_open_active_projects(self):
        return self._act_window(
            "Active projects", "project.project", "kanban,list,form",
            domain=[("active", "=", True)],
        )

    def action_open_open_tasks(self):
        return self._act_window(
            "Open tasks", "project.task", "kanban,list,form",
            domain=[("stage_id.fold", "=", False)],
        )
