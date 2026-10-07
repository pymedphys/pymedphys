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

"""A synthetic collection with a conspicuous marker in each attribute to protect.

:func:`build_corpus` builds, in memory and the same way every time, one
linked collection of the first supported release's CT and RT IODs: three CT
Image slices, an RT Structure Set that references the CT series and slices, an RT
Plan that references the structure set and the dose, and an RT Dose that
references the plan, all of one fictitious patient and study, with one Frame
of Reference, and a second RT Dose of the plan for review (below). It is
the input for validating each preset end to end: once the engine has
written the collection, the residual search
(:mod:`~pymedphys._dicom.deidentify.residuals`) should find none of the
markers that had to be removed or replaced.

**Markers.** Each attribute that Table E.1-1 lists and an instance's IOD
defines, at each place in the data set where the IOD's modules define it,
holds a marker: a value that is valid for the attribute's VR and VM in the
pinned PS3.6 data dictionary, and that no other placement in the collection
holds, except for the two placements that **Diagnostics and review**
describes. Text is ``SYNMK-00042``, a code string ``SYNMK_00042``, a person name
``SYNMK00042^MARKER00042``, a UID ``2.25.9999900042``, a URI
``https://synmk.invalid/SYNMK-00042``, a date a day from 1800 to 1899, a
datetime that date at noon, a time ``HHMMSS.424242`` whose seconds from
midnight are the marker's number, and a binary value of VR OB, OW, or UN the
text marker in ASCII, padded to an even length. No text marker occurs inside
another value of its file. A number of a binary VR, such as US or SS, and an
age (AS) cannot be made conspicuous: each is distinct, but it is found by
its place in the manifest, not by searching bytes. Each sequence that holds
a placement has one item, created along the path where needed, so every
place is reached through items numbered 0.

Some attributes must stay linked, so the collection's references resolve and
the reference graph (:mod:`~pymedphys._dicom.deidentify.reference_graph`)
has no findings: SOP Instance, Series Instance, and Study Instance UIDs at
the top level, Frame of Reference UID and Referenced Frame of Reference UID
wherever they are, each UID at a reference site
(:func:`~pymedphys._dicom.deidentify.references.reference_sites`), and the
Patient ID and Issuer of Patient ID at the top level. These hold the
collection's own UIDs, under ``2.25.88888``, and one patient's identifiers,
and are recorded as linked. A reference names an instance of the collection
with its SOP Class, except that Referenced Patient Sequence (0008,1120)
names a synthetic patient with Detached Patient Management SOP Class, and
Referenced Performed Procedure Step Sequence (0008,1111) a synthetic
procedure step with Modality Performed Procedure Step SOP Class, which the
reference graph does not resolve or report, since neither is a storage
class.

A sequence that Table E.1-1 lists is present with its item. Where no marker
is planted below it, a marker is put in the first attribute that the IOD
defines in its item, text first. A linked value does not count, since a
preset that keeps the sequence and replaces its UIDs would leave no marker.
Where the IOD defines no attribute in the item that can carry a marker, as
in Modified Attributes Sequence (0400,0550), or Referenced Patient Sequence,
whose item holds only UIDs, the sequence is recorded with
:attr:`NotPlantedReason.NO_MARKER_CARRIER`: its removal is checked by its
absence at its path in the manifest, not by the residual search.

**Caps.** An attribute is planted only where it lies in at most
:data:`MAX_DEPTH` nested items, and a sequence only where its item does. The
deepest references of an RT Structure Set, its Contour Image Sequence in the
RT Referenced Series Sequence, lie at that depth; the deeper places, such as
the Code Sequence Macros nested in the Request Attributes Sequence, repeat
macros already planted at shallower places. A repeating group is planted in
its first group only: Overlay Data (60xx,3000), which of the collection's IODs
only CT Image defines, is planted in group 6000 with VR OW, of the OB or OW
that PS3.6 allows, so it is written in Explicit VR only. An attribute that the pinned
dictionary gives no single VR, and a tag whose element number is masked,
are not planted. Each placement not planted is recorded with a
:class:`NotPlantedReason`. Pixel Data is not an attribute of Table E.1-1 and
holds only a few synthetic samples.

**Sequestering attributes.** An attribute whose Basic Profile action is a
plain X, and whose removal sequesters the instance because the IOD requires
it at a place no Type 3 sequence encloses
(:func:`~pymedphys._dicom.deidentify.compound_actions.resolve_plain_x_in_iod`),
is planted only in :data:`SEQUESTERED_FILE`, the third CT slice, and
recorded in the other files with
:attr:`NotPlantedReason.SEQUESTERS_INSTANCE`. Of the corpus's IODs these
are Responsible Person (0010,2297) and Responsible Organization (0010,2299)
at the top level. Planted in every file, they would sequester every
instance, and no preset could release any of the collection; planted in one,
that instance checks sequestration, :data:`REVIEW_FILE` checks review, and
the other five check each preset's output.

**Edge cases.** Each file except the first RT Dose, ``06-rtdose.dcm``, is
written in Explicit VR Little Endian, and that RT Dose in Implicit VR
Little Endian. pydicom 3.0.2 does not know some newer attributes, such as
(0008,001D), and reads them from that RT Dose as UN; the engine reads them
with the pinned dictionary. The first CT slice holds Patient Comments
(0010,4000) encoded with VR UN.
The RT Structure Set declares Specific Character Set ``ISO_IR 100`` and its
Patient's Name holds a Latin-1 letter. Every file has a private block of a
synthetic private creator at the top level, and another in the item of
Procedure Code Sequence (0008,1032), which pydicom knows; in the Implicit VR
file neither has a VR in the file. Every file is admitted by the engine's
strict source reader
(:func:`~pymedphys._dicom.deidentify.source.read_source`); none is
deliberately outside admission.

**Diagnostics and review.** Two placements exercise paths that a clean
collection never reaches. The RT Plan's Device UID (0018,1002), which the
Basic Profile replaces, holds ``2.25.`` followed by a text marker, which VR
UI does not allow (:attr:`PlacementKind.INVALID`): the strict reader admits
it, and pydicom, by default, warns and quotes it whenever it converts it, so
a run must keep the warning's text out of what it shows.
:data:`REVIEW_FILE`, a second RT Dose that references the plan and that the
plan does not reference, keeps in
Manufacturer's Model Name (0008,1090), which Table E.1-1 does not list and
the Basic Profile keeps, a copy of the RT Plan's RT Plan Label marker
(:attr:`PlacementKind.REVIEW_COPY`), so the residual search finds a source
value of another instance in its output and sends it to review. The third
CT slice remains sequestered; the other five files stay releasable.

**Manifest.** :class:`CorpusManifest` records, for each file, each
placement: its element path, VR, values, kind, the Table E.1-1 row it
covers, and why it was not planted where it was not.
:meth:`CorpusManifest.to_json` serialises it the same way every time.
Building reads the bundled tables, writes no files, uses no clock or
randomness, and logs nothing; :func:`write_corpus` writes the files to the
directory :data:`INSTANCES_DIRECTORY` of a directory its caller names, and
the manifest beside it, so that the directory of instances can be a run's
input.
"""

