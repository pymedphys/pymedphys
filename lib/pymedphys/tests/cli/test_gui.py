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

"""``pymedphys gui`` starts Streamlit bound to localhost without telemetry.

Streamlit listens on every network interface unless ``server.address`` is
set, and sends usage statistics by default. The GUI can display patient data,
so the launcher sets both explicitly; command-line flags take precedence over
any Streamlit configuration file.
"""

from pymedphys._imports import pytest

from pymedphys import _gui
from pymedphys.cli import define_parser


def _option(command, name):
    assert command.count(name) == 1, f"{name} should be passed exactly once"
    return command[command.index(name) + 1]


def _launch(monkeypatch, *cli_args):
    launched = []
    monkeypatch.setattr(_gui, "_fill_streamlit_credentials", lambda: None)
    monkeypatch.setattr(_gui.subprocess, "check_call", launched.append)

    args = define_parser().parse_args(["gui", *cli_args])
    args.func(args)

    assert len(launched) == 1
    return launched[0]


def test_default_launch_binds_localhost_without_usage_statistics(monkeypatch):
    command = _launch(monkeypatch)

    assert command[1:4] == ["-m", "streamlit", "run"]
    assert command[-1].endswith("_app.py")
    assert _option(command, "--server.address") == "localhost"
    assert _option(command, "--browser.gatherUsageStats") == "false"
    assert "--server.port" not in command


def test_port_is_passed_to_streamlit(monkeypatch):
    command = _launch(monkeypatch, "--port", "8600")

    assert _option(command, "--server.port") == "8600"


def test_address_can_be_widened_explicitly(monkeypatch):
    command = _launch(monkeypatch, "--address", "0.0.0.0")

    assert _option(command, "--server.address") == "0.0.0.0"
    assert _option(command, "--browser.gatherUsageStats") == "false"


def test_port_must_be_an_integer(capsys):
    with pytest.raises(SystemExit):
        define_parser().parse_args(["gui", "--port", "not-a-port"])

    assert "--port" in capsys.readouterr().err


@pytest.mark.parametrize("port", [None, 8600])
def test_streamlit_parses_the_command_as_intended(port):
    """Streamlit's own parser reads each option, and the app as the script.

    Checking with Streamlit's parser, rather than by position alone, catches
    an option that Streamlit would not recognise or would pass to the app as
    a script argument (for example after ``--``).
    """
    streamlit_cli = pytest.importorskip("streamlit.web.cli")
    command = _gui.build_streamlit_command(port=port)
    assert command[3] == "run"

    context = streamlit_cli.main_run.make_context("run", command[4:])

    assert context.params["server_address"] == "localhost"
    assert context.params["browser_gatherUsageStats"] is False
    assert context.params["server_port"] == port
    assert context.params["target"].endswith("_app.py")
    assert context.params["args"] == ()
