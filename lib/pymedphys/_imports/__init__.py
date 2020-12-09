import importlib
import pathlib

from pymedphys._imports import _parse

from pymedphys._vendor import apipkg

HERE = pathlib.Path(__file__).parent

imports_for_apipkg = _parse.parse_imports(HERE.joinpath("imports.py"))
apipkg.initpkg(__name__, imports_for_apipkg)  # type: ignore

THIS = importlib.import_module(__name__)
IMPORTABLES = dir(THIS)

# This will never actually run, but it helps pylint know what's going on
if "numpy" not in IMPORTABLES:
    from .imports import *

    raise ValueError("This section of code should never run")
