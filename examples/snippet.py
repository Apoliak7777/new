# sevlint: odoo=17.0 caller=server_action
"""Recompute delivery dates."""
from datetime import timedelta

for order in records:
    order.commitment_date = datetime.datetime.now() + timedelta(days=2)
    order.write({'note': 'epoch %s' % time.mktime(order.date_order.timetuple())})
raise UserError('Done')
