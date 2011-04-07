# This file is part of Nereid.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

"Nereid Shipping"

from decimal import Decimal
import threading
from Queue import Queue

from trytond.model import ModelView, ModelSQL, fields


class NereidtoShipping(ModelSQL, ModelView):
    "Nereid Shipping"
    _name = "nereid.shipping"
    _description = __doc__

	name = fields.char('Name', required=True, unique=True)
    active = fields.boolean('Active')
    is_allowed_for_guest = fields.boolean('Is allowed for Guest ?')
    available_countries = fields.Many2Many('nereid.shipping-country.country', 
    'shipping', 'country', 'Countries Available')
    website = fields.Many2One('nereid.website', 'Website')


    def default_website(self):
        return 0

    def default_available_countries(self):
        return 0

    def is_allowed_for_guest(self):
        return True

    def get_available_methods(self):
        """Return the JSONified list of shipment gateways available

        This is a XHR only method

        If type is specified as address then an address lookup is done

        The get could be made with the following options:

        1. address
            Checks if user is logged in
            Checks if its a valid address of the user
            extracts to_address from it

        2. Individually specify the following:
            street, street2, city, postal_code, state, country

        The state and country are not expanded into the ISO codes
        or names because doing that may not be required by many methods
        and some methods may requrie codes while others require name.

        So it is better to pass the ID of the same and the get_rate
        method of each decide if they want to expand into CODE or NAME

        """
        address_obj = self.pool.get('partner.partner.address')

        if 'address' in request.args:
            if 'user' not in session:
                abort(403)
            # If not validated as user's address this could lead to 
            # exploitation by ID
            address_id = int(request.args.get('address'))
            if address_id not in [a.id for a in 
                    request.nereid_user.partner_id.address]:
                abort(403)
            address = address_obj.browse_(address_id)
            result = self._get_available_methods(
                street = address.street,
                street2 = address.street2,
                city = address.city,
                zip = address.zip,
                state = address.state_id.id,
                country = address.country_id.id,
                )
        else:
            # Each specified manually
            result = self._get_available_methods(
                street = request.args.get('street'),
                street2 = request.args.get('street2'),
                city = request.args.get('city'),
                zip = request.args.get('zip'),
                state = int(request.args.get('state')),
                country = int(request.args.get('country')),
                )
        return jsonify(
            result = [(g['id'], g['name'], g['amount']) for g in result]
            )

    def _get_available_methods(self, **kwargs):
        """Return the list of tuple of available shipment methods"""
        model_obj = self.pool.get('ir.model')
        shipping_method_models = model_obj.search_(
            [('model', 'ilike', 'nereid.shipping.')])
        # Initialise a Queue and add it to kwargs, this is designed
        # this way so that in future this could be run simultaneously
        # in separate transactions in a multithreaded simultaneous
        # fashion. This may greatly speed up processes
        queue = Queue()
        kwargs['queue'] = queue
        for model in model_obj.browse_(shipping_method_models):
            method_obj = self.pool.get(model.model)
            getattr(method_obj, 'get_rate')(**kwargs)

        # Store the shipping quote in session so that it can be validated
        # without retrying to create quotes.
        session['shipping_quote'] = queue.queue
        return [record for record in queue.queue]

    def add_shipping_line(self, cart, form):
        '''
        Extract the shipping method and rate from the form
        Then create a new line in the sale order with the 
        name of the method and price
        '''
        sale_line_obj = self.pool.get('sale.order.line')
        sale_obj = self.pool.get('sale.order')
        uom_obj = self.pool.get('product.uom')

        shipment_method = self.browse_(form.shimpent_method.id)
        sale_line_obj.create_({
            'name': shipment_method.name,
            'order_id': cart.sale.id,
            'is_shipping_line': True,
            'price_unit': '', # TODO
            'product_uom': uom_obj.search_([('name', '=', 'PCE')]),
            })
        return True

    def get_shipping_options(self):
        '''
        Return shipping options. This is an XHR only method
        and the parameter in the GET request must be structured
        as follows:

            address : If address exists in the dictionary then
            the to_address will be constructed from the 
            partner.partner.address object with id indicated by 
            address

            If address doesnt exist, then the following fields
            are expected

            street, street2, city, postal_code, state, country

            where state and country are IDs which are then 
            transformed into ISO codes to pass to the 
            get_amount_for_method for each available option
        '''
        pass

    def get_amount_for_method(self, method, from_address, to_address):
        '''
        Return the amount for shipping for the method

        This method in turn calls each shipping method's estimate method
        which should call each shipping service and their corresponding
        services and return options in the following format:

        [{<service name>: <rate>}]

        :param method: ID of the shipping method
        :param from_address: Dict of address
            street, street2, city, postal_code, state, country
        :param to_address: ID of the to country
            street, street2, city, postal_code, state, country
        '''
        method = self.browse_(method)
        shipping_obj = self.pool.get(method.model)
        return shipping_obj.estimate(method, from_address, to_address)

    def get_rate(self):
        """Default method, this should be overwritten by each
        method
        """
        return []

NereidtoShipping()


class SaleOrderLine(ModelSQL, Modelview):
    "Sale-OrderLine"

    _name = 'sale.order.line'

    is_shipping_line = fields.boolean('Is Shipping Line?')

SaleOrderLine()


class Website(ModelSQL, Modelview):
    "Website"

    _name = "nereid.website"

        allowed_ship_methods = fields.many2many(
            'nereid_shipping-website',
            'website', 'shipping',
            'Allowed Shipping Methods',
        )

Website()


class IrModel(ModelSQL, Modelview):
    "Irmodel"
    _name = "ir.model"
IrModel()
