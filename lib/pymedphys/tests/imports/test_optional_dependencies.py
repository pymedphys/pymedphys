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

"""Optional dependencies are imported lazily, and missing ones are explained.

The base-install tests run in a fresh interpreter in which every import
outside the standard library and the base dependencies fails, as it would
after ``pip install pymedphys``. They need no separate environment, so they
run on every platform in the unit test matrix.
"""

import importlib.metadata
import json
import pathlib
import re
import subprocess
import sys
import textwrap

import pytest

from pymedphys import _extras
from pymedphys._dev import import_policy
from pymedphys._dev.paths import LIBRARY_PATH
from pymedphys._imports import _parse

BASE_INSTALL_SCRIPT = pathlib.Path(__file__).with_name("base_install.py")
IMPORT_REGISTRY = LIBRARY_PATH.joinpath("_imports", "imports.py")

# Runs first in each fresh interpreter. ``sys.argv`` holds the blocking
# script, whether to use it, and a JSON file of arguments for the test code.
_PRELUDE = """
import json, pathlib, runpy, sys
preloaded = set()
if sys.argv[2] == "base":
    blocker = runpy.run_path(sys.argv[1])
    preloaded = blocker["block_optional_dependencies"]()
arguments = json.loads(pathlib.Path(sys.argv[3]).read_text())
"""


