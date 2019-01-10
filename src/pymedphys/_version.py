"""Extracts version number information from gui/package.json
"""

# pylint: disable=C0103

import os
import json

try:
    HERE = os.path.dirname(__file__)
except NameError:
    HERE = os.path.join('src', 'pymedphys')

with open(os.path.join(HERE, 'gui', 'package.json')) as file:
    data = json.load(file)

version_info = data['version'].replace('.', ' ').replace('-', ' ').split(' ')
__version__ = '.'.join(map(str, version_info[:3])) + ''.join(version_info[3:])
