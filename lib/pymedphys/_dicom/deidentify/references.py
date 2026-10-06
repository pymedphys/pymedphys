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

"""Find where an instance refers to other instances, series, and studies.

An IOD's reference sites are derived from the PS3.3 module and macro tables
that :mod:`~pymedphys._dicom.deidentify.iods` generates, not listed by hand:
each place inside a sequence where the IOD defines one of
:data:`REFERENCE_TAGS`, such as Referenced SOP Instance UID (0008,1155) in an
RT Plan's Referenced Structure Set Sequence (300C,0060), with the attribute's
Type there. The attribute's tag gives the level of what it names, except
that Referenced SOP Instance UID names a study in the items of a Referenced
Study Sequence (0008,1110) or an RT Referenced Study Sequence (3006,0012),
where Referenced SOP Class UID (0008,1150) is the study's own class (PS3.3
Sections 10.6.1 and C.8.8.5.4). At the top level of the data set, the same
Series and Study Instance UIDs identify the instance itself.

An :class:`InstanceRecord` holds what the reference graph
(:mod:`~pymedphys._dicom.deidentify.reference_graph`) needs from one
instance: its identifiers, its patient, a digest of its source bytes, the
value at each reference site with the Referenced SOP Class UID (0008,1150)
beside it, and its frames of reference: its own Frame of Reference UID
(0020,0052), and, where its IOD defines them, the frames of reference that
an RT Structure Set lists and those its ROIs are defined in. Its ``repr``
shows only the IOD, so identifiers do not reach logs. An attribute without a value at a Type 3 site is left out,
since it means the same as an absent one (PS3.5 Section 7.4.5). Each
sequence that pydicom holds undecoded is decoded by
:func:`~pymedphys._dicom.deidentify.sequences.decode_items`, including one
that pydicom does not know, which it reads as UN from Implicit VR Little
Endian, with its VR in the pinned data dictionary, and one whose value does
not hold only items raises :class:`UnreadableSequence`.

Two inputs are identical copies only when their source bytes are the same:
they have the same Transfer Syntax UID (0002,0010), and the same bytes from
the end of the File Meta Information to the end of the file, leaving out
each group length element (gggg,0000) and the Data Set Trailing Padding
(FFFC,FFFC) at the top level of the data set (PS3.5 Section 7.2 and PS3.10
Section 7.2). The preamble and the File Meta Information are not part of
the data set (PS3.10 Section 7.1). A group length or padding inside an item
is compared as it is. The bytes are found by
:func:`~pymedphys._dicom.deidentify.file_layout.read_file_layout`, without
decoding any value, so neither a decoder nor a guessed VR can make
different values compare equal.

So copies conflict, which sequesters them, when they differ in any byte of
the data set, including differences of encoding alone: another transfer
syntax, such as Implicit VR rather than Explicit VR Little Endian, another
length form of a sequence or item, other padding of a value, or compressed
rather than native Pixel Data. A copy whose bytes cannot be shown to be
sound conflicts with every other copy: one whose structure cannot be read
to its end, one without a Transfer Syntax UID, one in a transfer syntax
whose data set is deflated or big endian, and one with a top-level group
length or Data Set Trailing Padding that holds items, whose elements would
otherwise be compared as if they were at the top level.

A record keeps a digest of the source bytes rather than the bytes, so
records stay small. Building one reads the file's bytes into a data set of
its own, so the caller's objects are left unchanged. It neither logs nor
warns; pydicom's warnings and log records, from reading the file until
the record is built, including those from decoding values and sequences,
are redacted by :func:`.diagnostics.redacted_diagnostics`, and pydicom's
errors are the entry point's to redact.
"""

from __future__ import annotations

import dataclasses
import enum
import functools
import hashlib
import io
import re
import struct
import types
from collections.abc import Iterator, Mapping, Sequence

from pymedphys._imports import pydicom

from .diagnostics import redacted_diagnostics
from .file_layout import (
    BIG_ENDIAN_TRANSFER_SYNTAXES,
    ElementPath,
    Region,
    read_file_layout,
)
from .iods import IOD
from .pseudonyms import SubjectIdentity
from .sequences import UnreadableItems, decode_items
from .sop_classes import iod_for_sop_class
from .standard import load_data_dictionary
from .uids import normalise_uid

