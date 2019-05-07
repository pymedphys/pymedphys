from glob import glob
from os.path import abspath, dirname, join as pjoin
from setuptools import setup, find_packages

root = dirname(abspath(__file__))


def execfile(fname, globs, locs=None):
    locs = locs or globs
    exec(compile(open(fname).read(), fname, "exec"), globs, locs)


packages = find_packages('src')
root_packages = [
    package
    for package in packages
    if "." not in package
]

assert len(root_packages) == 1
package = root_packages[0]

version_ns = {}  # type: ignore
version_filepath = glob(
    pjoin(root, 'src', package, '_version.py'))[0]
execfile(version_filepath, version_ns)

version = version_ns['__version__']


setup(
    name=package,
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
    packages=packages,
    package_dir={'': 'src'},
    license='AGPL-3.0-or-later',
    extras_require={
        'test': [
            'pytest'
        ]
    }
)
