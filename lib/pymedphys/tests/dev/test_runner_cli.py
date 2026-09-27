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

"""Exercise test-runner startup through the real command-line entry point."""

import os
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest
import toml

from pymedphys._dev.tests import LIBRARY_ROOT


def _run_cli(cwd, *args, env=None):
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(LIBRARY_ROOT.parent)
    if env:
        environment.update(env)
    return subprocess.run(
        [sys.executable, "-m", "pymedphys", "dev", *args],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.mark.parametrize("command", ["tests", "doctests"])
def test_cli_preserves_user_config_and_log(tmp_path, command):
    user_home = tmp_path / "home"
    config_dir = user_home / ".pymedphys"
    config_dir.mkdir(parents=True)
    log = user_home / "existing.log"
    log.write_text("Existing log must survive.\n", encoding="utf-8")
    config = config_dir / "config.toml"
    config.write_text(
        toml.dumps({"cli": {"logging": {"filename": str(log), "filemode": "w"}}}),
        encoding="utf-8",
    )
    original_config = config.read_bytes()
    original_log = log.read_bytes()
    sample = tmp_path / "test_sample.py"
    sample.write_text(
        '"""\n>>> 1 + 1\n2\n"""\n'
        if command == "doctests"
        else "def test_sample():\n    assert True\n",
        encoding="utf-8",
    )

    result = _run_cli(
        tmp_path,
        command,
        str(sample),
        "-q",
        env={"HOME": str(user_home), "USERPROFILE": str(user_home)},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout
    assert config.read_bytes() == original_config
    assert log.read_bytes() == original_log


def test_option_values_and_caller_relative_paths(tmp_path):
    # The option value and test path deliberately contain the same string.
    suite = tmp_path / "suite"
    suite.mkdir()
    (suite / "conftest.py").write_text(
        "def pytest_addoption(parser):\n" "    parser.addoption('--review-value')\n",
        encoding="utf-8",
    )
    (suite / "test_sample.py").write_text(
        "def test_sample(pytestconfig):\n"
        "    assert pytestconfig.getoption('--review-value') == 'suite'\n",
        encoding="utf-8",
    )
    report = tmp_path / "junit.xml"

    result = _run_cli(
        tmp_path,
        "tests",
        "suite",
        "--review-value",
        "suite",
        "--junit-prefix",
        "suite",
        f"--junitxml={report}",
        "-q",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    cases = ET.parse(report).findall(".//testcase")
    assert len(cases) == 1
    assert cases[0].get("classname").startswith("suite.")
    assert str(tmp_path) not in cases[0].get("classname")
