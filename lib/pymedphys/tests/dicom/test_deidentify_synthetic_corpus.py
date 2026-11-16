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

"""The synthetic corpus, its markers, and its manifest."""

# Every check reads the one corpus and its manifest, so the checks stay in
# one module.
# pylint: disable = too-many-lines

import bisect
import collections
import datetime
import io
import json
import re
import warnings

from pymedphys._imports import numpy, pydicom, pytest

from pymedphys._dicom.deidentify import (
    compound_actions,
    dummy_values,
    elements,
    icc_profiles,
    scope,
    standard,
    structured_content,
    synthetic_content_trees,
)
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.dates import MAX_OFFSET_WEEKS, MIN_OFFSET_WEEKS
from pymedphys._dicom.deidentify.file_layout import (
    ElementPath,
    Region,
    read_file_layout,
)
from pymedphys._dicom.deidentify.reference_graph import build_reference_graph
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.sop_classes import iod_for_sop_class
from pymedphys._dicom.deidentify.source import read_source
from pymedphys._dicom.deidentify.values import value_problem, values_problem

pytestmark = pytest.mark.pydicom

Kind = corpus_module.PlacementKind
Reason = corpus_module.NotPlantedReason
IMPLICIT = "1.2.840.10008.1.2"
EXPLICIT = "1.2.840.10008.1.2.1"
# The kinds whose values no other placement holds.
UNIQUE_KINDS = frozenset({Kind.PLANTED, Kind.CONTENT, Kind.PRIVATE, Kind.UN_ENCODED})
TEXT = r"SYNMK-\d{5}"
# The conspicuous form of a marker of each VR, written out independently.
MARKER_PATTERNS = {
    **dict.fromkeys(("AE", "LO", "LT", "SH", "ST", "UC", "UT", "UN", "OB", "OW"), TEXT),
    "AS": r"\d{3}W",
    "CS": r"SYNMK_\d{5}",
    "DA": r"(09|1[0-8])\d\d(0[1-9]|1[0-2])\d\d",
    "DS": r"8\d{5}\.5",
    "DT": r"(09|1[0-8])\d\d(0[1-9]|1[0-2])\d{8}",
    "IS": r"7\d{5}",
    "PN": r"SYNMK(\d{5})\^M[AÄ]RKER\1",
    "TM": r"([01]\d|2[0-3])[0-5]\d[0-5]\d\.424242",
    "UI": r"2\.25\.99999\d{5}",
    "UR": r"https://synmk\.invalid/SYNMK-\d{5}",
    "US": r"[1-9]\d{0,4}",
}
# The text VRs, whose markers are searched for as bytes.
TEXT_VRS = frozenset(MARKER_PATTERNS) - {"OB", "OW", "UN", "US"}
REFERENCED_SOP_CLASS = "(0008,1150)"
REFERENCED_SOP_INSTANCE = "(0008,1155)"
CONTENT_SEQUENCE = "(0040,A730)"
# The kinds that leave a value that the residual search can find.
MARKERS = frozenset({Kind.PLANTED, Kind.CONTENT})
# The IODs that each name their root template, in the order of their files.
TEMPLATE_IODS = (
    "Key Object Selection Document",
    "Mammography CAD SR",
    "Chest CAD SR",
    "Colon CAD SR",
    "Procedure Log",
    "Spectacle Prescription Report",
    "Macular Grid Thickness and Volume Report",
    "Waveform Annotation SR",
)
LINKED_PATTERNS = {
    Kind.LINKED_UID: r"2\.25\.88888\d{5}",
    Kind.LINKED_PATIENT: r"SYNMK-LINKED-(PATIENT|ISSUER)",
}


@pytest.fixture(name="corpus", scope="module")
def fixture_corpus():
    return corpus_module.build_corpus()


def _placements(corpus, *kinds):
    """Yield each file and placement of the given kinds, or of every kind."""
    for file in corpus.files:
        for placement in file.manifest.placements:
            if not kinds or placement.kind in kinds:
                yield file, placement


def _profile_rows():
    rows = standard.load_table_e1_1().attributes
    return [row.tag for row in rows if row.tag != standard.PRIVATE_ATTRIBUTES_TAG]


def _expected_places(iod):
    """Return each path and tag where the IOD defines an attribute of Table E.1-1."""
    rows = _profile_rows()
    exact = set(rows)
    masked = [row for row in rows if "x" in row]

    def covered(tag):
        return tag in exact or any(
            len(mask) == len(tag) and all(m in ("x", t) for m, t in zip(mask, tag))
            for mask in masked
        )

    return {
        (definition.path, definition.tag)
        for definition in iod.definitions
        if covered(definition.tag)
    }


class _Reader:
    """Read the elements of one file through the engine's decoder."""

    def __init__(self, data):
        self.evidence = read_source(data)
        dataset = self.evidence.dataset()
        codecs = elements.dataset_codecs(dataset, source=self.evidence)
        self._items = {(): (dataset, codecs, ())}

    def _item(self, within):
        if within not in self._items:
            dataset, codecs, ancestors = self._item(within[:-1])
            tag, index = within[-1]
            sequence = elements.read_element(
                dataset,
                ElementPath(within[:-1], tag),
                codecs,
                ancestors,
                source=self.evidence,
            )
            item = sequence.items[index]
            codecs = elements.dataset_codecs(item, codecs, within, source=self.evidence)
            self._items[within] = (item, codecs, (dataset, *ancestors))
        return self._items[within]

    def read(self, path):
        dataset, codecs, ancestors = self._item(path.items)
        return elements.read_element(
            dataset, path, codecs, ancestors, source=self.evidence
        )


def _number(tag):
    return int(tag[1:5] + tag[6:10], 16)


def _as_text(value):
    if isinstance(value, bytes):
        return value.decode("ascii").rstrip("\x00 ")
    return str(value)


def test_two_builds_are_byte_identical(corpus):
    again = corpus_module.build_corpus()

    assert [file.data for file in again.files] == [file.data for file in corpus.files]
    assert again.manifest == corpus.manifest
    assert again.manifest.to_json() == corpus.manifest.to_json()


def test_the_build_is_the_same_with_pydicoms_future_behaviour(
    corpus, pydicom_behaviour
):
    del pydicom_behaviour  # the build runs under each behaviour

    again = corpus_module.build_corpus()

    assert [file.data for file in again.files] == [file.data for file in corpus.files]