SOP_CLASS_TAG = "(0008,0016)"
REFERENCED_SOP_CLASS_TAG = "(0008,1150)"
REFERENCED_SOP_INSTANCE_TAG = "(0008,1155)"
FRAME_OF_REFERENCE_TAG = "(0020,0052)"
# Referenced Frame of Reference Sequence, whose items list the frames of
# reference of an RT Structure Set, and the path in each item to the images
# its contours are on (PS3.3 Section C.8.8.5).
REFERENCED_FRAME_OF_REFERENCE_SEQUENCE = "(3006,0010)"
FRAME_IMAGE_PATH = ("(3006,0012)", "(3006,0014)", "(3006,0016)")
# Structure Set ROI Sequence, and the frame of reference each ROI is in.
STRUCTURE_SET_ROI_SEQUENCE = "(3006,0020)"
REFERENCED_FRAME_OF_REFERENCE_UID_TAG = "(3006,0024)"
PATIENT_ID_TAG = "(0010,0020)"
ISSUER_OF_PATIENT_ID_TAG = "(0010,0021)"
_TRAILING_PADDING_TAG = "(FFFC,FFFC)"
# Data Set Trailing Padding is in its own region, at the top level or in an item.
_DATA_SET_REGIONS = (Region.DATA_SET, Region.TRAILING_PADDING)
_Within = tuple[tuple[str, int], ...]


class UnreadableSequence(Exception):
    """A sequence whose value does not hold only items.

    Not a :class:`ValueError`, which code that rejects invalid input could
    catch by accident. The message names the sequence by its path and never
    quotes a value.
    """

    def __init__(self, path: ElementPath) -> None:
        super().__init__(path)
        self.path = path

    def __str__(self) -> str:
        return f"{self.path} has items that cannot be read"


class Level(enum.Enum):
    """What a UID identifies: an instance, a series, or a study."""

    INSTANCE = "instance"
    SERIES = "series"
    STUDY = "study"


# The attributes that make a reference when they are inside a sequence, and
# the level of what they name, except in the items of STUDY_SEQUENCES.
REFERENCE_TAGS: Mapping[str, Level] = types.MappingProxyType(
    {
        REFERENCED_SOP_INSTANCE_TAG: Level.INSTANCE,
        "(0008,1167)": Level.INSTANCE,  # Multi-frame Source SOP Instance UID
        "(0020,000E)": Level.SERIES,  # Series Instance UID
        "(0020,000D)": Level.STUDY,  # Study Instance UID
    }
)
# The sequences in whose items Referenced SOP Instance UID names a study,
# by its Study Instance UID (PS3.3 Sections 10.6.1 and C.8.8.5.4).
STUDY_SEQUENCES = frozenset(
    {
        "(0008,1110)",  # Referenced Study Sequence
        "(3006,0012)",  # RT Referenced Study Sequence
    }
)
# The top-level attributes that identify an instance, its series, and its
# study. Each is Type 1 in a mandatory module of every supported IOD.
IDENTITY_TAGS: Mapping[Level, str] = types.MappingProxyType(
    {
        Level.INSTANCE: "(0008,0018)",  # SOP Instance UID
        Level.SERIES: "(0020,000E)",
        Level.STUDY: "(0020,000D)",
    }
)


@dataclasses.dataclass(frozen=True)
class ReferenceSite:
    """A place where an IOD refers to an instance, a series, or a study.

    Attributes
    ----------
    path : tuple of str
        The tags of the sequences whose items contain the reference,
        outermost first. Never empty.
    tag : str
        The tag of the referring attribute, a key of :data:`REFERENCE_TAGS`.
    level : Level
        What the attribute's value names: the level :data:`REFERENCE_TAGS`
        gives the tag, except that Referenced SOP Instance UID names a study
        where the innermost sequence of ``path`` is one of
        :data:`STUDY_SEQUENCES`.
    type : str
        The attribute's Type there, ``"1"``, ``"2"``, or ``"3"``: where the
        IOD's modules give it several, the strictest, with 1C counting as 1
        and 2C as 2, since a conditional element that is present has their
        requirements (PS3.5 Sections 7.4.2 and 7.4.4).
    """

    path: tuple[str, ...]
    tag: str
    level: Level
    type: str

    @property
    def attribute(self) -> tuple[str, ...]:
        """The tags from the outermost sequence to the referring attribute."""
        return (*self.path, self.tag)


