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
Type there. At the top level of the data set, the same Series and Study
Instance UIDs identify the instance itself.

An :class:`InstanceRecord` holds what the reference graph
(:mod:`~pymedphys._dicom.deidentify.reference_graph`) needs from one
instance: its identifiers, and the value at each reference site with the
Referenced SOP Class UID (0008,1150) beside it. Its ``repr`` shows only the
IOD, so identifiers do not reach logs. An attribute without a value at a
Type 3 site is left out, since it means the same as an absent one (PS3.5
Section 7.4.5). A sequence that pydicom does not know, which it reads as UN
from Implicit VR Little Endian, is decoded with its VR in the pinned data
dictionary. Building a record reads the data set without changing it, and
neither logs nor warns; pydicom's own warnings while it decodes values are
the entry point's to redact, as
:func:`pymedphys._dicom.anonymise.diagnostics.redacted_pydicom_diagnostics`
does for the legacy tools.
"""

from __future__ import annotations

import dataclasses
import enum
import functools
import types
from collections.abc import Iterator, Mapping

from pymedphys._imports import pydicom

from .iods import IOD
from .sop_classes import iod_for_sop_class
from .standard import load_data_dictionary
from .uids import normalise_uid

SOP_CLASS_TAG = "(0008,0016)"
REFERENCED_SOP_CLASS_TAG = "(0008,1150)"


class Level(enum.Enum):
    """What a UID identifies: an instance, a series, or a study."""

    INSTANCE = "instance"
    SERIES = "series"
    STUDY = "study"


# The attributes that make a reference when they are inside a sequence, and
# the level of what they name.
REFERENCE_TAGS: Mapping[str, Level] = types.MappingProxyType(
    {
        "(0008,1155)": Level.INSTANCE,  # Referenced SOP Instance UID
        "(0008,1167)": Level.INSTANCE,  # Multi-frame Source SOP Instance UID
        "(0020,000E)": Level.SERIES,  # Series Instance UID
        "(0020,000D)": Level.STUDY,  # Study Instance UID
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
        What the attribute's value names.
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
            REFERENCE_TAGS[tag],
            min(each.type.removesuffix("C") for each in iod.lookup(tag, path)),
        )
        for path, tag in places
    )


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
    """

    iod: str | None
    sop_instance: str | None = dataclasses.field(repr=False)
    series: str | None = dataclasses.field(repr=False)
    study: str | None = dataclasses.field(repr=False)
    references: tuple[Reference, ...] = dataclasses.field(repr=False)

    @classmethod
    def from_dataset(cls, dataset: pydicom.Dataset) -> InstanceRecord:
        """Return the record of a data set, without changing the data set."""
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
        and tag in _dictionary_sequences()
    ):
        yield from pydicom.values.convert_SQ(element.value, True, True)


@functools.lru_cache(maxsize=None)
def _dictionary_sequences() -> frozenset[str]:
    """Return the tags whose VR is SQ in the pinned data dictionary."""
    return frozenset(
        attribute.tag
        for attribute in load_data_dictionary().attributes
        if attribute.vr == "SQ"
    )
