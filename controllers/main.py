import logging
import pprint
import werkzeug

from openerp.addons.website_sale.controllers.main import website_sale as website_sale_orig
from openerp.http import request
from openerp import http, SUPERUSER_ID

_logger = logging.getLogger(__name__)


class banklink_controller(http.Controller):

    _return_url = '/payment/banklink/return/'
    _cancel_url = '/payment/banklink/cancel/'

    @http.route('/payment/banklink/return', type='http', auth="none")
    def banklink_return(self, **post):
        if post.get('VK_SERVICE') == '1111' and post.get('VK_AUTO') == 'Y':
            _logger.info('Beginning Banklink form_feedback with post data %s', pprint.pformat(post))
            self.banklink_validate_data(**post)
            # reply to bank's auto response with an empty HTTP 200 response (expected by banks)
            return ''
        return werkzeug.utils.redirect('/shop/payment/validate')

    @http.route('/payment/banklink/cancel', type='http', auth="none")
    def banklink_cancel(self, **post):
        _logger.info('Beginning Banklink cancel with post data %s', pprint.pformat(post))
        if post:
            self.banklink_validate_data(**post)
        return werkzeug.utils.redirect('/shop/payment')

    def banklink_validate_data(self, **post):
        cr, context = request.cr, request.context
        context = dict(context, no_quotation_send=True)
        return request.registry['payment.transaction'].form_feedback(cr, SUPERUSER_ID, post, 'banklink', context=context)


class website_sale(website_sale_orig):

    def _update_tx_acquirer(self, acquirer_id):
        tx = request.website.sale_get_transaction()
        if tx and acquirer_id:
            tx.acquirer_id = acquirer_id

    @http.route()
    def payment_transaction(self, acquirer_id):
        self._update_tx_acquirer(acquirer_id)
        return super(website_sale, self).payment_transaction(acquirer_id)

    def _update_tx_amount(self):
        order = request.website.sale_get_order(context=request.context)
        if order.payment_tx_id:
            order.payment_tx_id.amount = order.amount_total

    @http.route()
    def payment(self, **post):
        self._update_tx_amount()
        return super(website_sale, self).payment(**post)