def reference_sites(iod: IOD) -> tuple[ReferenceSite, ...]:
    """Return every place inside a sequence where ``iod`` defines a reference.

    Parameters
    ----------
    iod : IOD
        An IOD with its expanded attribute definitions, as
        :func:`~pymedphys._dicom.deidentify.iods.load_iod_tables` gives it.

    Returns
    -------
    tuple of ReferenceSite
        One for each path and tag, in the order of the IOD's definitions,
        even where several modules define the attribute there, with the
        strictest of their Types.

    Examples
    --------
    >>> rt_plan = iod_for_sop_class("1.2.840.10008.5.1.4.1.1.481.5")
    >>> [
    ...     (site.level.value, site.type)
    ...     for site in reference_sites(rt_plan)
    ...     if site.attribute == ("(300C,0060)", "(0008,1155)")
    ... ]  # Referenced Structure Set Sequence
    [('instance', '1')]
    >>> [
    ...     (site.level.value, site.type)
    ...     for site in reference_sites(rt_plan)
    ...     if site.attribute == ("(0008,1110)", "(0008,1155)")
    ... ]  # Referenced Study Sequence
    [('study', '1')]
    """
    places = dict.fromkeys(
        (definition.path, definition.tag)
        for definition in iod.definitions
        if definition.path and definition.tag in REFERENCE_TAGS
    )
    # The strictest Type, with 1C counting as 1 and 2C as 2.
    return tuple(
        ReferenceSite(
            path,
            tag,
            _level(path, tag),
            min(each.type.removesuffix("C") for each in iod.lookup(tag, path)),
        )
        for path, tag in places
    )


def _level(path: tuple[str, ...], tag: str) -> Level:
    """Return the level of what ``tag`` names in the items of ``path``."""
    if tag == REFERENCED_SOP_INSTANCE_TAG and path[-1] in STUDY_SEQUENCES:
        return Level.STUDY
    return REFERENCE_TAGS[tag]


@dataclasses.dataclass(frozen=True)
class Reference:
    """The value at one of an instance's reference sites.

    Its ``repr`` shows only the site.

    Attributes
    ----------
    site : ReferenceSite
    target : str
        The UID the reference names, without trailing NUL and space padding,
        or ``""`` if the attribute has no value, or a value that is not one
        UID, such as several values. At a Type 3 site, an attribute without a
        value means the same as an absent one (PS3.5 Section 7.4.5), so it
        makes no reference.
    target_class : str or None
        The Referenced SOP Class UID (0008,1150) in the same item, without
        padding, or ``None`` if the item has none, or its value is not one
        UID.
    """

    site: ReferenceSite
    target: str = dataclasses.field(repr=False)
    target_class: str | None = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True)
class FrameUse:
    """An item of an RT Structure Set's Referenced Frame of Reference Sequence.

    Its ``repr`` shows nothing of its values.

    Attributes
    ----------
    frame : str
        Its Frame of Reference UID (0020,0052), without padding, or ``""``
        if it has none, or a value that is not one UID.
    images : tuple of str
        The Referenced SOP Instance UID (0008,1155) of each item of its
        Contour Image Sequences (3006,0016), in its RT Referenced Study
        Sequence (3006,0012) and RT Referenced Series Sequence (3006,0014),
        in the order of the items, leaving out those without one UID.
    """

    frame: str = dataclasses.field(repr=False)
    images: tuple[str, ...] = dataclasses.field(repr=False)


