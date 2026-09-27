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

"""Extraction of the Pinnacle TAR archives given to the export CLI.

Every supported Python applies tarfile's ``data`` filter, so extraction
behaves the same on 3.11 to 3.14 and nothing lands outside the destination.
"""

import io
import pathlib
import tarfile

from pymedphys._imports import pytest

from pymedphys._pinnacle import pinnacle_cli


def _archive(path: pathlib.Path, members: dict[str, bytes], links=()) -> pathlib.Path:
    with tarfile.open(path, "w") as archive:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
        for name, target in links:
            info = tarfile.TarInfo(name)
            info.type = tarfile.SYMTYPE
            info.linkname = target
            archive.addfile(info)
    return path


def test_archive_members_are_extracted(tmp_path):
    archive = _archive(
        tmp_path / "plan.tar",
        {"Institution_1/Mount_0/Patient_1/Patient": b"patient file"},
    )
    destination = tmp_path / "out"
    destination.mkdir()

    pinnacle_cli.extract_tar(archive, destination)

    extracted = destination / "Institution_1/Mount_0/Patient_1/Patient"
    assert extracted.read_bytes() == b"patient file"


def test_names_containing_a_colon_are_skipped(tmp_path):
    archive = _archive(tmp_path / "plan.tar", {"a:b": b"x", "kept": b"y"})
    destination = tmp_path / "out"
    destination.mkdir()

    pinnacle_cli.extract_tar(archive, destination)

    assert sorted(path.name for path in destination.iterdir()) == ["kept"]


def test_member_escaping_the_destination_is_refused(tmp_path):
    archive = _archive(tmp_path / "plan.tar", {"../escaped": b"x"})
    destination = tmp_path / "out"
    destination.mkdir()

    with pytest.raises(ValueError, match="outside the extraction directory"):
        pinnacle_cli.extract_tar(archive, destination)

    assert not (tmp_path / "escaped").exists()


def test_link_pointing_outside_the_destination_is_refused(tmp_path):
    archive = _archive(tmp_path / "plan.tar", {}, links=[("link", "/etc/passwd")])
    destination = tmp_path / "out"
    destination.mkdir()

    with pytest.raises(ValueError, match="outside the extraction directory"):
        pinnacle_cli.extract_tar(archive, destination)

    assert not (destination / "link").exists()


def test_absolute_name_is_extracted_inside_the_destination(tmp_path):
    # The data filter strips a leading slash before checking the path.
    archive = _archive(tmp_path / "plan.tar", {"/absolute/file": b"x"})
    destination = tmp_path / "out"
    destination.mkdir()

    pinnacle_cli.extract_tar(archive, destination)

    assert (destination / "absolute/file").read_bytes() == b"x"
