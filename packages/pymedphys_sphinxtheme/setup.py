# -*- coding: utf-8 -*-
"""`sphinx_rtd_theme` lives on `Github`_.

.. _github: https://github.com/rtfd/sphinx_rtd_theme
"""
from io import open
from setuptools import setup
from pymedphys_sphinxtheme import __version__


setup(
    name='pymedphys_sphinxtheme',
    version=__version__,
    url='https://github.com/rtfd/sphinx_rtd_theme/',
    license='MIT',
    author='Dave Snider, Read the Docs, Inc. & contributors',
    author_email='dev@readthedocs.org',
    description='Read the Docs theme for Sphinx',
    long_description=open('README.rst', encoding='utf-8').read(),
    zip_safe=False,
    packages=['pymedphys_sphinxtheme'],
    package_data={'pymedphys_sphinxtheme': [
        'theme.conf',
        '*.html',
        'static/css/*.css',
        'static/js/*.js',
        'static/fonts/*.*'
    ]},
    include_package_data=True,
    # See http://www.sphinx-doc.org/en/stable/theming.html#distribute-your-theme-as-a-python-package
    entry_points={
        'sphinx.html_themes': [
            'pymedphys_sphinxtheme = pymedphys_sphinxtheme',
        ]
    },
    install_requires=[
        'sphinx >= 1.4, < 1.8',
        'readthedocs-sphinx-ext'
    ],
    classifiers=[
        'Framework :: Sphinx',
        'Framework :: Sphinx :: Theme',
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: MIT License',
        'Environment :: Console',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Operating System :: OS Independent',
        'Topic :: Documentation',
        'Topic :: Software Development :: Documentation',
    ],
    extras_require={
        'test': [
            'pytest'
        ]
    }
)