# The builder, its manifest's types, and its description stay together, so
# the module is long.
# pylint: disable = too-many-lines

from __future__ import annotations

import dataclasses
import datetime
import enum
import functools
import io
import json
import pathlib
import struct
import types
from collections.abc import Sequence

from pymedphys._imports import pydicom

from .compound_actions import RemovalExtent, resolve_plain_x_in_iod
from .elements import dataset_codecs, new_element
from .file_layout import ElementPath
from .iods import IOD
from .references import (
    REFERENCE_TAGS,
    REFERENCED_SOP_CLASS_TAG,
    Level,
    reference_sites,
)
from .sop_classes import iod_for_sop_class
from .standard import (
    PRIVATE_ATTRIBUTES_TAG,
    VM_PATTERN,
    dictionary_attribute,
    load_table_e1_1,
)
from .values import values_problem

IMPLICIT_VR_LITTLE_ENDIAN = "1.2.840.10008.1.2"
EXPLICIT_VR_LITTLE_ENDIAN = "1.2.840.10008.1.2.1"

CT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.2"
RT_DOSE_STORAGE = "1.2.840.10008.5.1.4.1.1.481.2"
RT_STRUCTURE_SET_STORAGE = "1.2.840.10008.5.1.4.1.1.481.3"
RT_PLAN_STORAGE = "1.2.840.10008.5.1.4.1.1.481.5"
# The retired class that PS3.3 Sections 10.6.1 and C.8.8.5.4 give a study in
# a Referenced Study Sequence or RT Referenced Study Sequence item.
DETACHED_STUDY_MANAGEMENT = "1.2.840.10008.3.1.2.3.1"

# The most items an attribute is planted in, nested one in another.
MAX_DEPTH = 4
# Every marker's number is below this, so markers have a fixed width of five
# digits and none is the start of another, every date is before 1900, every
# time is distinct, and the negated number fits VR SS.
MAX_MARKERS = 2**15
MARKER_PREFIX = "SYNMK"
MARKER_UID_ROOT = "2.25.99999"
LINKED_UID_ROOT = "2.25.88888"
# The one file in which an attribute whose removal sequesters is planted.
SEQUESTERED_FILE = "03-ct-3.dcm"
# The file that keeps a copy of another file's marker, for review.
REVIEW_FILE = "07-rtdose-review.dcm"
# The directory, within the one that write_corpus is given, of the files.
INSTANCES_DIRECTORY = "instances"

STUDY = f"{LINKED_UID_ROOT}00001"
FRAME_OF_REFERENCE = f"{LINKED_UID_ROOT}00002"
CT_SERIES = f"{LINKED_UID_ROOT}00100"
CT_SLICES = tuple(f"{LINKED_UID_ROOT}0010{number}" for number in (1, 2, 3))
STRUCTURE_SET_SERIES = f"{LINKED_UID_ROOT}00200"
STRUCTURE_SET = f"{LINKED_UID_ROOT}00201"
PLAN_SERIES = f"{LINKED_UID_ROOT}00300"
PLAN = f"{LINKED_UID_ROOT}00301"
DOSE_SERIES = f"{LINKED_UID_ROOT}00400"
DOSE = f"{LINKED_UID_ROOT}00401"
REVIEW_DOSE = f"{LINKED_UID_ROOT}00402"
# A patient and a procedure step that the collection names but does not hold.
PATIENT_REFERENCE = f"{LINKED_UID_ROOT}00003"
PROCEDURE_STEP = f"{LINKED_UID_ROOT}00004"
DETACHED_PATIENT_MANAGEMENT = "1.2.840.10008.3.1.2.1.1"
MODALITY_PERFORMED_PROCEDURE_STEP = "1.2.840.10008.3.1.2.3.3"
IMPLEMENTATION_CLASS = f"{LINKED_UID_ROOT}99999"
PATIENT_ID = f"{MARKER_PREFIX}-LINKED-PATIENT"
ISSUER_OF_PATIENT_ID = f"{MARKER_PREFIX}-LINKED-ISSUER"
PRIVATE_GROUP = 0x0009
# The sequence whose item holds the second private block: Procedure Code
# Sequence, which every IOD of the corpus defines and pydicom 3.0 knows.
PRIVATE_ITEM_SEQUENCE = "(0008,1032)"

