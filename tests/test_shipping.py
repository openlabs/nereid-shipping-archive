#!/usr/bin/env python
# -*- coding: UTF-8 -*-
'''
    callisto_shipping.test

    Test the callisto shipping API

    :copyright: (c) 2010-2011 by Openlabs Technologies & Consulting (P) Ltd.
    :license: GPLv3, see LICENSE for more details
'''
import json
from Queue import Queue
from urllib import urlencode

import unittest2 as unittest

from otcltools.openerp import create_database, drop_database
from otcltools.openerp import set_config, Model, Wizard
from otcltools.general import random_string
from callisto import Callisto, request
from callisto.wrappers import Response
from callisto.testing import setup_database, setup_module, setup_website
from callisto.testing import setup_url_map, setup_template, setup_user, get_user


DBNAME = random_string(strength='low')
CONFIG_PATH = 'openerp_serverrc'
EMAIL = 'test@example.com'
PASSWORD = 'test'
MODULE = ['callisto_shipping']


class TestShippingMethod(unittest.TestCase):
    'Test Case for Shipping Method'

    @classmethod
    def setUpClass(cls):
        setup_database(CONFIG_PATH, DBNAME)
        setup_module(MODULE)

        url_map_obj = Model('callisto.url_map')
        country_obj = Model('country.country')

        temp_template_id = setup_template(
            'temp-replacement.jinja', 'Test', 'en_US')
        setup_template(
            'shopping-cart.jinja', 
            'Cart:{{ cart.id }},{{get_cart_size()|round|int}},{{cart.sale.amount_total}}',
            'en_US')
        setup_template(
            'checkout.jinja', 
            '{{get_cart_size()|round|int}},{{form.errors}}',
            'en_US')
        setup_template(
            'login.jinja', 
            '',
            'en_US')
        setup_user('Guest User', 'guest@openlabs.co.in', 'password')
        setup_user('Regd User', 'user@example.com', 'password') 
        countries = country_obj.search_([], limit=10)
        setup_website('Default', url_map_obj.search_([], limit=1)[0], 
            category_template=temp_template_id, 
            product_template=temp_template_id,
            countries=[(6, 0, countries)])

    @classmethod
    def tearDownClass(cls):
        drop_database(DBNAME)

    def setUp(self):
        self.state_obj = Model('country.country.subdivision')
        self.website_obj = Model('callisto.website')
        self.product_obj = Model('product.product')
        self.category_obj = Model('product.category')

        self.application = self.setup_application()

    def setup_application(self):
        guest = get_user('guest@openlabs.co.in')
        return Callisto(DATABASE_NAME=DBNAME, 
            OPENERP_CONFIG=CONFIG_PATH, SITE='Default', 
            OPENERP_USER=1, DEBUG=True, GUEST_USER=guest.id)

    def test_0010_find_gateways(self):
        """No gateways must be returned if not enabled

        When no gateway is enabled then an empty list must be returned
        despite all shipping methods being there
        """
        website, = self.website_obj.find([])
        country = website.countries[0]
        state = self.state_obj.create_({
            'country_id': country.id,
            'name': 'Test State',
            'code': 'TST'
            })
        with self.application.test_client() as c:
            url = '/_available_shipping_methods?' + urlencode({
                'street': '2J Skyline Daffodil',
                'street2': 'Petta, Trippunithura',
                'city': 'Ernakulam',
                'zip': '682013',
                'state': state,
                'country': country.id,
                })
            result = c.get(url)
            self.assertEqual(json.loads(result.data), {u'result': []})

    def test_0020_flat_rate(self):
        """Flat rate shipping method must be available when added.

            If method is not allowed for guest user, he should not get
            that method.
        """
        flat_obj = Model('callisto.shipping.method.flat')
        website, = self.website_obj.find([])
        country = website.countries[0]
        state = self.state_obj.find([('country_id', '=', country.id)])[0]

        flat_rate = flat_obj.create_({
            'name': 'Flat Rate', 
            'available_countries': [(6, 0, [c.id for c in website.countries])], 
            'website': website.id,
            'price': 10.0
            })
        expected_result = {
            'amount': 10.0,
            'id': flat_rate,
            'name': u'Flat Rate'
            }
        #: Check if the get_rate method works
        q = Queue()
        with self.application.test_request_context('/'):
            with self.application.transaction:
                flat_obj.get_rate(q, country.id)
                result = q.get()
                self.assertEqual(result, expected_result)

        with self.application.test_client() as c:   
            # passing an invalid address withw wrong country       
            url = '/_available_shipping_methods?' + urlencode({
                'street': '2J Skyline Daffodil',
                #'street2': 'Petta, Trippunithura',
                #'city': 'Ernakulam',
                'zip': '682013',
                'state': state.id,
                'country': 100,
                })
            result = c.get(url)

            self.assertEqual(
                json.loads(result.data), {u'result': []})
            url = '/_available_shipping_methods?' + urlencode({
                'street': '2J Skyline Daffodil',
                'street2': 'Petta, Trippunithura',
                'city': 'Ernakulam',
                'zip': '682013',
                'state': state.id,
                'country': country.id,
                })
            result = c.get(url)

            self.assertEqual(
                json.loads(result.data), 
                {u'result': [[
                    expected_result['id'], 
                    expected_result['name'], 
                    expected_result['amount']
                    ]]
                })

        flat_obj.write_(flat_rate, {
            'is_allowed_for_guest': False
            })

        with self.application.test_client() as c:   
            url = '/_available_shipping_methods?' + urlencode({
                'street': '2J Skyline Daffodil',
                'street2': 'Petta, Trippunithura',
                'city': 'Ernakulam',
                'zip': '682013',
                'state': state.id,
                'country': country.id,
                })
            result = c.get(url)

            self.assertEqual(
                json.loads(result.data), {u'result': []})

    def test_0030_free_rate(self):
        """Free rate shipping method must be available, if created, 
            on successful satifaction of a condition.
        """
        flat_obj = Model('callisto.shipping.method.flat')
        free_obj = Model('callisto.shipping.method.free')

        flat_rate, = flat_obj.find([])
        website, = self.website_obj.find([])
        free_rate = free_obj.create_({
            'name': 'Free Rate', 
            'available_countries': [(6, 0, [c.id for c in website.countries])], 
            'website': website.id,
            'minimum_order_value': 100,
            })
        country = website.countries[0]
        state = self.state_obj.find([('country_id', '=', country.id)])[0]
        product_id = self.product_obj.create_({
            'name': 'Test Product',
            'categ_id': self.category_obj.search_([])[0],
            'list_price': 50,
            })

        expected_result = [[flat_rate.id, flat_rate.name, flat_rate.price]]

        with self.application.test_client() as c:
            # Create an order of low value
            c.post('/cart/add', data={'product': product_id, 'quantity': 1})

            url = '/_available_shipping_methods?' + urlencode({
                'street': '2J Skyline Daffodil',
                'street2': 'Petta, Trippunithura',
                'city': 'Ernakulam',
                'zip': '682013',
                'state': state.id,
                'country': country.id,
                })
            result = c.get(url)
            # Expected result is [] because the flat rate was made
            # is_allowed_for_guest = False.
            self.assertEqual(
                json.loads(result.data), {u'result': []})

            flat_obj.write_(flat_rate.id, {
                'is_allowed_for_guest': True
                })

            # Update order to have more value
            expected_result.append([free_rate, u'Free Rate', 0.0])
            c.post('/cart/add', data={'product': product_id, 'quantity': 5})
            result = c.get(url)
            self.assertEqual(
                json.loads(result.data), {u'result': expected_result})

    def test_0040_table_rate(self):
        """Table rate method must be available, if created,
            on successful satisfaction of conditions.
        """
        flat_obj = Model('callisto.shipping.method.flat')
        free_obj = Model('callisto.shipping.method.free')
        table_line_obj = Model('shipping.method.table.line')
        table_obj = Model('callisto.shipping.method.table')
        website, = self.website_obj.find([])
        flat_rate, = flat_obj.find([])
        free_rate, = free_obj.find([])
        product = self.product_obj.find([('name', '=', 'Test Product')])[0]

        state = self.state_obj.create_({
                'country_id': int(website.countries[3].id),
                'name': 'Test State 2',
                'code': 'ST2'
                })

        table = table_obj.create_({
            'name': 'Table Rate',
            'available_countries': [(6, 0, [c.id for c in website.countries])], 
            'website': website.id,
            'factor': 'total_price',
            })

        line = table_line_obj.create_({
            'country': int(website.countries[3].id),
            'state': state,
            'zip': '682013',
            'factor': '250',
            'price': 25.0,
            'table': table,
            })

        expected_result = [
            [flat_rate.id, flat_rate.name, flat_rate.price],
            [free_rate.id, free_rate.name, 0.0]]

        with self.application.test_client() as c:
            # Create an order of low value
            c.post('/cart/add', data={'product': product.id, 'quantity': 3})

            url = '/_available_shipping_methods?' + urlencode({
                'street': '2J Skyline Daffodil',
                'street2': 'Petta, Trippunithura',
                'city': 'Ernakulam',
                'zip': '682013',
                'state': state,
                'country': int(website.countries[3].id),
                })
            result = c.get(url)
            self.assertEqual(
                json.loads(result.data), {u'result': expected_result})

            # Add more products to make order high value
            c.post('/cart/add', data={'product': product.id, 'quantity': 7})

            expected_result.append([table, u'Table Rate', 25.0])

            url = '/_available_shipping_methods?' + urlencode({
                'street': '2J Skyline Daffodil',
                'street2': 'Petta, Trippunithura',
                'city': 'Ernakulam',
                'zip': '682013',
                'state': state,
                'country': int(website.countries[3].id),
                })
            result = c.get(url)
            self.assertEqual(
                json.loads(result.data), {u'result': expected_result})

    def test_0050_shipping_w_login(self):
        """Test all the cases for a logged in user.
        """
        flat_obj = Model('callisto.shipping.method.flat')
        free_obj = Model('callisto.shipping.method.free')
        table_obj = Model('callisto.shipping.method.table')
        table_line_obj = Model('shipping.method.table.line')
        address_obj = Model('partner.partner.address')
        website, = self.website_obj.find([])
        flat_rate, = flat_obj.find([])
        free_rate, = free_obj.find([])
        table_rate, = table_obj.find([])
        country = website.countries[0]
        product = self.product_obj.find([('name', '=', 'Test Product')])[0]
        state = self.state_obj.create_({
                'country_id': country.id,
                'name': 'Test State 3',
                'code': 'TS3'
                })

        address = get_user('user@example.com')

        expected_result = [[flat_rate.id, flat_rate.name, flat_rate.price]]

        with self.application.test_client() as c:
            c.post('/login', 
                data={'username': 'user@example.com', 'password': 'password'})

            url = '/_available_shipping_methods?' + urlencode({
                'street': '2J Skyline Daffodil',
                'street2': 'Petta, Trippunithura',
                'city': 'Ernakulam',
                'zip': '682013',
                'state': state,
                'country': country.id,
                })
            result = c.get(url)
            self.assertEqual(json.loads(result.data), {u'result': expected_result})

            address_obj.write_(address.id, {
                'street': 'C/21',
                'street2': 'JSSATEN',
                'city': 'Noida',
                'zip': '112233',
                'state_id': state,
                'country_id': country.id,
                })

            url = '/_available_shipping_methods?' + urlencode({
                'address': address.id,
                })
            result = c.get(url)
            self.assertEqual(json.loads(result.data), {u'result': expected_result})

            expected_result.append([free_rate.id, free_rate.name, 0.0])

            c.post('/cart/add', data={'product': product.id, 'quantity': 3})

            url = '/_available_shipping_methods?' + urlencode({
                'address': address.id,
                })
            result = c.get(url)
            self.assertEqual(json.loads(result.data), {u'result': expected_result})

            # Table rate will fail here as the country being submitted is not in 
            # table lines.

            c.post('/cart/add', data={'product': product.id, 'quantity': 7})

            url = '/_available_shipping_methods?' + urlencode({
                'address': address.id,
                })
            result = c.get(url)
            self.assertEqual(json.loads(result.data), {u'result': expected_result})

            line = table_line_obj.create_({
                'country': country.id,
                'state': state,
                'zip': '112233',
                'factor': '200',
                'price': 20.0,
                'table': table_rate.id,
                })

            expected_result.append([table_rate.id, table_rate.name, 20.0])

            result = c.get(url)
            self.assertEqual(json.loads(result.data), {u'result': expected_result})


test_cases = (TestShippingMethod, )


def load_tests(loader):
    suite = unittest.TestSuite()
    for test_class in test_cases:
        tests = loader.loadTestsFromTestCase(test_class)
        suite.addTests(tests)
    return suite

if __name__ == '__main__':
    from optparse import OptionParser
    parser = OptionParser(usage="%prog [options]")
    parser.add_option("-c", "--config", dest="config",
        help="OpenERP Configuration RC file", default='openerp_serverrc')
    (options, args) = parser.parse_args()
    CONFIG_PATH = options.config
    suite = load_tests(unittest.TestLoader())
    unittest.TextTestRunner(verbosity=2).run(suite)
