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

"""How ``pymedphys dev tests`` builds its pytest arguments."""

import pathlib

from pymedphys._dev import tests as dev_tests

LIBRARY_ROOT = dev_tests.LIBRARY_ROOT


def test_whole_package_is_collected_without_a_path(tmp_path: pathlib.Path):
    args = dev_tests.build_pytest_args(["-v", "-k", "gamma"], tmp_path)

    assert args == ["--pyargs", "pymedphys", "-v", "-k", "gamma"]


def test_library_relative_path_is_passed_through(tmp_path: pathlib.Path):
    args = dev_tests.build_pytest_args(["tests/dev", "-v"], tmp_path)

    assert "--pyargs" not in args
    assert args == ["tests/dev", "-v"]


def test_path_relative_to_the_callers_directory_is_made_absolute():
    repo_root = LIBRARY_ROOT.parent.parent
    relative = "lib/pymedphys/tests/dev/test_runner_arguments.py"

    args = dev_tests.build_pytest_args([relative], repo_root)

    assert args == [str(repo_root.joinpath(relative))]


def test_node_id_keeps_its_test_selector(tmp_path: pathlib.Path):
    node = "tests/dev/test_runner_arguments.py::test_node_id_keeps_its_test_selector"

    args = dev_tests.build_pytest_args([node], tmp_path)

    assert args == [node]


def test_missing_path_is_passed_to_pytest(tmp_path: pathlib.Path):
    # A mistyped path must reach pytest, which reports it as not found,
    # rather than silently falling back to running the whole suite.
    args = dev_tests.build_pytest_args(["tests/does_not_exist.py", "-v"], tmp_path)

    assert args == ["tests/does_not_exist.py", "-v"]


def test_option_values_are_not_mistaken_for_paths(tmp_path: pathlib.Path):
    # "tests" exists relative to the library root, but here it is a -k value.
    args = dev_tests.build_pytest_args(["-k", "tests", "-m", "not slow"], tmp_path)

    assert args[:2] == ["--pyargs", "pymedphys"]