_SOP_INSTANCE_TAG = "(0008,0018)"
_SERIES_TAG = "(0020,000E)"
_STUDY_TAG = "(0020,000D)"
_PATIENT_ID_TAG = "(0010,0020)"
_ISSUER_TAG = "(0010,0021)"
_PATIENTS_NAME_TAG = "(0010,0010)"
_FRAME_OF_REFERENCE_TAGS = frozenset({"(0020,0052)", "(3006,0024)"})
_CONTOUR_IMAGE_SEQUENCE = "(3006,0016)"
# Where an RT Structure Set references every CT slice, not only the first.
_RT_REFERENCED_CONTOUR_IMAGES = ("(3006,0010)", "(3006,0012)", "(3006,0014)")
# The instance a reference names, by the innermost sequence that holds it.
_TARGETS = types.MappingProxyType(
    {
        "(300C,0002)": PLAN,  # Referenced RT Plan Sequence
        "(300C,0060)": STRUCTURE_SET,  # Referenced Structure Set Sequence
        "(300C,0080)": DOSE,  # Referenced Dose Sequence
        _CONTOUR_IMAGE_SEQUENCE: CT_SLICES[0],
        "(0008,1120)": PATIENT_REFERENCE,  # Referenced Patient Sequence
        "(0008,1111)": PROCEDURE_STEP,  # Referenced Performed Procedure Step
    }
)
_SOP_CLASSES = types.MappingProxyType(
    {
        **dict.fromkeys(CT_SLICES, CT_IMAGE_STORAGE),
        STRUCTURE_SET: RT_STRUCTURE_SET_STORAGE,
        PLAN: RT_PLAN_STORAGE,
        DOSE: RT_DOSE_STORAGE,
        REVIEW_DOSE: RT_DOSE_STORAGE,
        PATIENT_REFERENCE: DETACHED_PATIENT_MANAGEMENT,
        PROCEDURE_STEP: MODALITY_PERFORMED_PROCEDURE_STEP,
    }
)
# The VR given to an attribute with alternatives, as Implicit VR gives it
# (PS3.5 Section A.1).
_DECIDED_VRS = types.MappingProxyType({"(60xx,3000)": "OW"})
# The text VRs, which a sequence's content marker has where it can.
_CONTENT_VRS = frozenset({"LO", "LT", "PN", "SH", "ST", "UC", "UT"})
_WORD_BYTES = {"OB": 1, "UN": 1, "OW": 2, "OF": 4, "OL": 4, "OD": 8, "OV": 8}
# Every value has an even length (PS3.5 Section 7.1.1).
_EVEN = 2
# The fractional seconds of every TM marker, so that times are conspicuous.
_TIME_SIGNATURE = ".424242"
# The time of every DT marker, which no TM marker matches.
_NOON = "120000"
_FIRST_DATE = datetime.date(1800, 1, 1)
_SECONDS_IN_A_DAY = 86_400


class PlacementKind(enum.Enum):
    """What a :class:`Placement` holds.

    Attributes
    ----------
    PLANTED
        A marker that no other placement holds, in an attribute of Table
        E.1-1.
    LINKED_UID
        One of the collection's own UIDs, which other placements share so
        that identities and references stay linked: an instance's SOP
        Instance, Series Instance, or Study Instance UID at the top level,
        the Frame of Reference UID, or a UID at a reference site.
    LINKED_PATIENT
        The patient's Patient ID or Issuer of Patient ID at the top level,
        the same in every file, so the study has one patient.
    SEQUENCE
        A sequence of Table E.1-1, present with the item that holds the
        markers below it. It has no values of its own.
    CONTENT
        A marker in an attribute that Table E.1-1 does not list, in the item
        of a sequence that it does and that holds no other marker.
    PRIVATE
        A private creator or private attribute of the synthetic private
        block, which Table E.1-1 covers by its row for private attributes.
    UN_ENCODED
        A marker in an attribute of Table E.1-1 written with VR UN in
        Explicit VR, in place of its own VR.
    NOT_PLANTED
        An attribute of Table E.1-1 that the IOD defines there but that is
        not planted, for the placement's ``reason``.
    INVALID
        A value of a UI attribute of Table E.1-1, ``2.25.`` followed by a
        text marker, which VR UI does not allow, so that pydicom warns,
        quoting it, when it converts it.
    REVIEW_COPY
        A copy of another file's marker, whose values equal that
        placement's, in an attribute that Table E.1-1 does not list and the
        Basic Profile keeps, so that the residual search finds it and sends
        the file to review.
    """

    PLANTED = "planted"
    LINKED_UID = "linked-uid"
    LINKED_PATIENT = "linked-patient"
    SEQUENCE = "sequence"
    CONTENT = "content"
    PRIVATE = "private"
    UN_ENCODED = "un-encoded"
    NOT_PLANTED = "not-planted"
    INVALID = "invalid"
    REVIEW_COPY = "review-copy"


# The kinds of placement that leave a marker below a sequence.
_MARKER_KINDS = frozenset({PlacementKind.PLANTED, PlacementKind.CONTENT})


class NotPlantedReason(enum.Enum):
    """Why an attribute of Table E.1-1 that the IOD defines is not planted."""

    DEPTH_CAP = "depth-cap"  # deeper than MAX_DEPTH items
    # A sequence whose item the IOD gives no attribute that can carry a
    # marker; the sequence itself is present.
    NO_MARKER_CARRIER = "no-marker-carrier"
    NO_SINGLE_VR = "no-single-vr"  # the pinned dictionary gives no single VR
    MASKED_ELEMENT = "masked-element"  # its element number is masked
    # Removing it sequesters the instance, so it is planted only in
    # SEQUESTERED_FILE.
    SEQUESTERS_INSTANCE = "sequesters-instance"


