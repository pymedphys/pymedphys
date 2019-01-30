import io
import sys
from glob import glob

import os
from os.path import basename
from os.path import dirname
from os.path import splitext

from setuptools import setup, find_packages
from setuptools.command.test import test as TestCommand

basename = os.path.basename
dirname = os.path.dirname
splitext = os.path.splitext

isfile = os.path.isfile
pjoin = os.path.join
repo_root = os.path.dirname(os.path.abspath(__file__))


def execfile(fname, globs, locs=None):
    locs = locs or globs
    exec(compile(open(fname).read(), fname, "exec"), globs, locs)


version_ns = {}  # type: ignore
execfile(pjoin(repo_root, 'src', 'pymedphys', '_version.py'), version_ns)

version = version_ns['__version__']


def read(*names, **kwargs):
    return io.open(
        pjoin(dirname(__file__), *names),
        encoding=kwargs.get('encoding', 'utf8')
    ).read()


# https://docs.pytest.org/en/latest/goodpractices.html#manual-integration
class PyTest(TestCommand):
    def initialize_options(self):
        TestCommand.initialize_options(self)

    def run_tests(self):

        # import here, cause outside the eggs aren't loaded
        import pytest

        errno = pytest.main([
            "-v", "--pylint", "--pylint-error-types=EF", "--mypy",
            "--doctest-modules", "--doctest-continue-on-failure",
            "--doctest-plus", "--doctest-rst", "--junitxml=junit/unit-test.xml"])
        sys.exit(errno)


setup(
    name="pymedphys",
    version=version,
    author="Simon Biggs",
    author_email="me@simonbiggs.net",
    description='Medical Physics python modules',
    long_description=read('README.rst'),
    long_description_content_type='text/x-rst',
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Topic :: Scientific/Engineering :: Medical Science Apps.',
        'Topic :: Scientific/Engineering :: Physics',
        'Intended Audience :: Science/Research',
        'Intended Audience :: Healthcare Industry'
    ],
    packages=find_packages('src'),
    package_dir={'': 'src'},
    py_modules=[splitext(basename(path))[0] for path in glob('src/*.py')],
    include_package_data=True,
    package_data={'pymedphys': []},
    entry_points={
        'console_scripts': [
            'trf2csv=pymedphys.entry_points.trf2csv:trf2csv_cli',
            # 'pymedphys=pymedphys.entry_points.gui:gui'
        ],
    },
    license='AGPLv3+',
    # data_files=get_data_files(),
    install_requires=[
        'numpy>=1.12',
        'scipy',
        'pandas',
        'xarray',
        'matplotlib',
        'attrs',
        'psutil',
        'pymssql',
        'keyring',
        'shapely',
        'pydicom>=1.0',
        'python-dateutil',
        'Pillow',
        'notebook'
    ],
    setup_requires=[
        'pytest-runner'
    ],
    tests_require=[
        'pylint',
        'coverage',
        'mypy',
        'pytest',
        'pytest-pylint',
        'pytest-mypy',
        'pytest-doctestplus',
        'sphinx-testing',
        'deepdiff',
        'numpydoc',
        'sphinx >= 1.4',
        'sphinx_rtd_theme',
        'layer-linter'
    ],
    cmdclass={"pytest": PyTest},
    extras_require={
        'docs': [
            'numpydoc',
            'sphinx >= 1.4',
            'sphinx_rtd_theme']}
)