def test_files_have_deterministic_names_and_the_linked_collection(corpus):
    assert [file.name for file in corpus.files] == [
        "01-ct-1.dcm",
        "02-ct-2.dcm",
        "03-ct-3.dcm",
        "04-rtstruct.dcm",
        "05-rtplan.dcm",
        "06-rtdose.dcm",
        "07-rtdose-review.dcm",
        "08-ct-enhanced.dcm",
        "09-ct-legacy-enhanced.dcm",
        "10-mr.dcm",
        "11-mr-enhanced.dcm",
        "12-mr-enhanced-color.dcm",
        "13-mr-legacy-enhanced.dcm",
        "14-mr-spectroscopy.dcm",
        "15-pet.dcm",
        "16-pet-enhanced.dcm",
        "17-pet-legacy-enhanced.dcm",
        "18-registration.dcm",
        "19-registration-deformable.dcm",
        "20-rt-beams-record.dcm",
        "21-rt-image.dcm",
        "22-sr-dose-x-ray.dcm",
        "23-sr-dose-radiopharmaceutical.dcm",
        "24-sr-basic-text.dcm",
        "25-sr-enhanced.dcm",
        "26-sr-comprehensive.dcm",
        "27-sr-comprehensive-3d.dcm",
        "28-sr-extensible.dcm",
        "29-sr-dose-enhanced-x-ray.dcm",
        "30-sr-dose-patient.dcm",
        "31-sr-dose-ct.dcm",
        "32-seg.dcm",
        "33-seg-label-map.dcm",
        "34-sr-key-object-selection.dcm",
        "35-sr-mammography-cad.dcm",
        "36-sr-chest-cad.dcm",
        "37-sr-colon-cad.dcm",
        "38-sr-procedure-log.dcm",
        "39-sr-spectacle-prescription.dcm",
        "40-sr-macular-grid.dcm",
        "41-sr-waveform-annotation.dcm",
        "47-rt-ion-plan.dcm",
        "48-rt-ion-beams-record.dcm",
        "49-rt-brachy-record.dcm",
        "50-rt-treatment-summary-record.dcm",
        "51-parametric-map.dcm",
        "52-real-world-value-mapping.dcm",
        "53-nm.dcm",
        "54-encapsulated-pdf.dcm",
        "55-seg-surface.dcm",
        "56-pr-grayscale.dcm",
        "57-pr-color.dcm",
        "58-pr-pseudo-color.dcm",
        "59-pr-blending.dcm",
        "60-pr-xa-xrf-grayscale.dcm",
        "61-pr-variable-modality-lut.dcm",
        "70-rt-segment-annotation.dcm",
        "71-rt-radiation-set.dcm",
        "72-c-arm-radiation.dcm",
        "73-tomotherapeutic-radiation.dcm",
        "74-robotic-arm-radiation.dcm",
        "75-rt-beams-delivery-instruction.dcm",
        "76-rt-brachy-delivery-instruction.dcm",
        "77-rt-radiation-set-delivery-instruction.dcm",
        "89-rt-image-enhanced.dcm",
        "90-rt-image-enhanced-continuous.dcm",
    ]
    assert [file.manifest.iod for file in corpus.files] == [
        "CT Image",
        "CT Image",
        "CT Image",
        "RT Structure Set",
        "RT Plan",
        "RT Dose",
        "RT Dose",
        "Enhanced CT Image",
        "Legacy Converted Enhanced CT Image",
        "MR Image",
        "Enhanced MR Image",
        "Enhanced MR Color Image",
        "Legacy Converted Enhanced MR Image",
        "MR Spectroscopy",
        "Positron Emission Tomography Image",
        "Enhanced PET Image",
        "Legacy Converted Enhanced PET Image",
        "Spatial Registration",
        "Deformable Spatial Registration",
        "RT Beams Treatment Record",
        "RT Image",
        "X-Ray Radiation Dose SR",
        "Radiopharmaceutical Radiation Dose SR",
        "Basic Text SR",
        "Enhanced SR",
        "Comprehensive SR",
        "Comprehensive 3D SR",
        "Extensible SR",
        "Enhanced X-Ray Radiation Dose SR",
        "Patient Radiation Dose SR",
        "X-Ray Radiation Dose SR",
        "Segmentation",
        "Segmentation",
        *TEMPLATE_IODS,
        "RT Ion Plan",
        "RT Ion Beams Treatment Record",
        "RT Brachy Treatment Record",
        "RT Treatment Summary Record",
        "Parametric Map",
        "Real World Value Mapping",
        "Nuclear Medicine Image",
        "Encapsulated PDF",
        "Surface Segmentation",
        "Grayscale Softcopy Presentation State",
        "Color Softcopy Presentation State",
        "Pseudo-Color Softcopy Presentation State",
        "Blending Softcopy Presentation State",
        "XA/XRF Grayscale Softcopy Presentation State",
        "Variable Modality LUT Softcopy Presentation State",
        "RT Segment Annotation",
        "RT Radiation Set",
        "C-Arm Photon-Electron Radiation",
        "Tomotherapeutic Radiation",
        "Robotic-Arm Radiation",
        "RT Beams Delivery Instruction",
        "RT Brachy Application Setup Delivery Instruction",
        "RT Radiation Set Delivery Instruction",
        "Enhanced RT Image",
        "Enhanced Continuous RT Image",
    ]
    # Counted from the start, so that a file added at the end moves none.
    assert corpus_module.STRUCTURED_REPORT_FILES == tuple(
        file.name for file in corpus.files[21:31] + corpus.files[33:41]
    )
    assert corpus_module.SEGMENTATION_FILES == tuple(
        file.name for file in corpus.files[31:33]
    )
    assert (
        corpus_module.ION_PLAN_FILE,
        corpus_module.ION_TREATMENT_RECORD_FILE,
    ) == tuple(file.name for file in corpus.files[41:43])
    assert (
        corpus_module.BRACHY_TREATMENT_RECORD_FILE,
        corpus_module.TREATMENT_SUMMARY_RECORD_FILE,
    ) == tuple(file.name for file in corpus.files[43:45])
    assert (
        corpus_module.PARAMETRIC_MAP_FILE,
        corpus_module.REAL_WORLD_VALUE_MAPPING_FILE,
    ) == tuple(file.name for file in corpus.files[45:47])
    assert corpus_module.NM_FILE == corpus.files[47].name
    assert corpus_module.ENCAPSULATED_PDF_FILE == corpus.files[48].name
    assert corpus_module.SURFACE_SEGMENTATION_FILE == corpus.files[49].name
    assert corpus_module.PRESENTATION_STATE_FILES == tuple(
        file.name for file in corpus.files[50:56]
    )
    assert {file.manifest.sop_class for file in corpus.files[50:56]} == (
        corpus_module.PRESENTATION_STATE_STORAGE_CLASSES
    )
    assert (
        corpus_module.ENHANCED_RT_IMAGE_FILE,
        corpus_module.ENHANCED_CONTINUOUS_RT_IMAGE_FILE,
    ) == tuple(file.name for file in corpus.files[64:66])
    assert (
        corpus_module.SEGMENT_ANNOTATION_FILE,
        corpus_module.RADIATION_SET_FILE,
        corpus_module.C_ARM_RADIATION_FILE,
        corpus_module.TOMOTHERAPEUTIC_RADIATION_FILE,
        corpus_module.ROBOTIC_ARM_RADIATION_FILE,
    ) == tuple(file.name for file in corpus.files[56:61])
    assert (
        corpus_module.BEAMS_DELIVERY_INSTRUCTION_FILE,
        corpus_module.BRACHY_DELIVERY_INSTRUCTION_FILE,
        corpus_module.RADIATION_SET_DELIVERY_INSTRUCTION_FILE,
    ) == tuple(file.name for file in corpus.files[61:64])
    # Every IOD of the first supported release.
    assert {file.manifest.iod for file in corpus.files} == scope.SUPPORTED_IODS


def _in_content_tree(path):
    """Return whether a path is below a report's Content Sequence."""
    return bool(path.items) and path.items[0][0] == CONTENT_SEQUENCE


def test_every_attribute_of_table_e1_1_that_the_iod_defines_is_placed(corpus):
    for file in corpus.files:
        iod = iod_for_sop_class(file.manifest.sop_class)
        expected = _expected_places(iod)
        found = collections.Counter()
        for placement in file.manifest.placements:
            path = placement.path
            if placement.kind in (Kind.PRIVATE, Kind.CONTENT, Kind.REVIEW_COPY):
                continue
            if placement.concept is not None or (
                file.name in corpus_module.STRUCTURED_REPORT_FILES
                and _in_content_tree(path)
            ):
                # A content item's value, or a reference, in its report's
                # content tree, whose template decides where it is. The
                # Encapsulated PDF has no template, and its Content Sequence's
                # places are recorded like any other.
                continue
            if any(index for _, index in path.items):
                # The structure set's references to the other slices.
                assert placement.kind is Kind.LINKED_UID
                continue
            # A repeating group is planted in its first group.
            tag = re.sub(r"^\((50|60)00,", r"(\1xx,", path.tag)
            if (tuple(each for each, _ in path.items), tag) not in expected:
                tag = path.tag
            found[tuple(each for each, _ in path.items), tag] += 1
            if placement.kind is Kind.NOT_PLANTED:
                assert placement.reason is not None
            elif placement.kind is Kind.SEQUENCE:
                assert placement.reason in (
                    None,
                    Reason.NO_MARKER_CARRIER,
                    Reason.KEPT_SEQUENCE,
                    Reason.CONTENT_TREE,
                )
            else:
                assert placement.reason is None

        if file.name in corpus_module.STRUCTURED_REPORT_FILES:
            # The tree's items decide what is below the Content Sequence.
            expected = {
                (path, tag) for path, tag in expected if path[:1] != ("(0040,A730)",)
            }
        assert set(found) == expected, file.name
        assert max(found.values()) == 1, file.name


# The attributes of Table E.1-1 that an instance of the corpus's IODs defines
# only below the depth cap: five items deep in a functional group of the
# Enhanced RT Images, Radiation Generation Mode Label and Description, in the
# items of Radiation Generation Mode Sequence (300A,067B), and Referenced
# Treatment Position Group UID, in those of Treatment Position Group Sequence
# (300A,060A). Their actions are tested on an Enhanced RT Image apart, in
# test_deidentify_instance_transform.py. In the RT Radiation Set Delivery
# Instruction, Referenced, Constituent, and Source Conceptual Volume UID lie
# five or six items deep, in the Conceptual Volume Macro of a task's patient
# position displacement; the RT Radiation Set and the radiations hold them
# less deep, and their actions in the instruction are tested apart there too.
ONLY_BEYOND_THE_DEPTH_CAP = {
    "(300A,067C)",
    "(300A,067D)",
    "(300A,0785)",
    "(3010,000B)",
    "(3010,0013)",
    "(3010,0015)",
}


