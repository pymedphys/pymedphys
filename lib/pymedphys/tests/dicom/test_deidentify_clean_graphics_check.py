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

# pylint: disable = too-many-lines

"""The check of the Clean Graphics Option on public human DICOM, on
synthetic archives and files: its pins, its reads, its runs and their
expectations, and that it writes no value of an instance. Values that must
never reach its output carry the text ``SENTINEL``."""

import dataclasses
import hashlib
import io
import json
import zipfile

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import clean_graphics_check as check_module
from pymedphys._dicom.deidentify import clean_graphics_runs as runs_module
from pymedphys._dicom.deidentify import (
    compound_actions,
    instance_transform,
    pixel_cleaning,
    pixel_risk,
    policy,
)
from pymedphys._dicom.deidentify.clean_graphics_check import (
    DCM4CHE_COMMIT,
    FORMAT,
    GRAYSCALE_SOFTCOPY_PRESENTATION_STATE,
    IDC_BUCKET,
    JSON_NAME,
    MARKDOWN_NAME,
    MEMBERS,
    OBJECT_COLLECTIONS,
    OBJECTS,
    PET_IMAGE,
    RT_IMAGE,
    CheckRefused,
    PinnedMember,
    PinnedObject,
    check,
    main,
    markdown,
    read_members,
    read_objects,
)
from pymedphys._dicom.deidentify.clean_graphics_runs import (
    EXPECTATIONS,
    SECONDARY_CAPTURE,
    stored_values_changed,
    unused_bits,
)
from pymedphys._dicom.deidentify.reviewed_annotations import annotation_digest
from pymedphys._dicom.deidentify.synthetic_corpus import (
    MULTI_FRAME_GRAYSCALE_WORD_SC_IMAGE_STORAGE,
)
from pymedphys._dicom.deidentify.text_evaluation_archives import (
    ARCHIVES,
    ZenodoArchive,
)
from pymedphys._dicom.deidentify.text_detection import TextBox
from pymedphys._dicom.deidentify.text_evaluation_frames import EvaluationRefused
from pymedphys._dicom.deidentify.text_evaluation_idc import OPEN_COLLECTIONS
from pymedphys._dicom.deidentify.text_evaluation_idc import SOURCE as IDC_HOST

from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

CARDIAC = "zenodo_cardiac_mr_0p55t"
KNEE = "zenodo_knee_mr_0p55t"
ACRIN = "acrin_flt_breast"
DCM4CHE = "dcm4che_test_data"
OBJECT_SERIES = "00000000-0000-4000-8000-000000000001"
OBJECT_INSTANCE = "00000000-0000-4000-8000-000000000002"
OBJECT_KEY = f"{OBJECT_SERIES}/{OBJECT_INSTANCE}.dcm"
CAPTURE_KEY = "ovly_p01.dcm"
PRESENTATION_STATE = "2.25.701"
ACTIVATING_STATE = "2.25.702"
PRESENTATION_STATE_SERIES = "2.25.700"
RT_IMAGE_INSTANCE = "2.25.801"
RT_IMAGE_SERIES = "2.25.800"
CAPTURE_INSTANCE = "2.25.901"
CAPTURE_SERIES = "2.25.900"
# The expectations of the images, and of every file written under the option.
(
    GROUPS_REMOVED,
    MARKERS_ONLY,
    SEQUESTERED_UNCLEANED,
    CLEARED_AND_HELD,
    ACTIVATION_KEPT,
    CLAIMED_AND_CLEAN,
) = EXPECTATIONS[7:13]


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


def _object(data, **changes):
    pin = {
        "collection": ACRIN,
        "key": OBJECT_KEY,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "sop_class": synthetic.CT_IMAGE_STORAGE,
    }
    pin.update(changes)
    return PinnedObject(**pin)


def _served(data, refused=False):
    def opener(_pinned):
        if refused:
            raise EvaluationRefused("SENTINEL")
        return io.BytesIO(data)

    return opener