def _run(tmp_path, body, arguments=None, *, base_install=True):
    """Run ``body`` in a fresh interpreter and return what it prints as JSON."""
    arguments_path = tmp_path.joinpath("arguments.json")
    arguments_path.write_text(json.dumps(arguments))
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            _PRELUDE + textwrap.dedent(body),
            str(BASE_INSTALL_SCRIPT),
            "base" if base_install else "full",
            str(arguments_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr

    return json.loads(result.stdout.splitlines()[-1])


_IMPORT_EACH = """
import importlib
failures = {}
for name in arguments:
    try:
        importlib.import_module(name)
    except Exception as error:  # report every failure, not just the first
        failures[name] = f"{type(error).__name__}: {error}"
print(json.dumps({"preloaded": sorted(preloaded), "failures": failures}))
"""


def _registry_roots():
    registry = _parse.parse_imports(IMPORT_REGISTRY)
    return {spec.split(".", maxsplit=1)[0] for spec in registry.values()}


def test_modules_without_a_required_extra_import_on_a_base_install(tmp_path):
    names = [
        name
        for name in import_policy.module_names()
        if import_policy.required_extra(name) is None
    ]

    result = _run(tmp_path, _IMPORT_EACH, names)

    # An optional package imported before the block would hide a failure.
    assert not set(result["preloaded"]) & _registry_roots()
    assert result["failures"] == {}


# Import names of a few packages that only each extra provides, to skip where
# the extra is not installed. The unit test jobs install ``user`` but not
# ``ai``, so only the ``user`` case runs there.
_EXTRA_MARKERS = {"user": ("streamlit",), "ai": ("anthropic", "trio", "httpx2")}


@pytest.mark.parametrize("extra", sorted(_EXTRA_MARKERS))
def test_modules_that_need_an_extra_import_with_it(tmp_path, extra):
    for module in _EXTRA_MARKERS[extra]:
        pytest.importorskip(module)

    names = [
        name
        for name in import_policy.module_names()
        if import_policy.required_extra(name) == extra
    ]

    result = _run(tmp_path, _IMPORT_EACH, names, base_install=False)

    assert result["failures"] == {}


@pytest.mark.parametrize(
    "module_name, extra",
    [
        ("pymedphys.gamma", None),
        ("pymedphys._gamma.implementation.shell", None),
        ("pymedphys._streamlit.index", "user"),
        ("pymedphys._streamlit.utilities.config", "user"),
        ("pymedphys._experimental.streamlit.apps.mosaiq_claude_chat", "user"),
        ("pymedphys._experimental.streamlit.apps.mosaiq_claude_chat.app", "ai"),
        ("pymedphys._ai.sql_agent.conversation", "ai"),
        ("pymedphys.tests.gamma.test_gamma_shell", "tests"),
        ("pymedphys.conftest", "tests"),
    ],
)
def test_the_most_specific_policy_entry_applies(module_name, extra):
    assert import_policy.required_extra(module_name) == extra


def test_the_policy_names_existing_modules():
    names = import_policy.module_names()

    for prefix in import_policy.REQUIRED_EXTRAS:
        assert any(name == prefix or name.startswith(prefix + ".") for name in names), (
            prefix
        )
    assert "pymedphys" in names
    assert "pymedphys._imports.imports" not in names


def test_a_missing_dependency_names_the_extra_that_provides_it(tmp_path):
    result = _run(
        tmp_path,
        """
        import pymedphys
        from pymedphys._imports import anthropic, pytest

        errors = {}
        for label, use in [
            ("numpy", lambda: pymedphys.gamma([0, 1], [0, 1], [0, 1], [0, 1], 1, 1)),
            ("anthropic", lambda: anthropic.Anthropic),
            ("pytest", lambda: pytest.raises),
        ]:
            try:
                use()
            except ModuleNotFoundError as error:
                errors[label] = {"name": error.name, "message": str(error)}
        print(json.dumps(errors))
        """,
    )

    assert result["numpy"]["name"] == "numpy"
    assert '"user" extra' in result["numpy"]["message"]
    assert result["anthropic"]["name"] == "anthropic"
    assert '"ai" extra' in result["anthropic"]["message"]
    assert '"tests" extra' in result["pytest"]["message"]


def test_introspection_sees_a_missing_dependency_as_absent(tmp_path):
    result = _run(
        tmp_path,
        """
        import doctest, inspect
        from pymedphys._imports import numpy as np
        import pymedphys._gamma.implementation.shell as shell

        results = {
            "has_wrapped": hasattr(np, "__wrapped__"),
            "is_class": inspect.isclass(np),
            "doctests_found": isinstance(doctest.DocTestFinder().find(shell), list),
        }
        try:
            np.array
        except ModuleNotFoundError:
            results["array"] = "ModuleNotFoundError"
        print(json.dumps(results))
        """,
    )

    assert result == {
        "has_wrapped": False,
        "is_class": False,
        "doctests_found": True,
        # Using the dependency still fails loudly, with the install hint.
        "array": "ModuleNotFoundError",
    }


@pytest.mark.parametrize(
    "import_name, distribution",
    [
        ("numpy", "numpy"),
        ("sklearn.cluster", "scikit-learn"),
        ("PIL", "Pillow"),
        ("yaml", "PyYAML"),
        ("mpl_toolkits.mplot3d.art3d", "matplotlib"),
    ],
)
def test_imports_map_to_their_distribution(import_name, distribution):
    assert _extras.distribution_for(import_name) == distribution


@pytest.mark.parametrize(
    "import_name, extra",
    [
        # ``user`` is suggested wherever it applies: the narrower extras
        # each miss dependencies of the features they are named after.
        ("numpy", "user"),
        ("pydicom.dataset", "user"),
        ("pandas", "user"),
        ("toml", "user"),
        ("PIL", "user"),
        ("anthropic", "ai"),
        ("pytest", "tests"),
        # Development tools are in dependency groups, not extras.
        ("tabulate", None),
        ("pylint", None),
        ("not_a_dependency", None),
    ],
)
def test_the_suggested_extra_covers_the_whole_feature(import_name, extra):
    assert _extras.extra_for(import_name) == extra


def test_release_hints_pin_the_installed_version():
    assert (
        _extras.install_command("user", "0.42.0")
        == 'python -m pip install "pymedphys[user]==0.42.0"'
    )


def test_development_hints_do_not_replace_the_install_with_a_release():
    message = _extras.missing_dependency_message("numpy", version="0.42.0.dev1")

    assert "==" not in message
    assert 'pip install -e ".[user]"' in message


@pytest.mark.parametrize(
    "import_name, expected",
    [
        ("tkinter.filedialog", "standard library"),
        ("tomlkit", "Reinstall PyMedPhys"),
        ("not_a_dependency", 'python -m pip install "not_a_dependency"'),
        # A development tool used by a ``pymedphys dev`` command.
        ("pylint", "uv sync"),
    ],
)
def test_other_missing_imports_are_explained(import_name, expected):
    assert expected in _extras.missing_dependency_message(import_name)


def test_every_registered_import_comes_from_a_declared_dependency():
    # Installed metadata, not pyproject.toml, so that this also runs from an
    # installed wheel, as the published-release tests do.
    requirements = importlib.metadata.requires("pymedphys") or []
    base = {
        re.match(r"[A-Za-z0-9._-]+", requirement).group()
        for requirement in requirements
        if "extra ==" not in requirement
    }
    assert base == set(_extras.BASE_DISTRIBUTIONS)

    undeclared = [
        root
        for root in _registry_roots()
        if root not in sys.stdlib_module_names
        and _extras.distribution_for(root) not in _extras.BASE_DISTRIBUTIONS
        and _extras.extra_for(root) is None
        and root not in DEVELOPMENT_TOOL_IMPORTS
    ]
    assert undeclared == []


# Registered imports that only ``pymedphys dev`` commands use. They come from
# the ``dev`` dependency group, which installed metadata does not record.
DEVELOPMENT_TOOL_IMPORTS = frozenset({"tabulate"})


def test_the_distribution_table_matches_the_installed_packages():
    installed = importlib.metadata.packages_distributions()

    for root in _registry_roots():
        if root not in installed:
            continue

        providers = {_extras.normalise(name) for name in installed[root]}
        assert _extras.normalise(_extras.distribution_for(root)) in providers, root
