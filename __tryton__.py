# This file is part of OpenERP and Callisto. 
# see COPYRIGHT and LICENSE at the root of this repository

{
    'name': 'Nereid - Shipping',
    'version': '1.0',
    'description': 
        """
        API to facilitate multiple shipping methods to integrate with Nereid
        """,
    'author': 'Openlabs Technologies & Consulting (P) LTD',
    'website': 'http://www.openlabs.co.in',
    'email'  : 'info@openlabs.co.in',
    'depends': [
	             'nereid_cart',
		],
    'xml': [
             'shipping.xml',
             'urls.xml',
        ]
}