def test_each_object_is_read_whole_from_its_place_in_the_bucket():
    data = synthetic.written(_overlaid())
    pinned = _object(data)

    found = read_objects((pinned,), opener=_served(data))

    assert found == ((pinned, data),)
    assert pinned.url == f"https://idc-open-data.s3.amazonaws.com/{OBJECT_KEY}"
    assert pinned.label == f"{ACRIN} 00000000"


def test_dcm4che_test_data_is_read_at_its_pinned_commit():
    pinned = PinnedObject(DCM4CHE, CAPTURE_KEY, 1, "0" * 64, SECONDARY_CAPTURE)

    assert pinned.url == (
        f"https://raw.githubusercontent.com/dcm4che/dcm4che/{DCM4CHE_COMMIT}"
        f"/dcm4che-test-data/src/main/resources/{CAPTURE_KEY}"
    )
    assert pinned.label == f"{DCM4CHE} ovly_p01"


@pytest.mark.parametrize(
    "case",
    [
        "a shorter object",
        "a longer object",
        "another digest",
        "another SOP Class",
        "an object that is not served",
    ],
)
def test_an_object_unlike_its_pin_is_refused(case):
    data = synthetic.written(_overlaid())
    pinned = _object(data)
    served = data
    if case == "a shorter object":
        served = data[:-1]
    elif case == "a longer object":
        served = data + b"\x00"
    elif case == "another digest":
        pinned = _object(data, sha256="2" * 64)
    elif case == "another SOP Class":
        pinned = _object(data, sop_class=PET_IMAGE)

    with pytest.raises(CheckRefused) as refused:
        read_objects(
            (pinned,),
            opener=_served(served, refused=case == "an object that is not served"),
        )

    assert "SENTINEL" not in str(refused.value)
    assert pinned.sha256 not in str(refused.value)
    assert OBJECT_INSTANCE not in str(refused.value)


@pytest.mark.parametrize(
    "change",
    [
        {"collection": "SENTINEL"},
        # An open collection of IDC, but not one that the check reads.
        {"collection": "tcga_brca"},
        {"key": "SENTINEL"},
        # IDC's identifiers, and the bucket's keys, are lower case.
        {"key": "A" + OBJECT_KEY[1:]},
        {"key": f"{OBJECT_SERIES}/../{OBJECT_INSTANCE}.dcm"},
        # A key of the other collection's form.
        {"key": CAPTURE_KEY},
        {"collection": DCM4CHE},
        {"collection": DCM4CHE, "key": f"../{CAPTURE_KEY}"},
        {"size": 0},
        {"sha256": "SENTINEL"},
    ],
)
def test_an_object_pinned_out_of_range_is_refused(change):
    pin = {
        "collection": ACRIN,
        "key": OBJECT_KEY,
        "size": 1,
        "sha256": "0" * 64,
        "sop_class": PET_IMAGE,
    }
    pin.update(change)

    with pytest.raises(CheckRefused) as refused:
        PinnedObject(**pin)

    assert "SENTINEL" not in str(refused.value)


def test_every_pinned_object_is_of_a_pinned_collection_and_named_apart():
    labels = [each.label for each in (*MEMBERS, *OBJECTS)]
    from_idc = [each for each in OBJECT_COLLECTIONS.values() if each.base == IDC_BUCKET]

    # Each of IDC's collections is one that the text detector's evaluation
    # vetted, under the licence that it vetted.
    assert [each.name for each in from_idc] == [ACRIN]
    assert all(each.host == IDC_HOST for each in from_idc)
    assert all(each.licence == OPEN_COLLECTIONS[each.name] for each in from_idc)
    assert all(name == each.name for name, each in OBJECT_COLLECTIONS.items())
    assert len({(each.collection, each.key) for each in OBJECTS}) == len(OBJECTS)
    assert len(set(labels)) == len(labels)


