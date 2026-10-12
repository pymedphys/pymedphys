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

"""`pymedphys dev imports` reports failures through its exit status."""

import pathlib
import subprocess

import pytest

from pymedphys._dev import tests as dev_tests

import_and_print = dev_tests._import_and_print  # pylint: disable = protected-access
venv_python = dev_tests._venv_python  # pylint: disable = protected-access

MISSING_DEPENDENCY = """Traceback (most recent call last):
  File "<string>", line 1, in <module>
  File "/venv/lib/pymedphys/_example.py", line 3, in <module>
    import notinstalled
ModuleNotFoundError: No module named 'notinstalled'
"""


def _fake_imports(failing):
    def check_output(command, **_):
        import_path = command[-1].removeprefix("import ")
        if import_path in failing:
            raise subprocess.CalledProcessError(
                1, command, output=failing[import_path].encode()
            )
        return b""

    return check_output


def test_import_failures_are_counted(monkeypatch, capsys):
    monkeypatch.setattr(
        dev_tests.subprocess,
        "check_output",
        _fake_imports(
            {
                "pymedphys._example": MISSING_DEPENDENCY,
                "pymedphys._broken": "SyntaxError: invalid syntax\n",
            }
        ),
    )

    failures = import_and_print(
        "python", ["pymedphys._fine", "pymedphys._example", "pymedphys._broken"]
    )

    assert failures == 2
    output = capsys.readouterr().out
    assert "notinstalled" in output
    assert "When importing pymedphys._broken" in output


def test_test_modules_that_skip_are_not_failures(monkeypatch):
    # pytest.importorskip raises Skipped when an optional dependency is
    # missing, which is how a test module opts out.
    monkeypatch.setattr(
        dev_tests.subprocess,
        "check_output",
        _fake_imports(
            {
                "pymedphys.tests.test_gui": (
                    "Skipped: could not import 'streamlit': "
                    "No module named 'streamlit'\n"
                )
            }
        ),
    )

    assert import_and_print("python", ["pymedphys.tests.test_gui"]) == 0


def test_clean_imports_pass(monkeypatch):
    monkeypatch.setattr(dev_tests.subprocess, "check_call", lambda *_, **__: 0)
    monkeypatch.setattr(dev_tests, "_import_and_print", lambda *_: 0)

    dev_tests.run_clean_imports(None)


def test_import_failures_exit_non_zero(monkeypatch):
    monkeypatch.setattr(dev_tests.subprocess, "check_call", lambda *_, **__: 0)
    results = iter([0, 3])
    monkeypatch.setattr(dev_tests, "_import_and_print", lambda *_: next(results))

    with pytest.raises(SystemExit) as exit_info:
        dev_tests.run_clean_imports(None)

    assert exit_info.value.code == 1


@pytest.mark.parametrize(
    "windows, expected",
    [(False, ("bin", "python")), (True, ("Scripts", "python.exe"))],
)
def test_the_venv_interpreter_path_suits_the_platform(windows, expected):
    venv = pathlib.Path("venv")
    assert venv_python(venv, windows=windows) == venv.joinpath(*expected)
