# Copyright (C) 2026 Matthew Jennings
# Copyright (C) 2021 Cancer Care Associates, Simon Biggs
# Copyright (C) 2020 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import pathlib
import re
import subprocess
import sys
import tempfile

from pymedphys._imports import pytest, tabulate, tqdm

import pymedphys._utilities.test as pmp_test_utils

LIBRARY_ROOT = pathlib.Path(__file__).parent.parent.resolve()
REPO_ROOT = LIBRARY_ROOT.parent.parent
PYLINT_RC_FILE = LIBRARY_ROOT.joinpath(".pylintrc")


def run_tests(_, remaining):
    _call_pytest(remaining, "pytest")


def _is_within_scopes(import_path, scopes):
    for scope in scopes:
        if import_path.startswith(scope):
            return True

    return False


def run_clean_imports(_):
    ignore_scopes = [
        "pymedphys.docs",
        "pymedphys._imports",
        # TODO: Remove the following modules if they aren't being maintained
        # see <https://github.com/pymedphys/pymedphys/issues/1382>
        "pymedphys._experimental.paulking",
    ]
    tests_scopes = ["pymedphys.conftest", "pymedphys.tests"]

    relative_paths = [
        path.relative_to(LIBRARY_ROOT.parent)
        for path in LIBRARY_ROOT.parent.rglob("**/*.py")
    ]

    all_import_paths = [
        ".".join(path.with_suffix("").parts).replace("-", "_")
        for path in relative_paths
    ]

    clean_import_paths = []
    tests_import_paths = []
    for import_path in all_import_paths:
        if _is_within_scopes(import_path, ignore_scopes):
            continue

        if _is_within_scopes(import_path, tests_scopes):
            tests_import_paths.append(import_path)
            continue

        clean_import_paths.append(import_path)

    python_executable = pmp_test_utils.get_executable_even_when_embedded()

    with tempfile.TemporaryDirectory() as temp_dir:
        subprocess.check_call([python_executable, "-m", "venv", temp_dir])
        new_python_executable = str(_venv_python(pathlib.Path(temp_dir)))

        print("Installing PyMedPhys with minimal dependencies...\n")
        subprocess.check_call(
            [new_python_executable, "-m", "pip", "install", "."], cwd=REPO_ROOT
        )

        print("\nImporting all modules that should be able to handle a clean import...")
        failures = _import_and_print(new_python_executable, clean_import_paths)

        print("Installing PyMedPhys with tests dependencies...\n")
        subprocess.check_call(
            [new_python_executable, "-m", "pip", "install", ".[tests]"], cwd=REPO_ROOT
        )

        print("\nImporting all modules that should be able to handle a tests import...")
        failures += _import_and_print(new_python_executable, tests_import_paths)

    if failures:
        print(f"{failures} module(s) failed to import.")
        sys.exit(1)


def _venv_python(venv_dir, windows=sys.platform == "win32"):
    if windows:
        return venv_dir.joinpath("Scripts", "python.exe")

    return venv_dir.joinpath("bin", "python")


def _import_and_print(python_executable, import_paths):
    """Import each module in its own interpreter; return the failure count."""
    failures = 0
    issues = set()
    for import_path in tqdm.tqdm(import_paths):
        try:
            # TODO: This can be seriously sped up by importing them all
            # within the same Python instance. Could make the following
            # flag:
            #
            #      `pymedphys dev imports --no-isolation`
            #
            # Then this version of the CLI can call that version within
            # the created venv.

            subprocess.check_output(
                [python_executable, "-c", f"import {import_path}"],
                stderr=subprocess.STDOUT,
            )
        except subprocess.CalledProcessError as e:
            error_text = e.output.decode()

            # A test module that calls pytest.importorskip opts out this way
            # when an optional dependency is missing.
            if re.search(r"^Skipped: ", error_text, re.MULTILINE):
                continue

            failures += 1

            match = re.search("ModuleNotFoundError: No module named '(.*)'", error_text)
            try:
                module, line = _get_problem_module_and_line_number(error_text)
                dependency = match.group(1)

                issues.add((module, line, dependency))

            except (AttributeError, IndexError, ValueError):
                print(f"When importing {import_path} the following error occurred:")
                print(error_text)

    print("")
    print(tabulate.tabulate(issues, headers=["Module", "Line", "Dependency"]))
    print("\n")

    return failures