def test_attributes_are_not_planted_only_beyond_the_depth_cap(corpus):
    reasons = collections.Counter()
    beyond = set()
    for file in corpus.files:
        placed = file.manifest.placements
        planted_tags = {p.path.tag for p in placed if p.kind is not Kind.NOT_PLANTED}
        for placement in placed:
            depth = len(placement.path.items)
            if placement.kind is Kind.NOT_PLANTED:
                reasons[placement.reason] += 1
                assert placement.values == ()
                if placement.reason in (
                    Reason.SEQUESTERS_INSTANCE,
                    Reason.CONTENT_TREE,
                ):
                    continue
                assert depth + (placement.vr == "SQ") > corpus_module.MAX_DEPTH
                # Each attribute capped is planted at a shallower place, but
                # those that the corpus's IODs define only below the cap.
                if placement.path.tag not in planted_tags:
                    beyond.add(placement.path.tag)
            elif not _in_content_tree(placement.path):
                # A report's template, not the cap, decides its tree's depth.
                assert depth <= corpus_module.MAX_DEPTH

    assert beyond == ONLY_BEYOND_THE_DEPTH_CAP
    assert set(reasons) == {
        Reason.DEPTH_CAP,
        Reason.SEQUESTERS_INSTANCE,
        Reason.CONTENT_TREE,
    }


# The sequences whose D a reviewed rule writes (D-021).
REVIEWED_DUMMY_SEQUENCES = {"(0040,1101)", "(0008,1111)", "(0040,A073)"}
# Institution Code Sequence's reviewed rule holds only directly in an item of
# Interlock Resolution User Sequence (D-021).
INSTITUTION_CODE_SEQUENCE = "(0008,0082)"
INTERLOCK_RESOLUTION_USER = "(300A,0746)"


def _reviewed(tag, path):
    """Return whether a reviewed rule writes D's value for a sequence at a place."""
    if tag == INSTITUTION_CODE_SEQUENCE:
        return path[-1:] == (INTERLOCK_RESOLUTION_USER,)
    return tag in REVIEWED_DUMMY_SEQUENCES


def _resolved(iod, tag, path):
    """Return the Basic Profile's action on a place, resolved by Type."""
    rows = {row.tag: row for row in standard.load_table_e1_1().attributes}
    if tag not in rows:
        return None
    action = rows[tag].basic_profile
    if action in compound_actions.COMPOUND_ACTIONS:
        return compound_actions.resolve_in_iod(iod, tag, path, action)
    return compound_actions.resolve_plain_in_iod(iod, tag, path, action)


def _sequesters_at(iod, tag, path, row):
    """Return whether the Basic Profile's action on a place sequesters.

    A plain X does where it removes an attribute that the IOD requires outside
    every Type 3 sequence (D-020), and a D where the VR has no dummy value and
    no reviewed rule gives one, unless a removed sequence encloses it (D-021).
    """
    rows = {each.tag: each for each in standard.load_table_e1_1().attributes}
    if rows[row].basic_profile == "X":
        return (
            compound_actions.resolve_plain_x_in_iod(iod, tag, path).extent
            is compound_actions.RemovalExtent.SEQUESTER
        )
    return (
        not _reviewed(tag, path)
        and not set(standard.dictionary_attribute(tag).vrs) & dummy_values.DUMMY_VRS
        and _resolved(iod, tag, path) == "D"
        and not any(
            _resolved(iod, path[depth], path[:depth]) == "X"
            for depth in range(len(path))
        )
    )


def _sequesters(iod, placement):
    """Return whether the Basic Profile's action on a placement sequesters.

    So it does within a sequence whose own action sequesters. A content
    item's value takes its concept's row of Table E.3.4-1, not a row of
    Table E.1-1, so only its enclosing sequences are judged here.
    """
    rows = {row.tag: row for row in standard.load_table_e1_1().attributes}
    path = tuple(tag for tag, _ in placement.path.items)
    own = placement.concept is None and _sequesters_at(
        iod, placement.path.tag, path, placement.profile_tag
    )
    return own or any(
        path[depth] in rows
        and _sequesters_at(iod, path[depth], path[:depth], path[depth])
        for depth in range(len(path))
    )


def test_an_attribute_whose_removal_sequesters_is_planted_in_one_instance(corpus):
    planted = collections.defaultdict(set)
    withheld = collections.defaultdict(set)
    for file, placement in _placements(corpus, Kind.PLANTED, Kind.NOT_PLANTED):
        iod = iod_for_sop_class(file.manifest.sop_class)
        if placement.concept is not None:
            # A content item's value, which its report's Content Sequence
            # holds, and whose D sequesters each report (D-021).
            assert file.name in corpus_module.STRUCTURED_REPORT_FILES
            assert _sequesters(iod, placement), placement
            continue
        if placement.reason is Reason.SEQUESTERS_INSTANCE:
            assert _sequesters(iod, placement), placement
            withheld[file.name].add(placement.path.tag)
        elif placement.kind is Kind.PLANTED and _sequesters(iod, placement):
            planted[file.name].add(placement.path.tag)

    # Responsible Person and Responsible Organization (D-020), only in the
    # third slice, so that the other instances can be released; and the
    # Enhanced PET Image's Radiopharmaceutical Start DateTime in no file.
    # Each report's Verifying Observer Sequence, which a reviewed rule keeps
    # with dummy values (D-021), the Requested Procedure ID of its Referenced
    # Request Sequence, which a plain X empties there (D-020), the
    # Institution Code Sequence of each treatment record's interlock
    # resolution user, whose dummy item a reviewed rule writes (D-021), and
    # Source Manufacturer in the RT Brachy Treatment Record's Recorded Source
    # Sequence, which a plain X empties there too, are planted.
    # Each softcopy Presentation State's Graphic Annotation Sequence, whose D
    # a sequence has no dummy value for (D-021), with what its item holds,
    # its Presentation Creation Date and Time, which a plain X removes where
    # they are Type 1 (D-020), and, but in the blending one, whose IOD has no
    # Overlay Plane Module, its Overlay Data, which a plain X removes where
    # the module is conditional, are planted in no file.
    both = {"(0010,2297)", "(0010,2299)"}
    annotation = {
        "(0070,0001)",  # Graphic Annotation Sequence
        "(0008,1140)",  # Referenced Image Sequence, in its item
        "(0008,1155)",  # Referenced SOP Instance UID, in that item
        "(0062,0021)",  # Tracking UID, in its item
        "(0070,0006)",  # Unformatted Text Value, in its Text Object Sequence
    }
    creation = {"(0070,0082)", "(0070,0083)"}
    overlay = {"(6000,3000)"}
    pdf = iod_for_sop_class(corpus_module.ENCAPSULATED_PDF_STORAGE)
    only_in = {
        "Enhanced PET Image": {"(0018,1078)"},
        # The document, Content Sequence and every nested item are omitted.
        "Encapsulated PDF": {"(0042,0011)", CONTENT_SEQUENCE}
        | {
            tag
            for path, tag in _expected_places(pdf)
            if path[:1] == (CONTENT_SEQUENCE,)
        },
        **dict.fromkeys(
            (
                "Grayscale Softcopy Presentation State",
                "Color Softcopy Presentation State",
                "Pseudo-Color Softcopy Presentation State",
                "XA/XRF Grayscale Softcopy Presentation State",
                "Variable Modality LUT Softcopy Presentation State",
            ),
            annotation | creation | overlay,
        ),
        "Blending Softcopy Presentation State": annotation | creation,
    }
    assert planted == {corpus_module.SEQUESTERED_FILE: both}
    assert corpus_module.SEQUESTERED_FILE == corpus.files[2].name
    assert withheld == {
        file.name: both | only_in.get(file.manifest.iod, set())
        for file in corpus.files
        if file.name != corpus_module.SEQUESTERED_FILE
    }


@pytest.mark.parametrize(
    ("name", "session"),
    [
        ("20-rt-beams-record.dcm", "(3008,0020)"),
        (corpus_module.ION_TREATMENT_RECORD_FILE, "(3008,0021)"),
    ],
)
def test_each_interlock_users_institution_code_sequence_is_planted(
    corpus, name, session
):
    # A reviewed rule writes its dummy item there (D-021), so the corpus
    # plants it, with markers in the Table E.1-1 attributes of its item, for
    # the runs to check that they are gone.
    (file,) = (each for each in corpus.files if each.name == name)
    user = (session, "(300A,0740)", "(300A,0746)")
    placements = [
        placement
        for placement in file.manifest.placements
        if tuple(tag for tag, _ in placement.path.items) == user
        and placement.path.tag == INSTITUTION_CODE_SEQUENCE
    ]
    assert [placement.kind for placement in placements] == [Kind.SEQUENCE]
    item = (*user, INSTITUTION_CODE_SEQUENCE)
    inside = {
        placement.path.tag: placement.kind
        for placement in file.manifest.placements
        if tuple(tag for tag, _ in placement.path.items) == item
    }
    # Context Group Version and Context Group Local Version.
    assert inside == {"(0008,0106)": Kind.PLANTED, "(0008,0107)": Kind.PLANTED}


