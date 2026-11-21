"""CLI handlers run once even when they raise an internal TypeError."""

import argparse
import sys

import pytest

from pymedphys import cli


def _invoke(monkeypatch, handler, *command_args):
    parser = argparse.ArgumentParser(prog="pymedphys")
    command = parser.add_subparsers().add_parser("sample")
    command.set_defaults(func=handler)
    monkeypatch.setattr(cli, "define_parser", lambda: parser)
    monkeypatch.setattr(cli, "get_logging_config", lambda: {})
    monkeypatch.setattr(cli, "run_logging_basic_config", lambda *_args: None)
    monkeypatch.setattr(sys, "argv", ["pymedphys", "sample", *command_args])
    cli.pymedphys_cli()


def test_handler_type_error_propagates_without_second_call(monkeypatch):
    calls = []

    def handler(args, remaining=None):
        calls.append((args, remaining))
        raise TypeError("failure inside the handler")

    with pytest.raises(TypeError, match="failure inside the handler"):
        _invoke(monkeypatch, handler)

    assert len(calls) == 1


def test_one_argument_handler_invoked_once(monkeypatch):
    calls = []

    def handler(args):
        calls.append(args)

    _invoke(monkeypatch, handler)
    assert len(calls) == 1


def test_two_argument_handler_receives_remaining_options(monkeypatch):
    calls = []

    def handler(args, remaining):
        calls.append(remaining)

    _invoke(monkeypatch, handler, "--plugin-opt")
    assert calls == [["--plugin-opt"]]


def test_one_argument_handler_rejects_unknown_options(monkeypatch):
    calls = []

    def handler(args):
        calls.append(args)

    with pytest.raises(SystemExit):
        _invoke(monkeypatch, handler, "--typo")
    assert calls == []
