# -*- coding: UTF-8 -*-
'''
    Nereid Shipping

    :copyright: (c) 2010-2013 by Openlabs Technologies & Consulting (P) Ltd.
    :license: GPLv3, see LICENSE for more details
'''
from methods import (
    FlatRateShipping, FreeShipping, ShippingTable, ShippingTableLine,
)
from shipping import (
    NereidShipping, DefaultCheckout, WebsiteShipping, Website, SaleLine,
    AvailableCountries,
)

from trytond.pool import Pool


def register():
    '''
        Register classes
    '''
    Pool.register(
        NereidShipping,
        AvailableCountries,
        DefaultCheckout,
        WebsiteShipping,
        Website,
        FlatRateShipping,
        FreeShipping,
        ShippingTable,
        ShippingTableLine,
        SaleLine,
        module='nereid_shipping', type_='model'
    )
