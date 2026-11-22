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
synthetic archives and files: its pins, its reads, its runs and their
expectations, and that it writes no value of an instance. Values that must
never reach its output carry the text ``SENTINEL``."""

import hashlib
import io
import json
import zipfile

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import clean_graphics_check as check_module
from pymedphys._dicom.deidentify import clean_graphics_runs as runs_module
from pymedphys._dicom.deidentify import policy
from pymedphys._dicom.deidentify.clean_graphics_check import (
    FORMAT,
    GRAYSCALE_SOFTCOPY_PRESENTATION_STATE,
    JSON_NAME,
    MARKDOWN_NAME,
    MEMBERS,
    RT_IMAGE,
    CheckRefused,
    PinnedMember,
    check,
    main,
    markdown,
    read_members,
)
from pymedphys._dicom.deidentify.clean_graphics_runs import EXPECTATIONS
from pymedphys._dicom.deidentify.reviewed_annotations import annotation_digest
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
    def opener(_archive, block):
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


# The runs and their expectations


def _on(number):
    return [
        synthetic.reference(synthetic.CT_IMAGE_STORAGE, synthetic.CT_SLICES[number])
    ]


def _text(value, number=0):
    """An annotation of one text object, on one CT slice."""
    return synthetic.item(
        GraphicLayer="LAYER",
        ReferencedImageSequence=_on(number),
        TextObjectSequence=[
            synthetic.item(
                AnchorPointAnnotationUnits="PIXEL",
                AnchorPoint=[5.0, 5.0],
                AnchorPointVisibility="N",
                UnformattedTextValue=value,
            )
        ],
    )


def _mark(number=0, points=(10.0, 10.0, 20.0, 20.0)):
    """An annotation of one line, on one CT slice."""
    return synthetic.item(
        GraphicLayer="LAYER",
        ReferencedImageSequence=_on(number),
        GraphicObjectSequence=[
            synthetic.item(
                GraphicAnnotationUnits="PIXEL",
                GraphicDimensions=2,
                NumberOfGraphicPoints=2,
                GraphicData=list(points),
                GraphicType="POLYLINE",
                GraphicFilled="N",
            )
        ],
    )


def _annotations():
    """On the first slice, a label, a line, and the patient's name, shown
    together; on the second, a line shown alone."""
    return [
        _text("SENTINEL LABEL"),
        _mark(),
        _text(synthetic.PATIENTS_NAME),
        _mark(1, (1.0, 2.0, 3.0, 4.0)),
    ]


def _state(annotations):
    dataset = synthetic.instance(
        GRAYSCALE_SOFTCOPY_PRESENTATION_STATE,
        PRESENTATION_STATE,
        PRESENTATION_STATE_SERIES,
        ReferencedSeriesSequence=[
            synthetic.item(
                SeriesInstanceUID=synthetic.CT_SERIES,
                ReferencedImageSequence=[
                    synthetic.reference(synthetic.CT_IMAGE_STORAGE, uid)
                    for uid in synthetic.CT_SLICES[:2]
                ],
            )
        ],
    )
    dataset.Modality = "PR"
    dataset.InstanceNumber = 1
    dataset.ContentLabel = "ANNOTATED"
    dataset.PresentationCreationDate = "20240305"
    dataset.PresentationCreationTime = "101500"
    dataset.DisplayedAreaSelectionSequence = [
        synthetic.item(
            DisplayedAreaTopLeftHandCorner=[1, 1],
            DisplayedAreaBottomRightHandCorner=[2, 2],
            PresentationSizeMode="SCALE TO FIT",
            PresentationPixelSpacing=["1", "1"],
        )
    ]
    dataset.PresentationLUTShape = "IDENTITY"
    dataset.GraphicLayerSequence = [
        synthetic.item(GraphicLayer="LAYER", GraphicLayerOrder=1)
    ]
    if annotations:
        dataset.GraphicAnnotationSequence = annotations
    return dataset


def _image():
    """A CT slice with two curve groups, which its IOD does not define."""
    dataset = synthetic.ct_slice(0)
    dataset.Modality = "CT"
    for group in (0x5000, 0x5002):
        dataset.add_new(group << 16 | 0x0005, "US", 2)  # Curve Dimensions
        dataset.add_new(group << 16 | 0x0010, "US", 1)  # Number of Points
        dataset.add_new(group << 16 | 0x0020, "CS", "POLY")  # Type of Data
        dataset.add_new(group << 16 | 0x0022, "LO", "SENTINEL CURVE")
        dataset.add_new(group << 16 | 0x3000, "OW", b"SENTINEL")  # Curve Data
    return dataset


def _found(state=None, image=None):
    """A Presentation State and an image, as read members."""
    state = synthetic.written(_state(_annotations()) if state is None else state)
    image = synthetic.written(_image() if image is None else image)
    return (
        (
            PinnedMember(
                CARDIAC,
                "23089164/" + "0" * 32,
                1,
                hashlib.sha256(state).hexdigest(),
                GRAYSCALE_SOFTCOPY_PRESENTATION_STATE,
            ),
            state,
        ),
        (
            PinnedMember(
                "sydney_braveheart_rt_image",
                "P01.zip",
                2,
                hashlib.sha256(image).hexdigest(),
                synthetic.CT_IMAGE_STORAGE,
            ),
            image,
        ),
    )


def _unmet(summary):
    return {
        each["expectation"]: each["not_met_for"]
        for each in summary["expectations"]
        if not each["met"]
    }


def test_each_expectation_is_met_where_the_engine_follows_the_design():
    summary = check(_found())

    assert summary["format"] == FORMAT
    assert summary["met"], _unmet(summary)
    assert [each["expectation"] for each in summary["expectations"]] == list(
        EXPECTATIONS
    )
    state, image = summary["members"]
    assert state["holds"]["graphic_annotations"] == 4
    assert state["holds"]["set_sizes"] == [3]
    runs = state["runs"]
    # Kept alone, an annotation shown with others is held until they are
    # decided on together, and one that names the patient is held whatever.
    assert runs["each_kept"]["annotations"] == {
        "held: echoes-identifier": 1,
        "held: not-reviewed-together": 2,
        "kept": 1,
    }
    assert runs["each_and_sets_kept"]["outcome"] == "held"
    assert runs["each_and_sets_kept"]["passes"] == 2
    assert runs["each_and_sets_kept"]["annotations"] == {
        "held: echoes-identifier": 1,
        "kept": 3,
    }
    assert runs["echoes_removed"]["outcome"] == "released"
    assert runs["echoes_removed"]["list"] == {
        "keep": 3,
        "keep together": 1,
        "remove": 1,
    }
    assert runs["echoes_removed"]["written"]["graphic_annotations"] == 3
    assert runs["echoes_removed"]["written"]["kept_as_received"] == 3
    # Without the label and the name, no two of those left are shown
    # together, so the list needs no decision on a set.
    assert runs["text_removed"]["outcome"] == "released"
    assert runs["text_removed"]["passes"] == 1
    assert runs["text_removed"]["written"]["graphic_annotations"] == 2
    assert image["holds"] == {"graphics": ["curve_data"], "curve_groups": 2}
    assert image["differences"] == {
        "added": [],
        "removed": [],
        "differ": ["(0012,0063)", "(0012,0064)"],
    }
    assert not summary["crashed"]


def test_the_summary_and_its_page_hold_no_value_of_an_instance():
    summary = check(_found())
    written = json.dumps(summary) + markdown(summary)

    assert "SENTINEL" not in written
    assert synthetic.PATIENTS_NAME not in written
    assert "2.25." not in written
    for annotation in _annotations():
        assert annotation_digest(annotation) not in written


def test_a_presentation_state_without_annotations_fails_by_its_label():
    summary = check(_found(state=_state([])))

    assert not summary["met"]
    unmet = _unmet(summary)
    assert unmet[EXPECTATIONS[0]] == [f"{CARDIAC} #1"]
    assert EXPECTATIONS[7] not in unmet


def test_an_engine_that_does_not_apply_the_option_fails(monkeypatch):
    monkeypatch.setattr(runs_module, "_OPTION", (policy.MODIFIED_DATES,))

    unmet = _unmet(check(_found()))

    assert unmet[EXPECTATIONS[8]] == ["sydney_braveheart_rt_image #2"]
    assert unmet[EXPECTATIONS[9]] == ["sydney_braveheart_rt_image #2"]


def test_a_member_that_raises_is_counted_by_where_never_by_its_message():
    state = b"SENTINEL" * 64
    member = PinnedMember(
        CARDIAC,
        "23089164/" + "0" * 32,
        1,
        hashlib.sha256(state).hexdigest(),
        GRAYSCALE_SOFTCOPY_PRESENTATION_STATE,
    )

    summary = check(((member, state), _found()[1]))

    assert sum(summary["crashed"].values()) == 1
    assert _unmet(summary)[EXPECTATIONS[-1]] == [f"{CARDIAC} #1"]
    assert "SENTINEL" not in json.dumps(summary) + markdown(summary)


def test_main_writes_the_summary_and_its_page(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(check_module, "read_members", _found)
    out = tmp_path / "results"

    assert main(["check", "--out", str(out)]) == 0

    summary = json.loads((out / JSON_NAME).read_text(encoding="utf-8"))
    page = (out / MARKDOWN_NAME).read_text(encoding="utf-8")
    assert summary["met"]
    assert page == markdown(summary)
    assert capsys.readouterr().out == page


def test_main_fails_unless_every_expectation_is_met(monkeypatch, tmp_path):
    monkeypatch.setattr(check_module, "read_members", lambda: _found(state=_state([])))

    assert main(["check", "--out", str(tmp_path / "results")]) == 1


def test_main_refuses_an_existing_out(tmp_path):
    with pytest.raises(SystemExit, match="must not exist"):
        main(["check", "--out", str(tmp_path)])


def test_each_table_of_the_page_has_the_columns_of_its_header():
    page = markdown(check(_found()))
    tables = [
        [line for line in block.splitlines() if line.startswith("|")]
        for block in page.split("\n\n")
    ]

    for rows in (each for each in tables if each):
        assert {row.count(" | ") for row in rows} == {rows[0].count(" | ")}
