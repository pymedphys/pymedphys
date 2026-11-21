"""No-secret-in-argv tests for the Zenodo token command."""

import argparse
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
