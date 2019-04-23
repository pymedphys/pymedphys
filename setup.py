from glob import glob
import io
from os.path import abspath, basename, dirname, join as pjoin, splitext
from setuptools import setup, find_packages

root = dirname(abspath(__file__))


def execfile(fname, globs, locs=None):
    locs = locs or globs
    exec(compile(open(fname).read(), fname, "exec"), globs, locs)


def read(*names, **kwargs):
    return io.open(
        pjoin(dirname(__file__), *names),
        encoding=kwargs.get('encoding', 'utf8')
    ).read()


package_dir = 'src'
packages = find_packages(package_dir)
root_packages = [
    package
    for package in packages
    if "." not in package
]

assert len(root_packages) == 1
package = root_packages[0]

version_ns = {}  # type: ignore
version_filepath = glob(
    pjoin(root, package_dir, package, '_version.py'))[0]
execfile(version_filepath, version_ns)

version = version_ns['__version__']


setup(
    name=package,
    version=version,
    author="PyMedPhys Contributors",
    author_email="developers@pymedphys.com",
    description='Medical Physics python modules',
    long_description=read('README.rst'),
    long_description_content_type='text/x-rst',
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)',
        'Programming Language :: Python :: 3.7',
        'Topic :: Scientific/Engineering :: Medical Science Apps.',
        'Topic :: Scientific/Engineering :: Physics',
        'Intended Audience :: Science/Research',
        'Intended Audience :: Healthcare Industry'
    ],
    packages=packages,
    package_dir={'': package_dir},
    include_package_data=True,
    package_data={'pymedphys': []},
    entry_points={
        'console_scripts': [
            'pymedphys=pymedphys.cli.main:pymedphys_cli'
        ],
    },
    license='AGPL-3.0-or-later',
    install_requires=[
        'pymedphys_analysis',
        'pymedphys_dicom',
        'pymedphys_fileformats',
        'pymedphys_labs',
        'pymedphys_logfiles',
        'pymedphys_coordsandscales',
        'pymedphys_electronfactors',
        'pymedphys_databases',
        'pymedphys_utilities',
        'pymedphys_workshops',
        'pymedphys_toolbox',
        'pymedphys_xlwings',
        'notebook',
        'jinja2'
    ],
    extras_require={
        'docs': [
            'm2r',
            'nbsphinx',
            'sphinx-autobuild',
            'sphinxcontrib-napoleon',
            'sphinx >= 1.4, < 1.8',
            'sphinx_rtd_theme',
            'sphinx-argparse'
        ],
        'testing': [
            'deepdiff',
            'pytest',
            'pytest-cov',
            'xlwings >= 0.15.4'
        ],
        'pylint': [
            'pylint'
        ],
        'formatting': [
            'autopep8',
            'pylint',
            'mypy'
        ]
    }
)
