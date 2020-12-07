import pathlib

from pymedphys._imports import _magic

HERE = pathlib.Path(__file__).parent

IMPORTABLES = _magic.import_magic(HERE)

# This will never actually run, but it helps pylint know what's going on
if "tensorflow" not in IMPORTABLES:
    from .imports import *

    raise ValueError("This section of code should never run")
