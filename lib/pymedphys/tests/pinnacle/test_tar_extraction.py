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

Pinnacle archives contain only files and directories, so links are refused
before anything is extracted, whatever the Python patch level. The remaining
members pass through tarfile's ``data`` filter on every supported Python.
"""

import io
import pathlib
import tarfile

from pymedphys._imports import pytest

from pymedphys._pinnacle import pinnacle_cli


def _archive(
    path: pathlib.Path, members: dict[str, bytes], links=(), after=None
) -> pathlib.Path:
    """Write ``members``, then ``links`` as (name, target, type), then ``after``."""
    with tarfile.open(path, "w") as archive:
        for name, content in members.items():
            _add_file(archive, name, content)
        for name, target, link_type in links:
            info = tarfile.TarInfo(name)
            info.type = link_type
            info.linkname = target
            archive.addfile(info)
        for name, content in (after or {}).items():
            _add_file(archive, name, content)
    return path


def _add_file(archive, name, content):
    info = tarfile.TarInfo(name)
    info.size = len(content)
    archive.addfile(info, io.BytesIO(content))


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


@pytest.mark.parametrize("link_type", [tarfile.SYMTYPE, tarfile.LNKTYPE])
@pytest.mark.parametrize("target", ["/etc/passwd", "../outside", "Patient"])
def test_links_are_refused_before_anything_is_extracted(tmp_path, link_type, target):
    # Refused even when the target is inside the destination: the known
    # bypasses of the data filter all go through links.
    archive = _archive(
        tmp_path / "plan.tar",
        {"Patient": b"patient file"},
        links=[("link", target, link_type)],
    )
    destination = tmp_path / "out"
    destination.mkdir()

    with pytest.raises(ValueError, match="link or special file"):
        pinnacle_cli.extract_tar(archive, destination)

    assert not list(destination.iterdir())


def test_chained_links_cannot_reach_outside(tmp_path):
    # The shape of CPython's June 2025 regression tests: a link to the
    # current directory, then a path that walks back out through it.
    archive = _archive(
        tmp_path / "plan.tar",
        {},
        links=[("loop", ".", tarfile.SYMTYPE)],
        after={"loop/../../escaped": b"x"},
    )
    destination = tmp_path / "out"
    destination.mkdir()

    with pytest.raises(ValueError, match="link or special file"):
        pinnacle_cli.extract_tar(archive, destination)

    assert not (tmp_path / "escaped").exists()
    assert not list(destination.iterdir())


def test_absolute_name_is_extracted_inside_the_destination(tmp_path):
    # The data filter strips a leading slash before checking the path.
    archive = _archive(tmp_path / "plan.tar", {"/absolute/file": b"x"})
    destination = tmp_path / "out"
    destination.mkdir()

    pinnacle_cli.extract_tar(archive, destination)

    assert (destination / "absolute/file").read_bytes() == b"x"
