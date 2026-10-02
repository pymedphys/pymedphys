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

"""``pymedphys experimental nomenclature tg263`` converts a TG-263 spreadsheet to JSON.

No test here reaches the network: the published edition is stood in for by
the invented spreadsheet in ``tests/nomenclature/data``.
"""

import dataclasses
import hashlib
import pathlib
import shutil
import urllib.error

from pymedphys._imports import pytest

from pymedphys._nomenclature import roi_list, tg263, tg263_published
from pymedphys.cli import define_parser

SPREADSHEET = (
    pathlib.Path(__file__).parents[1] / "nomenclature" / "data" / "tg263_invented.xls"
)


@pytest.fixture(autouse=True)
def _offline(tmp_path, monkeypatch):
    """Keep every test away from the network and the user's data directory."""

    def no_download(url, filepath):
        raise AssertionError(f"unexpected download of {url}")

    monkeypatch.setenv("PYMEDPHYS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(tg263_published, "download_with_progress", no_download)


def _run(*cli_args):
    args = define_parser().parse_args(
        ["experimental", "nomenclature", "tg263", *cli_args]
    )
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


def _stand_in_published(monkeypatch, content=None, **changes):
    """Make the invented spreadsheet the published edition, served offline.

    Returns the list of URLs downloaded.
    """
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

    monkeypatch.setattr(
        tg263_published, "PUBLISHED", dataclasses.replace(edition, **changes)
    )
    monkeypatch.setattr(tg263_published, "download_with_progress", download)
    return urls


def _fails(capsys, *cli_args):
    """Run the command, expecting status 1, and return its standard error."""
    with pytest.raises(SystemExit) as exit_info:
        _run(*cli_args)
    assert exit_info.value.code == 1
    return capsys.readouterr().err


def test_without_a_spreadsheet_the_published_edition_is_downloaded(
    tmp_path, monkeypatch, capsys
):
    urls = _stand_in_published(monkeypatch)
    output = tmp_path / "tg263.json"

    _run(str(output))

    assert urls == ["https://example.invalid/TG263_Invented_20260101.xls"]
    converted = tg263.load_json(output)
    assert converted.structures == tg263.read_spreadsheet(SPREADSHEET).structures
    assert converted.source.file == "TG263_Invented_20260101.xls"
    assert "TG263_Invented_20260101.xls" in capsys.readouterr().out


def test_a_cached_copy_is_converted_without_downloading_again(tmp_path, monkeypatch):
    urls = _stand_in_published(monkeypatch)
    _run(str(tmp_path / "first.json"))
    _run(str(tmp_path / "second.json"))

    assert len(urls) == 1
    assert (tmp_path / "first.json").read_bytes() == (
        tmp_path / "second.json"
    ).read_bytes()


def test_a_download_that_does_not_match_the_pin_fails_without_output(
    tmp_path, monkeypatch, capsys
):
    _stand_in_published(monkeypatch, content=b"not the published file")
    output = tmp_path / "tg263.json"

    err = _fails(capsys, str(output))

    assert not output.exists()
    assert "pinned SHA-256" in err
    assert "report it to PyMedPhys" in err


def test_entries_that_do_not_match_the_pin_fail_without_output(
    tmp_path, monkeypatch, capsys
):
    _stand_in_published(monkeypatch, content_sha256="0" * 64)
    output = tmp_path / "tg263.json"

    err = _fails(capsys, str(output))

    assert not output.exists()
    assert "content digest" in err


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.URLError("no route to host"),
        urllib.error.HTTPError("https://example.invalid", 404, "Not Found", None, None),
        TimeoutError(),
    ],
)
def test_a_download_that_fails_is_reported_without_output(
    tmp_path, monkeypatch, capsys, error
):
    _stand_in_published(monkeypatch)

    def unreachable(url, filepath):
        raise error

    monkeypatch.setattr(tg263_published, "download_with_progress", unreachable)
    output = tmp_path / "tg263.json"

    err = _fails(capsys, str(output))

    assert not output.exists()
    assert err.startswith("error: cannot download TG263_Invented_20260101.xls")
    assert "--spreadsheet" in err


def test_a_data_directory_that_cannot_be_used_is_not_called_a_download_failure(
    tmp_path, monkeypatch, capsys
):
    _stand_in_published(monkeypatch)
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("", encoding="utf-8")
    monkeypatch.setenv("PYMEDPHYS_DATA_DIR", str(blocker))

    err = _fails(capsys, str(tmp_path / "tg263.json"))

    assert "cannot download" not in err
    assert "not-a-directory" in err
    assert str(tmp_path) not in err


def test_an_existing_output_is_refused_before_downloading(
    tmp_path, monkeypatch, capsys
):
    urls = _stand_in_published(monkeypatch)
    output = tmp_path / "tg263.json"
    output.write_text("keep me", encoding="utf-8")

    err = _fails(capsys, str(output))

    assert not urls
    assert output.read_text(encoding="utf-8") == "keep me"
    assert "already exists" in err