@dataclasses.dataclass(frozen=True)
class InstanceRecord:
    """What the reference graph needs from one instance.

    Build one with :meth:`from_file`. Its ``repr`` shows only the IOD. It
    is small and can be pickled, so records can be built where the files
    are read, and the files dropped.

    Attributes
    ----------
    iod : str or None
        The name of the instance's IOD, such as ``"RT Plan"``, if its SOP
        Class UID (0008,0016) is a Storage SOP Class of an IOD whose tables
        are generated; otherwise ``None``, and the record has no references.
    sop_instance, series, study : str or None
        The instance's SOP Instance UID (0008,0018), Series Instance UID
        (0020,000E), and Study Instance UID (0020,000D) at the top level,
        without padding. ``None`` if the attribute is absent, empty, or has
        a value that is not one UID, such as several values.
    references : tuple of Reference
        Every value at the IOD's reference sites, by site in the order of
        :func:`reference_sites`, then in the order of the items.
    patient : SubjectIdentity or None
        The identity of the instance's Patient ID (0010,0020) with its Issuer
        of Patient ID (0010,0021), from which pseudonyms are derived, taking
        each attribute's text with any several values joined by backslashes.
        ``None`` if the Patient ID is absent, not text, or empty once its
        padding is removed: such an instance names no patient.
    digest : bytes or None
        The SHA-256 digest of the file's source bytes, as the module
        describes them: the length of the Transfer Syntax UID without
        padding as a 32-bit little endian number, the UID, then each byte of
        the data set in file order, except those of the top-level group
        lengths and Data Set Trailing Padding. Two files have the same digest
        exactly when their source bytes are the same. ``None`` if they cannot
        be shown to be sound: the file's structure cannot be read to its end,
        it has no Transfer Syntax UID, or one whose data set is deflated or
        big endian, or a top-level group length or Data Set Trailing Padding
        holds items. It only compares the
        inputs of a run, and is never stored or reported.
    frame_of_reference : str or None
        The Frame of Reference UID (0020,0052) at the top level, without
        padding, or ``None`` if it is absent, empty, or not one UID.
    frames : tuple of FrameUse
        Each item of the Referenced Frame of Reference Sequence (3006,0010),
        where the IOD defines its Frame of Reference UID, in order.
    roi_frames : tuple of str
        The Referenced Frame of Reference UID (3006,0024) of each item of the
        Structure Set ROI Sequence (3006,0020), where the IOD defines it, in
        order, without padding, or ``""`` for an item without one UID.
    """

    iod: str | None
    sop_instance: str | None = dataclasses.field(repr=False)
    series: str | None = dataclasses.field(repr=False)
    study: str | None = dataclasses.field(repr=False)
    references: tuple[Reference, ...] = dataclasses.field(repr=False)
    patient: SubjectIdentity | None = dataclasses.field(repr=False)
    digest: bytes | None = dataclasses.field(repr=False)
    frame_of_reference: str | None = dataclasses.field(default=None, repr=False)
    frames: tuple[FrameUse, ...] = dataclasses.field(default=(), repr=False)
    roi_frames: tuple[str, ...] = dataclasses.field(default=(), repr=False)

    @classmethod
    def from_file(cls, data: bytes | bytearray | memoryview) -> InstanceRecord:
        """Return the record of a DICOM PS3.10 file.

        Parameters
        ----------
        data : bytes, bytearray, or memoryview
            The whole file. It is copied, and read into a data set of the
            record's own, so the caller's objects are left unchanged.

        Returns
        -------
        InstanceRecord

        Raises
        ------
        UnreadableSequence
            If the value of a sequence on the path to a reference site, or
            to a frame of reference that the record holds, does not hold
            only items, as in a file truncated within it, or is big
            endian, which only pydicom can read.
        Exception
            Whatever pydicom raises for a file that it cannot read, such as
            :class:`pydicom.errors.InvalidDicomError`. Its message may hold
            values from the file, so the entry point redacts it.
        """
        data = bytes(data)
        # pydicom converts each value when it is first read, not in
        # dcmread, so the redaction lasts until the record is built.
        with redacted_diagnostics():
            dataset = pydicom.dcmread(io.BytesIO(data), defer_size=None)
            sop_class = _uid(dataset, SOP_CLASS_TAG)
            iod, sites = _iod_and_sites(sop_class) if sop_class else (None, ())
            found = []
            for site in sites:
                for item in _items(dataset, site.path):
                    element = _element(item, site.tag)
                    if element is None or (site.type == "3" and _is_empty(element)):
                        continue
                    target = _uid(item, site.tag) or ""
                    target_class = _uid(item, REFERENCED_SOP_CLASS_TAG)
                    found.append(Reference(site, target, target_class))
            frames, roi_frames = _frames(dataset, sop_class) if iod else ((), ())
            return cls(
                iod,
                _uid(dataset, IDENTITY_TAGS[Level.INSTANCE]),
                _uid(dataset, IDENTITY_TAGS[Level.SERIES]),
                _uid(dataset, IDENTITY_TAGS[Level.STUDY]),
                tuple(found),
                _patient(dataset),
                _source_digest(data),
                _uid(dataset, FRAME_OF_REFERENCE_TAG),
                frames,
                roi_frames,
            )

    def identifier(self, level: Level) -> str | None:
        """Return the UID that identifies the instance's entity at ``level``."""
        return {
            Level.INSTANCE: self.sop_instance,
            Level.SERIES: self.series,
            Level.STUDY: self.study,
        }[level]