def test_every_pinned_instance_is_read_the_members_first(monkeypatch):
    monkeypatch.setattr(check_module, "read_members", lambda: ("members",))
    monkeypatch.setattr(check_module, "read_objects", lambda: ("objects",))

    assert check_module.read_pinned() == ("members", "objects")


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


def _activating():
    """A Presentation State without annotations whose one overlay group
    holds only Overlay Activation Layer, which shows the overlay of group
    6000 of the slices that it references on its one graphic layer."""
    dataset = _state([])
    dataset.SOPInstanceUID = ACTIVATING_STATE
    dataset.ContentLabel = "ACTIVATING"
    dataset.GraphicLayerSequence = [
        synthetic.item(GraphicLayer="SENTINEL", GraphicLayerOrder=1)
    ]
    dataset.add_new(0x60001001, "CS", "SENTINEL")  # Overlay Activation Layer
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


def _overlaid():
    """A CT slice with an overlay group that holds Overlay Data and an
    Overlay Description, as ACRIN-FLT-Breast's PET images do."""
    dataset = synthetic.ct_slice(1)
    dataset.Modality = "CT"
    dataset.add_new(0x60000010, "US", 8)  # Overlay Rows
    dataset.add_new(0x60000011, "US", 8)  # Overlay Columns
    dataset.add_new(0x60000022, "LO", "SENTINEL OVERLAY")  # Overlay Description
    dataset.add_new(0x60000040, "CS", "G")  # Overlay Type
    dataset.add_new(0x60000050, "SS", [1, 1])  # Overlay Origin
    dataset.add_new(0x60000100, "US", 1)  # Overlay Bits Allocated
    dataset.add_new(0x60000102, "US", 0)  # Overlay Bit Position
    dataset.add_new(0x60003000, "OW", b"SENTINEL")  # Overlay Data, 8 by 8
    return dataset


def _capture():
    """A Secondary Capture of 12-bit stored values, with an overlay in each
    of bits 14 and 15 of Pixel Data and one overlay group with Overlay Data,
    as dcm4che's test pattern holds them."""
    dataset = synthetic.instance(SECONDARY_CAPTURE, CAPTURE_INSTANCE, CAPTURE_SERIES)
    dataset.Modality = "OT"
    dataset.ConversionType = "WSD"
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.Rows = dataset.Columns = 8
    dataset.BitsAllocated, dataset.BitsStored, dataset.HighBit = 16, 12, 11
    dataset.PixelRepresentation = 0
    words = (np.arange(64) * 37 % 4096).astype("<u2")
    words[::3] |= 1 << 14
    words[1::5] |= 1 << 15
    dataset.PixelData = words.tobytes()
    for group, bit in ((0x6000, 14), (0x6002, 15), (0x6004, 0)):
        dataset.add_new(group << 16 | 0x0010, "US", 8)  # Overlay Rows
        dataset.add_new(group << 16 | 0x0011, "US", 8)  # Overlay Columns
        dataset.add_new(group << 16 | 0x0040, "CS", "G")  # Overlay Type
        dataset.add_new(group << 16 | 0x0050, "SS", [1, 1])  # Overlay Origin
        dataset.add_new(group << 16 | 0x0100, "US", 16 if bit else 1)
        dataset.add_new(group << 16 | 0x0102, "US", bit)  # Overlay Bit Position
    dataset.add_new(0x60043000, "OW", b"SENTINEL")  # Overlay Data, 8 by 8
    return dataset


# Stored values with bit 14 or 15 set, of the 64 of _capture().
CAPTURE_UNUSED_BITS = len(set(range(0, 64, 3)) | set(range(1, 64, 5)))


class _Finder:
    """Finds one region of text in each frame."""

    # What decides its regions, as the method digest takes it.
    method = {"finder": "one region", "version": 1}

    def find(self, _frame) -> tuple[TextBox, ...]:
        return (TextBox(1, 1, 3, 3),)


def _check(found, detector=_Finder):
    return check(found, detector=detector)