def test_an_output_that_cannot_be_written_is_reported(tmp_path, capsys):
    output = tmp_path / "missing-directory" / "tg263.json"

    err = _fails(capsys, str(output), "--spreadsheet", str(SPREADSHEET))

    assert err.endswith("error: cannot write tg263.json: No such file or directory\n")
    assert "missing-directory" not in err


def test_a_write_that_fails_part_way_leaves_no_output(tmp_path, monkeypatch, capsys):
    output = tmp_path / "tg263.json"
    real_open = pathlib.Path.open

    class _FullDisk:
        def __init__(self, file):
            self.file = file

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            self.file.close()

        def write(self, data):
            self.file.write(data[:10])
            raise OSError(28, "No space left on device")

    def open_full_disk(path, *args, **kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        file = real_open(path, *args, **kwargs)
        return _FullDisk(file) if mode == "xb" else file

    monkeypatch.setattr(pathlib.Path, "open", open_full_disk)

    err = _fails(capsys, str(output), "--spreadsheet", str(SPREADSHEET))

    assert not output.exists()
    assert "No space left on device" in err


def test_a_local_copy_of_the_pinned_edition_is_checked_against_the_pin(
    tmp_path, monkeypatch, capsys
):
    # The file's SHA-256 matches, so its entries are checked as well.
    urls = _stand_in_published(monkeypatch, content_sha256="0" * 64)
    output = tmp_path / "tg263.json"

    err = _fails(capsys, str(output), "--spreadsheet", str(SPREADSHEET))

    assert not urls
    assert not output.exists()
    assert "content digest" in err


def test_a_local_copy_of_the_pinned_edition_is_converted_without_a_note(
    tmp_path, monkeypatch, capsys
):
    _stand_in_published(monkeypatch)

    _run(str(tmp_path / "tg263.json"), "--spreadsheet", str(SPREADSHEET))

    assert capsys.readouterr().err == ""


def test_another_workbook_is_converted_with_a_note(tmp_path, capsys):
    _run(str(tmp_path / "tg263.json"), "--spreadsheet", str(SPREADSHEET))

    err = capsys.readouterr().err
    assert err.startswith("note: tg263_invented.xls is not the pinned edition")
    assert "not checked against the pin" in err


def _run_roi_list(*cli_args):
    args = define_parser().parse_args(
        ["experimental", "nomenclature", "roi-list", *cli_args]
    )
    return args.func(args)


def test_an_institutional_list_is_converted_to_json(tmp_path, capsys):
    source = tmp_path / "site.csv"
    source.write_text("Name,Description\nLung_L,Left lung\n", encoding="utf-8")
    output = tmp_path / "site.json"

    _run_roi_list(str(source), str(output), "--list-version", "2026-10")

    expected = roi_list.read_csv(source, version="2026-10")
    assert output.read_bytes() == roi_list.to_json(expected).encode("utf-8")
    assert roi_list.load_json(output) == expected
    assert "Wrote 1 name from" in capsys.readouterr().out


def test_an_institutional_list_needs_a_version(tmp_path):
    source = tmp_path / "site.csv"
    source.write_text("Name\nLung_L\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exit_info:
        _run_roi_list(str(source), str(tmp_path / "site.json"))
    assert exit_info.value.code == 2


@pytest.mark.parametrize("name", [" site.csv", "site.csv\u00a0", "site\u202e.csv"])
def test_an_invalid_institutional_source_file_name_fails_without_output(
    tmp_path, capsys, name
):
    source = tmp_path / name
    source.write_text("Name\nLung_L\n", encoding="utf-8")
    output = tmp_path / "site.json"

    with pytest.raises(SystemExit) as exit_info:
        _run_roi_list(str(source), str(output), "--list-version", "1")

    assert exit_info.value.code == 1
    assert not output.exists()
    captured = capsys.readouterr()
    assert not captured.out
    assert captured.err == (
        "error: the source file name must be printable text without surrounding "
        "whitespace or directory separators; rename the CSV file\n"
    )


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


def test_malformed_csv_fails_without_a_traceback(tmp_path, capsys):
    source = tmp_path / "site.csv"
    source.write_text('Name,Description\nLung_L,"Left lung\nHeart,\n', encoding="utf-8")
    output = tmp_path / "site.json"

    with pytest.raises(SystemExit) as exit_info:
        _run_roi_list(str(source), str(output), "--list-version", "1")

    assert exit_info.value.code == 1
    assert not output.exists()
    assert capsys.readouterr().err.startswith("error: site.csv is not valid CSV")


@pytest.mark.parametrize("make", [lambda path: None, lambda path: path.mkdir()])
def test_an_unreadable_list_names_only_the_file(tmp_path, capsys, make):
    source = tmp_path / "site.csv"
    make(source)

    with pytest.raises(SystemExit) as exit_info:
        _run_roi_list(str(source), str(tmp_path / "site.json"), "--list-version", "1")

    assert exit_info.value.code == 1
    err = capsys.readouterr().err
    assert err.startswith("error: cannot read site.csv: ")
    assert str(tmp_path) not in err
