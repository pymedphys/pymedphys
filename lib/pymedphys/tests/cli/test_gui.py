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

"""``pymedphys gui`` serves only this computer unless given ``--address``."""

from pymedphys._imports import pytest

from pymedphys import _gui
from pymedphys.cli import define_parser


def _launch(monkeypatch, *cli_args):
    launched = []
    monkeypatch.setattr(_gui, "_fill_streamlit_credentials", lambda: None)
    monkeypatch.setattr(_gui.subprocess, "check_call", launched.append)

    args = define_parser().parse_args(["gui", *cli_args])
    args.func(args)

    assert len(launched) == 1
    return launched[0]


def _values(command, option):
    return [value for name, value in zip(command, command[1:]) if name == option]


def _streamlit_params(command):
    streamlit_cli = pytest.importorskip("streamlit.web.cli")
    context = streamlit_cli.main_run.make_context("run", command[4:])

    assert context.params["target"].endswith("_app.py")
    assert context.params["args"] == ()
    return context.params


def test_default_launch_serves_only_this_computer(monkeypatch):
    command = _launch(monkeypatch)

    assert command[1:4] == ["-m", "streamlit", "run"]
    assert _values(command, "--server.address") == ["127.0.0.1"]
    assert _values(command, "--server.allowedHosts") == ["localhost", "127.0.0.1"]
    assert _values(command, "--browser.gatherUsageStats") == ["false"]
    assert "--server.port" not in command


def test_address_opts_in_to_serving_another_interface(monkeypatch):
    command = _launch(monkeypatch, "--address", "0.0.0.0")

    assert _values(command, "--server.address") == ["0.0.0.0"]
    assert "--server.allowedHosts" not in command
    assert _values(command, "--browser.gatherUsageStats") == ["false"]


def test_streamlit_reads_the_default_options(monkeypatch):
    # Command line options take precedence over Streamlit's environment variables.
    monkeypatch.setenv("STREAMLIT_SERVER_ADDRESS", "0.0.0.0")
    monkeypatch.setenv("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "true")
    params = _streamlit_params(_launch(monkeypatch))

    assert params["server_address"] == "127.0.0.1"
    assert params["server_allowedHosts"] == ("localhost", "127.0.0.1")
    assert params["browser_gatherUsageStats"] is False
    assert params["server_port"] is None


def test_streamlit_reads_the_requested_address_and_port(monkeypatch):
    params = _streamlit_params(
        _launch(monkeypatch, "--address", "192.0.2.10", "--port", "8600")
    )

    assert params["server_address"] == "192.0.2.10"
    assert params["server_allowedHosts"] == ()
    assert params["browser_gatherUsageStats"] is False
    assert params["server_port"] == 8600


def test_port_must_be_an_integer(capsys):
    with pytest.raises(SystemExit):
        define_parser().parse_args(["gui", "--port", "not-a-port"])

    assert "--port" in capsys.readouterr().err


def test_launching_without_streamlit_names_the_extra_to_install(monkeypatch):
    find_spec = _gui.importlib.util.find_spec
    monkeypatch.setattr(
        _gui.importlib.util,
        "find_spec",
        lambda name, *args: None if name == "streamlit" else find_spec(name, *args),
    )
    monkeypatch.setattr(_gui.subprocess, "check_call", pytest.fail)

    args = define_parser().parse_args(["gui"])
    with pytest.raises(ModuleNotFoundError, match=r"\"user\" extra") as error:
        args.func(args)

    assert error.value.name == "streamlit"


@pytest.mark.parametrize("address", ["", "  "])
def test_address_must_not_be_empty(capsys, address):
    # Streamlit would serve every interface for an empty address.
    with pytest.raises(SystemExit):
        define_parser().parse_args(["gui", "--address", address])

    assert "--address" in capsys.readouterr().err


def test_address_help_warns_that_the_apps_are_open_to_anyone(capsys):
    with pytest.raises(SystemExit):
        define_parser().parse_args(["gui", "--help"])

    help_text = " ".join(capsys.readouterr().out.split())
    assert "no authentication" in help_text
    assert "patient data" in help_text
