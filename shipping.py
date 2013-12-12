# -*- coding: utf-8 -*-
"""
    shipping

    :copyright: (c) 2011-2013 by Openlabs Technologies & Consulting (P) LTD
    :license: GPLv3, see LICENSE for more details.
"""
from Queue import Queue
from decimal import Decimal

from nereid import abort, jsonify
from nereid.globals import request, session, current_app
from trytond.model import ModelView, ModelSQL, fields
from trytond.pool import Pool, PoolMeta

__all__ = [
    'NereidShipping', 'DefaultCheckout', 'WebsiteShipping', 'Website',
    'AvailableCountries', 'SaleLine',
]
__poolmeta__ = PoolMeta


class NereidShipping(ModelSQL, ModelView):
    "Nereid Shipping"
    __name__ = "nereid.shipping"

    name = fields.Char('Name', required=True, translate=True)
    active = fields.Boolean('Active')
    is_allowed_for_guest = fields.Boolean('Is allowed for Guest ?')
    available_countries = fields.Many2Many(
        'nereid.shipping-country.country',
        'shipping', 'country', 'Countries Available'
    )
    website = fields.Many2One('nereid.website', 'Website')

    @staticmethod
    def default_is_allowed_for_guest():
        "Returns True"
        return True

    @staticmethod
    def default_active():
        "Returns True"
        return True

    @classmethod
    def get_available_methods(cls):
        """Return the JSONified list of shipment gateways available

        This is a XHR only method

        If type is specified as address then an address lookup is done

        The get could be made with the following options:

        1. address
            Checks if user is logged in
            Checks if its a valid address of the user
            extracts to_address from it

        2. Individually specify the following:
            street, streetbis, city, postal_code, subdivision, country

        The subdivision and country are not expanded into the ISO codes
        or names because doing that may not be required by many methods
        and some methods may requrie codes while others require name.

        So it is better to pass the ID of the same and the get_rate
        method of each decide if they want to expand into CODE or NAME

        """
        Address = Pool().get('party.address')

        if 'address' in request.args:
            if request.is_guest_user:
                abort(403)
            # If not validated as user's address this could lead to
            # exploitation by ID
            address_id = request.args.get('address', type=int)
            if address_id not in [
                a.id for a in request.nereid_user.party.addresses
            ]:
                abort(403)
            address = Address(address_id)
            result = cls._get_available_methods(
                street=address.street,
                streetbis=address.streetbis,
                city=address.city,
                zip=address.zip,
                subdivision=address.subdivision.id,
                country=address.country.id,
            )
        else:
            # Each specified manually
            result = cls._get_available_methods(
                street=request.args.get('street'),
                streetbis=request.args.get('streetbis'),
                city=request.args.get('city'),
                zip=request.args.get('zip'),
                subdivision=int(request.args.get('subdivision')),
                country=int(request.args.get('country')),
            )
        return jsonify(
            result=[(g['id'], g['name'], g['amount']) for g in result]
        )

    @classmethod
    def _get_available_methods(cls, **kwargs):
        """Return the list of tuple of available shipment methods

        The method calls the get_rate method of each available shipping
        method with the keyword arguments in kwargs and queue. The method can
        use whatever data it wants to use from the kwargs and add a shipping
        option to the queue (using queue.put). The API expects the option
        to be a dictionary of the following format::

            {
                'id': <id of shipping method>,
                'name': <name to display on website>,
                'amount': <estimated amount>
            }
        """
        Model = Pool().get('ir.model')
        shipping_method_models = Model.search(
            [('model', 'ilike', 'nereid.shipping.%')]
        )

        # Initialise a Queue and add it to kwargs, this is designed
        # this way so that in future this could be run simultaneously
        # in separate transactions in a multithreaded simultaneous
        # fashion. This may greatly speed up processes
        queue = Queue()
        kwargs['queue'] = queue

        for model in shipping_method_models:
            Method = Pool().get(model.model)
            getattr(Method, 'get_rate')(**kwargs)

        return [record for record in queue.queue]

    @classmethod
    def add_shipping_line(cls, sale, shipment_method_id):
        '''
        Extract the shipping method and rate from the form
        Then create a new line or overwrite and existing line in the sale order
        with the name of the method and price and is_shipping_line flag set
        '''
        SaleLine = Pool().get('sale.line')

        address = sale.shipment_address
        available_methods = cls._get_available_methods(
            street=address.street,
            streetbis=address.streetbis,
            city=address.city,
            zip=address.zip,
            subdivision=address.subdivision.id,
            country=address.country.id,
        )

        for method in available_methods:
            if method['id'] == shipment_method_id:
                if not method['amount']:
                    current_app.logger.debug(
                        "Shipping amount is %s" % method['amount'])
                    break
                values = {
                    'description': 'Shipping (%s)' % method['name'],
                    'sale': sale.id,
                    'unit_price': Decimal(str(method['amount'])),
                    'quantity': 1,
                    'is_shipping_line': True,
                }
                existing_shipping_lines = SaleLine.search([
                    ('sale', '=', sale.id),
                    ('is_shipping_line', '=', True)
                ])
                if existing_shipping_lines:
                    SaleLine.write(existing_shipping_lines, values)
                else:
                    SaleLine.create([values])
                break
        else:
            current_app.logger.debug(
                'Selected shipment method (%s) not in ' +
                'shipping_quote (%s) in session' %
                (shipment_method_id, session['shipping_quote'])
            )
            abort(403)
        return True

    @classmethod
    def get_rate(cls, **kwargs):
        """Default method, this should be overwritten by each
        method.
        """
        return []


class DefaultCheckout(ModelSQL):
    "Default Checkout Functionality process payment addition"

    __name__ = 'nereid.checkout.default'

    @classmethod
    def _process_shipment(cls, sale, form):
        """Process the payment

        :param sale: Browse Record of Sale Order
        :param form: Instance of validated form
        """
        Shipping = Pool().get("nereid.shipping")
        return Shipping.add_shipping_line(sale, form.shipment_method.data)


class AvailableCountries(ModelSQL, ModelView):
    "Nereid Available Countries"
    __name__ = 'nereid.shipping-country.country'

    country = fields.Many2One(
        'country.country', 'Country',
        ondelete='CASCADE', required=True
    )
    shipping = fields.Many2One(
        'nereid.shipping', 'Shipping',
        ondelete='CASCADE', required=True
    )


class SaleLine(ModelSQL, ModelView):
    "Add Is Shipping Line to Sale Line"
    __name__ = 'sale.line'

    #: A flag field which indicates if the field is representive
    #: of a shipping line
    is_shipping_line = fields.Boolean('Is Shipping Line?', readonly=True)


class Website(ModelSQL, ModelView):
    "Website"
    __name__ = "nereid.website"

    allowed_ship_methods = fields.Many2Many(
        'nereid.website-nereid.shipping',
        'website', 'shipping', 'Allowed Shipping Methods'
    )


class WebsiteShipping(ModelSQL, ModelView):
    "Website Shipping Rel"
    __name__ = 'nereid.website-nereid.shipping'

    website = fields.Many2One(
        'nereid.website', 'website',
        ondelete='CASCADE', required=True
    )
    shipping = fields.Many2One(
        'nereid.shipping', 'shipping',
        ondelete='CASCADE', required=True
    )
