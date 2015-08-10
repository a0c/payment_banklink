# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2015 AVANSER LLC (<http://avanser.ee>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

{
    'name': 'Banklink Payment Acquirer',
    'author': 'Anton Chepurov @ AVANSER LLC',
    'version': '1.0',
    'category': 'Hidden',
    'summary': 'Payment Acquirer: Banklink Base Implementation',
    'description': """
Banklink
========
Provides a base for implementing Estonian banklinks (*pangalink*) for SEB, Swedbank, Nordea etc.

Working examples can be found in modules payment_seb and payment_swedbank.

Be sure to update the **web.base.url** system parameter in Settings > Parameters > System Parameters to the right HTTPS URL.
""",
    'website': 'www.avanser.ee',
    'depends': ['payment', 'sale'],
    'external_dependencies': {'python': ['M2Crypto', 'humanize']},
    'data': [
        'views/banklink.xml',
        'data/config.xml',
    ],
}