@dataclasses.dataclass(frozen=True)
class Placement:
    """One place in a file where a marker is, or would have been, planted.

    Attributes
    ----------
    path : ElementPath
        The sequences and items that hold the element, outermost first, and
        its tag, with a repeating group's first group, such as
        ``(6000,3000)``.
    vr : str
        The VR the element is built with, which an Implicit VR file does not
        hold; ``"UN"`` for :attr:`PlacementKind.UN_ENCODED`; or ``""`` where
        it is not planted for want of one.
    values : tuple of str
        The values as text: numbers in decimal, a tag as eight hexadecimal
        digits, and a binary value as the ASCII text it holds, which is
        padded to an even whole number of words with NUL, or with a space
        for UN.
        ``()`` for a sequence and for an attribute not planted.
    kind : PlacementKind
    profile_tag : str
        The tag of the row of Table E.1-1 that the placement covers, such as
        ``"(60xx,3000)"``, or its row for private attributes; ``""`` for
        :attr:`PlacementKind.CONTENT` and :attr:`PlacementKind.REVIEW_COPY`.
    reason : NotPlantedReason or None
        Why it is not planted, for :attr:`PlacementKind.NOT_PLANTED`; or
        :attr:`NotPlantedReason.NO_MARKER_CARRIER` for a
        :attr:`PlacementKind.SEQUENCE` with no marker below it; otherwise
        ``None``.
    """

    path: ElementPath
    vr: str
    values: tuple[str, ...]
    kind: PlacementKind
    profile_tag: str
    reason: NotPlantedReason | None = None

    def to_dict(self) -> dict[str, object]:
        """Return the placement as JSON-ready data."""
        return {
            "items": [[tag, index] for tag, index in self.path.items],
            "tag": self.path.tag,
            "vr": self.vr,
            "values": list(self.values),
            "kind": self.kind.value,
            "profile_tag": self.profile_tag,
            "reason": None if self.reason is None else self.reason.value,
        }


@dataclasses.dataclass(frozen=True)
class FileManifest:
    """What one file of the corpus holds, and where.

    Attributes
    ----------
    name : str
        The file's name, such as ``"01-ct-1.dcm"``.
    iod : str
        The name of its IOD, such as ``"CT Image"``.
    sop_class : str
    sop_instance : str
    transfer_syntax : str
        Implicit or Explicit VR Little Endian.
    specific_character_set : str
        The Specific Character Set (0008,0005) it declares, or ``""``.
    placements : tuple of Placement
        Those of the IOD's attributes of Table E.1-1 in the order of its
        definitions, then the content markers of sequences, the extra
        references, the private block, and any review copy.
    """

    name: str
    iod: str
    sop_class: str
    sop_instance: str
    transfer_syntax: str
    specific_character_set: str
    placements: tuple[Placement, ...]

    def to_dict(self) -> dict[str, object]:
        """Return the file's manifest as JSON-ready data."""
        return {
            "name": self.name,
            "iod": self.iod,
            "sop_class": self.sop_class,
            "sop_instance": self.sop_instance,
            "transfer_syntax": self.transfer_syntax,
            "specific_character_set": self.specific_character_set,
            "placements": [placement.to_dict() for placement in self.placements],
        }


@dataclasses.dataclass(frozen=True)
class CorpusManifest:
    """The manifest of every file of the corpus.

    Attributes
    ----------
    files : tuple of FileManifest
        In the order the files are built.
    max_depth : int
        :data:`MAX_DEPTH` when the corpus was built.
    """

    files: tuple[FileManifest, ...]
    max_depth: int = MAX_DEPTH

    def to_json(self) -> str:
        """Return the manifest as JSON text, the same for the same manifest."""
        document = {
            "schema": "pymedphys-deid-synthetic-corpus/1",
            "max_depth": self.max_depth,
            "files": [file.to_dict() for file in self.files],
        }
        return json.dumps(document, indent=1, sort_keys=True, ensure_ascii=True) + "\n"


@dataclasses.dataclass(frozen=True)
class CorpusFile:
    """One written file of the corpus. Its ``repr`` shows only its manifest."""

    manifest: FileManifest
    data: bytes = dataclasses.field(repr=False)

    @property
    def name(self) -> str:
        """The file's name."""
        return self.manifest.name


@dataclasses.dataclass(frozen=True)
class SyntheticCorpus:
    """The corpus's files, in the order they are built."""

    files: tuple[CorpusFile, ...]

    @property
    def manifest(self) -> CorpusManifest:
        """The manifest of every file."""
        return CorpusManifest(tuple(file.manifest for file in self.files))


@dataclasses.dataclass(frozen=True)
class _Spec:
    """An instance of the corpus, before its markers are planted."""

    name: str
    sop_class: str
    sop_instance: str
    series: str
    # The instance that a reference names where _TARGETS does not decide.
    default_target: str
    transfer_syntax: str = EXPLICIT_VR_LITTLE_ENDIAN
    character_set: str = ""
    # The tag of a top-level attribute written with VR UN.
    un_encoded: str = ""
    # The tag of a top-level UI attribute whose marker is invalid for VR UI.
    invalid: str = ""
    # The tag of a top-level attribute that keeps a copy of a marker, the
    # file that holds the marker, and the tag of its top-level attribute.
    review_copy: tuple[str, str, str] | None = None
    slice_index: int = 0


_SPECS = (
    _Spec(
        "01-ct-1.dcm",
        CT_IMAGE_STORAGE,
        CT_SLICES[0],
        CT_SERIES,
        CT_SLICES[1],
        un_encoded="(0010,4000)",  # Patient Comments
        slice_index=0,
    ),
    _Spec(
        "02-ct-2.dcm",
        CT_IMAGE_STORAGE,
        CT_SLICES[1],
        CT_SERIES,
        CT_SLICES[2],
        slice_index=1,
    ),
    _Spec(
        "03-ct-3.dcm",
        CT_IMAGE_STORAGE,
        CT_SLICES[2],
        CT_SERIES,
        CT_SLICES[0],
        slice_index=2,
    ),
    _Spec(
        "04-rtstruct.dcm",
        RT_STRUCTURE_SET_STORAGE,
        STRUCTURE_SET,
        STRUCTURE_SET_SERIES,
        CT_SLICES[0],
        character_set="ISO_IR 100",
    ),
    _Spec(
        "05-rtplan.dcm",
        RT_PLAN_STORAGE,
        PLAN,
        PLAN_SERIES,
        STRUCTURE_SET,
        invalid="(0018,1002)",  # Device UID
    ),
    _Spec(
        "06-rtdose.dcm",
        RT_DOSE_STORAGE,
        DOSE,
        DOSE_SERIES,
        PLAN,
        transfer_syntax=IMPLICIT_VR_LITTLE_ENDIAN,
    ),
    _Spec(
        REVIEW_FILE,
        RT_DOSE_STORAGE,
        REVIEW_DOSE,
        DOSE_SERIES,
        PLAN,
        # Manufacturer's Model Name keeps the plan's RT Plan Label.
        review_copy=("(0008,1090)", "05-rtplan.dcm", "(300A,0002)"),
    ),
)