def _found(state=None, activating=None, image=None, overlaid=None, capture=None):
    """A Presentation State with annotations, one without annotations whose
    overlay group holds only Overlay Activation Layer, and three images, one
    with curves, one with an overlay, and a Secondary Capture with overlays
    in unused bits of Pixel Data, as read members and objects."""
    state = synthetic.written(_state(_annotations()) if state is None else state)
    activating = synthetic.written(_activating() if activating is None else activating)
    image = synthetic.written(_image() if image is None else image)
    overlaid = synthetic.written(_overlaid() if overlaid is None else overlaid)
    capture = _capture() if capture is None else capture
    captured = synthetic.written(capture)
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
                KNEE,
                "23964089/" + "0" * 32,
                3,
                hashlib.sha256(activating).hexdigest(),
                GRAYSCALE_SOFTCOPY_PRESENTATION_STATE,
            ),
            activating,
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
        (_object(overlaid), overlaid),
        (
            _object(
                captured,
                collection=DCM4CHE,
                key=CAPTURE_KEY,
                sop_class=str(capture.SOPClassUID),
            ),
            captured,
        ),
    )


def _unmet(summary):
    return {
        each["expectation"]: each["not_met_for"]
        for each in summary["expectations"]
        if not each["met"]
    }


def test_each_expectation_is_met_where_the_engine_follows_the_design():
    summary = _check(_found())

    assert summary["format"] == FORMAT
    assert summary["met"], _unmet(summary)
    assert [each["expectation"] for each in summary["expectations"]] == list(
        EXPECTATIONS
    )
    state, activating, image, overlaid, capture = summary["members"]
    assert state["holds"]["graphic_annotations"] == 4
    assert state["holds"]["set_sizes"] == [3]
    assert state["holds"]["activation_only_overlay_groups"] == 0
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
    markers = {"added": [], "removed": [], "differ": ["(0012,0063)", "(0012,0064)"]}
    # Its overlay group only shows an overlay of the slices that it
    # references, so it is not an overlay, and nothing is decided by a list.
    assert activating["holds"]["graphics"] == []
    assert activating["holds"]["graphic_annotations"] == 0
    assert activating["holds"]["activation_only_overlay_groups"] == 1
    assert list(activating["runs"]) == ["modified_dates", "no_list"]
    for ran in activating["runs"].values():
        assert ran["outcome"] == "released"
        assert ran["written"]["activation_only_overlay_groups"] == 1
    assert activating["differences"] == markers
    assert image["holds"] == {
        "graphics": ["curve_data"],
        "curve_groups": 2,
        "overlay_groups": 0,
    }
    assert image["differences"] == markers
    # Removing Overlay Data removes its whole group, under Modified Dates
    # alone as with the option.
    assert overlaid["holds"] == {
        "graphics": ["overlay_data"],
        "curve_groups": 0,
        "overlay_groups": 1,
    }
    for name in ("modified_dates", "no_list"):
        assert overlaid["runs"][name]["outcome"] == "released"
        assert overlaid["runs"][name]["written"]["overlay_groups"] == 0
    assert overlaid["differences"] == markers
    # Its overlays in unused bits leave it to Clean Pixel Data, which clears
    # them as it blacks out the text, and holds it for review.
    assert capture["holds"] == {
        "graphics": ["overlay_data", "overlay_in_pixel_data"],
        "curve_groups": 0,
        "overlay_groups": 3,
        "unused_bits": CAPTURE_UNUSED_BITS,
    }
    assert list(capture["runs"]) == ["modified_dates", "no_list", "with_pixel_data"]
    for name in ("modified_dates", "no_list"):
        assert capture["runs"][name] == {
            "outcome": "sequestered",
            "reasons": {"transform: secondary-capture-not-cleaned": 1},
        }
    cleaned = capture["runs"]["with_pixel_data"]
    assert cleaned["outcome"] == "held"
    assert cleaned["reasons"] == {"pixel-data: text-blacked-out": 1}
    assert cleaned["written"]["unused_bits"] == 0
    # Only the region of text that the finder found, of 2 by 2 pixels, holds
    # other stored values.
    assert cleaned["written"]["text_regions"] == 1
    assert cleaned["written"]["changed_outside_text_regions"] == 0
    assert cleaned["written"]["overlay_groups"] == 0
    assert cleaned["written"]["claims_clean_graphics"]
    assert "differences" not in capture
    assert "differences" not in state
    assert not summary["crashed"]
    assert summary["finder"] == _Finder.method
    assert summary["collections"][-2:] == [
        {
            "name": ACRIN,
            "host": "NCI Imaging Data Commons",
            "licence": "CC BY 3.0",
            "citation": "doi:10.7937/k9/tcia.2017.ol20zmxg",
        },
        {
            "name": DCM4CHE,
            "host": "GitHub",
            "licence": "MPL 1.1, GPL 2.0 or later, or LGPL 2.1 or later",
            "citation": (
                f"https://github.com/dcm4che/dcm4che/tree/{DCM4CHE_COMMIT}"
                "/dcm4che-test-data"
            ),
        },
    ]
    assert [each["name"] for each in summary["collections"]] == [
        CARDIAC,
        KNEE,
        "sydney_braveheart_rt_image",
        ACRIN,
        DCM4CHE,
    ]


