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

"""The documentation command prepares, builds, and link-checks the site."""

import argparse
import sys
import types

import pytest

from pymedphys._dev import docs
from pymedphys.cli.dev import dev_cli


def _parse(*args):
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    dev_cli(subparsers)
    return parser.parse_args(["dev", "docs", *args])


@pytest.fixture(name="calls")
def fixture_calls(monkeypatch):
    """Record the command's side effects instead of performing them."""
    calls = {"copies": [], "commands": [], "downloads": [], "sphinx": []}
    monkeypatch.setattr(
        docs.shutil, "copy", lambda *paths: calls["copies"].append(paths)
    )
    monkeypatch.setattr(docs.subprocess, "check_call", calls["commands"].append)
    monkeypatch.setattr(docs.pymedphys, "data_path", calls["downloads"].append)

    def build_main(argv):
        calls["sphinx"].append(argv)
        return 0

    build = types.ModuleType("sphinx.cmd.build")
    build.build_main = build_main  # type: ignore[attr-defined]
    cmd = types.ModuleType("sphinx.cmd")
    cmd.build = build  # type: ignore[attr-defined]
    sphinx = types.ModuleType("sphinx")
    sphinx.cmd = cmd  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sphinx", sphinx)
    monkeypatch.setitem(sys.modules, "sphinx.cmd", cmd)
    monkeypatch.setitem(sys.modules, "sphinx.cmd.build", build)
    return calls


def test_html_build_downloads_data_and_executes_notebooks(calls):
    docs.build_docs(_parse())

    assert calls["downloads"] == docs.FILES_TO_PRE_DOWNLOAD
    (argv,) = calls["sphinx"]
    assert argv[:2] == ["-b", "html"]
    assert "-W" in argv
    assert not any(arg.startswith("nb_execution_mode") for arg in argv)


def test_linkcheck_reads_sources_without_executing_or_downloading(calls, tmp_path):
    docs.build_docs(_parse("--linkcheck", "--output", str(tmp_path)))

    # The copied pages and generated configuration are the link checker's
    # sources too, but no notebook runs, so no data is needed.
    assert len(calls["copies"]) == len(docs.FILE_COPY_MAPPING)
    assert calls["commands"] == [
        ["jupyter-book", "config", "sphinx", str(docs.DOCS_PATH)]
    ]
    assert calls["downloads"] == []
    (argv,) = calls["sphinx"]
    assert argv[:2] == ["-b", "linkcheck"]
    assert argv[argv.index("-D") + 1] == "nb_execution_mode=off"
    # A separate environment, so an HTML build never reuses doctrees read
    # without notebook outputs.
    assert argv[argv.index("-d") + 1] == str(
        tmp_path / "_build" / ".doctrees-linkcheck"
    )
    assert argv[-1] == str(tmp_path / "_build" / "linkcheck")


@pytest.mark.usefixtures("calls")
def test_linkcheck_failure_is_the_exit_status(monkeypatch):
    monkeypatch.setattr(sys.modules["sphinx.cmd.build"], "build_main", lambda argv: 1)

    with pytest.raises(SystemExit) as raised:
        docs.build_docs(_parse("--linkcheck"))

    assert raised.value.code == 1


def test_prep_and_linkcheck_are_exclusive(capsys):
    with pytest.raises(SystemExit):
        _parse("--prep", "--linkcheck")

    assert "not allowed with argument" in capsys.readouterr().err