def _get_problem_module_and_line_number(error_text):
    error_list = error_text.split("\n")
    has_apipkg = ["apipkg" in item for item in error_list]
    try:
        i = has_apipkg.index(True) - 2  # The module traceback before apipkg failed
    except ValueError:
        i = -4  # The last line in the traceback containing module information

    relevant_line = error_list[i]
    module = (
        re.search(r"(pymedphys.*)\.py", relevant_line)
        .group(1)
        .replace(os.sep, ".")
        .replace("-", "_")
    )
    line = int(re.search(r"line (\d+),", relevant_line).group(1))

    return module, line


def run_doctests(_, remaining):
    remaining = ["--doctest-modules"] + remaining
    _call_pytest(remaining, "doctests")


def resolve_test_paths(paths, original_cwd, *, pyargs=False):
    """Resolve pytest's parsed test paths relative to the caller or library.

    Only positional paths reach this function; pytest and plugin option
    values are left untouched. Missing paths are kept so pytest reports the
    collection error. Explicit --pyargs arguments keep their module names.
    """
    if not paths:
        return [str(LIBRARY_ROOT)]

    if pyargs:
        return list(paths)

    original_cwd = pathlib.Path(original_cwd)
    resolved = []
    for path in paths:
        path_part, separator, selector = path.partition("::")
        candidate = original_cwd.joinpath(path_part)
        if path_part and candidate.exists():
            resolved.append(f"{candidate.resolve()}{separator}{selector}")
        else:
            resolved.append(path)

    return resolved


# The plugin that resolves caller-relative test paths in the controller and
# in every pytest-xdist worker, and the variable it reads the caller's
# directory from. Only pytest imports the plugin, so that it can rewrite its
# assertions.
PATH_PLUGIN = "pymedphys._dev.pytest_paths"
CALLER_DIRECTORY_VARIABLE = "PYMEDPHYS_DEV_TESTS_CALLER_DIRECTORY"


def _call_pytest(remaining, label):
    original_cwd = os.getcwd()

    os.chdir(LIBRARY_ROOT)
    print(f"Running {label} with cwd set to:\n    {os.getcwd()}\n")

    os.environ[CALLER_DIRECTORY_VARIABLE] = original_cwd
    try:
        retcode = pytest.main(["-p", PATH_PLUGIN, *remaining])
    finally:
        os.chdir(original_cwd)

    sys.exit(retcode)


def run_pylint(_, remaining):
    original_cwd = os.getcwd()

    if LIBRARY_ROOT.parent.name == "lib":
        working_directory_to_use = LIBRARY_ROOT.parent.parent
    else:
        working_directory_to_use = LIBRARY_ROOT.parent

    os.chdir(working_directory_to_use)
    print(f"Linting with cwd set to:\n    {os.getcwd()}\n")

    python_executable = pmp_test_utils.get_executable_even_when_embedded()
    command = [
        python_executable,
        "-m",
        "pylint",
        "pymedphys",
        f"--rcfile={str(PYLINT_RC_FILE)}",
    ] + remaining

    try:
        subprocess.check_call(command)
    finally:
        os.chdir(original_cwd)


def start_mssql_docker(args):
    CWD = REPO_ROOT.joinpath("docker", "mosaiq")

    if args.daemon:
        if args.stop:
            raise ValueError("Can't call stop and daemon flag together")
        command = ["docker-compose", "up", "-d"]
    elif args.stop:
        command = ["docker-compose", "down"]
    else:
        command = ["docker-compose", "up"]

    subprocess.check_output(command, cwd=CWD)