@functools.lru_cache(maxsize=128)
def _iod_and_sites(sop_class: str) -> tuple[str | None, tuple[ReferenceSite, ...]]:
    iod = iod_for_sop_class(sop_class)
    if iod is None:
        return None, ()
    return iod.name, reference_sites(iod)


@functools.lru_cache(maxsize=128)
def _frame_places(sop_class: str) -> tuple[bool, bool]:
    """Return whether the IOD defines the listed frames and the ROIs' frames."""
    iod = iod_for_sop_class(sop_class)
    places = (
        set()
        if iod is None
        else {(definition.path, definition.tag) for definition in iod.definitions}
    )
    return (
        ((REFERENCED_FRAME_OF_REFERENCE_SEQUENCE,), FRAME_OF_REFERENCE_TAG) in places,
        ((STRUCTURE_SET_ROI_SEQUENCE,), REFERENCED_FRAME_OF_REFERENCE_UID_TAG)
        in places,
    )


def _frames(
    dataset: pydicom.Dataset, sop_class: str
) -> tuple[tuple[FrameUse, ...], tuple[str, ...]]:
    """Return the frames of reference that an instance lists, and its ROIs'."""
    listed, of_rois = _frame_places(sop_class)
    frames = []
    if listed:
        path = (REFERENCED_FRAME_OF_REFERENCE_SEQUENCE,)
        for index, item in enumerate(_items(dataset, path)):
            within = ((REFERENCED_FRAME_OF_REFERENCE_SEQUENCE, index),)
            images = tuple(
                image
                for each in _items(item, FRAME_IMAGE_PATH, within)
                if (image := _uid(each, REFERENCED_SOP_INSTANCE_TAG))
            )
            frames.append(FrameUse(_uid(item, FRAME_OF_REFERENCE_TAG) or "", images))
    roi_frames = ()
    if of_rois:
        roi_frames = tuple(
            _uid(item, REFERENCED_FRAME_OF_REFERENCE_UID_TAG) or ""
            for item in _items(dataset, (STRUCTURE_SET_ROI_SEQUENCE,))
        )
    return tuple(frames), roi_frames


def _element(dataset: pydicom.Dataset, tag: str) -> pydicom.DataElement | None:
    return dataset.get(int(tag[1:5] + tag[6:10], 16))


def _uid(dataset: pydicom.Dataset, tag: str) -> str | None:
    """Return the attribute's value without padding, if it is one non-empty UID."""
    element = _element(dataset, tag)
    if element is None or not isinstance(element.value, str):
        return None
    return normalise_uid(str(element.value)) or None


def _is_empty(element: pydicom.DataElement) -> bool:
    """Return whether the element has no value, or only padding."""
    value = element.value
    return element.VM == 0 or (isinstance(value, str) and not normalise_uid(value))


def _items(
    dataset: pydicom.Dataset, path: tuple[str, ...], within: _Within = ()
) -> Iterator[pydicom.Dataset]:
    """Yield every item of the innermost sequence of ``path``.

    ``within`` is the path of the items that hold ``dataset``, as in
    :class:`~pymedphys._dicom.deidentify.file_layout.ElementPath`.
    """
    if not path:
        yield dataset
        return
    sequence = _sequence(dataset, ElementPath(within, path[0]))
    for index, item in enumerate(sequence):
        yield from _items(item, path[1:], (*within, (path[0], index)))


