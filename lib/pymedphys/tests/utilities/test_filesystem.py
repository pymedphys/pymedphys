# Copyright (C) 2026 Jeffrey D. Cooney
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

import pathlib

from pymedphys._imports import pytest

from pymedphys._utilities import filesystem


def test_open_no_lock_reads_a_file(tmp_path):
    path = tmp_path / "log.txt"
    path.write_text("contents")

    with filesystem.open_no_lock(path) as a_file:
        assert a_file.read() == "contents"

    assert a_file.closed


def test_open_no_lock_raises_the_error_from_open(tmp_path, monkeypatch):
    # The cleanup used to reference the unopened file, replacing the error
    # from open() with an UnboundLocalError. On Windows, pywin32 reports a
    # missing file before open() is reached, so skip that step here.
    monkeypatch.setattr(filesystem, "get_detached_file_descriptor", lambda path: path)

    with pytest.raises(FileNotFoundError):
        with filesystem.open_no_lock(tmp_path / "missing.txt"):
            pass


@pytest.mark.parametrize(
    "value",
    [
        "../outside",
        "/outside",
        "..",
        ".",
        "a/b",
        "C:outside",
        "C:\\outside",
        "\\\\server\\share",
    ],
)
@pytest.mark.parametrize(
    "path_type",
    [pathlib.PurePosixPath, pathlib.PureWindowsPath],
    ids=["posix", "windows"],
)
def test_encode_file_name_gives_a_single_name(value, path_type):
    """A value becomes one file or folder name on POSIX and on Windows."""
    name = filesystem.encode_file_name(value)

    folder = path_type("folder")
    assert (folder / name).parent == folder
    assert name not in (".", "..")


@pytest.mark.parametrize(
    "value, expected",
    [
        ("../x", "..%2Fx"),
        ("..", "%2E%2E"),
        ("/tmp/x", "%2Ftmp%2Fx"),
        ("C:x", "C%3Ax"),
        ('123456_SMITH, JOHN "JACK"', "123456_SMITH, JOHN %22JACK%22"),
        ("a\x00b\tc\nd\x1fe", "a%00b%09c%0Ad%1Fe"),
    ],
)
def test_encode_file_name_encodes_path_characters(value, expected):
    assert filesystem.encode_file_name(value) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("CON", "%43%4F%4E"),
        ("con", "%63%6F%6E"),
        ("CoN", "%43%6F%4E"),
        ("CON.TXT", "%43%4F%4E%2E%54%58%54"),
        ("con.txt", "%63%6F%6E%2E%74%78%74"),
        ("CON.", "%43%4F%4E%2E"),
        ("CON ", "%43%4F%4E%20"),
        ("CON.. ", "%43%4F%4E%2E%2E%20"),
        ("PRN.txt", "%50%52%4E%2E%74%78%74"),
        ("AUX", "%41%55%58"),
        ("NUL ", "%4E%55%4C%20"),
        ("COM1.dcm", "%43%4F%4D%31%2E%64%63%6D"),
        ("LPT9", "%4C%50%54%39"),
        ("COM¹", "%43%4F%4D%B9"),
        ("LPT²", "%4C%50%54%B2"),
        ("CONIN$", "%43%4F%4E%49%4E%24"),
        ("CONOUT$.txt", "%43%4F%4E%4F%55%54%24%2E%74%78%74"),
    ],
)
def test_encode_file_name_escapes_windows_reserved_devices(
    value, expected, monkeypatch
):
    monkeypatch.setattr(filesystem, "_ON_WINDOWS", True)
    assert filesystem.encode_file_name(value) == expected


def test_encode_file_name_distinguishes_reserved_names_from_literal_escapes(
    monkeypatch,
):
    monkeypatch.setattr(filesystem, "_ON_WINDOWS", True)
    assert filesystem.encode_file_name("CON") == "%43%4F%4E"
    assert filesystem.encode_file_name("%43%4F%4E") == "%2543%254F%254E"


def test_posix_reserved_names_keep_their_existing_storage_paths(monkeypatch):
    monkeypatch.setattr(filesystem, "_ON_WINDOWS", False)
    for name in ("CON", "PRN.txt", "LPT9", "CON."):
        assert filesystem.encode_file_name(name) == name


def test_encode_file_name_keeps_ordinary_names_and_distinct_values():
    for name in [
        "987654321PyMedPhysID",
        "1.2.826.0.1.3680043.8.498.1",
        "123456_O'BRIEN, MARY-JANE J.",
    ]:
        assert filesystem.encode_file_name(name) == name

    values = ["a/b", "a%2Fb", "a:b", ".."]
    assert len({filesystem.encode_file_name(value) for value in values}) == 4
