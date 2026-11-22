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

"""The check of the Clean Graphics Option on public human DICOM, on
synthetic archives and files: its pins, its reads, its counts, and that it
writes nothing that names a file. Values that must never reach its output
carry the text ``SENTINEL``."""

import hashlib
import io
import zipfile

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import clean_graphics_check as check_module
from pymedphys._dicom.deidentify.clean_graphics_check import (
    GRAYSCALE_SOFTCOPY_PRESENTATION_STATE,
    MEMBERS,
    RT_IMAGE,
    CheckRefused,
    PinnedMember,
    read_members,
)
from pymedphys._dicom.deidentify.text_evaluation_archives import (
    ARCHIVES,
    ZenodoArchive,
)

from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

CARDIAC = "zenodo_cardiac_mr_0p55t"
PRESENTATION_STATE = "2.25.701"
PRESENTATION_STATE_SERIES = "2.25.700"
RT_IMAGE_INSTANCE = "2.25.801"
RT_IMAGE_SERIES = "2.25.800"


def _members():
    """A directory, a Presentation State, an RT Image, and a text file, as
    an archive's members, in order, each with its name and bytes."""
    state = synthetic.instance(
        GRAYSCALE_SOFTCOPY_PRESENTATION_STATE,
        PRESENTATION_STATE,
        PRESENTATION_STATE_SERIES,
    )
    image = synthetic.instance(RT_IMAGE, RT_IMAGE_INSTANCE, RT_IMAGE_SERIES)
    return (
        ("SENTINEL^NAME/", None),
        ("SENTINEL^NAME/state.dcm", synthetic.written(state)),
        ("SENTINEL^NAME/image.dcm", synthetic.written(image)),
        ("SENTINEL^NAME/notes.txt", b"SENTINEL"),
    )


def _zip(members, compression=zipfile.ZIP_DEFLATED):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=compression) as archive:
        for name, data in members:
            if data is None:
                archive.writestr(zipfile.ZipInfo(name), b"")
            else:
                archive.writestr(name, data)
    return buffer.getvalue()


def _pinned(data, **changes):
    """``data`` pinned as an archive of the cardiac record: its size and
    the SHA-256 of its bytes from its central directory to its end."""
    with zipfile.ZipFile(io.BytesIO(data)) as found:
        start = found.start_dir
    pin = {
        "record": 23089164,
        "size": len(data),
        "md5": "0" * 32,
        "central_directory_sha256": hashlib.sha256(data[start:]).hexdigest(),
    }
    pin.update(changes)
    return ZenodoArchive(**pin)


def _member(archive, entry, data, sop_class, **changes):
    pin = {
        "collection": CARDIAC,
        "archive": archive.key,
        "entry": entry,
        "sha256": hashlib.sha256(data).hexdigest(),
        "sop_class": sop_class,
    }
    pin.update(changes)
    return PinnedMember(**pin)


def _opener(data):
    def opener(archive, block):
        assert block == check_module.BLOCK
        return io.BytesIO(data)

    return opener


def test_each_member_is_read_by_its_place_in_its_pinned_archive():
    members = _members()
    data = _zip(members)
    archive = _pinned(data)
    image = _member(archive, 2, members[2][1], RT_IMAGE)
    state = _member(archive, 1, members[1][1], GRAYSCALE_SOFTCOPY_PRESENTATION_STATE)

    found = read_members((image, state), archives=(archive,), opener=_opener(data))

    assert found == ((image, members[2][1]), (state, members[1][1]))
    assert [member.label for member, _ in found] == [f"{CARDIAC} #2", f"{CARDIAC} #1"]


def _corrupted(data, name):
    """``data`` with one byte of the stored member ``name`` changed, which
    leaves the central directory as it was."""
    with zipfile.ZipFile(io.BytesIO(data)) as found:
        info = found.getinfo(name)
    header = info.header_offset
    name_length = int.from_bytes(data[header + 26 : header + 28], "little")
    extra_length = int.from_bytes(data[header + 28 : header + 30], "little")
    start = header + 30 + name_length + extra_length
    changed = bytearray(data)
    changed[start + 200] ^= 0xFF
    return bytes(changed)


@pytest.mark.parametrize(
    "case",
    [
        "another central directory",
        "another size",
        "a directory's place",
        "a place beyond the directory",
        "another digest",
        "another SOP Class",
        "a changed member",
        "another collection",
        "an archive that is not pinned",
    ],
)
def test_an_archive_or_member_unlike_its_pin_is_refused(case):
    members = _members()
    data = _zip(members, compression=zipfile.ZIP_STORED)
    archive = _pinned(data)
    state = members[1][1]
    member = _member(archive, 1, state, GRAYSCALE_SOFTCOPY_PRESENTATION_STATE)
    archives = (archive,)
    if case == "another central directory":
        archives = (_pinned(data, central_directory_sha256="1" * 64),)
    elif case == "another size":
        archives = (_pinned(data, size=len(data) + 1),)
    elif case == "a directory's place":
        member = _member(archive, 0, state, GRAYSCALE_SOFTCOPY_PRESENTATION_STATE)
    elif case == "a place beyond the directory":
        member = _member(archive, 4, state, GRAYSCALE_SOFTCOPY_PRESENTATION_STATE)
    elif case == "another digest":
        member = _member(
            archive, 1, state, GRAYSCALE_SOFTCOPY_PRESENTATION_STATE, sha256="2" * 64
        )
    elif case == "another SOP Class":
        member = _member(archive, 1, state, RT_IMAGE)
    elif case == "a changed member":
        data = _corrupted(data, members[1][0])
    elif case == "another collection":
        member = _member(
            archive,
            1,
            state,
            GRAYSCALE_SOFTCOPY_PRESENTATION_STATE,
            collection="zenodo_knee_mr_0p55t",
        )
    elif case == "an archive that is not pinned":
        archives = ()

    with pytest.raises(CheckRefused) as refused:
        read_members((member,), archives=archives, opener=_opener(data))

    assert "SENTINEL" not in str(refused.value)
    assert member.sha256 not in str(refused.value)


def test_a_pin_without_its_digest_or_with_a_place_out_of_range_is_refused():
    with pytest.raises(CheckRefused):
        PinnedMember(CARDIAC, "23089164/" + "0" * 32, 1, "SENTINEL", RT_IMAGE)
    with pytest.raises(CheckRefused):
        PinnedMember(CARDIAC, "23089164/" + "0" * 32, -1, "0" * 64, RT_IMAGE)


def test_every_pinned_member_is_in_a_pinned_archive_of_its_collection():
    keys = {archive.key: archive.collection.name for archive in ARCHIVES}

    assert all(keys.get(member.archive) == member.collection for member in MEMBERS)
    assert len({(member.archive, member.entry) for member in MEMBERS}) == len(MEMBERS)
