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

"""``pymedphys gui --port`` serves the GUI on the requested port."""

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


def test_default_launch_leaves_the_port_to_streamlit(monkeypatch):
    command = _launch(monkeypatch)

    assert command[1:4] == ["-m", "streamlit", "run"]
    assert "--server.port" not in command


def test_streamlit_reads_the_requested_port(monkeypatch):
    streamlit_cli = pytest.importorskip("streamlit.web.cli")
    command = _launch(monkeypatch, "--port", "8600")

    context = streamlit_cli.main_run.make_context("run", command[4:])

    assert context.params["server_port"] == 8600
    assert context.params["target"].endswith("_app.py")
    assert context.params["args"] == ()


def test_port_must_be_an_integer(capsys):
    with pytest.raises(SystemExit):
        define_parser().parse_args(["gui", "--port", "not-a-port"])

    assert "--port" in capsys.readouterr().err
