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

"""Exercise the CLI's real TAR extraction without downloaded patient data."""

import io
import logging
import tarfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, Mock

import pytest

from pymedphys._pinnacle import pinnacle_cli
from pymedphys.cli import define_parser

PATIENT_CONTENTS = b"Synthetic patient fixture\n"


@pytest.fixture(name="archive_cli")
def fixture_archive_cli(tmp_path, monkeypatch):
    """Isolate the extraction directory and the downstream Pinnacle parser."""
    context = SimpleNamespace(directory=tmp_path / "extracted", exporter=Mock())
    context.directory.mkdir()
    monkeypatch.setattr(pinnacle_cli, "PinnacleExport", context.exporter)
    monkeypatch.setattr(
        pinnacle_cli,
        "tempfile",
        SimpleNamespace(mkdtemp=lambda: str(context.directory)),
    )

    logger = logging.getLogger(pinnacle_cli.__name__)
    original_handlers = list(logger.handlers)
    original_level = logger.level
    yield context
    for handler in list(logger.handlers):
        if handler not in original_handlers:
            logger.removeHandler(handler)
            handler.close()
    logger.setLevel(original_level)


def _write_archive(path, member):
    with tarfile.open(path, "w") as archive:
        if member.isfile():
            member.size = len(PATIENT_CONTENTS)
            archive.addfile(member, io.BytesIO(PATIENT_CONTENTS))
        else:
            archive.addfile(member)


def _list_archive(path):
    args = define_parser().parse_args(["pinnacle", "export", str(path), "--list"])
    args.func(args)


@pytest.mark.parametrize("member_name", ["Patient", "nested/patient/Patient"])
def test_tar_patient_directory_reaches_exporter(tmp_path, archive_cli, member_name):
    archive = tmp_path / "patient.tar"
    _write_archive(archive, tarfile.TarInfo(member_name))

    with pytest.raises(SystemExit) as exit_info:
        _list_archive(archive)

    assert exit_info.value.code is None
    patient_directory = archive_cli.directory / Path(member_name).parent
    assert (patient_directory / "Patient").read_bytes() == PATIENT_CONTENTS
    archive_cli.exporter.assert_called_once_with(str(patient_directory), ANY)
    archive_cli.exporter.return_value.log_trial_names.assert_called_once_with()
    archive_cli.exporter.return_value.log_images.assert_called_once_with()


@pytest.mark.parametrize("member_type", ["file", "symlink", "hardlink"])
def test_members_outside_destination_are_refused(tmp_path, archive_cli, member_type):
    # The data filter applies on every supported Python, not only on 3.14,
    # where it became tarfile's default.
    archive = tmp_path / "outside.tar"
    outside = tmp_path / "outside"
    outside.write_bytes(b"Keep this file unchanged")
    if member_type == "file":
        member = tarfile.TarInfo("../outside")
    else:
        member = tarfile.TarInfo("patient/link")
        member.type = tarfile.SYMTYPE if member_type == "symlink" else tarfile.LNKTYPE
        member.linkname = str(outside)
    _write_archive(archive, member)

    expected = (
        "outside the extraction directory"
        if member_type == "file"
        else "link or special file"
    )
    with pytest.raises(ValueError, match=expected):
        _list_archive(archive)

    assert outside.read_bytes() == b"Keep this file unchanged"
    archive_cli.exporter.assert_not_called()
    assert not (archive_cli.directory / "patient" / "link").exists()
