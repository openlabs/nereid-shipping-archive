# -*- coding: utf-8 -*-
"""
    test_shipping

    Test Shipping Methods

    :copyright: © 2011-2013 by Openlabs Technologies & Consulting (P) Limited
    :license: GPLv3, see LICENSE for more details.
"""
import os
import sys
import json
from decimal import Decimal
from urllib import urlencode

DIR = os.path.abspath(os.path.normpath(os.path.join(
    __file__, '..', '..', '..', '..', '..', 'trytond')))
if os.path.isdir(DIR):
    sys.path.insert(0, os.path.dirname(DIR))

import unittest
import pycountry
from mock import patch
import trytond.tests.test_tryton
from trytond.tests.test_tryton import POOL, DB_NAME, USER, CONTEXT
from trytond.config import CONFIG
CONFIG['smtp_from'] = "testing@openlabs.co.in"

from trytond.transaction import Transaction

from nereid.testing import NereidTestCase


class TestShipping(NereidTestCase):
    """Test Shipping Methods"""

    def setUp(self):
        trytond.tests.test_tryton.install_module('nereid_shipping')
        self.Currency = POOL.get('currency.currency')
        self.Company = POOL.get('company.company')
        self.Website = POOL.get('nereid.website')
        self.UrlMap = POOL.get('nereid.url_map')
        self.Language = POOL.get('ir.lang')
        self.NereidUser = POOL.get('nereid.user')
        self.Party = POOL.get('party.party')
        self.Locale = POOL.get('nereid.website.locale')
        self.User = POOL.get('res.user')

        self.Sale = POOL.get('sale.sale')
        self.Country = POOL.get('country.country')
        self.Address = POOL.get('party.address')
        self.PriceList = POOL.get('product.price_list')
        self.Shipping = POOL.get('nereid.shipping')
        self.Flat = POOL.get('nereid.shipping.method.flat')
        self.Free = POOL.get('nereid.shipping.method.free')
        self.Table = POOL.get('nereid.shipping.method.table')
        self.TableLine = POOL.get('shipping.method.table.line')
        self.IRProperty = POOL.get('ir.property')
        self.IRField = POOL.get('ir.model.field')
        self.Location = POOL.get('stock.location')
        self.Subdivision = POOL.get('country.subdivision')
        self.Uom = POOL.get('product.uom')

        self.templates = {
            'home.jinja': ' Home ',
            'checkout.jinja': '{{ form.errors }}',
            'login.jinja':
                '{{ login_form.errors }}'
                '{{get_flashed_messages()}}',
            'shopping-cart.jinja':
                'Cart:{{ cart.id }},{{get_cart_size()|round|int}}'
                ',{{cart.sale.total_amount}}',
            'emails/sale-confirmation-text.jinja': ' ',
            'emails/sale-confirmation-html.jinja': ' ',
        }

        # Patch SMTP Lib
        self.smtplib_patcher = patch('smtplib.SMTP')
        self.PatchedSMTP = self.smtplib_patcher.start()

    def tearDown(self):
        # Unpatch SMTP Lib
        self.smtplib_patcher.stop()

    def _create_product_category(self, name, vlist):
        """
        Creates a product category

        Name is mandatory while other value may be provided as keyword
        arguments

        :param name: Name of the product category
        :param vlist: List of dictionaries of values to create
        """
        Category = POOL.get('product.category')

        for values in vlist:
            values['name'] = name
        return Category.create(vlist)

    def _create_product_template(self, name, vlist, uri, uom=u'Unit'):
        """
        Create a product template with products and return its ID

        :param name: Name of the product
        :param vlist: List of dictionaries of values to create
        :param uri: uri of product template
        :param uom: Note it is the name of UOM (not symbol or code)
        """
        ProductTemplate = POOL.get('product.template')
        Uom = POOL.get('product.uom')

        for values in vlist:
            values['name'] = name
            values['default_uom'], = Uom.search([('name', '=', uom)], limit=1)
            values['sale_uom'], = Uom.search([('name', '=', uom)], limit=1)
            values['products'] = [
                ('create', [{
                    'uri': uri,
                    'displayed_on_eshop': True
                }])
            ]
        return ProductTemplate.create(vlist)

    def _create_coa_minimal(self, company):
        """Create a minimal chart of accounts
        """
        AccountTemplate = POOL.get('account.account.template')
        Account = POOL.get('account.account')

        account_create_chart = POOL.get(
            'account.create_chart', type="wizard")

        account_template, = AccountTemplate.search(
            [('parent', '=', None)]
        )

        session_id, _, _ = account_create_chart.create()
        create_chart = account_create_chart(session_id)
        create_chart.account.account_template = account_template
        create_chart.account.company = company
        create_chart.transition_create_account()

        receivable, = Account.search([
            ('kind', '=', 'receivable'),
            ('company', '=', company),
        ])
        payable, = Account.search([
            ('kind', '=', 'payable'),
            ('company', '=', company),
        ])
        create_chart.properties.company = company
        create_chart.properties.account_receivable = receivable
        create_chart.properties.account_payable = payable
        create_chart.transition_create_properties()

    def _get_account_by_kind(self, kind, company=None, silent=True):
        """Returns an account with given spec

        :param kind: receivable/payable/expense/revenue
        :param silent: dont raise error if account is not found
        """
        Account = POOL.get('account.account')
        Company = POOL.get('company.company')

        if company is None:
            company, = Company.search([], limit=1)

        accounts = Account.search([
            ('kind', '=', kind),
            ('company', '=', company)
        ], limit=1)
        if not accounts and not silent:
            raise Exception("Account not found")
        return accounts[0] if accounts else False

    def _create_payment_term(self):
        """Create a simple payment term with all advance
        """
        PaymentTerm = POOL.get('account.invoice.payment_term')

        return PaymentTerm.create([{
            'name': 'Direct',
            'lines': [('create', [{'type': 'remainder'}])]
        }])

    def _create_countries(self, count=5):
        """
        Create some sample countries and subdivisions
        """
        for country in list(pycountry.countries)[0:count]:
            countries = self.Country.create([{
                'name': country.name,
                'code': country.alpha2,
            }])
            try:
                divisions = pycountry.subdivisions.get(
                    country_code=country.alpha2
                )
            except KeyError:
                pass
            else:
                for subdivision in list(divisions)[0:count]:
                    self.Subdivision.create([{
                        'country': countries[0].id,
                        'name': subdivision.name,
                        'code': subdivision.code,
                        'type': subdivision.type.lower(),
                    }])

    def _create_pricelists(self):
        """
        Create the pricelists
        """
        # Setup the pricelists
        self.party_pl_margin = Decimal('1.10')
        self.guest_pl_margin = Decimal('1.00')
        user_price_list, = self.PriceList.create([{
            'name': 'PL 1',
            'company': self.company.id,
            'lines': [
                ('create', [{
                    'formula': 'unit_price * %s' % self.party_pl_margin
                }])
            ],
        }])
        guest_price_list, = self.PriceList.create([{
            'name': 'PL 2',
            'company': self.company.id,
            'lines': [
                ('create', [{
                    'formula': 'unit_price * %s' % self.guest_pl_margin
                }])
            ],
        }])
        return guest_price_list.id, user_price_list.id

    def _create_shipping(self, name):
        '''
        Create shipping

        :params name: Name string

        :returns: active record of shipping
        '''
        return self.Shipping.create([{
            'name': name,
            'available_countries': [
                ('add', [c.id for c in self.website.countries])
            ],
            'website': self.website.id,
        }])[0]

    def setup_defaults(self):
        currency, = self.Currency.create([{
            'name': 'US Dollar',
            'code': 'USD',
            'symbol': '$',
        }])
        with Transaction().set_context(company=None):
            company_party, = self.Party.create([{
                'name': 'openlabs'
            }])

        self.company, = self.Company.create([{
            'party': company_party,
            'currency': currency,
        }])

        AdminUser = self.User(USER)
        AdminUser.company = self.company
        AdminUser.main_company = self.company
        AdminUser.save()

        # Create Chart of Accounts
        self._create_coa_minimal(self.company)

        # Create payment terms
        self._create_payment_term()

        guest_price_list, user_price_list = self._create_pricelists()

        self._create_countries()
        self.available_countries = self.Country.search([], limit=5)

        self.category, = self._create_product_category(
            'Category', [{'uri': 'category'}]
        )

        guest_party, = self.Party.create([{
            'name': 'Non registered user',
            'sale_price_list': guest_price_list,
        }])
        guest_user, = self.NereidUser.create([{
            'party': guest_party,
            'display_name': 'Guest User',
            'email': 'guest@openlabs.co.in',
            'company': self.company,
        }])

        regd_party, = self.Party.create([{
            'name': 'Registered user',
            'sale_price_list': user_price_list,
        }])
        self.regd_user, = self.NereidUser.create([{
            'party': regd_party,
            'display_name': 'Redg User',
            'email': 'email@example.com',
            'password': 'password',
            'company': self.company,
        }])

        # Create Locale
        en_us, = self.Language.search([('code', '=', 'en_US')])
        locale_en_us, = self.Locale.create([{
            'code': 'en_US',
            'language': en_us,
            'currency': currency,
        }])

        # Location
        location, = self.Location.search([
            ('type', '=', 'storage')
        ], limit=1)
        warehouse, = self.Location.search([
            ('type', '=', 'warehouse')
        ], limit=1)

        # Create websiteAvailableCountries
        url_map, = self.UrlMap.search([], limit=1)
        self.website, = self.Website.create([{
            'name': 'localhost',
            'url_map': url_map,
            'company': self.company,
            'application_user': AdminUser,
            'default_locale': locale_en_us,
            'guest_user': guest_user,
            'currencies': [('set', [currency])],
            'countries': [('set', self.available_countries)],
            'warehouse': warehouse,
            'stock_location': location,
            'categories': [('set', [self.category.id])],
        }])

        # Create product templates with products
        self.template, = self._create_product_template(
            'product-1',
            [{
                'category': self.category.id,
                'type': 'goods',
                'salable': True,
                'list_price': Decimal('10'),
                'cost_price': Decimal('5'),
                'account_expense': self._get_account_by_kind('expense').id,
                'account_revenue': self._get_account_by_kind('revenue').id,
            }],
            uri='product-1',
        )
        self.product = self.template.products[0]

    def test_0010_check_cart(self):
        """Assert nothing broke the cart."""
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()
            with app.test_client() as c:
                rv = c.get('/cart')
                self.assertEqual(rv.status_code, 200)

                c.post('/cart/add', data={
                    'product': self.product.id, 'quantity': 5
                })
                rv = c.get('/cart')
                self.assertEqual(rv.status_code, 200)

            sales = self.Sale.search([])
            self.assertEqual(len(sales), 1)
            sale = sales[0]
            self.assertEqual(len(sale.lines), 1)
            self.assertEqual(sale.lines[0].product.id, self.product.id)

    def test_0020_find_gateways(self):
        """No gateways must be returned if not enabled

        When no gateway is enabled then an empty list must be returned
        despite all shipping methods being there
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            country = self.website.countries[0]
            subdivision = country.subdivisions[0]
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
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            country = self.website.countries[0]
            subdivision = country.subdivisions[0]
            app = self.get_app()

            shipping = self._create_shipping('Flat Rate')
            flat_rate, = self.Flat.create([{
                'shipping': shipping.id,
                'price': Decimal('10.0'),
            }])
            expected_result = {
                'amount': 10.0,
                'id': flat_rate.id,
                'name': u'Flat Rate'
            }

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
                    {
                        u'result': [[
                            expected_result['id'],
                            expected_result['name'],
                            expected_result['amount']
                        ]]
                    }
                )
                flat_rate.shipping.is_allowed_for_guest = False
                flat_rate.shipping.save()

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
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            country = self.website.countries[0]
            subdivision = country.subdivisions[0]
            app = self.get_app()

            shipping_flat = self._create_shipping('Flat Rate')
            shipping_flat.is_allowed_for_guest = False
            shipping_flat.save()

            shipping_free = self._create_shipping('Free Rate')

            flat_rate, = self.Flat.create([{
                'shipping': shipping_flat.id,
                'price': Decimal('10.0'),
            }])

            free_rate, = self.Free.create([{
                'shipping': shipping_free.id,
                'minimum_order_value': Decimal('100.0'),
            }])

            expected_result = [
                [flat_rate.id, flat_rate.shipping.name, float(flat_rate.price)]
            ]

            with app.test_client() as c:
                # Create an order of low value
                c.post(
                    '/cart/add',
                    data={'product': self.product.id, 'quantity': 1}
                )

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

                flat_rate.shipping.is_allowed_for_guest = True
                flat_rate.shipping.save()

                # Update order to have more value
                expected_result.append([free_rate.id, u'Free Rate', 0.0])
                c.post(
                    '/cart/add',
                    data={'product': self.product.id, 'quantity': 50})
                result = c.get(url)
                self.assertEqual(
                    json.loads(result.data), {u'result': expected_result})

    def test_0050_table_rate(self):
        """Table rate method must be available, if created,
            on successful satisfaction of conditions.
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            country = self.website.countries[0]
            subdivision = country.subdivisions[0]
            app = self.get_app()

            ship_flat = self._create_shipping('Flat Rate')
            ship_free = self._create_shipping('Free Rate')
            ship_table = self._create_shipping('Table Rate')

            flat_rate, = self.Flat.create([{
                'shipping': ship_flat.id,
                'price': Decimal('10.0'),
            }])

            free_rate, = self.Free.create([{
                'shipping': ship_free.id,
                'minimum_order_value': Decimal('100.0'),
            }])

            table, = self.Table.create([{
                'shipping': ship_table.id,
                'factor': 'total_price',
            }])

            line, = self.TableLine.create([{
                'country': country.id,
                'subdivision': subdivision.id,
                'zip': '682013',
                'factor': 250.0,
                'price': Decimal('25.0'),
                'table': table.id,
            }])

            #: float because the prices are JSON serialised
            expected_result = [
                [flat_rate.id, flat_rate.shipping.name, float(flat_rate.price)],
                [free_rate.id, free_rate.shipping.name, 0.00],
                [table.id, u'Table Rate', 25.0]
            ]

            with app.test_client() as c:
                # Create an order of low value
                c.post(
                    '/cart/add',
                    data={'product': self.product.id, 'quantity': 3}
                )

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
                    json.loads(result.data), {u'result': [expected_result[0]]})

                # Add more products to make order high value
                c.post(
                    '/cart/add',
                    data={'product': self.product.id, 'quantity': 50}
                )

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
                    json.loads(result.data), {u'result': expected_result})

    def test_0060_shipping_w_login(self):
        """Test all the cases for a logged in user.
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            country = self.website.countries[0]
            subdivision = country.subdivisions[0]
            app = self.get_app()

            ship_flat = self._create_shipping('Flat Rate')
            ship_free = self._create_shipping('Free Rate')
            ship_table = self._create_shipping('Table Rate')

            flat_rate, = self.Flat.create([{
                'shipping': ship_flat.id,
                'price': Decimal('10.0'),
            }])

            free_rate, = self.Free.create([{
                'shipping': ship_free.id,
                'minimum_order_value': Decimal('100.0'),
            }])

            table, = self.Table.create([{
                'shipping': ship_table.id,
                'factor': 'total_price',
            }])

            line, = self.TableLine.create([{
                'country': country.id,
                'subdivision': subdivision.id,
                'zip': '682013',
                'factor': 250.0,
                'price': Decimal('25.0'),
                'table': table.id,
            }])

            address = self.regd_user.party.addresses[0]

            expected_result = [
                [flat_rate.id, flat_rate.shipping.name, float(flat_rate.price)]
            ]
            expected_result2 = expected_result + [
                [free_rate.id, free_rate.shipping.name, 0.00]
            ]

            with app.test_client() as c:
                c.post('/login',
                    data={'email': 'email@example.com', 'password': 'password'})
                c.post(
                    '/cart/add',
                    data={'product': self.product.id, 'quantity': 3}
                )
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
                    {u'result': expected_result}
                )

                self.Address.write([address], {
                    'street': 'C/21',
                    'streetbis': 'JSSATEN',
                    'city': 'Noida',
                    'zip': '112233',
                    'subdivision': subdivision.id,
                    'country': country.id,
                })

                url = '/_available_shipping_methods?' + urlencode({
                    'address': address.id,
                })
                result = c.get(url)
                self.assertEqual(
                    json.loads(result.data), {u'result': expected_result}
                )

                c.post(
                    '/cart/add',
                    data={'product': self.product.id, 'quantity': 50}
                )

                url = '/_available_shipping_methods?' + urlencode({
                    'address': address.id,
                })
                result = c.get(url)
                self.assertEqual(
                    json.loads(result.data), {u'result': expected_result2})

                # Table rate will fail here as the country being submitted is
                # not in table lines.

                c.post(
                    '/cart/add',
                    data={'product': self.product.id, 'quantity': 50}
                )

                url = '/_available_shipping_methods?' + urlencode({
                    'address': address.id,
                })
                result = c.get(url)
                self.assertEqual(
                    json.loads(result.data), {u'result': expected_result2})

                line, = self.TableLine.create([{
                    'country': country.id,
                    'subdivision': subdivision.id,
                    'zip': '112233',
                    'factor': 200.0,
                    'price': Decimal('25.0'),
                    'table': table.id,
                }])
                expected_result2.append([table.id, table.shipping.name, 25.0])

                c.post(
                    '/cart/add',
                    data={'product': self.product.id, 'quantity': 50}
                )

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
                    {u'result': expected_result2}
                )

    def test_0070_checkout(self):
        """Test whether shipping line is added while checkout
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            country = self.website.countries[0]
            subdivision = country.subdivisions[0]
            app = self.get_app()

            shipping = self._create_shipping('Flat Rate')

            shipment_method, = self.Flat.create([{
                'shipping': shipping.id,
                'price': Decimal('10.0'),
            }])

            # Create an account_revenue entry so that the shipping line
            # picks it up automatically
            field, = self.IRField.search([
                ('model.model', '=', 'product.template'),
                ('name', '=', 'account_revenue')
            ])
            self.IRProperty.create([{
                'field': field.id,
                'res': None,
                'value': 'account.account,%d' %
                    self._get_account_by_kind('revenue')
            }])

            with app.test_client() as c:
                c.post('/cart/add', data={
                    'product': self.product.id, 'quantity': 30
                })

                rv = c.get('/checkout')
                self.assertEqual(rv.status_code, 200)

                rv = c.post('/checkout', data={
                    'new_billing_address-name': 'Name',
                    'new_billing_address-street': 'Street',
                    'new_billing_address-streetbis': 'Streetbis',
                    'new_billing_address-zip': 'ZIP',
                    'new_billing_address-city': 'City',
                    'new_billing_address-email': 'email123@example.com',
                    'new_billing_address-phone': '1234567',
                    'new_billing_address-country': country.id,
                    'new_billing_address-subdivision': subdivision.id,
                    'shipping_same_as_billing': True,
                    'shipment_method': shipment_method.id,
                    'payment_method': 1,
                })
                self.assertEqual(rv.status_code, 302)

                sales = self.Sale.search([
                    ('state', '!=', 'draft'), ('is_cart', '=', True)
                ], order=[('id', 'DESC')])
                self.assertEqual(len(sales), 1)
                sale = sales[0]
                self.assertEqual(sale.total_amount, Decimal('310.00'))
                self.assertEqual(sale.tax_amount, Decimal('0'))
                self.assertEqual(len(sale.lines), 2)
                self.assertEqual(sale.state, 'confirmed')


def suite():
    "Shipping test suite"
    suite = unittest.TestSuite()
    suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestShipping)
    )
    return suite


if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
