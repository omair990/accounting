from odoo import SUPERUSER_ID, models
from odoo.exceptions import UserError


class IrModuleModule(models.Model):
    """Restrict module uninstall to system administrators.

    By default Odoo allows any user with `base.group_settings` to manage
    modules, which can lead to accidental uninstalls in shared environments.
    This module narrows that to:

      - SUPERUSER (uid=1, used by CLI / odoo-bin shell)
      - Members of `base.group_system` (Settings → Administration / Settings)
      - Anyone running with the `omran_force_uninstall` context flag,
        which automation scripts can opt into deliberately.

    Anyone else attempting to uninstall sees a clear error explaining why.
    """
    _inherit = 'ir.module.module'

    def _omran_check_uninstall_permission(self):
        if self.env.context.get('omran_force_uninstall'):
            return
        if self.env.uid == SUPERUSER_ID:
            return
        if self.env.user.has_group('base.group_system'):
            return
        raise UserError(
            "You don't have permission to uninstall apps on this instance. "
            "Ask a system administrator (Settings → Users & Companies → "
            "Users with the Administration group)."
        )

    def button_uninstall(self):
        self._omran_check_uninstall_permission()
        return super().button_uninstall()

    def button_immediate_uninstall(self):
        self._omran_check_uninstall_permission()
        return super().button_immediate_uninstall()

    def module_uninstall(self):
        self._omran_check_uninstall_permission()
        return super().module_uninstall()
