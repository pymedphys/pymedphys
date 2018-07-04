from setuptools import setup, find_packages

with open('README.md', 'r') as readme_file:
    long_description = readme_file.read()

setup(
    name="pymedphys",
    version="0.1.9",
    author="Simon Biggs",
    author_email="me@simonbiggs.net",
    description='Medical Physics python modules',
    long_description=long_description,
    long_description_content_type='text/markdown',
    classifiers=[
    'Development Status :: 3 - Alpha',
    'License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)',
    'Programming Language :: Python :: 3.6',
    'Topic :: Scientific/Engineering :: Medical Science Apps.',
    'Topic :: Scientific/Engineering :: Physics',
    'Intended Audience :: Science/Research',
    'Intended Audience :: Healthcare Industry'
    ],
    packages=find_packages(),
    license='AGPLv3+',
    install_requires=[
        'numpy',
        'scipy',
        'pandas',
        'matplotlib',
        'numba',
        'attrs',
        'psutil',
        'pymssql',
        'keyring',
        'shapely',
        'pydicom',
    ]
)
