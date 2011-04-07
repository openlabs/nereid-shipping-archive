# This file is part of Nereid.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
"""
Nereid Shipping
"""
from trytond.model import ModelView, ModelSQL, fields
from trytond.transaction import Transaction

class FlatRateShipping(ModelSQL, Modelview):
    "Nereid Flat Rate Shipping"
    _name = "nereid.shipping.method.flat"
    _inherits = {"nereid.shipping": "shipping"}
    _description = __doc__

     shipping = fields.Many2One('nereid.shipping', 'Shipping', required=True),
     price = fields.float('Price')

    def default_shipping(self):
        return 0

    def default_price(self):
        return 0

    def get_rate(self, queue, country, **kwargs):
        "Get the rate "
        domain = [
            ('available_countries', '=', country),
            ('website', '=', request.nereid_website.id),
            ]
        if 'user' not in session:
            domain.append(('is_allowed_for_guest', '=', True))

        rate_id = self.search_(domain)
        if not rate_id:
            return
        rate = self.browse_(rate_id[0])
        queue.put({
            'id': rate.id, 
            'name': rate.name, 
            'amount': rate.price
            })
        return

FlatRateShipping()


class FreeShipping(ModelSqQL, Modelview):
    "Nereid Free Shipping"
    _name = "nereid.shipping.method.free"
    _inherits = {"nereid.shipping": "shipping"}
    _description = __doc__

     shipping = fields.Many2One('nereid.shipping', 'Shipping', required=True)
     minimum_order_value = fields.float('Minimum Order Value')

    def default_shipping=(self)
            return 0

    def default_minimum_order_value=(self)
            return 0

    def get_rate(self, queue, country, **kwargs):
        "Free shipping if order value is above a certain limit"
        cart_obj = self.pool.get('nereid.cart')
        domain = [
            ('available_countries', '=', country),
            ('website', '=', request.nereid_website.id),
            ]
        if 'user' not in session:
            domain.append(('is_allowed_for_guest', '=', True))

        rate_id = self.search_(domain)
        if not rate_id:
            return
        rate = self.browse_(rate_id[0])
        cart = cart_obj.open_cart()
        if cart.sale.amount_total >= rate.minimum_order_value:
            queue.put({
                'id': rate.id, 
                'name': rate.name, 
                'amount': 0.00,
                })
        return

FreeShipping()


class ShippingTable(ModelSQL, Modelview):
    "Nereid Shipping Table"
    _name = 'nereid.shipping.method.table'
    _inherits = {"nereid.shipping": "shipping"}
    _description = __doc__

    shipping = fields.Many2One('nereid.shipping', 'Shipping', required=True)
    lines = fields.One2Many('shipping.method.table.line', 'table', 'Table Lines')
    factor = fields.selection([
            ('total_price', 'Total Price'),
            #TODO: Implement later
            #('total_weight', 'Total Weight'),
            #('total_quantity', 'Total Quantity'),
            ], 'Factor', required=True)

    def default_shipping(self)
            return 0

    def default_lines(self)
            return 0

    def get_rate(self, queue, zip, state, country, **kwargs):
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
            3: ''[0:2] + [('state', '=', False), ('zip', '=', False)]
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

        table_ids = self.search_(domain)
        if not table_ids: return 

        table = self.browse_(table_ids[0])
        cart = cart_obj.open_cart()
        compared_value = cart.sale.amount_total
        # TODO: Build the logic for other factors here and put 
        # compared value under an IF

        domain = [
            ('table', '=', table_ids[0]),       # 0
            ('country', '=', country),          # 1
            ('state', '=', state),              # 2
            ('zip', '=', zip),                  # 3
            ]
        # Try finding lines with max => min match
        # Read the doc string for the logic here
        for index in (None, -1, -2, -3):
            search_domain = domain[:index] + [
                (l[0], '=', False) for l in domain[index:] if index
                ]
            line_ids = line_obj.search_(search_domain, order = "factor DESC")
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

        for line in line_obj.browse_(lines):
            if compared_value >= line.factor:
                return {
                    'id': line.table.id,
                    'name': line.table.name, 
                    'amount': line.price
                        }

ShippingTable()


class ShippingTableLine(ModelSQL, Modelview):
    "Shipping Table Line"
    _name = 'shipping.method.table.line'
    _description = __doc__

    country = fields.Many2One('country.country', 'Country')
    state = fields.Many2One('country.country.state', 'State', 
        domain="[('country_id','=',country)]")
    zip = fields.char('ZIP', size=10)
    factor = fields.float('Factor', required=True, help="Value (inclusive) and above"
    )
    price = fields.float('Price', required=True)
    table = fields.many2one('nereid.shipping.method.table', 'Shipping Table')


    def __init__(self):
        super(ShippingTable,self).__init__()
        self._sql_constraints= [
            ('combination_uniq', 'unique (country, state, zip, factor, table)', 
            'Error! Redundant entries not possible.')
    ]

ShippingTableLine()
