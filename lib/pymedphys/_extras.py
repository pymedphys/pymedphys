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

"""Which extra provides each optional dependency, and how to install it.

``pymedphys._imports`` calls ``missing_dependency_message`` when library code
uses an optional package that is not installed. This module must import with
only the standard library, because it runs when dependencies are missing.
"""

import functools
import re
import sys
import tomllib

from pymedphys._dev.paths import DEPENDENCY_EXTRA_PATH
from pymedphys._version import __version__

# Import names whose distribution has a different name. Every other import
# name is also its distribution's name.
DISTRIBUTION_FOR_IMPORT = {
    "attr": "attrs",
    "dateutil": "python-dateutil",
    "libjpeg": "pylibjpeg-libjpeg",
    "mpl_toolkits": "matplotlib",
    "PIL": "Pillow",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
}

# The distributions in ``[project].dependencies``.
BASE_DISTRIBUTIONS = frozenset({"tomlkit"})

# The extras to suggest, in order of preference. ``user`` comes first because
# it holds every dependency of every feature except the AI app, so it always
# fixes the error. The narrow feature extras, such as ``dicom``, are never
# suggested: one missing package usually means a whole feature is missing, and
# the code cannot tell which feature the user wants. Development tools are in
# dependency groups, which are not published, so no extra provides them.
EXTRA_PREFERENCE = ("user", "ai", "tests")


def normalise(distribution: str) -> str:
    """Normalise a distribution name as PEP 503 does."""
    return re.sub(r"[-_.]+", "-", distribution).lower()


def distribution_for(import_name: str) -> str:
    """Return the distribution that provides an import, such as ``numpy.linalg``."""
    top_level = import_name.split(".", maxsplit=1)[0]

    return DISTRIBUTION_FOR_IMPORT.get(top_level, top_level)


@functools.cache
def _distributions_by_extra() -> dict[str, frozenset[str]]:
    with open(DEPENDENCY_EXTRA_PATH, "rb") as f:
        extras = tomllib.load(f)

    return {
        extra: frozenset(normalise(name) for name in distributions)
        for extra, distributions in extras.items()
    }


def extra_for(import_name: str) -> str | None:
    """Return the extra to suggest for an import, or None if no extra has it."""
    distribution = normalise(distribution_for(import_name))
    extras = _distributions_by_extra()

    for extra in EXTRA_PREFERENCE:
        if distribution in extras.get(extra, ()):
            return extra

    return None


def _is_release(version: str) -> bool:
    return not re.search(r"dev|\+", version)


def install_command(extra: str, version: str = __version__) -> str:
    """Return the command that installs PyMedPhys with an extra."""
    return f'python -m pip install "pymedphys[{extra}]=={version}"'


def missing_dependency_message(
    import_name: str, needed_for: str | None = None, version: str = __version__
) -> str:
    """Explain how to install a missing optional dependency."""
    top_level = import_name.split(".", maxsplit=1)[0]
    distribution = distribution_for(import_name)
    needed = f' (needed for "{needed_for}")' if needed_for else ""
    problem = f'PyMedPhys could not import "{top_level}"{needed}.'

    if top_level in sys.stdlib_module_names:
        return (
            f"{problem} It is part of the Python standard library, but this "
            "Python installation does not include it. Use a Python "
            "installation that does."
        )

    if distribution in BASE_DISTRIBUTIONS:
        return (
            f'{problem} "{distribution}" is a required dependency of '
            "PyMedPhys, so the installation is incomplete. Reinstall PyMedPhys."
        )

    extra = extra_for(import_name)
    if extra is None:
        return (
            f"{problem} No PyMedPhys extra provides it. If you are working on "
            "PyMedPhys from a source checkout, run `uv sync` in the checkout, "
            "which installs every development tool. Otherwise install it with:"
            f'\n\n    python -m pip install "{distribution}"'
        )

    provided_by = (
        f'It is provided by "{distribution}", which is in the optional "{extra}" extra.'
    )
    if _is_release(version):
        return (
            f"{problem} {provided_by} Install the extra with:\n\n"
            f"    {install_command(extra, version)}"
        )

    # Installing a release here would replace the development version.
    return (
        f"{problem} {provided_by} This is a development version of PyMedPhys, "
        "so install the extra from the source you installed PyMedPhys from, "
        "for example by running this in a source checkout:\n\n"
        f'    python -m pip install -e ".[{extra}]"'
    )
