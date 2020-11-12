import ast
import importlib
import pathlib

from pymedphys._vendor import apipkg

HERE = pathlib.Path(__file__).parent

with open(HERE.joinpath("imports.py")) as f:
    imports_string = f.read()


imports_for_apipkg = {}

for node in ast.parse(imports_string).body:
    if not isinstance(node, ast.Import):
        raise ValueError("Only direct import statements are supported")

    aliases = list(node.names)
    if len(aliases) != 1:
        raise ValueError("Only one alias per import supported")

    alias = aliases[0]
    asname = alias.asname

    if asname is None:
        asname = alias.name

    imports_for_apipkg[asname] = alias.name


apipkg.initpkg(__name__, imports_for_apipkg)  # type: ignore

THIS = importlib.import_module(__name__)
IMPORTABLES = dir(THIS)

# This will never actually run, but it helps pylint know what's going on
if "numpy" not in IMPORTABLES:
    from .imports import *

    raise ValueError("This section of code should never run")
