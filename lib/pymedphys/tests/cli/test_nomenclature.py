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

"""``pymedphys nomenclature tg263`` converts a TG-263 spreadsheet to JSON.

No test here reaches the network: the published edition is stood in for by
the invented spreadsheet in ``tests/nomenclature/data``.
"""

import dataclasses
import hashlib
import pathlib
import shutil

from pymedphys._imports import pytest

from pymedphys._nomenclature import roi_list, tg263, tg263_published
from pymedphys.cli import define_parser

SPREADSHEET = (
    pathlib.Path(__file__).parents[1] / "nomenclature" / "data" / "tg263_invented.xls"
)


def _run(*cli_args):
    args = define_parser().parse_args(["nomenclature", "tg263", *cli_args])
    return args.func(args)


def test_the_spreadsheet_is_converted_to_json(tmp_path, capsys):
    output = tmp_path / "tg263.json"
    _run(str(output), "--spreadsheet", str(SPREADSHEET))

    assert output.read_text(encoding="utf-8") == tg263.to_json(
        tg263.read_spreadsheet(SPREADSHEET)
    )
    assert tg263.load_json(output) == tg263.read_spreadsheet(SPREADSHEET)
    out = capsys.readouterr().out
    assert "tg263.json" in out
    assert str(len(tg263.read_spreadsheet(SPREADSHEET).structures)) in out


def test_the_output_is_written_as_utf8_bytes_without_platform_newlines(tmp_path):
    output = tmp_path / "tg263.json"
    _run(str(output), "--spreadsheet", str(SPREADSHEET))

    expected = tg263.to_json(tg263.read_spreadsheet(SPREADSHEET)).encode("utf-8")
    assert output.read_bytes() == expected


def test_an_existing_output_is_not_overwritten(tmp_path, capsys):
    output = tmp_path / "tg263.json"
    output.write_text("keep me", encoding="utf-8")

    with pytest.raises(SystemExit) as exit_info:
        _run(str(output), "--spreadsheet", str(SPREADSHEET))

    assert exit_info.value.code == 1
    assert output.read_text(encoding="utf-8") == "keep me"
    assert "already exists" in capsys.readouterr().err


def test_a_file_that_is_not_a_tg263_spreadsheet_fails_without_output(tmp_path, capsys):
    spreadsheet = tmp_path / "not-a-workbook.xls"
    spreadsheet.write_bytes(b"not a workbook")
    output = tmp_path / "tg263.json"

    with pytest.raises(SystemExit) as exit_info:
        _run(str(output), "--spreadsheet", str(spreadsheet))

    assert exit_info.value.code == 1
    assert not output.exists()
    err = capsys.readouterr().err
    assert err.startswith("error: ")
    assert "not a readable .xls workbook" in err


def test_a_missing_spreadsheet_fails_without_output(tmp_path, capsys):
    output = tmp_path / "tg263.json"

    with pytest.raises(SystemExit) as exit_info:
        _run(str(output), "--spreadsheet", str(tmp_path / "missing.xls"))

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

    _run(str(output), "--spreadsheet", str(spreadsheet))

    assert "private" not in output.read_text(encoding="utf-8")
    assert tg263.load_json(output).source.file == SPREADSHEET.name


