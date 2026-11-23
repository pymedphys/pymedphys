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

"""The dicom extra provides every package that DICOM code imports.

CI installs the dicom extra alone and runs the DICOM tests, so a package
missing from the extra fails them, but only in the code paths those tests
reach. The de-identification corpus's share of that run follows dependency
inputs and the nightly run, so this static check runs with every unit test
run: each optional package that a module under ``pymedphys._dicom`` imports
must be in the dicom extra or the base install, or be one of the reviewed
packages whose features work without it.
"""

import ast
import importlib.metadata
import re

from pymedphys import _extras
from pymedphys._dev.paths import LIBRARY_PATH
from pymedphys._imports import _parse

IMPORT_REGISTRY = LIBRARY_PATH.joinpath("_imports", "imports.py")
DICOM_ROOT = LIBRARY_PATH.joinpath("_dicom")

# Packages that DICOM code imports without the dicom extra providing them.
# Each serves a feature whose code and tests work, or skip themselves,
# without it, which the dicom extra's own test run checks. Review a new
# entry against that run before adding it here.
REVIEWED_OPTIONAL = {
    # The independent DICOM validators, a development and evidence tool.
    "dicom-validator": "pymedphys._dicom.deidentify.dicom_validators",
    # Decoding of compressed pixel data that pydicom cannot decode alone.
    "imagecodecs": "pymedphys._dicom.deidentify.imagecodecs_plugin",
    # Plotting helpers for dose display.
    "matplotlib": "pymedphys._dicom.dose",
    # Rendering of encapsulated PDF documents for review.
    "pypdfium2": "pymedphys._dicom.deidentify.encapsulated_documents",
}


def _dicom_extra() -> set[str]:
    # Installed metadata, as in test_optional_dependencies, so that this also
    # runs from an installed wheel.
    extra = set()
    for requirement in importlib.metadata.requires("pymedphys") or []:
        if re.search(r"""extra\s*==\s*["']dicom["']""", requirement):
            name = re.match(r"[A-Za-z0-9._-]+", requirement).group()
            extra.add(_extras.normalise(name))
    return extra


def _module_name(path) -> str:
    relative = path.relative_to(LIBRARY_PATH.parent).with_suffix("")
    parts = relative.parts[:-1] if relative.name == "__init__" else relative.parts
    return ".".join(parts)


def _optional_imports() -> dict[str, set[str]]:
    """Map each distribution that DICOM code imports to the modules using it."""
    registry = _parse.parse_imports(IMPORT_REGISTRY)
    used: dict[str, set[str]] = {}
    for path in sorted(DICOM_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "pymedphys._imports":
                for alias in node.names:
                    spec = registry[alias.name]
                    root = spec.split(".", maxsplit=1)[0]
                    distribution = _extras.normalise(_extras.distribution_for(root))
                    used.setdefault(distribution, set()).add(_module_name(path))
    return used


def test_dicom_code_imports_only_what_the_dicom_extra_provides():
    dicom = _dicom_extra()
    assert {"numpy", "pydicom"} <= dicom
    base = {_extras.normalise(name) for name in _extras.BASE_DISTRIBUTIONS}

    unprovided = {
        distribution: sorted(modules)
        for distribution, modules in _optional_imports().items()
        if distribution not in dicom | base and distribution not in REVIEWED_OPTIONAL
    }
    assert unprovided == {}


def test_each_reviewed_optional_package_is_still_used_where_listed():
    used = _optional_imports()
    for distribution, module in REVIEWED_OPTIONAL.items():
        assert module in used.get(distribution, set()), distribution
        assert distribution not in _dicom_extra(), distribution