def test_a_finder_that_finds_no_text_still_holds_the_capture_for_review():
    class Blind(_Finder):
        def find(self, _frame) -> tuple[TextBox, ...]:
            return ()

    summary = _check(_found(), detector=Blind)
    cleaned = summary["members"][-1]["runs"]["with_pixel_data"]

    assert summary["met"], _unmet(summary)
    assert cleaned["reasons"] == {"pixel-data: no-text-found": 1}
    assert cleaned["written"]["unused_bits"] == 0
    # Every stored value is compared, and none changes.
    assert cleaned["written"]["text_regions"] == 0
    assert cleaned["written"]["changed_outside_text_regions"] == 0


def test_the_finder_is_made_once_and_only_for_a_run_with_clean_pixel_data():
    made = []

    def detector():
        made.append(_Finder())
        return made[-1]

    without = _check(_found()[:-1], detector=detector)
    assert not made
    assert not without["finder"]
    assert "| Finder |" not in markdown(without)

    _check((*_found(), *_found()[-1:]), detector=detector)
    assert len(made) == 1


def test_a_finder_that_cannot_be_made_fails_by_where_it_raised():
    def detector():
        raise RuntimeError("SENTINEL")

    summary = _check(_found(), detector=detector)
    unmet = _unmet(summary)

    assert unmet[CLEARED_AND_HELD] == [f"{DCM4CHE} ovly_p01"]
    assert unmet[EXPECTATIONS[-1]] == [f"{DCM4CHE} ovly_p01"]
    assert sum(summary["crashed"].values()) == 1
    assert "SENTINEL" not in json.dumps(summary) + markdown(summary)


def test_the_summary_and_its_page_hold_no_value_of_an_instance():
    summary = _check(_found())
    written = json.dumps(summary) + markdown(summary)

    assert "SENTINEL" not in written
    assert synthetic.PATIENTS_NAME not in written
    assert "2.25." not in written
    assert OBJECT_SERIES not in written
    assert OBJECT_INSTANCE not in written
    for annotation in _annotations():
        assert annotation_digest(annotation) not in written


def test_a_presentation_state_without_annotations_or_activation_fails_by_its_label():
    summary = _check(_found(state=_state([])))

    assert not summary["met"]
    unmet = _unmet(summary)
    assert unmet[ACTIVATION_KEPT] == [f"{CARDIAC} #1"]
    assert unmet[EXPECTATIONS[0]] == ["no instance"]
    assert GROUPS_REMOVED not in unmet


def test_an_image_without_curves_or_overlay_data_fails_by_its_label():
    image = synthetic.ct_slice(0)
    image.Modality = "CT"

    unmet = _unmet(_check(_found(image=image)))

    assert unmet[GROUPS_REMOVED] == ["sydney_braveheart_rt_image #2"]


