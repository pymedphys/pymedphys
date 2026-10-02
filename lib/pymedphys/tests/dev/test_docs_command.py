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
from pymedphys._dicom.deidentify import requirements, traceability
from pymedphys.cli.dev import dev_cli


def _parse(*args):
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    dev_cli(subparsers)
    return parser.parse_args(["dev", "docs", *args])


@pytest.fixture(name="calls")
def fixture_calls(monkeypatch, tmp_path):
    """Record the command's side effects instead of performing them."""
    calls = {"copies": [], "commands": [], "downloads": [], "sphinx": []}
    # The matrix page is generated, not copied, so keep it out of the docs tree.
    monkeypatch.setattr(
        docs, "DEID_MATRIX_PAGE", tmp_path / "deidentification-requirements.md"
    )
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


@pytest.mark.parametrize("args", [(), ("--prep",), ("--linkcheck",)])
def test_every_build_writes_the_requirements_matrix_page(
    calls, monkeypatch, tmp_path, args
):
    page = tmp_path / "deidentification-requirements.md"
    monkeypatch.setattr(docs, "DEID_MATRIX_PAGE", page)

    docs.build_docs(_parse(*args))

    register = requirements.load_requirements()
    assert page.read_text(encoding="utf-8") == traceability.render_markdown(
        traceability.build_matrix(register)
    )
    # The page is written before Sphinx reads the sources.
    assert calls["commands"][0] == [
        "jupyter-book",
        "config",
        "sphinx",
        str(docs.DOCS_PATH),
    ]


def test_the_requirements_matrix_page_has_no_test_results(monkeypatch, tmp_path):
    page = tmp_path / "deidentification-requirements.md"
    monkeypatch.setattr(docs, "DEID_MATRIX_PAGE", page)

    docs.write_deid_matrix_page()

    text = page.read_text(encoding="utf-8")
    assert text.startswith("# DICOM de-identification requirements-to-tests matrix\n")
    assert "Test results are from" not in text
    assert "Traced tests" not in text


@pytest.mark.usefixtures("calls")
def test_clean_writes_no_requirements_matrix_page(monkeypatch, tmp_path):
    page = tmp_path / "deidentification-requirements.md"
    monkeypatch.setattr(docs, "DEID_MATRIX_PAGE", page)

    docs.build_docs(_parse("--clean"))

    assert not page.exists()


def test_the_requirements_matrix_page_is_listed_and_not_committed():
    page = docs.DEID_MATRIX_PAGE
    assert page.parent == docs.DOCS_PATH / "contrib" / "info"
    toctree = (page.parent / "index.md").read_text(encoding="utf-8")
    assert f"\ndeidentification-design\n{page.stem}\n" in toctree
    ignored = (docs.DOCS_PATH / ".gitignore").read_text(encoding="utf-8")
    assert page.relative_to(docs.DOCS_PATH).as_posix() in ignored.splitlines()