def build_corpus() -> SyntheticCorpus:
    """Build the corpus's files and their manifest, the same way every time.

    Returns
    -------
    SyntheticCorpus
        Seven files: three CT slices, then the RT Structure Set, RT Plan, RT
        Dose, and the RT Dose for review. Two builds give the same bytes and
        the same manifest.
    """
    markers = _Markers()
    files: list[CorpusFile] = []
    for spec in _SPECS:
        earlier = {file.name: file.manifest for file in files}
        dataset, manifest = _Instance(spec, markers, earlier).build()
        files.append(CorpusFile(manifest, _written(dataset, spec)))
    return SyntheticCorpus(tuple(files))


def write_corpus(
    corpus: SyntheticCorpus, directory: pathlib.Path
) -> tuple[pathlib.Path, ...]:
    """Write the corpus's files, and its manifest as ``manifest.json``.

    The files go in ``directory / INSTANCES_DIRECTORY``, created if needed,
    which holds nothing else, so it can be given to a run as its input; the
    manifest, which holds every marker, goes in ``directory``.

    Parameters
    ----------
    corpus : SyntheticCorpus
    directory : pathlib.Path
        An existing directory. No file in it is overwritten.

    Returns
    -------
    tuple of pathlib.Path
        The paths written, the files in order and then the manifest.

    Raises
    ------
    FileExistsError
        If a file to be written already exists, before anything is written.
    """
    instances = directory / INSTANCES_DIRECTORY
    paths = [instances / file.name for file in corpus.files]
    path = directory / "manifest.json"
    for each in (*paths, path):
        if each.exists():
            raise FileExistsError(f"{each.name} already exists in the directory")
    instances.mkdir(exist_ok=True)
    written = []
    for each, file in zip(paths, corpus.files):
        with open(each, "xb") as stream:
            stream.write(file.data)
        written.append(each)
    with open(path, "x", encoding="utf-8", newline="\n") as stream:
        stream.write(corpus.manifest.to_json())
    written.append(path)
    return tuple(written)


class _Markers:
    """Number the markers in the order they are planted, across the corpus."""

    def __init__(self) -> None:
        self._number = 0
        self._ages = 0

    def values(
        self, vr: str, count: int, *, latin_1: bool = False
    ) -> tuple[list[object], tuple[str, ...]]:
        """Return ``count`` new markers for ``vr``, as values and as text."""
        values: list[object] = []
        for _ in range(count):
            self._number += 1
            if self._number >= MAX_MARKERS:
                raise ValueError("the corpus has more markers than their width")
            if vr == "AS":
                # Ages have only a thousand values of each unit.
                self._ages += 1
                if self._ages > 999:
                    raise ValueError("the corpus has more ages than weeks to give")
                values.append(f"{self._ages:03d}W")
            else:
                values.append(_marker(vr, self._number, latin_1))
        return values, tuple(_as_text(vr, value) for value in values)


def _marker(vr: str, number: int, latin_1: bool) -> object:
    """Return the marker numbered ``number`` as a value of ``vr``."""
    text = f"{MARKER_PREFIX}-{number:05d}"
    if vr in _WORD_BYTES:
        return _padded(text, vr)
    day = _FIRST_DATE + datetime.timedelta(days=number)
    seconds = number % _SECONDS_IN_A_DAY
    time = f"{seconds // 3600:02d}{seconds // 60 % 60:02d}{seconds % 60:02d}"
    time += _TIME_SIGNATURE
    given = "MÄRKER" if latin_1 else "MARKER"
    formats: dict[str, object] = {
        "AE": text,
        "CS": f"{MARKER_PREFIX}_{number:05d}",
        "DA": day.strftime("%Y%m%d"),
        "DS": f"8{number:05d}.5",
        "DT": day.strftime("%Y%m%d") + _NOON,
        "IS": f"7{number:05d}",
        "PN": f"{MARKER_PREFIX}{number:05d}^{given}{number:05d}",
        "TM": time,
        "UI": f"{MARKER_UID_ROOT}{number:05d}",
        "UR": f"https://synmk.invalid/{text}",
        "AT": 0x7FFF0000 + number,
        "FD": number + 0.5,
        "FL": number + 0.5,
        "SL": -(900_000_000 + number),
        "SS": -number,
        "SV": -(9_000_000_000 + number),
        "UL": 900_000_000 + number,
        "US": number,
        "UV": 9_000_000_000 + number,
    }
    return formats.get(vr, text)


def _padded(text: str, vr: str) -> bytes:
    """Return ``text`` in ASCII, padded to a whole number of the VR's words."""
    data = text.encode("ascii")
    width = max(_WORD_BYTES[vr], _EVEN)
    pad = b" " if vr == "UN" else b"\x00"
    return data + pad * (-len(data) % width)


def _as_text(vr: str, value: object) -> str:
    """Return a value as the manifest records it."""
    if isinstance(value, bytes):
        return value.decode("ascii").rstrip("\x00 ")
    if vr == "AT":
        return f"{value:08X}"
    return str(value)


def _least_count(vm: str) -> int:
    """Return the fewest values that the VM allows, and at least one."""
    match = VM_PATTERN.fullmatch(vm.split(" or ")[0])
    return max(1, int(match.group(1))) if match else 1


def _number(tag: str) -> int:
    return int(tag[1:5] + tag[6:10], 16)


def _items(path: Sequence[str]) -> tuple[tuple[str, int], ...]:
    """Return the items numbered 0 of each sequence of ``path``."""
    return tuple((tag, 0) for tag in path)


