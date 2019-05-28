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


source_path = 'src'
packages = find_packages(source_path)
root_packages = [
    package
    for package in packages
    if "." not in package
]

assert len(root_packages) == 1
package = root_packages[0]
package_directory = pjoin(root, source_path, package)


def get_variable_from_file(filepath, variable):
    filepath_in_package = pjoin(package_directory, filepath)
    globs = {}
    execfile(filepath_in_package, globs)
    variable_value = globs[variable]

    return variable_value


version = get_variable_from_file('_version.py', '__version__')
install_requires = get_variable_from_file(
    '_install_requires.py', 'install_requires')


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
    package_dir={'': source_path},
    include_package_data=True,
    package_data={'pymedphys': []},
    entry_points={
        'console_scripts': [
            'pymedphys=pymedphys.cli.main:pymedphys_cli'
        ],
    },
    license='AGPL-3.0-or-later',
    install_requires=install_requires,
    extras_require={
        'docs': [
            'm2r',
            'nbsphinx',
            'sphinx-autobuild',
            'sphinxcontrib-napoleon',
            'sphinx >= 1.4, < 1.8',
            'pymedphys_sphinxtheme',
            'sphinx-argparse'
        ],
        'test': [
            'deepdiff',
            'pytest',
            'pytest-cov',
            'xlwings >= 0.15.4'
        ],
        'lint': [
            'autopep8',
            'pylint',
            'mypy'
        ],
        'dev': [
            'semver'
        ]
    }
)
