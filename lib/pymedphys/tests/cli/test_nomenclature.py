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

"""``pymedphys nomenclature tg263`` converts a TG-263 spreadsheet to JSON."""

import pathlib
import shutil

from pymedphys._imports import pytest

from pymedphys._nomenclature import tg263
from pymedphys.cli import define_parser

SPREADSHEET = (
    pathlib.Path(__file__).parents[1] / "nomenclature" / "data" / "tg263_invented.xls"
)


def _run(*cli_args):
    args = define_parser().parse_args(["nomenclature", "tg263", *cli_args])
    return args.func(args)


def test_the_spreadsheet_is_converted_to_json(tmp_path, capsys):
    output = tmp_path / "tg263.json"
    _run(str(SPREADSHEET), str(output))

    assert output.read_text(encoding="utf-8") == tg263.to_json(
        tg263.read_spreadsheet(SPREADSHEET)
    )
    assert tg263.load_json(output) == tg263.read_spreadsheet(SPREADSHEET)
    out = capsys.readouterr().out
    assert "tg263.json" in out
    assert str(len(tg263.read_spreadsheet(SPREADSHEET).structures)) in out


def test_the_output_is_written_as_utf8_bytes_without_platform_newlines(tmp_path):
    output = tmp_path / "tg263.json"
    _run(str(SPREADSHEET), str(output))

    expected = tg263.to_json(tg263.read_spreadsheet(SPREADSHEET)).encode("utf-8")
    assert output.read_bytes() == expected


def test_an_existing_output_is_not_overwritten(tmp_path, capsys):
    output = tmp_path / "tg263.json"
    output.write_text("keep me", encoding="utf-8")

    with pytest.raises(SystemExit) as exit_info:
        _run(str(SPREADSHEET), str(output))

    assert exit_info.value.code == 1
    assert output.read_text(encoding="utf-8") == "keep me"
    assert "already exists" in capsys.readouterr().err


def test_a_file_that_is_not_a_tg263_spreadsheet_fails_without_output(tmp_path, capsys):
    spreadsheet = tmp_path / "not-a-workbook.xls"
    spreadsheet.write_bytes(b"not a workbook")
    output = tmp_path / "tg263.json"

    with pytest.raises(SystemExit) as exit_info:
        _run(str(spreadsheet), str(output))

    assert exit_info.value.code == 1
    assert not output.exists()
    err = capsys.readouterr().err
    assert err.startswith("error: ")
    assert "not a readable .xls workbook" in err


def test_a_missing_spreadsheet_fails_without_output(tmp_path, capsys):
    output = tmp_path / "tg263.json"

    with pytest.raises(SystemExit) as exit_info:
        _run(str(tmp_path / "missing.xls"), str(output))

    assert exit_info.value.code == 1
    assert not output.exists()
    assert capsys.readouterr().err.startswith("error: ")


def test_the_output_names_the_spreadsheet_by_its_file_name_only(tmp_path):
    # The source record keeps the file name, not the directory it was in.
    directory = tmp_path / "private" / "downloads"
    directory.mkdir(parents=True)
    spreadsheet = directory / SPREADSHEET.name
    shutil.copyfile(SPREADSHEET, spreadsheet)
    output = tmp_path / "tg263.json"

    _run(str(spreadsheet), str(output))

    assert "private" not in output.read_text(encoding="utf-8")
    assert tg263.load_json(output).source.file == SPREADSHEET.name
