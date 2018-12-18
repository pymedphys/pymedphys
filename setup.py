import io
from glob import glob

import os
from os.path import basename
from os.path import dirname
from os.path import splitext

from setuptools import setup, find_packages

basename = os.path.basename
dirname = os.path.dirname
splitext = os.path.splitext

isfile = os.path.isfile
pjoin = os.path.join
repo_root = os.path.dirname(os.path.abspath(__file__))


def execfile(fname, globs, locs=None):
    locs = locs or globs
    exec(compile(open(fname).read(), fname, "exec"), globs, locs)


version_ns = {}
execfile(pjoin(repo_root, 'src', 'pymedphys', '_version.py'), version_ns)

version = version_ns['__version__']


def read(*names, **kwargs):
    return io.open(
        pjoin(dirname(__file__), *names),
        encoding=kwargs.get('encoding', 'utf8')
    ).read()


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
        ],
    },
    license='AGPLv3+',
    install_requires=[
        'numpy',
        'scipy',
        'pandas',
        'matplotlib',
        'attrs',
        'psutil',
        'pymssql',
        'keyring',
        'shapely',
        'pydicom',
        'python-dateutil'
    ]
)
