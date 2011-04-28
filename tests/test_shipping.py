# -*- coding: utf-8 -*-
"""
    test_shipping

    Test Shipping Methods

    :copyright: © 2011 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
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


def suite():
    "Checkout test suite"
    suite = unittest.TestSuite()
    suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestShipping)
        )
    return suite


if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