def test_markers_are_unique_and_conspicuous(corpus):
    seen = collections.Counter()
    for _, placement in _placements(corpus, *UNIQUE_KINDS):
        assert placement.values, placement
        for value in placement.values:
            assert re.fullmatch(MARKER_PATTERNS[placement.vr], value), placement
            seen[value] += 1
    for kind, pattern in LINKED_PATTERNS.items():
        for _, placement in _placements(corpus, kind):
            assert re.fullmatch(pattern, placement.values[0]), placement

    assert seen and max(seen.values()) == 1
    numbers = [
        int(match.group(1))
        for value in seen
        if (match := re.search(r"SYNMK[-_]?(\d{5})", value))
    ]
    assert len(numbers) == len(set(numbers))


def test_dates_are_distinct_valid_dates_before_1900(corpus):
    dates = [
        value[:8]
        for _, placement in _placements(corpus, Kind.PLANTED)
        if placement.vr in ("DA", "DT")
        for value in placement.values
    ]

    assert dates and len(dates) == len(set(dates))
    assert all(value_problem("DA", date) is None for date in dates)
    assert all("0900" <= date[:4] <= "1899" for date in dates)


def test_no_date_shifted_under_modified_dates_is_another_markers(corpus):
    # The Modified Dates Option moves a subject's dates back by 52 to 520
    # whole weeks, so no two marker dates may be that far apart, or a
    # shifted date would be another marker's, which the residual search
    # finds.
    days = sorted(
        datetime.date(int(value[:4]), int(value[4:6]), int(value[6:8])).toordinal()
        for _, placement in _placements(corpus, Kind.PLANTED)
        if placement.vr in ("DA", "DT")
        for value in placement.values
    )
    shortest, longest = 7 * MIN_OFFSET_WEEKS, 7 * MAX_OFFSET_WEEKS

    assert days[-1] - days[0] > longest
    for day in days:
        within = bisect.bisect_right(days, day + longest) - bisect.bisect_left(
            days, day + shortest
        )
        assert within == 0, datetime.date.fromordinal(day)


def test_values_read_back_and_are_valid_for_their_vr_and_vm(corpus):
    for file in corpus.files:
        reader = _Reader(file.data)
        for placement in file.manifest.placements:
            # The invalid UID marker is checked in its own test.
            if placement.kind in (
                Kind.NOT_PLANTED,
                Kind.PRIVATE,
                Kind.UN_ENCODED,
                Kind.INVALID,
            ):
                continue
            attribute = standard.dictionary_attribute(placement.path.tag)
            element = reader.read(placement.path)
            if placement.kind is Kind.SEQUENCE:
                assert element.vr == "SQ" and len(element.items) >= 1
                continue
            values = [_as_text(value) for value in element.values]

            assert tuple(values) == placement.values, placement.path
            assert element.vr == placement.vr
            assert values_problem(attribute.vr, attribute.vm, element.values) is None


def test_binary_private_and_un_values_hold_their_marker(corpus):
    for file, placement in _placements(corpus, Kind.PRIVATE, Kind.UN_ENCODED):
        evidence = read_source(file.data)
        field = evidence.value_field(placement.path)
        (text,) = placement.values

        assert field.rstrip(b"\x00 ") == text.encode("ascii")
        assert values_problem(placement.vr, "1", [text]) is None or (
            placement.vr == "UN"
        )


def test_every_file_is_admitted_by_the_strict_reader(corpus):
    for file in corpus.files:
        evidence = read_source(file.data)
        for placement in file.manifest.placements:
            assert (placement.path in evidence) == (
                placement.kind is not Kind.NOT_PLANTED
            ), placement


def test_the_reference_graph_has_no_findings(corpus):
    graph = build_reference_graph(
        [InstanceRecord.from_file(file.data) for file in corpus.files]
    )

    assert not graph.findings
    targets = {(edge.source, edge.target) for edge in graph.edges}
    # The structure set references every slice, the plan the structure set
    # and the dose, and each dose the plan.
    assert {(3, 0), (3, 1), (3, 2), (4, 3), (4, 5), (5, 4), (6, 4)} <= targets
    # The MR and PET Images reference the first slice, each other image the
    # single-frame one of its modality, the treatment record the plan, the RT
    # Ion Plan the structure set, the dose, and the plan, the RT Ion Beams
    # Treatment Record the RT Ion Plan, the RT Brachy Treatment Record the
    # plan and the RT Beams Treatment Record, the RT Treatment Summary Record
    # the plan and the RT Brachy Treatment Record, the Parametric Map the MR
    # Image, the Real World Value Mapping the PET Image, the RT Beams and RT
    # Brachy Application Setup Delivery Instructions the plan, and the RT
    # Radiation Set Delivery Instruction the RT Radiation Set.
    names = [file.name for file in corpus.files]
    position = names.index
    sources = {
        "08-ct-enhanced.dcm": "01-ct-1.dcm",
        "09-ct-legacy-enhanced.dcm": "01-ct-1.dcm",
        "10-mr.dcm": "01-ct-1.dcm",
        "11-mr-enhanced.dcm": "10-mr.dcm",
        "12-mr-enhanced-color.dcm": "10-mr.dcm",
        "13-mr-legacy-enhanced.dcm": "10-mr.dcm",
        "14-mr-spectroscopy.dcm": "10-mr.dcm",
        "15-pet.dcm": "01-ct-1.dcm",
        "16-pet-enhanced.dcm": "15-pet.dcm",
        "17-pet-legacy-enhanced.dcm": "15-pet.dcm",
        "20-rt-beams-record.dcm": "05-rtplan.dcm",
        "48-rt-ion-beams-record.dcm": "47-rt-ion-plan.dcm",
        "49-rt-brachy-record.dcm": "05-rtplan.dcm",
        "51-parametric-map.dcm": "10-mr.dcm",
        "52-real-world-value-mapping.dcm": "15-pet.dcm",
        "75-rt-beams-delivery-instruction.dcm": "05-rtplan.dcm",
        "76-rt-brachy-delivery-instruction.dcm": "05-rtplan.dcm",
        "77-rt-radiation-set-delivery-instruction.dcm": "71-rt-radiation-set.dcm",
    }
    assert {
        (position(source), position(target)) for source, target in sources.items()
    } <= targets
    ion_plan = position("47-rt-ion-plan.dcm")
    assert {(ion_plan, 3), (ion_plan, 4), (ion_plan, 5)} <= targets
    summary = position("50-rt-treatment-summary-record.dcm")
    brachy = position("49-rt-brachy-record.dcm")
    beams = position("20-rt-beams-record.dcm")
    assert {(brachy, beams), (summary, 4), (summary, brachy)} <= targets
    # The Surface Segmentation names the first slice, from which its surface
    # was generated.
    surface = position(corpus_module.SURFACE_SEGMENTATION_FILE)
    assert (surface, 0) in targets


def test_each_treatment_record_names_its_own_plan_with_its_class(corpus):
    # The RT Ion Beams Treatment Record's Referenced RT Plan Sequence names the
    # RT Ion Plan, with its Storage SOP Class, as the RT Beams Treatment
    # Record's names the RT Plan, and the RT Brachy Treatment Record's and the
    # RT Treatment Summary Record's name the RT Plan, whose application setups
    # the brachy record records.
    files = {file.name: file for file in corpus.files}
    for record, plan, sop_class in (
        (
            "20-rt-beams-record.dcm",
            corpus_module.PLAN,
            corpus_module.RT_PLAN_STORAGE,
        ),
        (
            corpus_module.ION_TREATMENT_RECORD_FILE,
            corpus_module.ION_PLAN,
            corpus_module.RT_ION_PLAN_STORAGE,
        ),
        (
            corpus_module.BRACHY_TREATMENT_RECORD_FILE,
            corpus_module.PLAN,
            corpus_module.RT_PLAN_STORAGE,
        ),
        (
            corpus_module.TREATMENT_SUMMARY_RECORD_FILE,
            corpus_module.PLAN,
            corpus_module.RT_PLAN_STORAGE,
        ),
    ):
        dataset = pydicom.dcmread(pydicom.filebase.DicomBytesIO(files[record].data))
        (reference,) = dataset.ReferencedRTPlanSequence
        assert reference.ReferencedSOPInstanceUID == plan, record
        assert reference.ReferencedSOPClassUID == sop_class, record
    ion_plan = files[corpus_module.ION_PLAN_FILE].manifest
    assert ion_plan.sop_class == corpus_module.RT_ION_PLAN_STORAGE
    plan = pydicom.dcmread(pydicom.filebase.DicomBytesIO(files["05-rtplan.dcm"].data))
    assert "ApplicationSetupSequence" in plan


