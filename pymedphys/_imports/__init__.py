import importlib

import apipkg

apipkg.initpkg(__name__, {"numpy": "numpy"})

THIS = importlib.import_module(__name__)
IMPORTABLES = dir(THIS)


# This will never actually run, but it helps pylint know what's going on
if "numpy" not in IMPORTABLES:
    import numpy