def test_an_engine_that_removes_overlay_data_without_its_group_fails(monkeypatch):
    # Removing Overlay Data alone from a CT Image, which requires it in its
    # group, sequesters the image (D-020).
    monkeypatch.setattr(
        compound_actions, "_overlay_plane_is_user_optional", lambda _iod: False
    )

    unmet = _unmet(_check(_found()))

    assert unmet[GROUPS_REMOVED] == [f"{ACRIN} 00000000"]
    assert unmet[MARKERS_ONLY] == [f"{ACRIN} 00000000"]


def test_an_engine_that_does_not_clear_an_overlay_in_pixel_data_fails(monkeypatch):
    # As though no overlay group placed its overlay in unused bits: Clean
    # Pixel Data then finds those bits set, and cannot clean the capture.
    monkeypatch.setattr(instance_transform, "overlay_planes", lambda *_: 0)

    unmet = _unmet(_check(_found()))

    assert unmet[CLEARED_AND_HELD] == [f"{DCM4CHE} ovly_p01"]


def test_an_engine_that_changes_stored_values_outside_the_text_fails(monkeypatch):
    # As though clearing the overlays cleared every stored bit too, and the
    # engine's own check of its write missed it.
    monkeypatch.setattr(
        pixel_cleaning,
        "_cleared",
        lambda _layout, words, _overlays: np.zeros_like(words),
    )
    monkeypatch.setattr(instance_transform, "redaction_problem", lambda *_: False)

    summary = _check(_found())
    cleaned = summary["members"][-1]["runs"]["with_pixel_data"]

    assert _unmet(summary)[CLEARED_AND_HELD] == [f"{DCM4CHE} ovly_p01"]
    assert cleaned["outcome"] == "held"
    assert cleaned["written"]["unused_bits"] == 0
    assert cleaned["written"]["changed_outside_text_regions"] > 0


def test_an_image_with_an_overlay_in_pixel_data_that_is_not_a_capture_fails():
    # A CT slice is released with its overlay's bits cleared under Clean
    # Graphics, which no expectation of this check covers yet.
    capture = _capture()
    capture.SOPClassUID = synthetic.CT_IMAGE_STORAGE
    capture.Modality = "CT"

    unmet = _unmet(_check(_found(capture=capture)))

    assert unmet[SEQUESTERED_UNCLEANED] == [f"{DCM4CHE} ovly_p01"]


def test_a_multi_frame_capture_is_held_to_a_capture_s_expectations():
    # Each of the five Secondary Capture SOP Classes is sequestered without
    # Clean Pixel Data, and not only Secondary Capture Image Storage.
    capture = _capture()
    capture.SOPClassUID = MULTI_FRAME_GRAYSCALE_WORD_SC_IMAGE_STORAGE
    capture.NumberOfFrames = 1
    capture.FrameIncrementPointer = 0x00182001  # Page Number Vector
    capture.PageNumberVector = [1]

    summary = _check(_found(capture=capture))

    assert summary["met"], _unmet(summary)
    runs = summary["members"][-1]["runs"]
    assert runs["no_list"]["reasons"] == {"transform: secondary-capture-not-cleaned": 1}
    assert runs["with_pixel_data"]["outcome"] == "held"


def test_an_engine_that_does_not_apply_the_option_fails(monkeypatch):
    monkeypatch.setattr(runs_module, "_OPTION", (policy.MODIFIED_DATES,))

    unmet = _unmet(_check(_found()))

    assert unmet[MARKERS_ONLY] == [
        "sydney_braveheart_rt_image #2",
        f"{ACRIN} 00000000",
    ]
    assert unmet[ACTIVATION_KEPT] == [f"{KNEE} #3"]
    assert unmet[CLAIMED_AND_CLEAN] == [
        f"{KNEE} #3",
        "sydney_braveheart_rt_image #2",
        f"{ACRIN} 00000000",
    ]


