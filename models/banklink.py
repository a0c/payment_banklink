# -*- coding: utf-8 -*-
import base64
from dateutil import parser as DP
from datetime import datetime as DT, timedelta
import logging
import os
from M2Crypto import EVP, X509
import pytz
import time
import urlparse

import humanize

from openerp.exceptions import ValidationError
from openerp.tools import float_compare
from openerp import api, fields, models
from openerp.addons.payment_banklink.controllers.main import banklink_controller


_logger = logging.getLogger(__name__)

CUR_PATH = os.path.dirname(os.path.abspath(__file__))

BANKLINK_DATETIME_FORMAT = '%Y-%m-%dT%H:%M:%S%z'
CUR_TIMEZONE = pytz.timezone(time.tzname[0])
UTC_TIMEZONE = pytz.timezone('UTC')
ALLOWED_TIMEDELTA = timedelta(minutes=5)
LANG = {'en_US': 'ENG', 'et_EE': 'EST', 'ru_RU': 'RUS'}
VK_ORDER = {
    '1012': ['VK_SERVICE', 'VK_VERSION', 'VK_SND_ID', 'VK_STAMP', 'VK_AMOUNT', 'VK_CURR', 'VK_REF', 'VK_MSG',
             'VK_RETURN', 'VK_CANCEL', 'VK_DATETIME'],
    '1111': ['VK_SERVICE', 'VK_VERSION', 'VK_SND_ID', 'VK_REC_ID', 'VK_STAMP', 'VK_T_NO', 'VK_AMOUNT', 'VK_CURR',
             'VK_REC_ACC', 'VK_REC_NAME', 'VK_SND_ACC', 'VK_SND_NAME',  'VK_REF', 'VK_MSG', 'VK_T_DATETIME'],
    '1911': ['VK_SERVICE', 'VK_VERSION', 'VK_SND_ID', 'VK_REC_ID', 'VK_STAMP', 'VK_REF', 'VK_MSG'],
}


def h(obj):
    return humanize.naturaltime(obj)


class BanklinkPaymentAcquirer(models.Model):
    _inherit = 'payment.acquirer'

    def _default_msg(self):
        base_url = self.get_base_url().replace('http://', '').replace('https://', '')
        base_url = base_url and ' (%s)' % base_url or ''
        return u'PANGALINK%s: %%s' % base_url

    bank_id = fields.Char('Bank ID', size=16, readonly=1)
    VK_SND_ID = fields.Char('Merchant ID (VK_SND_ID)', size=16)
    msg_tmpl = fields.Char('Explanation Template', size=255, default=_default_msg)

    def banklink_form_generate_values(self, cr, uid, id, partner_values, tx_values, context=None):
        acquirer = self.browse(cr, uid, id, context=context)
        base_url = acquirer.get_base_url()
        so = self.get_order(tx_values['reference'], acquirer.sudo().env['sale.order'])

        banklink_tx_values = dict(tx_values)
        banklink_tx_values.update({
            'VK_SERVICE': u'1012',
            'VK_VERSION': u'008',
            'VK_SND_ID': u'%s' % acquirer.VK_SND_ID,
            'VK_STAMP': u'%s' % so.id,
            'VK_AMOUNT': u'%s' % tx_values['amount'],
            'VK_CURR': u'EUR',
            'VK_REF': u'%s' % (tx_values['partner'].ref or ''),
            'VK_MSG': self._prepare_msg(acquirer, tx_values, partner_values),
            'VK_RETURN': u'%s' % urlparse.urljoin(base_url, banklink_controller._return_url),
            'VK_CANCEL': u'%s' % urlparse.urljoin(base_url, banklink_controller._cancel_url),
            'VK_DATETIME': self.generate_date(),
            'VK_ENCODING': u'UTF-8',
            'VK_LANG': LANG.get(tx_values['partner'].lang, u'EST'),
            'show_button': not so.payment_tx_id or so.payment_tx_id.state != 'done'
        })
        banklink_tx_values['VK_MAC'] = self.encrypt_MAC_string(banklink_tx_values, acquirer.get_key('%s_get_private_key'))
        return partner_values, banklink_tx_values

    @api.model
    def get_base_url(self):
        return self.sudo().env['ir.config_parameter'].get_param('web.base.url')

    def _prepare_msg(self, acquirer, tx_values, partner_values):
        return acquirer.msg_tmpl % tx_values['reference']

    def get_order(self, order_name, so_obj):
        so = so_obj.search([('name', '=', order_name)], limit=1)
        assert so, 'Could not find Sale Order with name %s' % order_name
        return so[0]

    def get_key(self, key_getter):
        key = self.get_method_value(key_getter)
        return self.full_path(key)

    def get_method_value(self, method_name):
        method_name = method_name % self.provider
        if not hasattr(self, method_name):
            raise NotImplementedError('Method %s() not defined for %s payment acquirer' % (method_name, self.name))
        return getattr(self, method_name)()

    def full_path(self, key):
        return os.path.isabs(key) and str(key) or str(os.path.join(CUR_PATH, '../../payment_%s' % self.provider, key))

    def encrypt_MAC_string(self, tx_values, priv_key):
        priv_key = EVP.load_key(priv_key)
        priv_key.sign_init()
        priv_key.sign_update(self.generate_MAC_string(tx_values))
        mac = priv_key.sign_final()
        return base64.encodestring(mac).replace('\n', '')

    def verify_MAC_string(self, tx_values, signature, cert):
        pub_key = X509.load_cert(cert).get_pubkey()
        pub_key.verify_init()
        pub_key.verify_update(self.generate_MAC_string(tx_values))
        return pub_key.verify_final(base64.decodestring(signature))

    def generate_MAC_string(self, tx_values):
        return ''.join('%03d%s' % (len(tx_values[k]), tx_values[k].encode('utf-8')) for k in VK_ORDER[tx_values['VK_SERVICE']])

    def generate_date(self):
        return DT.now(tz=CUR_TIMEZONE).strftime(BANKLINK_DATETIME_FORMAT)

    def _wrap_payment_block(self, cr, uid, html_block, amount, currency_id, context=None):
        if not html_block.strip():
            return ''
        return super(BanklinkPaymentAcquirer, self)._wrap_payment_block(cr, uid, html_block, amount, currency_id, context=context)


class BanklinkTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _banklink_form_get_tx_from_data(self, cr, uid, data, context=None):
        so_id = data.get('VK_STAMP')
        if not so_id:
            error_msg = 'Banklink: received data with missing reference (%s)' % so_id
            _logger.error(error_msg)
            raise ValidationError(error_msg)

        so = self.pool.get('sale.order').browse(cr, uid, int(so_id), context=context)
        if so.payment_tx_id:
            return so.payment_tx_id

        tx_ids = self.pool['payment.transaction'].search(cr, uid, [('reference', '=', so.name)], context=context)
        if not tx_ids or len(tx_ids) > 1:
            error_msg = 'Banklink: received data for reference %s' % so.name
            if not tx_ids:
                error_msg += '; no order found'
            else:
                error_msg += '; multiple orders found'
            _logger.error(error_msg)
            raise ValidationError(error_msg)
        return self.browse(cr, uid, tx_ids[0], context=context)

    def _banklink_form_get_invalid_parameters(self, cr, uid, tx, data, context=None):
        invalid_parameters = []

        acquirer = tx.acquirer_id
        if data.get('VK_SERVICE') not in ('1111', '1911'):
            invalid_parameters.append(('VK_SERVICE', data.get('VK_SERVICE'), '1111 or 1911'))
        if data.get('VK_VERSION') != '008':
            invalid_parameters.append(('VK_VERSION', data.get('VK_VERSION'), '008'))
        if data.get('VK_SND_ID') != acquirer.bank_id:
            invalid_parameters.append(('VK_SND_ID', data.get('VK_SND_ID'), acquirer.bank_id))
        if data.get('VK_REC_ID') != acquirer.VK_SND_ID:
            invalid_parameters.append(('VK_REC_ID', data.get('VK_REC_ID'), acquirer.VK_SND_ID))
        if int(data.get('VK_STAMP')) != tx.sale_order_id.id:
            invalid_parameters.append(('VK_STAMP', data.get('VK_STAMP'), tx.sale_order_id.id))
        if data.get('VK_SERVICE') == '1111':
            if float_compare(float(data.get('VK_AMOUNT', '0.0')), tx.amount, 2) != 0:
                invalid_parameters.append(('VK_AMOUNT', data.get('VK_AMOUNT'), tx.amount))
            if data.get('VK_CURR') != tx.currency_id.name:
                invalid_parameters.append(('VK_CURR', data.get('VK_CURR'), tx.currency_id.name))
            try:
                tx.parse_date(data.get('VK_T_DATETIME'))
            except ValueError:
                invalid_parameters.append(('VK_T_DATETIME', data.get('VK_T_DATETIME'), '<time in DATETIME format, e.g. 2015-03-13T07:21:14+0200>'))
        tx_values = {k: v for k, v in data.iteritems() if k.startswith('VK_')}
        if not acquirer.verify_MAC_string(tx_values, data.get('VK_MAC'), acquirer.get_key('%s_get_bank_cert')):
            invalid_parameters.append(('VK_MAC', '-smth1-', '-smth2-'))

        return invalid_parameters

    def _banklink_form_validate(self, cr, uid, tx, data, context=None):
        status = data.get('VK_SERVICE')

        if status == '1111':
            d = {
                'acquirer_reference': data.get('VK_T_NO', ''),
                'partner_reference': '%s, %s' % (data.get('VK_SND_NAME', ''), data.get('VK_SND_ACC', '')),
            }
            now = self.now()
            time = self.parse_date(data.get('VK_T_DATETIME'))
            if abs(now - time) < ALLOWED_TIMEDELTA:
                _logger.info('Validated %s payment for tx %s: set as done' % (tx.acquirer_id.name, tx.reference))
                d.update(state='done', date_validate=time)
            else:
                _logger.info('Received late notification for %s payment %s: set as pending' % (tx.acquirer_id.name, tx.reference))
                msg = 'Pending after 1111 request with VK_T_DATETIME=%s' % data.get('VK_T_DATETIME')
                msg += ' - paid %s, while accepted is %s.' % (h(now - time), h(ALLOWED_TIMEDELTA))
                d.update(state='pending', state_message=msg)
            return tx.write(d)
        elif status == '1911':
            _logger.info('%s payment %s failed: set as error' % (tx.acquirer_id.name, tx.reference))
            d = {
                'state_message': data.get('VK_REF', ''),
            }
            d['state_message'] += d['state_message'] and ': %s' % data.get('VK_MSG', '') or data.get('VK_MSG', '')
            d.update(state='error')
            return tx.write(d)
        else:
            error = 'Received unrecognized status for %s payment %s: %s, set as error' % (tx.acquirer_id.name, tx.reference, status)
            _logger.info(error)
            d = dict(state='error', state_message=error)
            return tx.write(d)

    def parse_date(self, date):
        return DP.parse(date).astimezone(tz=UTC_TIMEZONE)

    def now(self):
        return DT.now(tz=CUR_TIMEZONE)
