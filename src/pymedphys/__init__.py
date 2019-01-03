"""Module docstring
"""

# pylint: disable=W0401,C0413


import os
from glob import glob

from ._version import version_info, __version__

MODULE_PATHS = glob(os.path.join(
    os.path.dirname(__file__), '[!_]*.py'))

__all__ = [
    os.path.basename(module_path)[:-3]
    for module_path in MODULE_PATHS
]

del os
del glob
del MODULE_PATHS

from . import *  # nopep8