def test_an_engine_that_takes_an_activation_for_an_overlay_fails(monkeypatch):
    # As the engine did before it read a group that holds only Overlay
    # Activation Layer as no overlay.
    monkeypatch.setattr(pixel_risk, "_OVERLAY_ACTIVATION_LAYER_ELEMENT", None)

    unmet = _unmet(_check(_found()))

    assert unmet[ACTIVATION_KEPT] == [f"{KNEE} #3"]


@pytest.mark.parametrize("kept", ["none", "another value"])
def test_a_file_written_without_the_activation_as_received_fails(monkeypatch, kept):
    # pylint: disable-next = protected-access
    written = runs_module._written

    def altered(data):
        found = written(data)
        if not found.claims_clean_graphics:
            return found
        layers = tuple(
            pydicom.DataElement(each.tag, each.VR, "OTHER")
            for each in found.activation_layers
            if kept == "another value"
        )
        return dataclasses.replace(found, activation_layers=layers)

    monkeypatch.setattr(runs_module, "_written", altered)

    unmet = _unmet(_check(_found()))

    assert list(unmet) == [ACTIVATION_KEPT]
    assert unmet[ACTIVATION_KEPT] == [f"{KNEE} #3"]


def test_a_member_that_raises_is_counted_by_where_never_by_its_message():
    state = b"SENTINEL" * 64
    member = PinnedMember(
        CARDIAC,
        "23089164/" + "0" * 32,
        1,
        hashlib.sha256(state).hexdigest(),
        GRAYSCALE_SOFTCOPY_PRESENTATION_STATE,
    )

    summary = _check(((member, state), *_found()[1:]))

    assert sum(summary["crashed"].values()) == 1
    assert _unmet(summary)[EXPECTATIONS[-1]] == [f"{CARDIAC} #1"]
    assert "SENTINEL" not in json.dumps(summary) + markdown(summary)