def _item(
    dataset: pydicom.Dataset, items: Sequence[tuple[str, int]]
) -> pydicom.Dataset:
    """Return the item at ``items``, creating each sequence and item needed."""
    for tag, index in items:
        number = _number(tag)
        if number not in dataset:
            dataset[number] = pydicom.DataElement(number, "SQ", pydicom.Sequence())
        sequence = dataset[number].value
        while len(sequence) <= index:
            sequence.append(pydicom.Dataset())
        dataset = sequence[index]
    return dataset


@functools.lru_cache(maxsize=None)
def _basic_profile_actions() -> types.MappingProxyType[str, str]:
    """Return the Basic Profile's action for each row of Table E.1-1."""
    return types.MappingProxyType(
        {row.tag: row.basic_profile for row in load_table_e1_1().attributes}
    )


@functools.lru_cache(maxsize=None)
def _profile_places(iod: IOD) -> tuple[tuple[tuple[str, ...], str, str], ...]:
    """Return each place the IOD defines an attribute of Table E.1-1.

    Each is its path, the tag the IOD gives, and the tag of its row of the
    table, once for each path and tag, in the order of the definitions.
    """
    rows = [
        row.tag
        for row in load_table_e1_1().attributes
        if row.tag != PRIVATE_ATTRIBUTES_TAG
    ]
    exact = frozenset(rows)
    masked = [row for row in rows if "x" in row]
    places: dict[tuple[tuple[str, ...], str], str] = {}
    for definition in iod.definitions:
        tag = definition.tag
        row = (
            tag
            if tag in exact
            else next((mask for mask in masked if _matches(mask, tag)), None)
        )
        if row is not None:
            places.setdefault((definition.path, tag), row)
    return tuple((path, tag, row) for (path, tag), row in places.items())


def _matches(mask: str, tag: str) -> bool:
    """Return whether a tag of Table E.1-1 with ``x`` digits covers ``tag``."""
    return len(mask) == len(tag) and all(
        digit in ("x", found) for digit, found in zip(mask, tag)
    )


