# -*- coding: utf-8 -*-
"""
    setup for nereid shipping

    :copyright: (c) 2013 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from setuptools import setup, Command
import re
import os
import ConfigParser


class XmlTests(Command):
    """Runs the tests and save the result to an XML file

    Running this requires unittest-xml-reporting which can
    be installed using::

        pip install unittest-xml-reporting

    """
    description = "Run nosetests with coverage"

    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        import coverage
        import xmlrunner
        cov = coverage.coverage(source=["trytond.modules.nereid_graduit"])
        cov.start()
        from tests import suite
        xmlrunner.XMLTestRunner(output="xml-test-results").run(suite())
        cov.stop()
        cov.save()
        cov.xml_report(outfile="coverage.xml")


class RunAudit(Command):
    """Audits source code using PyFlakes for following issues:
        - Names which are used but not defined or used before they are defined.
        - Names which are redefined without having been used.
    """
    description = "Audit source code with PyFlakes"
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        import sys
        try:
            import pyflakes.scripts.pyflakes as flakes
        except ImportError:
            print "Audit requires PyFlakes installed in your system."
            sys.exit(-1)

        warns = 0
        # Define top-level directories
        dirs = ('.')
        for dir in dirs:
            for root, _, files in os.walk(dir):
                if root.startswith(('./build')):
                    continue
                for file in files:
                    if file != '__init__.py' and file.endswith('.py'):
                        warns += flakes.checkPath(os.path.join(root, file))
        if warns > 0:
            print "Audit finished with total %d warnings." % warns
        else:
            print "No problems found in sourcecode."


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

config = ConfigParser.ConfigParser()
config.readfp(open('tryton.cfg'))
info = dict(config.items('tryton'))
for key in ('depends', 'extras_depend', 'xml'):
    if key in info:
        info[key] = info[key].strip().splitlines()
major_version, minor_version, _ = info.get('version', '0.0.1').split('.', 2)
major_version = int(major_version)
minor_version = int(minor_version)

requires = []
for dep in info.get('depends', []):
    if not re.match(r'(nereid_cart|workflow|webdav)(\W|$)', dep):
        requires.append(
            'trytond_%s >= %s.%s, < %s.%s' %
            (
                dep, major_version, minor_version, major_version,
                minor_version + 1
            )
        )
requires.append(
    'trytond >= %s.%s, < %s.%s' %
    (major_version, minor_version, major_version, minor_version + 1)
)

setup(
    name='trytond_nereid_shipping',
    version=info.get('version', '0.0.1'),
    description='''API to facilitate multiple shipping methods to integrate
        with Nereid''',
    author="Openlabs Technologies & Consulting (P) LTD",
    author_email="info@openlabs.co.in",
    url="http://www.openlabs.co.in/",
    package_dir={'trytond.modules.nereid_shipping': '.'},
    packages=[
        'trytond.modules.nereid_shipping',
        'trytond.modules.nereid_shipping.tests',
    ],
    package_data={
        'trytond.modules.nereid_shipping': info.get('xml', [])
            + ['tryton.cfg'],
    },
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Plugins',
        'Intended Audience :: Developers',
        'Intended Audience :: Financial and Insurance Industry',
        'Intended Audience :: Legal Industry',
        'Intended Audience :: Manufacturing',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Framework :: Tryton',
        'Topic :: Office/Business',
    ],
    license='GPL-3',
    install_requires=requires,
    tests_require=['pycountry', 'mock'],
    zip_safe=False,
    entry_points="""
    [trytond.modules]
    nereid_shipping = trytond.modules.nereid_shipping
    """,
    test_suite='tests.suite',
    cmdclass={
        'xmltests': XmlTests,
        'audit': RunAudit,
    },
    test_loader='trytond.test_loader:Loader',
)
