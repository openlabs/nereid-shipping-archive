# This file is part of Nereid.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
"""
Nereid Shipping
"""
from decimal import Decimal

from nereid.globals import request, session
from trytond.model import ModelSQL, ModelView, fields
from trytond.pyson import Eval


class FlatRateShipping(ModelSQL, ModelView):
    "Nereid Flat Rate Shipping"
    _name = "nereid.shipping.method.flat"
    _inherits = {'nereid.shipping': 'shipping'}
    _description = __doc__

    shipping = fields.Many2One('nereid.shipping', 'Shipping', required=True)
    price = fields.Numeric('Price', required=True)

    def default_model(self):
        "Sets self name"
        return self._name

    def get_rate(self, queue, country, **kwargs):
        "Get the rate "
        domain = [
            ('available_countries', '=', country),
            ('website', '=', request.nereid_website.id),
            ]
        if request.is_guest_user:
            domain.append(('is_allowed_for_guest', '=', True))

        rate_id = self.search(domain)
        if not rate_id:
            return None

        rate = self.browse(rate_id[0])
        queue.put({
            'id': rate.id, 
            'name': rate.name, 
            'amount': float(rate.price)
            })
        return

FlatRateShipping()


class FreeShipping(ModelSQL, ModelView):
    "Nereid Free Shipping"
    _name = "nereid.shipping.method.free"
    _inherits = {"nereid.shipping": "shipping"}
    _description = __doc__

    shipping = fields.Many2One('nereid.shipping', 'Shipping', required=True)
    minimum_order_value = fields.Numeric('Minimum Order Value')

    def get_rate(self, queue, country, **kwargs):
        "Free shipping if order value is above a certain limit"
        cart_obj = self.pool.get('nereid.cart')
        domain = [
            ('available_countries', '=', country),
            ('website', '=', request.nereid_website.id),
            ]
        if 'user' not in session:
            domain.append(('is_allowed_for_guest', '=', True))

        rate_id = self.search(domain)
        if not rate_id:
            return

        rate = self.browse(rate_id[0])
        cart = cart_obj.open_cart()
        if cart.sale.total_amount >= rate.minimum_order_value:
            queue.put({
                'id': rate.id,
                'name': rate.name,
                'amount': float(Decimal('0')),
                })
        return

FreeShipping()


class ShippingTable(ModelSQL, ModelView):
    "Nereid Shipping Table"
    _name = 'nereid.shipping.method.table'
    _inherits = {'nereid.shipping': 'shipping'}
    _description = __doc__

    shipping = fields.Many2One('nereid.shipping', 'Shipping', required=True)
    lines = fields.One2Many('shipping.method.table.line', 
            'table', 'Table Lines')
    factor = fields.Selection([
            ('total_price', 'Total Price'),
            #TODO: ('total_weight', 'Total Weight'),
            #TODO: ('total_quantity', 'Total Quantity'),
            ], 'Factor', required=True)

    def default_model(self):
        "Sets Self Name"
        return self._name

    def get_rate(self, queue, zip, subdivision, country, **kwargs):
        """Calculate the price of shipment based on factor, shipment address
            and factor defined in table lines.

        The filter logic might look a bit wierd, the loop basic is below

           >>> p = [0, 1, 2, 3] 
           >>> for i in [None, -1, -2, -3]:
           ...     p[:i] + [-x for x in p[i:] if i]
           ... 
           [0,      1,      2,      3]
           [0,      1,      2,     -3]
           [0,      1,     -2,     -3]
           [0,     -1,     -2,     -3]

        Basically what the loop does is, it mutates the loop starting from
        the end. The domain leaves are falsified in every iteration. So first
        loop will be:
            1: Actual Domain
            2: Actual Domain[0:3] + [('zip', '=', False)]
            3: ''[0:2] + [('subdivision', '=', False), ('zip', '=', False)]
            4: ''[0:1] + [('country', '=', False), ...]
        """
        line_obj = self.pool.get('shipping.method.table.line')
        cart_obj = self.pool.get('nereid.cart')

        domain = [
            ('available_countries', '=', country),
            ('website', '=', request.nereid_website.id),
            ]
        if 'user' not in session:
            domain.append(('is_allowed_for_guest', '=', True))

        table_ids = self.search(domain)
        if not table_ids:
            return

        cart = cart_obj.open_cart()
        compared_value = cart.sale.total_amount

        # compared value under an IF

        domain = [
            ('table', '=', table_ids[0]),       # 0
            ('country', '=', country),          # 1
            ('subdivision', '=', subdivision),              # 2
            ('zip', '=', zip),                  # 3
            ]
        # Try finding lines with max => min match
        # Read the doc string for the logic here
        for index in (None, -1, -2, -3):
            search_domain = domain[:index] + [
                (l[0], '=', False) for l in domain[index:] if index
                ]
            line_ids = line_obj.search(search_domain, order = "factor DESC")
            if line_ids:
                result = self.find_slab(line_ids, compared_value)
                if result: 
                    queue.put(result)
                    break

    def find_slab(self, lines, compared_value):
        """
        Returns the correct amount considering the slab provided
        the other values were matched to certain lines.

        The lines are assumed to be sorted on the basis of decreasing
        factor
        """
        line_obj = self.pool.get('shipping.method.table.line')

        for line in line_obj.browse(lines):
            if compared_value >= line.factor:
                return {
                    'id': line.table.id,
                    'name': line.table.name, 
                    'amount': float(line.price)
                        }

ShippingTable()


class ShippingTableLine(ModelSQL, ModelView):
    "Shipping Table Line"
    _name = 'shipping.method.table.line'
    _description = __doc__

    country = fields.Many2One('country.country', 'Country')
    subdivision = fields.Many2One('country.subdivision', 'Subdivision', 
        domain=[('country', '=', Eval('country'))])
    zip = fields.Char('ZIP')
    factor = fields.Float('Factor', required=True, 
            help="Value (inclusive) and above")
    price = fields.Float('Price', required=True)
    table = fields.Many2One('nereid.shipping.method.table', 'Shipping Table')


ShippingTableLine()
