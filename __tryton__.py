# This file is part of Tryton and Nereid. 
# see COPYRIGHT and LICENSE at the root of this repository

{
    'name': 'Nereid - Shipping',
    'version': '2.0.0.1',
    'description': '''API to facilitate multiple shipping methods to 
        integrate with Nereid''',
    'author': 'Openlabs Technologies & Consulting (P) LTD',
    'website': 'http://www.openlabs.co.in',
    'email'  : 'info@openlabs.co.in',
    'depends': [
        'nereid_cart_b2c',
        'nereid_checkout',
	],
    'xml': [
        'shipping.xml',
        'urls.xml',
    ]
}