class _Instance:
    """Plant the markers of one instance of the corpus."""

    def __init__(
        self,
        spec: _Spec,
        markers: _Markers,
        earlier: dict[str, FileManifest] | None = None,
    ) -> None:
        iod = iod_for_sop_class(spec.sop_class)
        if iod is None:
            raise ValueError("the corpus's SOP Classes have generated IODs")
        self.spec = spec
        self.iod = iod
        self.markers = markers
        self.dataset = pydicom.Dataset()
        if spec.character_set:
            self.dataset[0x00080005] = pydicom.DataElement(
                0x00080005, "CS", spec.character_set
            )
        self.codecs = dataset_codecs(self.dataset)
        self.levels = {
            (site.path, site.tag): site.level for site in reference_sites(iod)
        }
        self.placements: list[Placement] = []
        self.earlier = earlier or {}

    def build(self) -> tuple[pydicom.Dataset, FileManifest]:
        """Return the instance's data set and its manifest."""
        for path, tag, row in _profile_places(self.iod):
            self._place(path, tag, row)
        self._fill_sequences()
        self._reference_every_slice()
        self._add_private_blocks()
        self._add_review_copy()
        self._add_structure()
        manifest = FileManifest(
            self.spec.name,
            self.iod.name,
            self.spec.sop_class,
            self.spec.sop_instance,
            self.spec.transfer_syntax,
            self.spec.character_set,
            tuple(self.placements),
        )
        return self.dataset, manifest

    def _record(
        self,
        path: ElementPath,
        vr: str,
        values: tuple[str, ...],
        kind: PlacementKind,
        row: str,
        reason: NotPlantedReason | None = None,
    ) -> None:
        self.placements.append(Placement(path, vr, values, kind, row, reason))

    def _place(self, path: tuple[str, ...], tag: str, row: str) -> None:
        """Plant one attribute of Table E.1-1, or record why it is not."""
        written = tag.replace("xx,", "00,", 1) if tag[3:5] == "xx" else tag
        element_path = ElementPath(_items(path), written)
        attribute = dictionary_attribute(written) if "x" not in written else None
        vr = _DECIDED_VRS.get(tag) or (
            attribute.vrs[0] if attribute and len(attribute.vrs) == 1 else ""
        )
        reason = None
        if "x" in written:
            reason = NotPlantedReason.MASKED_ELEMENT
        elif attribute is None or not vr:
            reason = NotPlantedReason.NO_SINGLE_VR
        elif len(path) + (vr == "SQ") > MAX_DEPTH:
            reason = NotPlantedReason.DEPTH_CAP
        elif self.spec.name != SEQUESTERED_FILE and self._sequesters(
            path, written, row
        ):
            reason = NotPlantedReason.SEQUESTERS_INSTANCE
        if reason is not None or attribute is None:
            self._record(element_path, vr, (), PlacementKind.NOT_PLANTED, row, reason)
            return
        item = _item(self.dataset, element_path.items)
        if vr == "SQ":
            _item(item, ((written, 0),))
            self._record(element_path, vr, (), PlacementKind.SEQUENCE, row)
            return
        linked = self._linked(path, tag)
        if linked is not None:
            kind, value = linked
            item[_number(written)] = new_element(element_path, vr, [value], self.codecs)
            self._record(element_path, vr, (value,), kind, row)
            return
        if not path and tag == self.spec.un_encoded:
            values, text = self.markers.values("UN", 1)
            element = pydicom.DataElement(_number(written), "UN", values[0])
            # pydicom gives a known attribute its own VR in place of UN.
            element.VR = "UN"
            item[_number(written)] = element
            self._record(element_path, "UN", text, PlacementKind.UN_ENCODED, row)
            return
        if not path and tag == self.spec.invalid and vr == "UI":
            _, (marker,) = self.markers.values("LO", 1)
            value = f"2.25.{marker}"
            # Built without pydicom's check, which would warn.
            item[_number(written)] = pydicom.DataElement(
                _number(written),
                vr,
                value,
                validation_mode=pydicom.config.IGNORE,
            )
            self._record(element_path, vr, (value,), PlacementKind.INVALID, row)
            return
        latin_1 = (
            bool(self.spec.character_set) and not path and (tag == _PATIENTS_NAME_TAG)
        )
        values, text = self.markers.values(
            vr, _least_count(attribute.vm), latin_1=latin_1
        )
        item[_number(written)] = new_element(element_path, vr, values, self.codecs)
        self._record(element_path, vr, text, PlacementKind.PLANTED, row)

    def _sequesters(self, path: tuple[str, ...], tag: str, row: str) -> bool:
        """Return whether the Basic Profile's action on a place sequesters."""
        return (
            _basic_profile_actions()[row] == "X"
            and resolve_plain_x_in_iod(self.iod, tag, path).extent
            is RemovalExtent.SEQUESTER
        )

    def _linked(
        self, path: tuple[str, ...], tag: str
    ) -> tuple[PlacementKind, str] | None:
        """Return the linked value of an attribute, and set its item's class."""
        top_level = {
            _SOP_INSTANCE_TAG: (PlacementKind.LINKED_UID, self.spec.sop_instance),
            _SERIES_TAG: (PlacementKind.LINKED_UID, self.spec.series),
            _STUDY_TAG: (PlacementKind.LINKED_UID, STUDY),
            _PATIENT_ID_TAG: (PlacementKind.LINKED_PATIENT, PATIENT_ID),
            _ISSUER_TAG: (PlacementKind.LINKED_PATIENT, ISSUER_OF_PATIENT_ID),
        }
        if not path and tag in top_level:
            return top_level[tag]
        if tag in _FRAME_OF_REFERENCE_TAGS:
            return PlacementKind.LINKED_UID, FRAME_OF_REFERENCE
        level = self.levels.get((path, tag))
        if level is None or tag not in REFERENCE_TAGS:
            return None
        if level is Level.STUDY:
            self._set_class(path, DETACHED_STUDY_MANAGEMENT, 0)
            return PlacementKind.LINKED_UID, STUDY
        if level is Level.SERIES:
            return PlacementKind.LINKED_UID, CT_SERIES
        target = _TARGETS.get(path[-1], self.spec.default_target)
        self._set_class(path, _SOP_CLASSES[target], 0)
        return PlacementKind.LINKED_UID, target

    def _set_class(self, path: tuple[str, ...], sop_class: str, index: int) -> None:
        """Give an item its Referenced SOP Class UID, where the IOD defines it."""
        if not self.iod.lookup(REFERENCED_SOP_CLASS_TAG, path):
            return
        items = (*_items(path[:-1]), (path[-1], index))
        item = _item(self.dataset, items)
        number = _number(REFERENCED_SOP_CLASS_TAG)
        if number not in item:
            element_path = ElementPath(items, REFERENCED_SOP_CLASS_TAG)
            item[number] = new_element(element_path, "UI", [sop_class], self.codecs)

    def _fill_sequences(self) -> None:
        """Give each sequence of Table E.1-1 without a marker below it one.

        The deepest sequences go first, so a marker put in one counts for
        the sequences that hold it. Only a marker counts: a linked value
        stays with a sequence that a preset keeps.
        """
        sequences = sorted(
            (
                (position, placement)
                for position, placement in enumerate(self.placements)
                if placement.kind is PlacementKind.SEQUENCE
            ),
            key=lambda each: (-len(each[1].path.items), each[0]),
        )
        profile = {(path, tag) for path, tag, _ in _profile_places(self.iod)}
        for position, sequence in sequences:
            inside = (*sequence.path.items, (sequence.path.tag, 0))
            if any(
                placement.path.items[: len(inside)] == inside
                and placement.kind in _MARKER_KINDS
                for placement in self.placements
            ):
                continue
            path = tuple(tag for tag, _ in inside)
            candidates = [
                attribute
                for definition in self.iod.definitions
                if definition.path == path
                and "x" not in definition.tag
                and (path, definition.tag) not in profile
                and (attribute := dictionary_attribute(definition.tag)) is not None
                and attribute.vr not in ("SQ", "UI")
                and len(attribute.vrs) == 1
            ]
            # Text first, which the residual search looks for.
            candidates.sort(key=lambda attribute: attribute.vr not in _CONTENT_VRS)
            if not candidates:
                self.placements[position] = dataclasses.replace(
                    sequence, reason=NotPlantedReason.NO_MARKER_CARRIER
                )
                continue
            attribute = candidates[0]
            values, text = self.markers.values(attribute.vr, _least_count(attribute.vm))
            element_path = ElementPath(inside, attribute.tag)
            _item(self.dataset, inside)[_number(attribute.tag)] = new_element(
                element_path, attribute.vr, values, self.codecs
            )
            self._record(element_path, attribute.vr, text, PlacementKind.CONTENT, "")

    def _reference_every_slice(self) -> None:
        """Have the structure set's RT Referenced Series reference each slice."""
        if self.spec.sop_class != RT_STRUCTURE_SET_STORAGE:
            return
        path = (*_RT_REFERENCED_CONTOUR_IMAGES, _CONTOUR_IMAGE_SEQUENCE)
        tag = "(0008,1155)"
        for index, target in enumerate(CT_SLICES[1:], start=1):
            items = (*_items(path[:-1]), (path[-1], index))
            element_path = ElementPath(items, tag)
            _item(self.dataset, items)[_number(tag)] = new_element(
                element_path, "UI", [target], self.codecs
            )
            self._set_class(path, CT_IMAGE_STORAGE, index)
            self._record(element_path, "UI", (target,), PlacementKind.LINKED_UID, tag)

    def _add_private_blocks(self) -> None:
        """Add a private block at the top level, and in an item."""
        places: list[tuple[tuple[str, int], ...]] = [
            (),
            ((PRIVATE_ITEM_SEQUENCE, 0),),
        ]
        for items in places:
            item = _item(self.dataset, items)
            creator = f"({PRIVATE_GROUP:04X},0010)"
            elements = [(creator, "LO")] + [
                (f"({PRIVATE_GROUP:04X},10{offset:02X})", vr)
                for offset, vr in enumerate(("LO", "PN", "DA"), start=1)
            ]
            for tag, vr in elements:
                values, text = self.markers.values(vr, 1)
                if values_problem(vr, "1", values):
                    raise ValueError("a private marker is invalid for its VR")
                item[_number(tag)] = pydicom.DataElement(_number(tag), vr, values[0])
                self._record(
                    ElementPath(items, tag),
                    vr,
                    text,
                    PlacementKind.PRIVATE,
                    PRIVATE_ATTRIBUTES_TAG,
                )

    def _add_review_copy(self) -> None:
        """Copy an earlier file's marker into an attribute the profile keeps."""
        if self.spec.review_copy is None:
            return
        tag, name, source = self.spec.review_copy
        (marker,) = [
            placement
            for placement in self.earlier[name].placements
            if placement.path == ElementPath((), source)
            and placement.kind is PlacementKind.PLANTED
        ]
        attribute = dictionary_attribute(tag)
        if attribute is None or attribute.vrs != ("LO",):
            raise ValueError("the copy goes in an attribute of VR LO")
        if tag in _basic_profile_actions() or _number(tag) in self.dataset:
            raise ValueError(
                "the copy goes in an empty attribute that Table E.1-1 does not list"
            )
        path = ElementPath((), tag)
        self.dataset[_number(tag)] = new_element(
            path, "LO", list(marker.values), self.codecs
        )
        self._record(path, "LO", marker.values, PlacementKind.REVIEW_COPY, "")

    def _set(self, items: Sequence[tuple[str, int]], tag: str, values: list) -> None:
        """Set an attribute that holds no marker, unless a marker is there."""
        item = _item(self.dataset, items)
        if _number(tag) in item:
            return
        attribute = dictionary_attribute(tag)
        if attribute is None:
            raise ValueError(f"{tag} is not in the pinned data dictionary")
        vr = "OW" if tag == "(7FE0,0010)" else attribute.vrs[0]
        item[_number(tag)] = new_element(
            ElementPath(tuple(items), tag), vr, values, self.codecs
        )

    def _add_structure(self) -> None:
        """Add the attributes that make the instance an image, ROI, plan, or dose."""
        put = self._set
        put((), "(0008,0016)", [self.spec.sop_class])
        if self.spec.sop_class == CT_IMAGE_STORAGE:
            put((), "(0008,0060)", ["CT"])
            put((), "(0008,0008)", ["ORIGINAL", "PRIMARY", "AXIAL"])
            put((), "(0018,0050)", ["2"])
            put((), "(0020,0032)", ["-1", "-1", str(2 * self.spec.slice_index)])
            put((), "(0020,0037)", ["1", "0", "0", "0", "1", "0"])
            put((), "(0028,1052)", ["-1024"])
            put((), "(0028,1053)", ["1"])
            self._add_pixels(16, 1, struct.pack("<4h", 0, 1024, 2048, 3072))
        elif self.spec.sop_class == RT_STRUCTURE_SET_STORAGE:
            put((), "(0008,0060)", ["RTSTRUCT"])
            put(_items(["(3006,0020)"]), "(3006,0022)", ["1"])
            put(_items(["(3006,0020)"]), "(3006,0036)", ["MANUAL"])
            put(_items(["(3006,0039)"]), "(3006,0084)", ["1"])
            contour = _items(["(3006,0039)", "(3006,0040)"])
            put(contour, "(3006,0042)", ["POINT"])
            put(contour, "(3006,0046)", ["1"])
            put(contour, "(3006,0050)", ["0", "0", "0"])
        elif self.spec.sop_class == RT_PLAN_STORAGE:
            put((), "(0008,0060)", ["RTPLAN"])
            put((), "(300A,000C)", ["PATIENT"])
        else:
            put((), "(0008,0060)", ["RTDOSE"])
            put((), "(0020,0032)", ["-1", "-1", "0"])
            put((), "(0020,0037)", ["1", "0", "0", "0", "1", "0"])
            put((), "(0028,0008)", ["2"])
            put((), "(0028,0009)", [0x3004000C])
            put((), "(3004,0002)", ["GY"])
            put((), "(3004,0004)", ["PHYSICAL"])
            put((), "(3004,000A)", ["PLAN"])
            put((), "(3004,000C)", ["0", "2"])
            put((), "(3004,000E)", ["0.001"])
            self._add_pixels(32, 0, struct.pack("<8I", *range(0, 8000, 1000)))

    def _add_pixels(self, bits: int, representation: int, data: bytes) -> None:
        """Add a 2 by 2 monochrome image of ``bits``-bit samples."""
        put = self._set
        put((), "(0028,0002)", [1])
        put((), "(0028,0004)", ["MONOCHROME2"])
        put((), "(0028,0010)", [2])
        put((), "(0028,0011)", [2])
        put((), "(0028,0030)", ["1", "1"])
        put((), "(0028,0100)", [bits])
        put((), "(0028,0101)", [bits])
        put((), "(0028,0102)", [bits - 1])
        put((), "(0028,0103)", [representation])
        put((), "(7FE0,0010)", [data])


def _written(dataset: pydicom.Dataset, spec: _Spec) -> bytes:
    """Return the instance written as a file in its transfer syntax."""
    meta = pydicom.dataset.FileMetaDataset()
    meta.MediaStorageSOPClassUID = pydicom.uid.UID(spec.sop_class)
    meta.MediaStorageSOPInstanceUID = pydicom.uid.UID(spec.sop_instance)
    meta.TransferSyntaxUID = pydicom.uid.UID(spec.transfer_syntax)
    meta.ImplementationClassUID = pydicom.uid.UID(IMPLEMENTATION_CLASS)
    meta.ImplementationVersionName = f"{MARKER_PREFIX}_CORPUS"
    dataset.file_meta = meta
    stream = io.BytesIO()
    pydicom.dcmwrite(stream, dataset, enforce_file_format=True)
    return stream.getvalue()
