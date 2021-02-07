import collections
import sys
from collections.abc import Iterable, Sequence

collections.Iterable = Iterable  # type: ignore
collections.Sequence = Sequence  # type: ignore

from . import py_gui, watcher

sys.modules["pylinac.py_gui"] = py_gui
sys.modules["pylinac.watcher"] = watcher

# pylint: disable = unused-import
from pymedphys._imports import pylinac  # isort: skip
