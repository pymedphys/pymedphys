# Copyright (C) 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Simulate a base install of PyMedPhys in the current interpreter.

Run this file with ``runpy.run_path`` in a fresh interpreter, before anything
imports PyMedPhys, and call ``block_optional_dependencies``. Importing it as a
module would import PyMedPhys before the block is in place.
"""

import importlib.abc
import sys

# The distributions in ``[project].dependencies``, by import name.
BASE_IMPORTS = frozenset({"pymedphys", "tomlkit"})


class _OptionalDependencyBlocker(importlib.abc.MetaPathFinder):
    def __init__(self, allowed):
        self._allowed = allowed

    def find_spec(self, fullname, path=None, target=None):  # pylint: disable = unused-argument
        if fullname.split(".", maxsplit=1)[0] in self._allowed:
            return None

        raise ModuleNotFoundError(f"No module named {fullname!r}", name=fullname)


def block_optional_dependencies():
    """Make every import outside the standard library and the base install fail.

    Returns the top-level names of third-party modules that were already
    imported, by ``site`` hooks for example, which the block cannot unload.
    """
    preloaded = {
        name.split(".", maxsplit=1)[0]
        for name in sys.modules
        if name.split(".", maxsplit=1)[0] not in sys.stdlib_module_names
    }
    allowed = set(sys.stdlib_module_names) | BASE_IMPORTS | preloaded
    sys.meta_path.insert(0, _OptionalDependencyBlocker(allowed))

    return preloaded - BASE_IMPORTS
