# Copyright (C) 2026 Jeff (jdotc1)

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""CLI handlers run once even when they raise an internal TypeError."""

import argparse
import sys

import pytest

from pymedphys import cli


def _invoke(monkeypatch, handler, *command_args):
    parser = argparse.ArgumentParser(prog="pymedphys")
    command = parser.add_subparsers().add_parser("sample")
    command.add_argument("--sample-value")
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

    _invoke(monkeypatch, handler, "--sample-value", "one")
    assert len(calls) == 1
    assert isinstance(calls[0], argparse.Namespace)
    assert calls[0].sample_value == "one"
    assert calls[0].func is handler


def test_two_argument_handler_receives_remaining_options(monkeypatch):
    calls = []

    def handler(args, remaining):
        calls.append((args, remaining))

    _invoke(monkeypatch, handler, "--sample-value", "two", "--plugin-opt")
    assert len(calls) == 1
    args, remaining = calls[0]
    assert isinstance(args, argparse.Namespace)
    assert args.sample_value == "two"
    assert args.func is handler
    assert remaining == ["--plugin-opt"]


def test_one_argument_handler_rejects_unknown_options(monkeypatch):
    calls = []

    def handler(args):
        calls.append(args)

    with pytest.raises(SystemExit):
        _invoke(monkeypatch, handler, "--typo")
    assert not calls