def test_main_writes_the_summary_and_its_page(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(check_module, "read_pinned", _found)
    monkeypatch.setattr(check_module, "_detector", _Finder)
    out = tmp_path / "results"

    assert main(["check", "--out", str(out)]) == 0

    summary = json.loads((out / JSON_NAME).read_text(encoding="utf-8"))
    page = (out / MARKDOWN_NAME).read_text(encoding="utf-8")
    assert summary["met"]
    assert page == markdown(summary)
    assert capsys.readouterr().out == page


def test_main_fails_unless_every_expectation_is_met(monkeypatch, tmp_path):
    monkeypatch.setattr(check_module, "read_pinned", lambda: _found(state=_state([])))
    monkeypatch.setattr(check_module, "_detector", _Finder)

    assert main(["check", "--out", str(tmp_path / "results")]) == 1


def test_main_refuses_an_existing_out(tmp_path):
    with pytest.raises(SystemExit, match="must not exist"):
        main(["check", "--out", str(tmp_path)])


def test_each_table_of_the_page_has_the_columns_of_its_header():
    page = markdown(_check(_found()))
    tables = [
        [line for line in block.splitlines() if line.startswith("|")]
        for block in page.split("\n\n")
    ]

    for rows in (each for each in tables if each):
        assert {row.count(" | ") for row in rows} == {rows[0].count(" | ")}


def _stored(words, *, bits_stored=12, signed=False, transfer_syntax=None):
    """A data set of one frame of 16-bit stored ``words``, read back from
    its file."""
    dataset = synthetic.ct_slice(0)
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = "MONOCHROME2"
    dataset.Rows, dataset.Columns = 1, len(words)
    dataset.BitsAllocated, dataset.BitsStored = 16, bits_stored
    dataset.HighBit = bits_stored - 1
    dataset.PixelRepresentation = int(signed)
    dataset.PixelData = np.asarray(words, dtype="<u2").tobytes()
    syntax = transfer_syntax or synthetic.EXPLICIT_VR_LITTLE_ENDIAN
    return synthetic.read(synthetic.written(dataset, syntax))


def test_unused_bits_count_the_values_that_hold_more_than_their_sign():
    # 12-bit values, unsigned: any bit above bit 11 is unused.
    assert unused_bits(_stored([1, 1 << 12, 1 << 15 | 5, 4095])) == 2
    # Signed: each unused bit holds the sign, so -1 and -2048 hold no more.
    signed = [0xFFFF, 0xF800, 0x07FF, 0x0800, 0xF7FF]
    assert unused_bits(_stored(signed, signed=True)) == 2
    # Every bit is stored, so none is unused.
    assert unused_bits(_stored([0xFFFF, 0], bits_stored=16)) == 0
    # Read as stored, and the same in Implicit VR Little Endian.
    implicit = _stored([1 << 13], transfer_syntax=synthetic.IMPLICIT_VR_LITTLE_ENDIAN)
    assert unused_bits(implicit) == 1


def test_stored_values_changed_count_stored_bits_outside_the_regions():
    source = _stored([1, 2 | 1 << 14, 3, 4])
    # Clearing a bit above High Bit changes no stored value.
    assert stored_values_changed(source, _stored([1, 2, 3, 4]), ()) == 0
    # A changed stored value counts, unless a region of text holds it.
    written = _stored([1, 2, 0, 4])
    assert stored_values_changed(source, written, ()) == 1
    assert stored_values_changed(source, written, (TextBox(0, 2, 1, 3),)) == 0
    # A region past the frame's edge holds its part within the frame.
    assert stored_values_changed(source, written, (TextBox(0, 2, 5, 9),)) == 0
    # The stored bits end at High Bit: here bits 4 to 15.
    source, same, other = (_stored(each) for each in ([16, 1], [16, 2], [32, 1]))
    for each in (source, same, other):
        each.HighBit = 15
    assert stored_values_changed(source, same, ()) == 0
    assert stored_values_changed(source, other, ()) == 1


def _colour(words, planar):
    """One row of two pixels of three samples, as ``planar`` stores them."""
    dataset = _stored(words)
    dataset.Columns = 2
    dataset.SamplesPerPixel = 3
    dataset.PlanarConfiguration = planar
    return dataset


def test_stored_values_changed_read_each_planar_configuration():
    source = [1, 2, 3, 4, 5, 6]
    written = [1, 2, 3, 4, 0, 6]
    # The fifth word is the second pixel's second sample by pixel, and the
    # first pixel's third sample by plane; the region holds the second pixel.
    region = (TextBox(0, 1, 1, 2),)
    for planar, changed in ((0, 0), (1, 1)):
        assert (
            stored_values_changed(
                _colour(source, planar), _colour(written, planar), region
            )
            == changed
        )


def test_stored_values_changed_need_pixel_data_described_alike():
    source = _stored([1, 2])
    # A written file that took the unused bits for stored ones.
    assert stored_values_changed(source, _stored([1, 2], bits_stored=16), ()) is None
    compressed = _stored([1, 2])
    compressed.file_meta.TransferSyntaxUID = "1.2.840.10008.1.2.5"  # RLE Lossless
    assert stored_values_changed(source, compressed, ()) is None
    assert stored_values_changed(compressed, compressed, ()) is None
    short = _stored([1, 2])
    short.PixelData = short.PixelData[:2]
    assert stored_values_changed(source, short, ()) is None
    undescribed = _stored([1, 2])
    del undescribed.BitsStored
    assert stored_values_changed(undescribed, undescribed, ()) is None


def test_unused_bits_are_not_read_without_native_pixel_data():
    assert unused_bits(synthetic.read(synthetic.written(synthetic.ct_slice(0)))) is None
    stored = _stored([1 << 13])
    stored.file_meta.TransferSyntaxUID = "1.2.840.10008.1.2.5"  # RLE Lossless
    assert unused_bits(stored) is None
    stored = _stored([1 << 13])
    stored.BitsAllocated = 1
    assert unused_bits(stored) is None