def _sequence(dataset: pydicom.Dataset, path: ElementPath) -> Sequence[pydicom.Dataset]:
    """Return the items of the sequence at ``path``, or none if it is absent.

    pydicom decodes a sequence as it reads the file only if its length is
    undefined, and holds any other raw, to decode when it is first accessed
    without checking its items. A raw value is decoded here instead, by
    :func:`~pymedphys._dicom.deidentify.sequences.decode_items`, with VR SQ
    in Explicit VR, or, where the pinned dictionary gives its attribute VR
    SQ, without a VR in Implicit VR, or as UN, which PS3.5 Section 6.2.2
    lets a reader that knows its VR decode as Implicit VR Little Endian,
    whatever the transfer syntax. A value that does not hold only items
    raises :class:`UnreadableSequence`. Each sequence of defined length
    nested in the items is left raw, to be decoded here by its own path.
    Items are decoded in pydicom's default character set, whatever the
    Specific Character Set (0008,0005) of the data set that holds them,
    since only UIDs are read from them.
    """
    element = dataset.get_item(int(path.tag[1:5] + path.tag[6:10], 16))
    if not isinstance(element, pydicom.dataelem.RawDataElement):
        return element.value if element is not None and element.VR == "SQ" else ()
    if element.VR not in ("SQ", None, "UN") or (
        element.VR != "SQ" and _dictionary_vrs().get(path.tag) != "SQ"
    ):
        return ()
    explicit = element.VR == "SQ"
    try:
        return decode_items(
            element.value or b"",
            explicit=explicit,
            little_endian=element.is_little_endian or not explicit,
            offset=element.value_tell or 0,
            nested=False,
        )
    except UnreadableItems:
        pass
    raise UnreadableSequence(path)


@functools.lru_cache(maxsize=None)
def _dictionary_vrs() -> Mapping[str, str]:
    """Return the VR of each tag that has one VR in the pinned data dictionary.

    A tag of a repeating group, such as (60xx,3000), and a tag whose VR
    depends on the data set, such as "US or SS", are left out.
    """
    return types.MappingProxyType(
        {
            attribute.tag: attribute.vr
            for attribute in load_data_dictionary().attributes
            if re.fullmatch("[A-Z]{2}", attribute.vr) and attribute.vr != "UN"
        }
    )


def _text(dataset: pydicom.Dataset, tag: str) -> str:
    """Return the attribute's text, with several values joined by backslashes."""
    element = _element(dataset, tag)
    value = None if element is None else element.value
    if isinstance(value, pydicom.multival.MultiValue):
        return "\\".join(str(each) for each in value)
    return value if isinstance(value, str) else ""


def _patient(dataset: pydicom.Dataset) -> SubjectIdentity | None:
    try:
        return SubjectIdentity.from_patient_id(
            _text(dataset, PATIENT_ID_TAG), _text(dataset, ISSUER_OF_PATIENT_ID_TAG)
        )
    except ValueError:  # The Patient ID is empty.
        return None


def _source_digest(data: bytes) -> bytes | None:
    """Return the digest of the file's source bytes, or ``None`` if unsound."""
    try:
        layout = read_file_layout(data)
    except ValueError:  # The data set is deflated.
        return None
    syntax = layout.transfer_syntax
    if not layout.readable or not syntax or syntax in BIG_ENDIAN_TRANSFER_SYNTAXES:
        return None
    # The UID's length first, so that its bytes cannot run into the data set's.
    encoded = syntax.encode()
    digest = hashlib.sha256(struct.pack("<I", len(encoded)) + encoded)
    for span in layout.spans:
        location = span.location
        if location.region not in _DATA_SET_REGIONS or location.element is None:
            continue
        items, tag = location.element.items, location.element.tag
        if not _is_left_out(items[0][0] if items else tag):
            digest.update(data[span.start : span.end])
        elif items:
            # An element left out holds items, whose elements would
            # otherwise be compared as if at the top level.
            return None
    return digest.digest()


def _is_left_out(tag: str) -> bool:
    """Return whether a top-level element with ``tag`` is left out of the digest."""
    return tag[6:10] == "0000" or tag == _TRAILING_PADDING_TAG
