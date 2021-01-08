import sys

from . import py_gui, watcher

sys.modules["pylinac.py_gui"] = py_gui
sys.modules["pylinac.watcher"] = watcher

# pylint: disable = unused-import
from pymedphys._imports import pylinac  # isort: skip
