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
    args = dev_tests.resolve_test_paths([], tmp_path)

    assert args == [str(LIBRARY_ROOT)]


def test_library_relative_path_is_passed_through(tmp_path: pathlib.Path):
    args = dev_tests.resolve_test_paths(["tests/dev"], tmp_path)

    assert "--pyargs" not in args
    assert args == ["tests/dev"]


def test_path_relative_to_the_callers_directory_is_made_absolute(
    tmp_path: pathlib.Path,
):
    relative = "suite/test_sample.py"
    test_file = tmp_path.joinpath(relative)
    test_file.parent.mkdir()
    test_file.touch()

    args = dev_tests.resolve_test_paths([relative], tmp_path)

    assert args == [str(test_file.resolve())]


def test_node_id_keeps_its_test_selector(tmp_path: pathlib.Path):
    node = "tests/dev/test_runner_arguments.py::test_node_id_keeps_its_test_selector"

    args = dev_tests.resolve_test_paths([node], tmp_path)

    assert args == [node]


def test_missing_path_is_passed_to_pytest(tmp_path: pathlib.Path):
    # A mistyped path must reach pytest, which reports it as not found,
    # rather than silently falling back to running the whole suite.
    args = dev_tests.resolve_test_paths(["tests/does_not_exist.py"], tmp_path)

    assert args == ["tests/does_not_exist.py"]


def test_explicit_pyargs_keeps_module_names(tmp_path: pathlib.Path):
    tmp_path.joinpath("pymedphys").mkdir()
    args = dev_tests.resolve_test_paths(["pymedphys"], tmp_path, pyargs=True)

    assert args == ["pymedphys"]
