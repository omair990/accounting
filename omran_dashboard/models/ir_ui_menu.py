from odoo import models


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    def omran_open(self):
        self.ensure_one()
        action = self.action
        if not action:
            return False
        return action.sudo().read()[0]
