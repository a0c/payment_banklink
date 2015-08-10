from openerp import models


class sale_order(models.Model):
    _inherit = "sale.order"

    def force_quotation_send(self, cr, uid, ids, context=None):
        if context.get('no_quotation_send', False):
            return True
        return super(sale_order, self).force_quotation_send(cr, uid, ids, context=context)
