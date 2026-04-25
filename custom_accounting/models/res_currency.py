# -*- coding: utf-8 -*-
"""
Currency extensions for the custom accounting module.

Note: Odoo base already provides res.currency and res.currency.rate with full
multi-currency support including conversion. We only extend here if needed.
The base model already handles:
    - rate_ids (One2many to res.currency.rate)
    - _convert() method for currency conversion
    - rounding, decimal_places, etc.

This file is kept as a placeholder for future custom extensions
(e.g., automatic rate fetching from a central bank API).
"""
