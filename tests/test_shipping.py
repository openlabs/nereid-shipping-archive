# -*- coding: utf-8 -*-
"""
    test_shipping

    Test Shipping Methods

    :copyright: © 2011 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
import json
from Queue import Queue
from urllib import urlencode
from ast import literal_eval
from decimal import Decimal
import unittest2 as unittest

from trytond.config import CONFIG
CONFIG.options['db_type'] = 'sqlite'
from trytond.modules import register_classes
register_classes()

from nereid.testing import testing_proxy
from trytond.transaction import Transaction


class TestShipping(unittest.TestCase):
    """Test Shipping Methods"""

    @classmethod
    def setUpClass(cls):
        # Install module
        testing_proxy.install_module('nereid_shipping')

        uom_obj = testing_proxy.pool.get('product.uom')
        journal_obj = testing_proxy.pool.get('account.journal')
        country_obj = testing_proxy.pool.get('country.country')

        with Transaction().start(testing_proxy.db_name, 1, None) as txn:
            # Create company
            company = testing_proxy.create_company('Test Company')
            testing_proxy.set_company_for_user(1, company)
            # Create Fiscal Year
            fiscal_year = testing_proxy.create_fiscal_year(company=company)
            # Create Chart of Accounts
            testing_proxy.create_coa_minimal(company)
            # Create payment term
            testing_proxy.create_payment_term()

            cls.guest_user = testing_proxy.create_guest_user()

            category_template = testing_proxy.create_template(
                'category-list.jinja', ' ')
            product_template = testing_proxy.create_template(
                'product-list.jinja', ' ')
            cls.available_countries = country_obj.search([], limit=5)
            cls.site = testing_proxy.create_site('testsite.com', 
                category_template = category_template,
                product_template = product_template,
                countries = [('set', cls.available_countries)])

            testing_proxy.create_template('home.jinja', ' Home ', cls.site)
            testing_proxy.create_template('checkout.jinja', 
                '{{form.errors}}', cls.site)
            testing_proxy.create_template(
                'login.jinja', 
                '{{ login_form.errors }} {{get_flashed_messages()}}', cls.site)
            testing_proxy.create_template('shopping-cart.jinja', 
                'Cart:{{ cart.id }},{{get_cart_size()|round|int}},{{cart.sale.total_amount}}', 
                cls.site)
            product_template = testing_proxy.create_template(
                'product.jinja', ' ', cls.site)
            category_template = testing_proxy.create_template(
                'category.jinja', ' ', cls.site)

            category = testing_proxy.create_product_category(
                'Category', template=category_template, uri='category')
            stock_journal = journal_obj.search([('code', '=', 'STO')])[0]
            cls.product = testing_proxy.create_product(
                'product 1', category,
                type = 'stockable',
                # purchasable = True,
                salable = True,
                list_price = Decimal('10'),
                cost_price = Decimal('5'),
                account_expense = testing_proxy.get_account_by_kind('expense'),
                account_revenue = testing_proxy.get_account_by_kind('revenue'),
                nereid_template = product_template,
                uri = 'product-1',
                sale_uom = uom_obj.search([('name', '=', 'Unit')], limit=1)[0],
                #account_journal_stock_input = stock_journal,
                #account_journal_stock_output = stock_journal,
                )

            txn.cursor.commit()

    def get_app(self, **options):
        options.update({
            'SITE': 'testsite.com',
            'GUEST_USER': self.guest_user,
            })
        return testing_proxy.make_app(**options)

    def setUp(self):
        self.sale_obj = testing_proxy.pool.get('sale.sale')
        self.country_obj = testing_proxy.pool.get('country.country')
        self.address_obj = testing_proxy.pool.get('party.address')
        self.website_obj = testing_proxy.pool.get('nereid.website')
        self.flat_obj = testing_proxy.pool.get('nereid.shipping.method.flat')
        self.free_obj = testing_proxy.pool.get('nereid.shipping.method.free')
        self.table_obj = testing_proxy.pool.get('nereid.shipping.method.table')
        self.table_line_obj = testing_proxy.pool.get('shipping.method.table.line')

    def test_0010_check_cart(self):
        """Assert nothing broke the cart."""
        app = self.get_app()
        with app.test_client() as c:
            rv = c.get('/cart')
            self.assertEqual(rv.status_code, 200)

            c.post('/cart/add', data={
                'product': self.product, 'quantity': 5
                })
            rv = c.get('/cart')
            self.assertEqual(rv.status_code, 200)

        with Transaction().start(testing_proxy.db_name, testing_proxy.user, None):
            sales_ids = self.sale_obj.search([])
            self.assertEqual(len(sales_ids), 1)
            sale = self.sale_obj.browse(sales_ids[0])
            self.assertEqual(len(sale.lines), 1)
            self.assertEqual(sale.lines[0].product.id, self.product)

    def test_0020_find_gateways(self):
        """No gateways must be returned if not enabled

        When no gateway is enabled then an empty list must be returned
        despite all shipping methods being there
        """
        with Transaction().start(testing_proxy.db_name, 
                testing_proxy.user, testing_proxy.context) as txn:

            website_id = self.website_obj.search([])[0]
            website = self.website_obj.browse(website_id)
            country = website.countries[0]
            subdivision = country.subdivisions[0]

            txn.cursor.commit()

        app = self.get_app()
        with app.test_client() as c:
            url = '/_available_shipping_methods?' + urlencode({
                'street': '2J Skyline Daffodil',
                'streetbis': 'Petta, Trippunithura',
                'city': 'Ernakulam',
                'zip': '682013',
                'subdivision': subdivision.id,
                'country': country.id,
                })
            result = c.get(url)
            self.assertEqual(json.loads(result.data), {u'result': []})

    def test_0030_flat_rate(self):
        """Flat rate shipping method must be available when added.

            If method is not allowed for guest user, he should not get
            that method.
        """
        with Transaction().start(testing_proxy.db_name, 
                testing_proxy.user, testing_proxy.context) as txn:
            website_id = self.website_obj.search([])[0]
            website = self.website_obj.browse(website_id)
            country = website.countries[0]
            subdivision = country.subdivisions[0]

            flat_rate = self.flat_obj.create({
                'name': 'Flat Rate', 
                'available_countries': [('add', [c.id for c in website.countries])], 
                'website': website.id,
                'price': Decimal('10.0'),
                })
            expected_result = {
                'amount': 10.0,
                'id': flat_rate,
                'name': u'Flat Rate'
                }

            txn.cursor.commit()

        app = self.get_app()
        with app.test_client() as c:
            # passing an invalid address withw wrong country       
            url = '/_available_shipping_methods?' + urlencode({
                'street': '2J Skyline Daffodil',
                #'streetbis': 'Petta, Trippunithura',
                #'city': 'Ernakulam',
                'zip': '682013',
                'subdivision': subdivision.id,
                'country': 100,
                })
            result = c.get(url)

            self.assertEqual(
                json.loads(result.data), {u'result': []})
            url = '/_available_shipping_methods?' + urlencode({
                'street': '2J Skyline Daffodil',
                'streetbis': 'Petta, Trippunithura',
                'city': 'Ernakulam',
                'zip': '682013',
                'subdivision': subdivision.id,
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
        with Transaction().start(testing_proxy.db_name, 
                testing_proxy.user, testing_proxy.context) as txn:
            self.flat_obj.write(flat_rate, {
                'is_allowed_for_guest': False
                })

            txn.cursor.commit()

        app = self.get_app()
        with app.test_client() as c:
            url = '/_available_shipping_methods?' + urlencode({
                'street': '2J Skyline Daffodil',
                'streetbis': 'Petta, Trippunithura',
                'city': 'Ernakulam',
                'zip': '682013',
                'subdivision': subdivision.id,
                'country': country.id,
                })
            result = c.get(url)

            self.assertEqual(
                json.loads(result.data), {u'result': []})

    def test_0040_free_rate(self):
        """Free rate shipping method must be available, if created, 
            on successful satifaction of a condition.
        """
        with Transaction().start(testing_proxy.db_name, 
                testing_proxy.user, testing_proxy.context) as txn:
            flat_rate_id = self.flat_obj.search([])[0]
            flat_rate = self.flat_obj.browse(flat_rate_id)
            website_id = self.website_obj.search([])[0]
            website = self.website_obj.browse(website_id)
            country = website.countries[0]
            subdivision = country.subdivisions[0]

            free_rate = self.free_obj.create({
                'name': 'Free Rate', 
                'available_countries': [('add', [c.id for c in website.countries])], 
                'website': website_id,
                'minimum_order_value': Decimal('100.0'),
                })

            expected_result = [[flat_rate.id, flat_rate.name, float(flat_rate.price)]]

            txn.cursor.commit()

        app = self.get_app()
        with app.test_client() as c:
            # Create an order of low value
            c.post('/cart/add', data={'product': self.product, 'quantity': 1})

            url = '/_available_shipping_methods?' + urlencode({
                'street': '2J Skyline Daffodil',
                'streetbis': 'Petta, Trippunithura',
                'city': 'Ernakulam',
                'zip': '682013',
                'subdivision': subdivision.id,
                'country': country.id,
                })
            result = c.get(url)
            # Expected result is [] because the flat rate was made
            # is_allowed_for_guest = False.
            self.assertEqual(
                json.loads(result.data), {u'result': []})

        with Transaction().start(testing_proxy.db_name, 
                testing_proxy.user, testing_proxy.context) as txn:

            self.flat_obj.write(flat_rate.id, {
                'is_allowed_for_guest': True
                })

            txn.cursor.commit()

        app = self.get_app()
        with app.test_client() as c:
            # Update order to have more value
            expected_result.append([free_rate, u'Free Rate', 0.0])
            c.post('/cart/add', data={'product': self.product, 'quantity': 50})
            result = c.get(url)
            self.assertEqual(
                json.loads(result.data), {u'result': expected_result})

    def test_0050_table_rate(self):
        """Table rate method must be available, if created,
            on successful satisfaction of conditions.
        """
        with Transaction().start(testing_proxy.db_name, 
                testing_proxy.user, testing_proxy.context) as txn:

            flat_rate_id = self.flat_obj.search([])[0]
            flat_rate = self.flat_obj.browse(flat_rate_id)
            free_rate_id = self.free_obj.search([])[0]
            free_rate = self.free_obj.browse(free_rate_id)

            website_id = self.website_obj.search([])[0]
            website = self.website_obj.browse(website_id)
            country = website.countries[0]
            subdivision = country.subdivisions[0]
            product = self.product

            table = self.table_obj.create({
                'name': 'Table Rate',
                'available_countries': [('add', [c.id for c in website.countries])], 
                'website': website.id,
                'factor': 'total_price',
                })

            line = self.table_line_obj.create({
                'country': int(website.countries[3].id),
                'subdivision': int(website.countries[3].subdivisions[0].id),
                'zip': '682013',
                'factor': 250.0,
                'price': Decimal('25.0'),
                'table': table,
                })

            #: float because the prices are JSON serialised
            expected_result = [
                [flat_rate.id, flat_rate.name, float(flat_rate.price)],
                [free_rate.id, free_rate.name, 0.00]
                ]

            txn.cursor.commit()

        app = self.get_app()
        with app.test_client() as c:
            # Create an order of low value
            c.post('/cart/add', data={'product': product, 'quantity': 3})

            url = '/_available_shipping_methods?' + urlencode({
                'street': '2J Skyline Daffodil',
                'streetbis': 'Petta, Trippunithura',
                'city': 'Ernakulam',
                'zip': '682013',
                'subdivision': subdivision.id,
                'country': int(website.countries[3].id),
                })
            result = c.get(url)
            self.assertEqual(
                json.loads(result.data), {u'result': expected_result})

            # Add more products to make order high value
            c.post('/cart/add', data={'product': product, 'quantity': 7})

            expected_result.append([table, u'Table Rate', 25.0])

            url = '/_available_shipping_methods?' + urlencode({
                'street': '2J Skyline Daffodil',
                'streetbis': 'Petta, Trippunithura',
                'city': 'Ernakulam',
                'zip': '682013',
                'subdivision': subdivision.id,
                'country': int(website.countries[3].id),
                })
            result = c.get(url)
            self.assertEqual(
                json.loads(result.data), {u'result': expected_result})

    def test_0060_shipping_w_login(self):
        """Test all the cases for a logged in user.
        """
        with Transaction().start(testing_proxy.db_name, 
                testing_proxy.user, testing_proxy.context) as txn:
            flat_rate_id = self.flat_obj.search([])[0]
            flat_rate = self.flat_obj.browse(flat_rate_id)
            website_id = self.website_obj.search([])[0]
            website = self.website_obj.browse(website_id)
            country = website.countries[0]
            subdivision = country.subdivisions[0]
            free_rate_id = self.free_obj.search([])[0]
            free_rate = self.free_obj.browse(free_rate_id)
            table_rate_id = self.table_obj.search([])[0]
            table_rate = self.table_obj.browse(table_rate_id)

            regd_user_id = testing_proxy.create_user_party('Registered User', 
                    'email@example.com', 'password')
            address = self.address_obj.browse(regd_user_id)

            expected_result = [
                [flat_rate.id, flat_rate.name, float(flat_rate.price)]
                ]

            txn.cursor.commit()

        app = self.get_app()
        with app.test_client() as c:
            c.post('/login', 
                data={'username': 'email@example.com', 'password': 'password'})
            c.post('/cart/add', data={'product': self.product, 'quantity': 3})
            url = '/_available_shipping_methods?' + urlencode({
                'street': '2J Skyline Daffodil',
                'streetbis': 'Petta, Trippunithura',
                'city': 'Ernakulam',
                'zip': '682013',
                'subdivision': subdivision.id,
                'country': country.id,
                })
            result = c.get(url)
            self.assertEqual(json.loads(result.data), {u'result': expected_result})

        with Transaction().start(testing_proxy.db_name, 
                testing_proxy.user, testing_proxy.context) as txn:
            self.address_obj.write(address.id, {
                'street': 'C/21',
                'streetbis': 'JSSATEN',
                'city': 'Noida',
                'zip': '112233',
                'subdivision': subdivision.id,
                'country': country.id,
                })
            txn.cursor.commit()

        app = self.get_app()
        with app.test_client() as c:
            url = '/_available_shipping_methods?' + urlencode({
                'address': address.id,
                })
            result = c.get(url)
            self.assertEqual(json.loads(result.data), {u'result': expected_result})

            expected_result.append([free_rate.id, free_rate.name, 0.00])

            c.post('/cart/add', data={'product': self.product, 'quantity': 3})

            url = '/_available_shipping_methods?' + urlencode({
                'address': address.id,
                })
            result = c.get(url)
            self.assertEqual(json.loads(result.data), {u'result': expected_result})

            # Table rate will fail here as the country being submitted is not in 
            # table lines.

            c.post('/cart/add', data={'product': self.product, 'quantity': 7})

            url = '/_available_shipping_methods?' + urlencode({
                'address': address.id,
                })
            result = c.get(url)
            self.assertEqual(json.loads(result.data), {u'result': expected_result})

        with Transaction().start(testing_proxy.db_name, 
                testing_proxy.user, testing_proxy.context) as txn:
            line = self.table_line_obj.create({
                'country': country.id,
                'subdivision': subdivision.id,
                'zip': '112233',
                'factor': 200.0,
                'price': Decimal('20.0'),
                'table': table_rate.id,
                })
            txn.cursor.commit()

        app = self.get_app()
        with app.test_client() as c:
            expected_result.append([table_rate.id, table_rate.name, 20.0])

            result = c.get(url)
            self.assertEqual(json.loads(result.data), {u'result': expected_result})


def suite():
    "Checkout test suite"
    suite = unittest.TestSuite()
    suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestShipping)
        )
    return suite


if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
