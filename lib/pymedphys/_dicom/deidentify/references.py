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
instance: its identifiers, its patient, a digest of its content, and the
value at each reference site with the Referenced SOP Class UID (0008,1150)
beside it. Its ``repr`` shows only the IOD, so identifiers do not reach logs.
An attribute without a value at a Type 3 site is left out, since it means
the same as an absent one (PS3.5 Section 7.4.5). A sequence that pydicom
does not know, which it reads as UN from Implicit VR Little Endian, is
decoded with its VR in the pinned data dictionary.

Two instances are identical copies when their content is the same, and
their content is the same only when their data sets decode to the same
elements, with the same VRs and values. The content of a data set is, for each element in tag
order: its tag; its VR; for a value that pydicom holds as bytes, other than
an OB value, the value's byte order; and its value as Implicit VR Little
Endian encodes it (PS3.5 Sections 7.1.3 and 7.5), with its length, and with
every sequence and item of defined length. It leaves out the File Meta
Information, group 0002, and group lengths (gggg,0000), which PS3.5 Section
7.2 retires and whose values depend on the encoding; the preamble is not
part of the data set.

The VR is the one that applies in the data set: the VR that pydicom holds,
except that a VR that pydicom decides only when it writes the data set,
such as "US or SS", is decided as pydicom decides it, and that a UN value
whose tag has one VR in the pinned data dictionary is decoded with that VR
as Implicit VR Little Endian (PS3.5 Section 6.2.2), since pydicom reads an
attribute that it does not know from an Implicit VR file as UN. Each element
is read, decoded, and encoded again, so the content depends neither on
which little endian transfer syntax with native (uncompressed) Pixel Data
the file has, such as Implicit VR or Explicit VR Little Endian, as long as
a data dictionary gives every element's VR, nor on the length form of its
sequences, which values pydicom has read or deferred so far, or padding
that decoding removes.

Where the content cannot show that copies are equal, they conflict, which
sequesters them. An element that neither pydicom's data dictionaries nor
the pinned one lists, such as most private elements, has no VR in an
Implicit VR file, so pydicom reads it as UN and keeps its value as bytes,
which could encode a value of any VR. Such an element conflicts with a copy
that holds it with a VR, as a copy read from an Explicit VR file does. The
same bytes can also be different values in different byte orders: OD, OF,
OL, OV, and OW values are in the byte order of their data set (PS3.5
Section 7.3), which pydicom keeps. The byte order in the content is that of
the data set that holds the value, or little endian for a value decoded
from UN, and a data set built in memory, rather than read, has none. So a
copy in the retired Explicit VR Big Endian conflicts with a little endian
one that holds such a value, and a copy built in memory conflicts with one
read from a file. Some differences of encoding also make copies conflict. Encapsulated Pixel Data
is compared in its encapsulated form, so a compressed and an uncompressed
copy of an image conflict, and so do copies of an image whose Pixel Data is
8-bit, which Implicit VR Little Endian holds as OW and Explicit VR Little
Endian can hold as OB (PS3.5 Annex A).

A record keeps a digest of the content rather than the data set, so records
stay small. It must be built from a data set read in full: not read with
``stop_before_pixels`` or ``specific_tags``, and with every deferred value
still readable from its file. Otherwise two copies that differ only in the
elements left unread would have the same content.