def _stand_in_published(monkeypatch, tmp_path, content=None):
    """Make the invented spreadsheet the published edition, served offline."""
    nomenclature = tg263.read_spreadsheet(SPREADSHEET)
    edition = tg263_published.Edition(
        sheet=nomenclature.source.sheet,
        url="https://example.invalid/TG263_Invented_20260101.xls",
        sha256=hashlib.sha256(SPREADSHEET.read_bytes()).hexdigest(),
        content_sha256=tg263.content_sha256(
            [dataclasses.asdict(s) for s in nomenclature.structures]
        ),
    )
    urls = []

    def download(url, filepath):
        urls.append(url)
        data = SPREADSHEET.read_bytes() if content is None else content
        pathlib.Path(filepath).write_bytes(data)

    monkeypatch.setenv("PYMEDPHYS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(tg263_published, "PUBLISHED", edition)
    monkeypatch.setattr(tg263_published, "download_with_progress", download)
    return urls


def test_without_a_spreadsheet_the_published_edition_is_downloaded(
    tmp_path, monkeypatch, capsys
):
    urls = _stand_in_published(monkeypatch, tmp_path)
    output = tmp_path / "tg263.json"

    _run(str(output))

    assert urls == ["https://example.invalid/TG263_Invented_20260101.xls"]
    converted = tg263.load_json(output)
    assert converted.structures == tg263.read_spreadsheet(SPREADSHEET).structures
    assert converted.source.file == "TG263_Invented_20260101.xls"
    assert "TG263_Invented_20260101.xls" in capsys.readouterr().out


def test_a_download_that_does_not_match_the_pin_fails_without_output(
    tmp_path, monkeypatch, capsys
):
    _stand_in_published(monkeypatch, tmp_path, content=b"not the published file")
    output = tmp_path / "tg263.json"

    with pytest.raises(SystemExit) as exit_info:
        _run(str(output))

    assert exit_info.value.code == 1
    assert not output.exists()
    assert "pinned SHA-256" in capsys.readouterr().err


def test_a_download_that_fails_is_reported_without_output(
    tmp_path, monkeypatch, capsys
):
    _stand_in_published(monkeypatch, tmp_path)

    def unreachable(url, filepath):
        raise OSError("network is unreachable")

    monkeypatch.setattr(tg263_published, "download_with_progress", unreachable)
    output = tmp_path / "tg263.json"

    with pytest.raises(SystemExit) as exit_info:
        _run(str(output))

    assert exit_info.value.code == 1
    assert not output.exists()
    err = capsys.readouterr().err
    assert err.startswith("error: cannot download")
    assert "--spreadsheet" in err


def _run_roi_list(*cli_args):
    args = define_parser().parse_args(["nomenclature", "roi-list", *cli_args])
    return args.func(args)


def test_an_institutional_list_is_converted_to_json(tmp_path, capsys):
    source = tmp_path / "site.csv"
    source.write_text("Name,Description\nLung_L,Left lung\n", encoding="utf-8")
    output = tmp_path / "site.json"

    _run_roi_list(str(source), str(output), "--list-version", "2026-10")

    expected = roi_list.read_csv(source, version="2026-10")
    assert output.read_bytes() == roi_list.to_json(expected).encode("utf-8")
    assert roi_list.load_json(output) == expected
    assert "1 names" in capsys.readouterr().out


def test_an_institutional_list_needs_a_version(tmp_path):
    source = tmp_path / "site.csv"
    source.write_text("Name\nLung_L\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exit_info:
        _run_roi_list(str(source), str(tmp_path / "site.json"))
    assert exit_info.value.code == 2


def test_an_invalid_institutional_list_fails_without_output(tmp_path, capsys):
    source = tmp_path / "site.csv"
    source.write_text("Name,Site\nLung_L,A\n", encoding="utf-8")
    output = tmp_path / "site.json"

    with pytest.raises(SystemExit) as exit_info:
        _run_roi_list(str(source), str(output), "--list-version", "1")

    assert exit_info.value.code == 1
    assert not output.exists()
    assert capsys.readouterr().err == "error: unknown column 'Site'\n"


def test_an_institutional_list_never_overwrites(tmp_path):
    source = tmp_path / "site.csv"
    source.write_text("Name\nLung_L\n", encoding="utf-8")
    output = tmp_path / "site.json"
    output.write_text("keep me", encoding="utf-8")

    with pytest.raises(SystemExit):
        _run_roi_list(str(source), str(output), "--list-version", "1")
    assert output.read_text(encoding="utf-8") == "keep me"
