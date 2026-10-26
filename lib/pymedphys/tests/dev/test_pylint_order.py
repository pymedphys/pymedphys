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

"""`pymedphys dev lint` sorts Pylint's own package expansion.

Pylint is in the lint dependency group, which a plain ``uv sync`` installs and
CI's unit-test jobs do not, so these tests run only where it is installed.
"""

import re
import subprocess
import sys

import pytest

from pymedphys._dev import tests as dev_tests

pytest.importorskip("pylint")

PROGRAM = dev_tests._PYLINT_IN_PATH_ORDER  # pylint: disable = protected-access
MODULES = ("zeta", "alpha", "Beta", "mid/inner", "mid2/first", "tests/bad")


def _package(root):
    package = root / "pkg"
    for module in MODULES:
        path = package / f"{module}.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        for directory in path.relative_to(package).parents:
            (package / directory / "__init__.py").write_text('"""A package."""\n')
        path.write_text(
            "print(undefined_name)\n" if module == "tests/bad" else "X = 1\n"
        )
    rcfile = root / "pylintrc"
    rcfile.write_text("[MAIN]\njobs = 1\n")
    return rcfile


def _lint(root, *arguments):
    rcfile = _package(root)
    return subprocess.run(
        [sys.executable, "-c", PROGRAM, "pkg", f"--rcfile={rcfile}", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def test_lints_the_modules_in_path_order(tmp_path):
    result = _lint(
        tmp_path,
        "--disable=all",
        "--enable=missing-module-docstring",
        "--ignore=CVS,tests",
    )

    modules = re.findall(r"^\*+ Module (\S+)$", result.stdout, flags=re.MULTILINE)
    assert modules == [
        "pkg.Beta",
        "pkg.alpha",
        "pkg.mid.inner",
        "pkg.mid2.first",
        "pkg.zeta",
    ]


def test_keeps_directories_the_ignore_option_leaves_out(tmp_path):
    arguments = ("--disable=all", "--enable=undefined-variable")

    ignored = _lint(tmp_path / "ignored", *arguments, "--ignore=CVS,tests")
    linted = _lint(tmp_path / "linted", *arguments)

    assert ignored.returncode == 0, ignored.stdout
    assert "E0602" in linted.stdout
    assert linted.returncode != 0
