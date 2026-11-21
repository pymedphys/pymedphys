# Copyright (C) 2026 jdotc1

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""No-secret-in-argv tests for the Zenodo token command."""

import argparse
import warnings
from types import SimpleNamespace

import pytest

from pymedphys._data import zenodo
from pymedphys.cli.zenodo import zenodo_cli


def test_set_token_parser_supports_no_positional_credential():
    parser = argparse.ArgumentParser()
    zenodo_cli(parser.add_subparsers(dest="command"))
    assert parser.parse_args(["zenodo", "set-token"]).token is None


def test_zenodo_set_token_reads_environment_without_prompt(monkeypatch):
    stored = []
    monkeypatch.setenv("PYMEDPHYS_ZENODO_TOKEN", "synthetic-env-token")
    monkeypatch.setattr(zenodo, "set_zenodo_access_token", stored.append)
    monkeypatch.setattr(
        zenodo.getpass, "getpass", lambda *_: pytest.fail("Unexpected prompt")
    )
    zenodo.set_zenodo_access_token_cli(SimpleNamespace(token=None))
    assert stored == ["synthetic-env-token"]


def test_zenodo_set_token_uses_hidden_prompt_without_env(monkeypatch):
    stored = []
    monkeypatch.delenv("PYMEDPHYS_ZENODO_TOKEN", raising=False)
    monkeypatch.setattr(zenodo.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(zenodo.getpass, "getpass", lambda *_: "synthetic-prompt-token")
    monkeypatch.setattr(zenodo, "set_zenodo_access_token", stored.append)
    zenodo.set_zenodo_access_token_cli(SimpleNamespace(token=None))
    assert stored == ["synthetic-prompt-token"]


def test_zenodo_set_token_fails_without_token_or_terminal(monkeypatch):
    monkeypatch.delenv("PYMEDPHYS_ZENODO_TOKEN", raising=False)
    monkeypatch.setattr(zenodo.sys, "stdin", SimpleNamespace(isatty=lambda: False))
    with pytest.raises(ValueError, match="PYMEDPHYS_ZENODO_TOKEN"):
        zenodo.set_zenodo_access_token_cli(SimpleNamespace(token=None))


def test_zenodo_set_token_rejects_empty_credentials(monkeypatch):
    monkeypatch.setenv("PYMEDPHYS_ZENODO_TOKEN", "")
    with pytest.raises(ValueError, match="non-empty"):
        zenodo.set_zenodo_access_token_cli(SimpleNamespace(token=None))



def test_zenodo_set_token_refuses_getpass_echo_fallback(monkeypatch):
    stored = []
    monkeypatch.delenv("PYMEDPHYS_ZENODO_TOKEN", raising=False)
    monkeypatch.setattr(zenodo.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(zenodo, "set_zenodo_access_token", stored.append)

    def unavailable_echo_suppression(*_args):
        warnings.warn("Unable to disable terminal echo", zenodo.getpass.GetPassWarning)
        pytest.fail("Should not read token after GetPassWarning")

    monkeypatch.setattr(zenodo.getpass, "getpass", unavailable_echo_suppression)
    with pytest.raises(ValueError, match="Cannot hide Zenodo token input"):
        zenodo.set_zenodo_access_token_cli(SimpleNamespace(token=None))
    assert stored == []


def test_zenodo_set_token_cli_reports_missing_token_without_traceback(
    monkeypatch, capsys
):
    monkeypatch.delenv("PYMEDPHYS_ZENODO_TOKEN", raising=False)
    monkeypatch.setattr(zenodo.sys, "stdin", SimpleNamespace(isatty=lambda: False))
    parser = argparse.ArgumentParser()
    zenodo_cli(parser.add_subparsers(dest="command"))
    args = parser.parse_args(["zenodo", "set-token"])

    with pytest.raises(SystemExit) as exc:
        args.func(args)

    assert exc.value.code == 2
    stderr = capsys.readouterr().err
    assert "error: No Zenodo token supplied" in stderr
    assert "Traceback" not in stderr


def test_zenodo_set_token_prefers_explicit_argument(monkeypatch):
    stored = []
    monkeypatch.setenv("PYMEDPHYS_ZENODO_TOKEN", "synthetic-env-token")
    monkeypatch.setattr(zenodo, "set_zenodo_access_token", stored.append)
    zenodo.set_zenodo_access_token_cli(SimpleNamespace(token="explicit-token"))
    assert stored == ["explicit-token"]
