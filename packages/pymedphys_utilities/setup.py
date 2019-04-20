from glob import glob
from os.path import abspath, basename, dirname, join as pjoin, splitext
from setuptools import setup, find_packages

root = dirname(abspath(__file__))


def execfile(fname, globs, locs=None):
    locs = locs or globs
    exec(compile(open(fname).read(), fname, "exec"), globs, locs)


version_ns = {}  # type: ignore
version_filepath = glob(
    pjoin(root, 'src', 'pymedphys*', '_version.py'))[0]
execfile(version_filepath, version_ns)

version = version_ns['__version__']


setup(
    name="pymedphys_utilities",
    version=version,
    author="PyMedPhys Contributors",
    author_email="developers@pymedphys.com",
    description='',
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
    license='AGPLv3+'
)
