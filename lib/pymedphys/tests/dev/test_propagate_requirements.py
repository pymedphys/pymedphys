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

"""How ``pymedphys dev propagate`` exports the pinned requirements files."""

import pathlib

import pytest

from pymedphys._dev import propagate

make_requirements_txt = propagate._make_requirements_txt  # pylint: disable = protected-access


@pytest.fixture(name="export_calls")
def fixture_export_calls(monkeypatch, tmp_path: pathlib.Path):
    """Replace ``uv export`` with a stub that writes one pinned requirement."""
    calls = []

    def fake_check_call(cmd, cwd):
        calls.append(cmd)
        output = cmd[cmd.index("--output-file") + 1]
        pathlib.Path(cwd, output).write_text("numpy==1.26.4\n", encoding="utf-8")

    monkeypatch.setattr(propagate, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(propagate.subprocess, "check_call", fake_check_call)

    return calls


@pytest.mark.parametrize(
    "extras, editable, project_line",
    [(["user"], False, ".[user]"), (["docs"], True, "-e .[docs]")],
)
def test_project_is_listed_once_with_its_extras(
    export_calls, tmp_path: pathlib.Path, extras, editable, project_line
):
    make_requirements_txt(
        extras=extras,
        filename="requirements.txt",
        include_pymedphys=True,
        editable=editable,
    )

    (cmd,) = export_calls
    # uv would otherwise add its own bare ``-e .`` line for the project.
    assert "--no-emit-project" in cmd
    lines = tmp_path.joinpath("requirements.txt").read_text().splitlines()
    assert lines == ["numpy==1.26.4", project_line]


def test_development_dependency_group_is_not_exported(export_calls):
    make_requirements_txt(
        extras=["user"],
        filename="requirements.txt",
        include_pymedphys=True,
        editable=False,
    )

    (cmd,) = export_calls
    assert "--no-default-groups" in cmd
