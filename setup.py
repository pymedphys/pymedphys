import io
from glob import glob
from os.path import basename
from os.path import dirname
from os.path import join
from os.path import splitext

from setuptools import setup, find_packages


def read(*names, **kwargs):
    return io.open(
        join(dirname(__file__), *names),
        encoding=kwargs.get('encoding', 'utf8')
    ).read()


setup(
    name="pymedphys",
    version="0.3.0",
    author="Simon Biggs",
    author_email="me@simonbiggs.net",
    description='Medical Physics python modules',
    long_description=read('README.md'),
    long_description_content_type='text/markdown',
    classifiers=[
        'Development Status :: 3 - Alpha',
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
        'pymssql',
        'keyring',
        'shapely',
        'pydicom',
        'python-dateutil'
    ]
)
