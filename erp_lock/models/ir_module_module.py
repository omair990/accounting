from odoo import SUPERUSER_ID, models
from odoo.exceptions import UserError


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    def _omran_block_uninstall(self):
        # SUPERUSER (shell / CLI) can still do maintenance; UI users are blocked.
        if self.env.uid != SUPERUSER_ID:
            raise UserError("Uninstalling apps is disabled on this ERP instance.")

    def button_uninstall(self):
        self._omran_block_uninstall()
        return super().button_uninstall()

    def button_immediate_uninstall(self):
        self._omran_block_uninstall()
        return super().button_immediate_uninstall()

    def module_uninstall(self):
        self._omran_block_uninstall()
        return super().module_uninstall()
