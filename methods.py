# -*- coding: utf-8 -*-
"""
    methods

    Nereid Shipping

    :copyright: (c) 2011-2013 by Openlabs Technologies & Consulting (P) LTD
    :license: GPLv3, see LICENSE for more details.
"""
from nereid.globals import request, session
from trytond.model import ModelSQL, ModelView, fields
from trytond.pyson import Eval
from trytond.pool import Pool, PoolMeta

__all__ = [
    'FlatRateShipping', 'FreeShipping', 'ShippingTable', 'ShippingTableLine',
]
__poolmeta__ = PoolMeta


class FlatRateShipping(ModelSQL, ModelView):
    "Nereid Flat Rate Shipping"
    __name__ = "nereid.shipping.method.flat"

    shipping = fields.Many2One('nereid.shipping', 'Shipping', required=True)
    price = fields.Numeric('Price', required=True)

    @classmethod
    def default_model(cls):
        "Sets self name"
        return cls.__name__

    @classmethod
    def get_rate(cls, queue, country, **kwargs):
        "Get the rate "
        domain = [
            ('shipping.available_countries', '=', country),
            ('shipping.website', '=', request.nereid_website.id),
        ]
        if request.is_guest_user:
            domain.append(('shipping.is_allowed_for_guest', '=', True))

        rates = cls.search(domain)
        if not rates:
            return None

        rate = rates[0]
        queue.put({
            'id': rate.id,
            'name': rate.shipping.name,
            'amount': float(rate.price)
        })
        return


class FreeShipping(ModelSQL, ModelView):
    "Nereid Free Shipping"
    __name__ = "nereid.shipping.method.free"

    shipping = fields.Many2One('nereid.shipping', 'Shipping', required=True)
    minimum_order_value = fields.Numeric('Minimum Order Value')

    @classmethod
    def get_rate(cls, queue, country, **kwargs):
        "Free shipping if order value is above a certain limit"
        Cart = Pool().get('nereid.cart')
        domain = [
            ('shipping.available_countries', '=', country),
            ('shipping.website', '=', request.nereid_website.id),
        ]
        if 'user' not in session:
            domain.append(('shipping.is_allowed_for_guest', '=', True))

        rates = cls.search(domain)
        if not rates:
            return

        rate = rates[0]
        cart = Cart.open_cart()
        if cart.sale.total_amount >= rate.minimum_order_value:
            queue.put({
                'id': rate.id,
                'name': rate.shipping.name,
                'amount': 0.00,
            })
        return


class ShippingTable(ModelSQL, ModelView):
    "Nereid Shipping Table"
    __name__ = 'nereid.shipping.method.table'

    shipping = fields.Many2One('nereid.shipping', 'Shipping', required=True)
    lines = fields.One2Many(
        'shipping.method.table.line', 'table', 'Table Lines')
    factor = fields.Selection([
        ('total_price', 'Total Price'),
        #TODO: ('total_weight', 'Total Weight'),
        #TODO: ('total_quantity', 'Total Quantity'),
    ], 'Factor', required=True)

    @classmethod
    def default_model(cls):
        "Sets Self Name"
        return cls.__name__

    @classmethod
    def get_rate(cls, queue, zip, subdivision, country, **kwargs):
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
        Line = Pool().get('shipping.method.table.line')
        Cart = Pool().get('nereid.cart')

        domain = [
            ('shipping.available_countries', '=', country),
            ('shipping.website', '=', request.nereid_website.id),
        ]
        if 'user' not in session:
            domain.append(('shipping.is_allowed_for_guest', '=', True))

        tables = cls.search(domain)
        if not tables:
            return

        cart = Cart.open_cart()
        compared_value = cart.sale.total_amount

        # compared value under an IF

        domain = [
            ('table', '=', tables[0].id),       # 0
            ('country', '=', country),          # 1
            ('subdivision', '=', subdivision),  # 2
            ('zip', '=', zip),                  # 3
        ]
        # Try finding lines with max => min match
        # Read the doc string for the logic here
        for index in (None, -1, -2, -3):
            search_domain = domain[:index] + [
                (l[0], '=', None) for l in domain[index:] if index
            ]
            lines = Line.search(
                search_domain, order=[('factor', 'DESC')])
            if lines:
                result = cls.find_slab(lines, compared_value)
                if result:
                    queue.put(result)
                    break

    @classmethod
    def find_slab(cls, lines, compared_value):
        """
        Returns the correct amount considering the slab provided
        the other values were matched to certain lines.

        The lines are assumed to be sorted on the basis of decreasing
        factor
        """
        for line in lines:
            if float(compared_value) >= float(line.factor):
                return {
                    'id': line.table.id,
                    'name': line.table.shipping.name,
                    'amount': float(line.price),
                }


class ShippingTableLine(ModelSQL, ModelView):
    "Shipping Table Line"
    __name__ = 'shipping.method.table.line'

    country = fields.Many2One('country.country', 'Country')
    subdivision = fields.Many2One(
        'country.subdivision', 'Subdivision',
        domain=[('country', '=', Eval('country'))],
        depends=['country']
    )
    zip = fields.Char('ZIP')
    factor = fields.Float(
        'Factor', required=True, help="Value (inclusive) and above"
    )
    price = fields.Numeric('Price', required=True)
    table = fields.Many2One('nereid.shipping.method.table', 'Shipping Table')