def test_the_brachy_and_summary_records_name_the_records_they_relate_to(corpus):
    # The RT Treatment Summary Record's Referenced Treatment Record Sequence
    # names the RT Brachy Treatment Record, and the RT Brachy Treatment
    # Record's names the RT Beams Treatment Record, each with its Storage SOP
    # Class, so the collection holds references from a record to a record of
    # another IOD.
    files = {file.name: file for file in corpus.files}
    for record, named, sop_class in (
        (
            corpus_module.TREATMENT_SUMMARY_RECORD_FILE,
            corpus_module.BRACHY_TREATMENT_RECORD,
            corpus_module.RT_BRACHY_TREATMENT_RECORD_STORAGE,
        ),
        (
            corpus_module.BRACHY_TREATMENT_RECORD_FILE,
            corpus_module.TREATMENT_RECORD,
            corpus_module.RT_BEAMS_TREATMENT_RECORD_STORAGE,
        ),
    ):
        dataset = pydicom.dcmread(pydicom.filebase.DicomBytesIO(files[record].data))
        assert dataset.Modality == "RTRECORD", record
        (reference,) = dataset.ReferencedTreatmentRecordSequence
        assert reference.ReferencedSOPInstanceUID == named, record
        assert reference.ReferencedSOPClassUID == sop_class, record
    for name, sop_class, iod in (
        (
            corpus_module.BRACHY_TREATMENT_RECORD_FILE,
            corpus_module.RT_BRACHY_TREATMENT_RECORD_STORAGE,
            "RT Brachy Treatment Record",
        ),
        (
            corpus_module.TREATMENT_SUMMARY_RECORD_FILE,
            corpus_module.RT_TREATMENT_SUMMARY_RECORD_STORAGE,
            "RT Treatment Summary Record",
        ),
    ):
        manifest = files[name].manifest
        assert (manifest.sop_class, manifest.iod) == (sop_class, iod)


def test_the_surface_segmentation_holds_a_closed_mesh_of_its_one_segment(corpus):
    files = {file.name: file for file in corpus.files}
    dataset = pydicom.dcmread(
        pydicom.filebase.DicomBytesIO(
            files[corpus_module.SURFACE_SEGMENTATION_FILE].data
        )
    )

    assert dataset.SOPClassUID == corpus_module.SURFACE_SEGMENTATION_STORAGE
    assert dataset.Modality == "SEG"
    assert "PixelData" not in dataset
    (segment,) = dataset.SegmentSequence
    (referenced,) = segment.ReferencedSurfaceSequence
    assert (segment.SurfaceCount, referenced.ReferencedSurfaceNumber) == (1, 1)
    (source,) = referenced.SegmentSurfaceSourceInstanceSequence
    assert source.ReferencedSOPInstanceUID == corpus_module.CT_SLICES[0]
    assert dataset.NumberOfSurfaces == 1
    (surface,) = dataset.SurfaceSequence
    assert (surface.FiniteVolume, surface.Manifold) == ("YES", "YES")
    (points,) = surface.SurfacePointsSequence
    coordinates = numpy.frombuffer(points.PointCoordinatesData, "<f4")
    assert points.NumberOfSurfacePoints * 3 == coordinates.size == 12
    (primitives,) = surface.SurfaceMeshPrimitivesSequence
    triangles = numpy.frombuffer(primitives.LongTrianglePointIndexList, "<u4")
    # Four triangles, of points indexed from 1, each edge shared by two.
    assert triangles.size == 12
    assert set(triangles.tolist()) == {1, 2, 3, 4}
    edges = collections.Counter(
        frozenset(pair)
        for triangle in triangles.reshape(4, 3).tolist()
        for pair in (
            (triangle[0], triangle[1]),
            (triangle[1], triangle[2]),
            (triangle[2], triangle[0]),
        )
    )
    assert len(edges) == 6 and set(edges.values()) == {2}


def test_the_delivery_instructions_name_what_they_instruct_with_its_class(corpus):
    # The RT Beams Delivery Instruction names the RT Plan, the RT Beams
    # Treatment Record of the session that it continues, and the RT Image as
    # a reference image; the RT Brachy Application Setup Delivery Instruction
    # names the RT Plan, within the plan's series of its study; and the RT
    # Radiation Set Delivery Instruction names the RT Radiation Set, and its
    # C-Arm Photon-Electron Radiation in each task and as omitted. Each is a
    # PLAN, as PS3.3 Sections A.64.4.1, A.79.4.1, and A.86.1.13.4.1 require.
    files = {file.name: file for file in corpus.files}

    def item(dataset, keywords):
        for keyword in keywords:
            (dataset,) = dataset[keyword].value
        return dataset

    for name, sop_class, iod, named in (
        (
            corpus_module.BEAMS_DELIVERY_INSTRUCTION_FILE,
            corpus_module.RT_BEAMS_DELIVERY_INSTRUCTION_STORAGE,
            "RT Beams Delivery Instruction",
            (
                (
                    ("ReferencedRTPlanSequence",),
                    corpus_module.PLAN,
                    corpus_module.RT_PLAN_STORAGE,
                ),
                (
                    ("ReferencedTreatmentRecordSequence",),
                    corpus_module.TREATMENT_RECORD,
                    corpus_module.RT_BEAMS_TREATMENT_RECORD_STORAGE,
                ),
                (
                    (
                        "BeamTaskSequence",
                        "DeliveryVerificationImageSequence",
                        "RelatedReferenceRTImageSequence",
                    ),
                    corpus_module.RT_IMAGE,
                    corpus_module.RT_IMAGE_STORAGE,
                ),
            ),
        ),
        (
            corpus_module.BRACHY_DELIVERY_INSTRUCTION_FILE,
            corpus_module.RT_BRACHY_APPLICATION_SETUP_DELIVERY_INSTRUCTION_STORAGE,
            "RT Brachy Application Setup Delivery Instruction",
            (
                (
                    (
                        "ReferencedRTPlanSequence",
                        "ReferencedSeriesSequence",
                        "ReferencedSOPSequence",
                    ),
                    corpus_module.PLAN,
                    corpus_module.RT_PLAN_STORAGE,
                ),
            ),
        ),
        (
            corpus_module.RADIATION_SET_DELIVERY_INSTRUCTION_FILE,
            corpus_module.RT_RADIATION_SET_DELIVERY_INSTRUCTION_STORAGE,
            "RT Radiation Set Delivery Instruction",
            (
                (
                    ("ReferencedRTRadiationSetSequence",),
                    corpus_module.RADIATION_SET,
                    corpus_module.RT_RADIATION_SET_STORAGE,
                ),
                (
                    ("RTRadiationTaskSequence", "ReferencedRTRadiationSequence"),
                    corpus_module.C_ARM_RADIATION,
                    corpus_module.C_ARM_PHOTON_ELECTRON_RADIATION_STORAGE,
                ),
                (
                    ("OmittedRadiationSequence", "ReferencedRTRadiationSequence"),
                    corpus_module.C_ARM_RADIATION,
                    corpus_module.C_ARM_PHOTON_ELECTRON_RADIATION_STORAGE,
                ),
            ),
        ),
    ):
        manifest = files[name].manifest
        assert (manifest.sop_class, manifest.iod) == (sop_class, iod)
        dataset = pydicom.dcmread(pydicom.filebase.DicomBytesIO(files[name].data))
        assert dataset.Modality == "PLAN", name
        for keywords, target, target_class in named:
            reference = item(dataset, keywords)
            assert reference.ReferencedSOPInstanceUID == target, keywords
            assert reference.ReferencedSOPClassUID == target_class, keywords
    plan = item(
        pydicom.dcmread(
            pydicom.filebase.DicomBytesIO(
                files[corpus_module.BRACHY_DELIVERY_INSTRUCTION_FILE].data
            )
        ),
        ("ReferencedRTPlanSequence",),
    )
    assert plan.StudyInstanceUID == corpus_module.STUDY
    (series,) = plan.ReferencedSeriesSequence
    assert series.SeriesInstanceUID == corpus_module.PLAN_SERIES