Building a record reads every value of the data set without changing it, and
neither logs nor warns; pydicom's own warnings and errors while it reads,
decodes, and encodes values are the entry point's to redact, as
:func:`pymedphys._dicom.anonymise.diagnostics.redacted_pydicom_diagnostics`
does for the legacy tools.
"""

from __future__ import annotations

import copy
import dataclasses
import enum
import functools
import hashlib
import re
import struct
import types
from collections.abc import Iterator, Mapping

from pymedphys._imports import pydicom

from .iods import IOD
from .pseudonyms import SubjectIdentity
from .sop_classes import iod_for_sop_class
from .standard import load_data_dictionary
from .uids import normalise_uid

SOP_CLASS_TAG = "(0008,0016)"
REFERENCED_SOP_CLASS_TAG = "(0008,1150)"
REFERENCED_SOP_INSTANCE_TAG = "(0008,1155)"
PATIENT_ID_TAG = "(0010,0020)"
ISSUER_OF_PATIENT_ID_TAG = "(0010,0021)"
ITEM_TAG = 0xFFFEE000


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
class InstanceRecord:
    """What the reference graph needs from one instance.

    Build one with :meth:`from_dataset`. Its ``repr`` shows only the IOD. It
    is small and can be pickled, so records can be built where the data
    sets are read, and the data sets dropped.

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
    digest : bytes
        The SHA-256 digest of the data set's content, as the module describes
        it, so two data sets have the same digest exactly when their content
        is the same. It only compares the inputs of a run, and is never
        stored or reported.
    """

    iod: str | None
    sop_instance: str | None = dataclasses.field(repr=False)
    series: str | None = dataclasses.field(repr=False)
    study: str | None = dataclasses.field(repr=False)
    references: tuple[Reference, ...] = dataclasses.field(repr=False)
    patient: SubjectIdentity | None = dataclasses.field(repr=False)
    digest: bytes = dataclasses.field(repr=False)

    @classmethod
    def from_dataset(cls, dataset: pydicom.Dataset) -> InstanceRecord:
        """Return the record of a data set, without changing the data set.

        ``dataset`` must be read in full: not read with
        ``stop_before_pixels`` or ``specific_tags``, and with every deferred
        value still readable from its file. The digest covers only the
        elements the data set holds, so copies that differ only in elements
        left unread would otherwise be identical.
        """
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
        return cls(
            iod,
            _uid(dataset, IDENTITY_TAGS[Level.INSTANCE]),
            _uid(dataset, IDENTITY_TAGS[Level.SERIES]),
            _uid(dataset, IDENTITY_TAGS[Level.STUDY]),
            tuple(found),
            _patient(dataset),
            _content_digest(dataset),
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
    dataset: pydicom.Dataset, path: tuple[str, ...]
) -> Iterator[pydicom.Dataset]:
    """Yield every item of the innermost sequence of ``path``."""
    if not path:
        yield dataset
        return
    element = _element(dataset, path[0])
    if element is not None:
        for item in _sequence(element, path[0]):
            yield from _items(item, path[1:])


def _sequence(element: pydicom.DataElement, tag: str) -> Iterator[pydicom.Dataset]:
    """Yield the items of a sequence, decoding a UN value with its dictionary VR.

    PS3.5 Section 6.2.2 lets a reader that knows the VR of a UN value decode
    it as Implicit VR Little Endian, whatever the transfer syntax. pydicom
    reads a sequence it does not know as UN in Implicit VR Little Endian,
    unless its length is undefined.
    """
    if element.VR == "SQ":
        yield from element.value
    elif (
        element.VR == "UN"
        and isinstance(element.value, bytes)
        and _dictionary_vrs().get(tag) == "SQ"
    ):
        yield from pydicom.values.convert_SQ(element.value, True, True)


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


def _content_digest(dataset: pydicom.Dataset) -> bytes:
    digest = hashlib.sha256()
    for encoded in _encoded(dataset, pydicom.charset.default_encoding, [dataset]):
        digest.update(encoded)
    return digest.digest()


def _encoded(
    dataset: pydicom.Dataset,
    encodings: str | list[str],
    ancestors: list[pydicom.Dataset],
) -> Iterator[bytes]:
    """Yield the content of each element of ``dataset``, the first of ``ancestors``.

    ``ancestors`` holds the data set and the items that contain it, nearest
    first, up to the data set of the instance.
    """
    encodings = dataset.get("SpecificCharacterSet", encodings)
    for tag in sorted(dataset.keys()):
        if tag.element == 0 or (len(ancestors) == 1 and tag.group == 2):
            continue
        element, byte_order = _as_held(dataset[tag], encodings, ancestors)
        if element.VR == "SQ":
            encoded = _with_length(
                tag,
                b"".join(
                    _with_length(
                        ITEM_TAG,
                        b"".join(_encoded(item, encodings, [item, *ancestors])),
                    )
                    for item in element.value
                ),
            )
        else:
            written = pydicom.filebase.DicomBytesIO()
            written.is_implicit_VR = True
            written.is_little_endian = True
            pydicom.filewriter.write_data_element(written, element, encodings)
            encoded = written.getvalue()
        vr = element.VR.encode()
        # The tag, then the VR and the byte order, then the length and value.
        yield encoded[:4] + struct.pack("<B", len(vr)) + vr + byte_order + encoded[4:]


def _with_length(tag: int, value: bytes) -> bytes:
    """Return the tag, the value's length, and the value (PS3.5 Section 7.1.3)."""
    return struct.pack("<HHI", tag >> 16, tag & 0xFFFF, len(value)) + value


def _as_held(
    element: pydicom.DataElement,
    encodings: str | list[str],
    ancestors: list[pydicom.Dataset],
) -> tuple[pydicom.DataElement, bytes]:
    """Return the element with the VR that applies in its data set, and a byte order.

    The element is in the first of ``ancestors``, which holds its data set
    and the items that contain it, nearest first. Its VR is the one that
    pydicom holds, except that a UN value whose tag has one VR in the
    pinned data dictionary is decoded with that VR as Implicit VR Little
    Endian (PS3.5 Section 6.2.2), and that a VR that pydicom decides only
    when it writes the data set, such as "US or SS", is decided as pydicom
    decides it, from the data set and the items that contain it. Neither
    changes the data set.

    The byte order is ``b"<"`` for little endian, ``b">"`` for big endian,
    or ``b"?"`` for none, for a value that pydicom holds as bytes, other
    than an OB value, which is a stream of bytes: that of the data set, or
    little endian for a value decoded from UN. A data set built in memory,
    rather than read, has none. It is ``b"-"`` for any other value.
    """
    dataset = ancestors[0]
    little_endian = dataset.original_encoding[1]
    tag = f"({element.tag.group:04X},{element.tag.element:04X})"
    if (
        element.VR == "UN"
        and isinstance(element.value, bytes)
        and tag in _dictionary_vrs()
    ):
        raw = pydicom.dataelem.RawDataElement(
            element.tag,
            _dictionary_vrs()[tag],
            len(element.value),
            element.value,
            0,
            True,
            True,
        )
        element = pydicom.dataelem.convert_raw_data_element(
            raw, encoding=pydicom.charset.convert_encodings(encodings)
        )
        little_endian = True
    elif element.VR in pydicom.valuerep.AMBIGUOUS_VR:
        # pydicom decides the VR of the copy in place.
        element = copy.copy(element)
        pydicom.filewriter.correct_ambiguous_vr_element(
            element, dataset, little_endian is not False, ancestors
        )
    held_as_bytes = isinstance(element.value, bytes) or element.is_buffered
    if element.VR == "OB" or not held_as_bytes:
        return element, b"-"
    return element, {True: b"<", False: b">", None: b"?"}[little_endian]
