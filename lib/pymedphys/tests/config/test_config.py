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

"""Following ``redirect`` entries in a PyMedPhys ``config.toml``."""

import pathlib

from pymedphys._imports import pytest

from pymedphys import _config


def _write(path: pathlib.Path, text: str) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _redirect(path: pathlib.Path, target) -> pathlib.Path:
    return _write(path, f"redirect = '{target}'\n")


def test_config_without_a_redirect_is_returned(tmp_path):
    _write(tmp_path / "config.toml", "site = 'here'\n")

    assert _config.get_config(tmp_path) == {"site": "here"}


def test_absolute_redirects_are_followed_in_turn(tmp_path):
    final = _write(tmp_path / "shared" / "final.toml", "site = 'there'\n")
    middle = _redirect(tmp_path / "middle" / "config.toml", final)
    _redirect(tmp_path / "config.toml", middle)

    assert _config.get_config(tmp_path) == {"site": "there"}


def test_relative_redirect_is_resolved_beside_its_config(tmp_path, monkeypatch):
    _write(tmp_path / "home" / "shared" / "config.toml", "site = 'there'\n")
    _redirect(tmp_path / "home" / "config.toml", "shared/config.toml")
    # A file at the same relative path from the working directory must not
    # be the one that is read.
    _write(tmp_path / "elsewhere" / "shared" / "config.toml", "site = 'wrong'\n")
    monkeypatch.chdir(tmp_path / "elsewhere")

    assert _config.get_config(tmp_path / "home") == {"site": "there"}


def test_redirect_to_itself_raises(tmp_path):
    _redirect(tmp_path / "config.toml", tmp_path / "config.toml")

    with pytest.raises(ValueError, match="redirect loop"):
        _config.get_config(tmp_path)


def test_redirect_cycle_raises(tmp_path):
    first = tmp_path / "config.toml"
    second = tmp_path / "other" / "config.toml"
    _redirect(first, second)
    _redirect(second, "../config.toml")

    with pytest.raises(ValueError, match="redirect loop"):
        _config.get_config(tmp_path)