def test_two_instances_are_in_implicit_vr_and_the_rest_explicit(corpus):
    syntaxes = {
        file.name: read_source(file.data).transfer_syntax for file in corpus.files
    }

    assert syntaxes == {
        file.name: file.manifest.transfer_syntax for file in corpus.files
    }
    assert [name for name, syntax in syntaxes.items() if syntax == IMPLICIT] == [
        "06-rtdose.dcm",
        "10-mr.dcm",
    ]
    assert set(syntaxes.values()) == {IMPLICIT, EXPLICIT}


def test_an_element_is_encoded_as_un_in_explicit_vr(corpus):
    found = list(_placements(corpus, Kind.UN_ENCODED))

    assert len(found) == 1
    file, placement = found[0]
    evidence = read_source(file.data)
    assert evidence.transfer_syntax == EXPLICIT
    assert evidence.element(placement.path).vr == "UN"
    assert placement.path == ElementPath((), "(0010,4000)")
    assert placement.profile_tag == "(0010,4000)"


def test_each_file_has_private_blocks_at_the_top_level_and_in_an_item(corpus):
    for file in corpus.files:
        private = [
            placement
            for placement in file.manifest.placements
            if placement.kind is Kind.PRIVATE
        ]
        evidence = read_source(file.data)
        creators = [p for p in private if p.path.tag.endswith(",0010)")]

        assert {len(p.path.items) for p in creators} == {0, 1}
        assert all(int(p.path.tag[1:5], 16) % 2 for p in private)
        assert all(p.profile_tag == standard.PRIVATE_ATTRIBUTES_TAG for p in private)
        for placement in private:
            extent = evidence.element(placement.path)
            implicit = evidence.transfer_syntax == IMPLICIT
            assert extent.vr == (None if implicit else placement.vr)


def test_the_structure_set_has_a_second_character_set(corpus):
    (structure_set,) = [
        file for file in corpus.files if file.manifest.iod == "RT Structure Set"
    ]
    reader = _Reader(structure_set.data)
    path = ElementPath((), "(0010,0010)")
    element = reader.read(path)
    (placement,) = [p for p in structure_set.manifest.placements if p.path == path]

    assert structure_set.manifest.specific_character_set == "ISO_IR 100"
    assert element.codecs == ("latin_1",)
    assert not str(element.values[0]).isascii()
    assert str(element.values[0]) == placement.values[0]
    assert "Ä".encode("latin-1") in structure_set.data
    others = [file for file in corpus.files if file is not structure_set]
    assert all(not file.manifest.specific_character_set for file in others)


def test_sequences_hold_a_marker_unless_their_item_can_hold_none(corpus):
    without = set()
    kept = set()
    tree = set()
    for file in corpus.files:
        iod = iod_for_sop_class(file.manifest.sop_class)
        placed = file.manifest.placements
        for sequence in placed:
            if sequence.kind is not Kind.SEQUENCE:
                continue
            if sequence.reason is Reason.CONTENT_TREE:
                # The tree's items, which hold its own markers, decide what
                # the sequence holds.
                tree.add((file.name, sequence.path))
                continue
            inside = (*sequence.path.items, (sequence.path.tag, 0))
            # Linked UIDs survive a preset that keeps the sequence and
            # remaps its UIDs, so only a marker counts.
            below = [
                p
                for p in placed
                if p.path.items[: len(inside)] == inside and p.kind in MARKERS
            ]
            if below:
                assert sequence.reason is None, sequence.path
                continue
            if sequence.reason is Reason.KEPT_SEQUENCE:
                kept.add(sequence.path.tag)
                continue
            assert sequence.reason is Reason.NO_MARKER_CARRIER, sequence.path
            path = tuple(tag for tag, _ in inside)
            for definition in iod.definitions:
                if definition.path == path and "x" not in definition.tag:
                    attribute = standard.dictionary_attribute(definition.tag)
                    assert attribute.vr in ("SQ", "UI") or len(attribute.vrs) > 1
            without.add(sequence.path.tag)
        for content in (p for p in placed if p.kind is Kind.CONTENT):
            assert any(
                p.kind is Kind.SEQUENCE
                and (*p.path.items, (p.path.tag, 0)) == content.path.items
                for p in placed
            ), content.path

    # Modified Attributes Sequence, whose item holds any attribute modified,
    # and the reference sequences whose items hold only UIDs.
    assert {
        "(0400,0550)",
        "(0008,1110)",
        "(0008,1111)",
        "(0008,1120)",
        "(0008,1140)",
    } <= without
    # The Referenced Image Sequence that each registration requires in its
    # Registration Sequence or Deformable Registration Sequence, which the
    # Basic Profile keeps, replacing its UIDs.
    assert kept == {"(0008,1140)"}
    # The Content Sequence that each report's template builds.
    assert tree == {
        (name, ElementPath((), "(0040,A730)"))
        for name in corpus_module.STRUCTURED_REPORT_FILES
    }


def test_the_manifest_json_is_deterministic_and_matches_the_files(corpus):
    text = corpus.manifest.to_json()
    document = json.loads(text)

    assert text == corpus_module.build_corpus().manifest.to_json()
    assert text.isascii()
    assert document["max_depth"] == corpus_module.MAX_DEPTH
    assert [each["name"] for each in document["files"]] == [
        file.name for file in corpus.files
    ]
    for each, file in zip(document["files"], corpus.files):
        reader = _Reader(file.data)
        assert each["transfer_syntax"] == reader.evidence.transfer_syntax
        assert len(each["placements"]) == len(file.manifest.placements)
        for record in each["placements"]:
            path = ElementPath(
                tuple((tag, index) for tag, index in record["items"]), record["tag"]
            )
            if record["kind"] == "not-planted":
                assert path not in reader.evidence
                assert record["reason"] and not record["values"]
                continue
            if record["kind"] in ("private", "un-encoded", "invalid"):
                field = reader.evidence.value_field(path)
                assert field.rstrip(b"\x00 ").decode("ascii") == record["values"][0]
                continue
            element = reader.read(path)
            assert element.vr == record["vr"]
            assert [_as_text(value) for value in element.values] == record["values"]


def test_the_corpus_is_written_only_to_a_new_place(corpus, tmp_path):
    written = corpus_module.write_corpus(corpus, tmp_path)
    instances = tmp_path / corpus_module.INSTANCES_DIRECTORY

    assert written == (
        *(instances / file.name for file in corpus.files),
        tmp_path / "manifest.json",
    )
    assert [path.read_bytes() for path in written[:-1]] == [
        file.data for file in corpus.files
    ]
    assert written[-1].read_text(encoding="utf-8") == corpus.manifest.to_json()
    # The directory of instances, the input of a run, holds no manifest.
    assert sorted(path.name for path in instances.iterdir()) == [
        file.name for file in corpus.files
    ]
    with pytest.raises(FileExistsError):
        corpus_module.write_corpus(corpus, tmp_path)


def test_the_repr_shows_no_file_bytes(corpus):
    assert "data=" not in repr(corpus.files[0])


def test_every_defined_length_is_even(corpus):
    for file in corpus.files:
        layout = read_file_layout(file.data)
        checked = 0
        for extent in layout.elements:
            if extent.undefined_length:
                continue
            assert (extent.end - extent.value_start) % 2 == 0, (
                file.name,
                str(extent.location),
            )
            checked += 1
        # Nested elements are among those checked.
        assert any(
            extent.location.element.items
            for extent in layout.elements
            if extent.location.region is Region.DATA_SET
        )
        assert checked > 100


def test_each_text_marker_occurs_once_in_its_file(corpus):
    for file in corpus.files:
        codec = "latin-1" if file.manifest.specific_character_set else "ascii"
        for placement in file.manifest.placements:
            if placement.kind not in UNIQUE_KINDS or placement.vr not in TEXT_VRS:
                continue
            for value in placement.values:
                assert file.data.count(value.encode(codec)) == 1, (
                    file.name,
                    placement.path,
                )


def test_markers_have_five_digits_and_their_16_bit_integers_are_distinct(corpus):
    # Markers are numbered within five digits, and SS and US markers, the
    # negated and plain numbers of their own counts, each within its VR.
    assert corpus_module.MAX_MARKERS <= 10**5
    for vr, low, high in (("SS", -(2**15), -1), ("US", 1, 2**16 - 1)):
        values = [
            int(value)
            for _, placement in _placements(corpus, Kind.PLANTED)
            if placement.vr == vr
            for value in placement.values
        ]
        assert len(values) == len(set(values)), vr
        assert all(low <= value <= high for value in values), vr


def test_times_are_distinct(corpus):
    times = [
        value
        for _, placement in _placements(corpus, Kind.PLANTED)
        if placement.vr == "TM"
        for value in placement.values
    ]

    assert times and len(times) == len(set(times))


def test_every_planted_placement_covers_a_row_of_table_e1_1_or_e3_4_1(corpus):
    """A content item's value covers its concept's row of Table E.3.4-1.

    Its Text Value (0040,A160), for one, is not a row of Table E.1-1.
    """
    rows = set(_profile_rows())
    concepts = {
        concept.key for concept in structured_content.load_table_e3_4_1().concepts
    }
    for _, placement in _placements(corpus, Kind.PLANTED, Kind.SEQUENCE):
        if placement.concept is not None:
            assert placement.concept in concepts, placement.path
        else:
            assert placement.profile_tag in rows, placement.path


def test_every_reference_item_has_its_referenced_sop_class(corpus):
    for file in corpus.files:
        evidence = read_source(file.data)
        references = [
            p
            for p in file.manifest.placements
            if p.kind is Kind.LINKED_UID
            and p.path.items
            and p.path.tag == REFERENCED_SOP_INSTANCE
        ]
        assert references
        for placement in references:
            path = ElementPath(placement.path.items, REFERENCED_SOP_CLASS)
            assert path in evidence, (file.name, placement.path)


def test_patient_and_procedure_step_references_have_their_own_classes(corpus):
    reader = _Reader(corpus.files[0].data)
    expected = {
        "(0008,1120)": "1.2.840.10008.3.1.2.1.1",  # Detached Patient Management
        "(0008,1111)": "1.2.840.10008.3.1.2.3.3",  # Modality Performed Proc. Step
    }
    for sequence, sop_class in expected.items():
        items = ((sequence, 0),)
        target = reader.read(ElementPath(items, REFERENCED_SOP_INSTANCE)).values
        found = reader.read(ElementPath(items, REFERENCED_SOP_CLASS)).values

        assert found == (sop_class,)
        assert target[0] not in corpus_module.CT_SLICES


def test_the_items_private_block_is_in_a_sequence_pydicom_knows(corpus):
    for file in corpus.files:
        (creator,) = [
            p
            for p in file.manifest.placements
            if p.kind is Kind.PRIVATE and p.path.items and p.path.tag.endswith(",0010)")
        ]
        ((tag, _),) = creator.path.items
        number = int(tag[1:5] + tag[6:10], 16)
        dataset = pydicom.dcmread(pydicom.filebase.DicomBytesIO(file.data))

        assert pydicom.datadict.dictionary_has_tag(number)
        assert dataset[number].VR == "SQ"


def test_the_corpus_is_not_written_over_an_existing_file(corpus, tmp_path):
    instances = tmp_path / corpus_module.INSTANCES_DIRECTORY
    instances.mkdir()
    existing = instances / corpus.files[2].name
    existing.write_bytes(b"kept")

    with pytest.raises(FileExistsError):
        corpus_module.write_corpus(corpus, tmp_path)

    assert existing.read_bytes() == b"kept"
    assert [path.name for path in instances.iterdir()] == [existing.name]
    assert [path.name for path in tmp_path.iterdir()] == [instances.name]


def test_the_corpus_is_not_written_beside_an_existing_manifest(corpus, tmp_path):
    existing = tmp_path / "manifest.json"
    existing.write_text("kept", encoding="utf-8")

    with pytest.raises(FileExistsError):
        corpus_module.write_corpus(corpus, tmp_path)

    assert existing.read_text(encoding="utf-8") == "kept"
    assert [path.name for path in tmp_path.iterdir()] == [existing.name]


def test_a_second_dose_keeps_a_copy_of_a_marker_the_profile_replaces(corpus):
    names = [file.name for file in corpus.files]
    review = corpus.files[names.index(corpus_module.REVIEW_FILE)]
    plan = corpus.files[names.index("05-rtplan.dcm")]
    rows = {row.tag: row for row in standard.load_table_e1_1().attributes}

    (copy,) = [p for p in review.manifest.placements if p.kind is Kind.REVIEW_COPY]
    (label,) = [
        p
        for p in plan.manifest.placements
        if p.path == ElementPath((), "(300A,0002)") and p.kind is Kind.PLANTED
    ]
    # Manufacturer's Model Name, which Table E.1-1 does not list, holds the
    # plan's RT Plan Label, which the Basic Profile replaces.
    assert copy.path == ElementPath((), "(0008,1090)")
    assert copy.path.tag not in rows
    assert rows["(300A,0002)"].basic_profile == "D"
    assert copy.vr == "LO" and copy.values == label.values
    assert copy.profile_tag == ""
    assert [_as_text(v) for v in _Reader(review.data).read(copy.path).values] == list(
        copy.values
    )
    # No other placement copies a marker.
    assert [p for _, p in _placements(corpus, Kind.REVIEW_COPY)] == [copy]


def test_one_uid_marker_is_invalid_for_its_vr(corpus):
    names = [file.name for file in corpus.files]
    plan = corpus.files[names.index("05-rtplan.dcm")]
    rows = {row.tag: row for row in standard.load_table_e1_1().attributes}

    (invalid,) = [p for _, p in _placements(corpus, Kind.INVALID)]
    assert invalid in plan.manifest.placements
    # Device UID, which the Basic Profile replaces.
    assert invalid.path == ElementPath((), "(0018,1002)")
    assert invalid.profile_tag == "(0018,1002)"
    assert rows["(0018,1002)"].basic_profile == "U"
    (value,) = invalid.values
    assert re.fullmatch(r"2\.25\." + TEXT, value) and len(value) % 2 == 0
    assert value_problem("UI", value) is not None
    # Its marker is in no other placement, and nowhere else in its file.
    (number,) = re.findall(r"SYNMK-(\d{5})", value)
    others = {
        found
        for _, placement in _placements(corpus, *UNIQUE_KINDS)
        for text in placement.values
        for found in re.findall(r"(?:SYNMK|MARKER|99999)[-_]?(\d{5})", text)
    }
    assert others and number not in others
    assert plan.data.count(value.encode()) == 1
    # The strict reader admits it, and pydicom finds it invalid and quotes it.
    evidence = read_source(plan.data)
    assert evidence.value_field(invalid.path).rstrip(b"\x00").decode() == value
    with pytest.raises(ValueError, match=re.escape(value)):
        pydicom.valuerep.validate_value("UI", value, pydicom.config.RAISE)


def test_building_emits_no_warning():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        corpus_module.build_corpus()


def test_each_image_has_its_frames_and_the_colour_image_its_icc_profile(corpus):
    frames = {}
    for file in corpus.files:
        dataset = pydicom.dcmread(pydicom.filebase.DicomBytesIO(file.data))
        if "PixelData" not in dataset:
            continue
        count = int(dataset.get("NumberOfFrames", 1))
        frames[file.manifest.iod] = count
        size = dataset.Rows * dataset.Columns * dataset.SamplesPerPixel
        assert len(dataset.PixelData) == count * size * dataset.BitsAllocated // 8

        if file.manifest.iod == "Enhanced MR Color Image":
            assert dataset.PhotometricInterpretation == "RGB"
            assert dataset.ICCProfile == corpus_module.SOURCE_ICC_PROFILE
            assert icc_profiles.data_colour_space(dataset.ICCProfile) == (
                icc_profiles.RGB
            )
            # The marker is in the description, the copyright, the device
            # manufacturer and model descriptions, and a private tag.
            marker = corpus_module.MARKER_PREFIX.encode()
            assert dataset.ICCProfile.count(marker) == 5
        else:
            assert dataset.PhotometricInterpretation == "MONOCHROME2"
            assert "ICCProfile" not in dataset

    # Every image but those of the single-frame IODs, and the RT Image, whose
    # IOD allows one frame or more, has two frames.
    assert {iod for iod, count in frames.items() if count == 1} == {
        "CT Image",
        "MR Image",
        "Positron Emission Tomography Image",
        "RT Image",
    }
    assert set(frames.values()) == {1, 2}


def test_the_spectroscopy_instance_holds_spectroscopy_data_only(corpus):
    (file,) = [f for f in corpus.files if f.manifest.iod == "MR Spectroscopy"]
    dataset = pydicom.dcmread(pydicom.filebase.DicomBytesIO(file.data))
    points = (
        dataset.Rows
        * dataset.Columns
        * int(dataset.NumberOfFrames)
        * dataset.DataPointRows
        * dataset.DataPointColumns
    )

    assert "PixelData" not in dataset
    assert dataset.DataRepresentation == "REAL"
    assert len(dataset.SpectroscopyData) == 4 * points


# The root template of each report's tree, and the concept name of each
# content item of the tree whose value is recorded, by file, with the
# value's VR: each a row of Table E.3.4-1.
_DEVICE_OBSERVER_UID = ("DCM", "121012", "UIDREF")
_IRRADIATION_EVENT_UID = ("DCM", "113769", "UIDREF")
_DATETIME_STARTED = ("DCM", "111526", "DATETIME")
_IDENTIFICATION_OF_THE_X_RAY_SOURCE = ("DCM", "113832", "TEXT")
_CONTENT_CONCEPTS = {
    "22-sr-dose-x-ray.dcm": (
        "10001",
        {
            _DEVICE_OBSERVER_UID: "UI",
            ("DCM", "110180", "UIDREF"): "UI",  # Study Instance UID
            _IRRADIATION_EVENT_UID: "UI",
            _DATETIME_STARTED: "DT",
        },
    ),
    "23-sr-dose-radiopharmaceutical.dcm": (
        "10021",
        {
            ("DCM", "113503", "UIDREF"): "UI",  # Administration Event UID
            ("DCM", "123003", "DATETIME"): "DT",  # Start DateTime
            ("DCM", "113870", "PNAME"): "PN",  # Person Name
        },
    ),
    **{
        name: ("2000", {("DCM", "121008", "PNAME"): "PN"})  # Person Observer Name
        for name in corpus_module.GENERAL_REPORT_FILES[:3]
    },
    **{
        name: (
            "1500",
            {
                ("DCM", "121008", "PNAME"): "PN",  # Person Observer Name
                ("DCM", "121232", "UIDREF"): "UI",  # Source series for segmentation
            },
        )
        for name in corpus_module.GENERAL_REPORT_FILES[3:]
    },
    "29-sr-dose-enhanced-x-ray.dcm": (
        "10040",
        {
            _DEVICE_OBSERVER_UID: "UI",
            _IRRADIATION_EVENT_UID: "UI",
            _DATETIME_STARTED: "DT",
            ("DCM", "111527", "DATETIME"): "DT",  # DateTime Ended
            _IDENTIFICATION_OF_THE_X_RAY_SOURCE: "UT",
            ("DCM", "112227", "UIDREF"): "UI",  # Frame of Reference UID
        },
    ),
    "30-sr-dose-patient.dcm": (
        "10030",
        {
            _DEVICE_OBSERVER_UID: "UI",
            ("DCM", "128403", "TEXT"): "UT",  # Radiation Dose Estimate Name
        },
    ),
    corpus_module.CT_DOSE_REPORT_FILE: (
        "10011",
        {
            _DEVICE_OBSERVER_UID: "UI",
            ("DCM", "113809", "DATETIME"): "DT",  # Start of X-Ray Irradiation
            ("DCM", "113810", "DATETIME"): "DT",  # End of X-Ray Irradiation
            ("DCM", "110180", "UIDREF"): "UI",  # Study Instance UID
            _IRRADIATION_EVENT_UID: "UI",
            _IDENTIFICATION_OF_THE_X_RAY_SOURCE: "UT",
            ("DCM", "113870", "PNAME"): "PN",  # Person Name
        },
    ),
    # A key object selection's and a chest CAD report's required rows, and a
    # spectacle prescription's, hold no identifying value.
    "34-sr-key-object-selection.dcm": ("2010", {}),
    "35-sr-mammography-cad.dcm": (
        "4000",
        {
            ("DCM", "111060", "DATE"): "DA",  # Study Date
            ("DCM", "111061", "TIME"): "TM",  # Study Time
        },
    ),
    "36-sr-chest-cad.dcm": ("4100", {}),
    "37-sr-colon-cad.dcm": (
        "4120",
        {
            ("DCM", "112227", "UIDREF"): "UI",  # Frame of Reference UID
            ("DCM", "110180", "UIDREF"): "UI",  # Study Instance UID
            ("DCM", "111060", "DATE"): "DA",  # Study Date
            ("DCM", "111061", "TIME"): "TM",  # Study Time
            ("DCM", "112002", "UIDREF"): "UI",  # Series Instance UID
        },
    ),
    **{
        name: (template, {("DCM", "121008", "PNAME"): "PN"})  # Person Observer Name
        for name, template in (
            ("38-sr-procedure-log.dcm", "3001"),
            ("40-sr-macular-grid.dcm", "2100"),
            ("41-sr-waveform-annotation.dcm", "3750"),
        )
    },
    "39-sr-spectacle-prescription.dcm": ("2020", {}),
}
# The content items whose values are the collection's own UIDs, by IOD:
# the study that the X-ray report's scope of accumulation names, and the
# colon CAD report's image set and CT series.
_LINKED_CONCEPTS = {
    "X-Ray Radiation Dose SR": {
        ("DCM", "110180", "UIDREF"): corpus_module.STUDY,
    },
    "Colon CAD SR": {
        ("DCM", "112227", "UIDREF"): corpus_module.FRAME_OF_REFERENCE,
        ("DCM", "110180", "UIDREF"): corpus_module.STUDY,
        ("DCM", "112002", "UIDREF"): corpus_module.CT_SERIES,
    },
}


def test_each_report_records_the_identifying_values_of_its_content_tree(corpus):
    concepts = {
        concept.key for concept in structured_content.load_table_e3_4_1().concepts
    }
    files = {file.name: file for file in corpus.files}
    for name in corpus_module.STRUCTURED_REPORT_FILES:
        file = files[name]
        dataset = pydicom.dcmread(io.BytesIO(file.data))
        (template,) = dataset.ContentTemplateSequence
        assert template.MappingResource == "DCMR"
        root_template, recorded = _CONTENT_CONCEPTS[name]
        assert template.TemplateIdentifier == root_template
        # The CT dose report's TID 10011 is the X-Ray Radiation Dose SR's
        # other root template.
        assert root_template == (
            synthetic_content_trees.CT_RADIATION_DOSE_TEMPLATE
            if name == corpus_module.CT_DOSE_REPORT_FILE
            else synthetic_content_trees.ROOT_TEMPLATES[file.manifest.sop_class]
        )
        assert dataset.ValueType == "CONTAINER"
        assert dataset.Modality == (
            "KO" if file.manifest.iod == "Key Object Selection Document" else "SR"
        )
        content = [p for p in file.manifest.placements if p.concept is not None]
        assert {p.concept: p.vr for p in content} == recorded
        assert {p.concept for p in content} <= concepts
        for placement in content:
            # Each value is read back by its own test; here, its item.
            item = dataset
            for tag, index in placement.path.items:
                item = item[_number(tag)].value[index]
            assert (
                _as_text(item[_number(placement.path.tag)].value)
                == (placement.values[0])
            )
            (code,) = item.ConceptNameCodeSequence
            assert (
                code.CodingSchemeDesignator,
                code.CodeValue,
                item.ValueType,
            ) == placement.concept
            assert placement.profile_tag == placement.path.tag
        # Only the collection's own study, series, and frame are linked.
        assert {
            p.concept: p.values[0] for p in content if p.kind is Kind.LINKED_UID
        } == _LINKED_CONCEPTS.get(file.manifest.iod, {})
        assert all(
            p.kind is Kind.PLANTED for p in content if p.kind is not Kind.LINKED_UID
        )
    assert set(_CONTENT_CONCEPTS) == set(corpus_module.STRUCTURED_REPORT_FILES)


def test_no_marker_is_planted_in_a_reports_root_content_item_sequences(corpus):
    instances = {file.manifest.sop_instance for file in corpus.files}
    for file in corpus.files:
        if file.name not in corpus_module.STRUCTURED_REPORT_FILES:
            assert all(
                p.reason is not Reason.CONTENT_TREE for p in file.manifest.placements
            )
            assert all(p.concept is None for p in file.manifest.placements)
            continue
        for placement in file.manifest.placements:
            items = placement.path.items
            top = items[0][0] if items else placement.path.tag
            if top not in ("(0040,A043)", "(0040,A730)"):
                assert placement.reason is not Reason.CONTENT_TREE
            elif items and top == "(0040,A730)":
                # Only the tree's own values are recorded below it, the
                # frame of reference of a SCOORD3D item, the collection's,
                # and the instance that an IMAGE item references or a
                # COMPOSITE item names, one of the collection's, such as its
                # CT dose report, each of which takes its own row of Table
                # E.1-1.
                if placement.concept is None:
                    assert placement.kind is Kind.LINKED_UID, placement
                    if placement.path.tag == REFERENCED_SOP_INSTANCE:
                        assert set(placement.values) <= instances, placement
                    else:
                        assert (placement.path.tag, placement.values) == (
                            "(3006,0024)",
                            (corpus_module.FRAME_OF_REFERENCE,),
                        ), placement
            elif placement.concept is None:
                assert placement.reason is Reason.CONTENT_TREE, placement
                assert placement.values == ()
