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

"""Read an instance's indicators of risk in its pixel data.

The engine does not change pixel data and never claims the Clean Pixel Data
or Clean Recognizable Visual Features Options. It reports indicators of risk
for review instead: of text burned into the pixel data, and of a face that
could be reconstructed and recognised. :func:`assess_pixel_risk` reads them
from one instance's attributes; it never inspects the pixel data, so the
absence of an indicator is not evidence that the risk is absent.

The indicators are:

- Burned In Annotation (0028,0301) of YES.
- Recognizable Visual Features (0028,0302) of YES. A received NO of either
  attribute counts for nothing: the assessment is the same as when the
  attribute is absent.
- Image Type (0008,0008) whose second value is SECONDARY, an image created
  after the examination (PS3.3 Section C.7.6.1.1.2). Screen captures, such
  as dose screens, are made after the examination and usually carry
  burned-in text (MIDI report Section 1.19.1).
- Conversion Type (0008,0064), of any value, which describes how an image
  was converted or captured, such as from a workstation's screen or a
  scanned document (PS3.3 Section C.8.6.1).
- An overlay group, (6000,eeee) to (601E,eeee), without Overlay Data
  (60xx,3000). PS3.3 before 2004 let an overlay lie in unused bits of Pixel
  Data (Section C.9.2), so its graphics and text stay in the pixel data when
  the Basic Profile removes the overlay's attributes.
- In an RT Structure Set, an ROI whose RT ROI Interpreted Type (3006,00A4)
  is EXTERNAL, the patient's outline, and that has contours: the outline of
  the head can be reconstructed into a face (MIDI report Section 1.20.4).

Values are compared whatever their case, though CS is upper case, so that a
writer's lower-case "yes" does not hide an indicator. An attribute that
cannot be read as its VR in the pinned data dictionary, such as an ROI
number that is not an integer, is itself reported, as unreadable evidence
of the risk that it bears on, since reading it could otherwise hide an
indicator. Findings name attribute paths, never values.

:func:`assess_ct_series` reads the indicators that need a whole series:
every CT volume may hold a reconstructable face, and one whose attributes
name a region of the head or neck in a reviewed list from PS3.16 Annex L
says that it does.

Reading leaves the data set as it was: pydicom converts an element read from
a file on first access, in place, and under strict reading its errors can
quote the value. So each element is read as it was stored, with
``get_item(..., keep_deferred=True)``, checked against its pinned VR, and
decoded apart from the data set; any decoding error is replaced, not
chained. pydicom's own warnings are the entry point's to redact, as
:func:`pymedphys._dicom.anonymise.diagnostics.redacted_pydicom_diagnostics`
does for the legacy tools.
"""

from __future__ import annotations

import dataclasses
import enum
import functools
import pathlib
import re
import tomllib
from collections.abc import Iterator, MutableSequence, Sequence

from pymedphys._imports import pydicom

from .file_layout import ElementPath
from .standard import VRS, load_data_dictionary
from .uids import normalise_uid


class Risk(enum.Enum):
    """What an indicator suggests that the pixel data could disclose."""

    BURNED_IN_TEXT = "burned-in-text"
    RECONSTRUCTABLE_FACE = "reconstructable-face"


class Indicator(enum.Enum):
    """Why an instance's attributes suggest a risk in its pixel data."""

    BURNED_IN_ANNOTATION = "burned-in-annotation"
    RECOGNIZABLE_VISUAL_FEATURES = "recognizable-visual-features"
    SECONDARY_IMAGE = "secondary-image"
    CONVERTED_IMAGE = "converted-image"
    EMBEDDED_OVERLAY = "embedded-overlay"
    PATIENT_SURFACE_CONTOUR = "patient-surface-contour"
    CT_VOLUME = "ct-volume"
    HEAD_OR_NECK = "head-or-neck"
    # An attribute that bears on a risk could not be read.
    UNREADABLE = "unreadable"

    @property
    def risk(self) -> Risk | None:
        """The risk the indicator bears on; ``None`` for unreadable evidence."""
        return _RISKS[self]


_RISKS = {
    Indicator.BURNED_IN_ANNOTATION: Risk.BURNED_IN_TEXT,
    Indicator.RECOGNIZABLE_VISUAL_FEATURES: Risk.RECONSTRUCTABLE_FACE,
    Indicator.SECONDARY_IMAGE: Risk.BURNED_IN_TEXT,
    Indicator.CONVERTED_IMAGE: Risk.BURNED_IN_TEXT,
    Indicator.EMBEDDED_OVERLAY: Risk.BURNED_IN_TEXT,
    Indicator.PATIENT_SURFACE_CONTOUR: Risk.RECONSTRUCTABLE_FACE,
    Indicator.CT_VOLUME: Risk.RECONSTRUCTABLE_FACE,
    Indicator.HEAD_OR_NECK: Risk.RECONSTRUCTABLE_FACE,
    Indicator.UNREADABLE: None,
}


def _checked_risk(indicator: Indicator, risk: Risk | None) -> Risk:
    """Return the risk a finding bears on, checking it against its indicator."""
    expected = indicator.risk
    if risk is None:
        if expected is None:
            raise ValueError("unreadable evidence needs the risk it bears on")
        return expected
    if expected is not None and risk is not expected:
        raise ValueError(f"{indicator.value} bears on {expected.value}")
    return risk


@dataclasses.dataclass(frozen=True)
class Finding:
    """One indicator, and where it is.

    Attributes
    ----------
    indicator : Indicator
    path : ElementPath
        The attribute that shows the indicator: for an embedded overlay, the
        overlay group's first element, and for a patient surface, the ROI's
        Contour Sequence (3006,0040).
    risk : Risk, optional
        The risk the finding bears on. It defaults to the indicator's, and
        must be given for unreadable evidence.

    Raises
    ------
    ValueError
        If ``risk`` is not the indicator's, or is missing for unreadable
        evidence.
    """

    indicator: Indicator
    path: ElementPath
    risk: Risk | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "risk", _checked_risk(self.indicator, self.risk))

    def __str__(self) -> str:
        assert self.risk is not None
        return f"{self.risk.value}: {self.indicator.value} at {self.path}"


@dataclasses.dataclass(frozen=True)
class PixelRiskAssessment:
    """An instance's indicators of risk in its pixel data.

    Attributes
    ----------
    pixel_data : bool
        Whether the top-level data set has Pixel Data (7FE0,0010), Float
        Pixel Data (7FE0,0008), or Double Float Pixel Data (7FE0,0009).
    findings : tuple of Finding
        In the order of the attributes in the data set.
    """

    pixel_data: bool
    findings: tuple[Finding, ...]

    @property
    def risks(self) -> frozenset[Risk]:
        """The risks that any finding bears on."""
        return frozenset(
            finding.risk for finding in self.findings if finding.risk is not None
        )


_BURNED_IN_ANNOTATION = "(0028,0301)"
_RECOGNIZABLE_VISUAL_FEATURES = "(0028,0302)"
_IMAGE_TYPE = "(0008,0008)"
_CONVERSION_TYPE = "(0008,0064)"
_ROI_CONTOUR_SEQUENCE = "(3006,0039)"
_CONTOUR_SEQUENCE = "(3006,0040)"
_RT_ROI_OBSERVATIONS_SEQUENCE = "(3006,0080)"
_REFERENCED_ROI_NUMBER = "(3006,0084)"
_RT_ROI_INTERPRETED_TYPE = "(3006,00A4)"
_SOP_CLASS_UID = "(0008,0016)"
_CODE_VALUE = "(0008,0100)"
_CODING_SCHEME_DESIGNATOR = "(0008,0102)"
_ANATOMIC_REGION_SEQUENCE = "(0008,2218)"
_BODY_PART_EXAMINED = "(0018,0015)"
_NUMBER_OF_FRAMES = "(0028,0008)"

# The VR in the pinned data dictionary of each attribute read, which a test
# checks against it.
READ_VRS = {
    _IMAGE_TYPE: "CS",
    _CONVERSION_TYPE: "CS",
    _BURNED_IN_ANNOTATION: "CS",
    _RECOGNIZABLE_VISUAL_FEATURES: "CS",
    _ROI_CONTOUR_SEQUENCE: "SQ",
    _CONTOUR_SEQUENCE: "SQ",
    _RT_ROI_OBSERVATIONS_SEQUENCE: "SQ",
    _REFERENCED_ROI_NUMBER: "IS",
    _RT_ROI_INTERPRETED_TYPE: "CS",
    _SOP_CLASS_UID: "UI",
    _CODE_VALUE: "SH",
    _CODING_SCHEME_DESIGNATOR: "SH",
    _ANATOMIC_REGION_SEQUENCE: "SQ",
    _BODY_PART_EXAMINED: "CS",
    _NUMBER_OF_FRAMES: "IS",
}

_PIXEL_DATA_TAGS = (0x7FE00008, 0x7FE00009, 0x7FE00010)
_OVERLAY_DATA_ELEMENT = 0x3000
_UNDEFINED_LENGTH = 0xFFFFFFFF
# An IS value: an optional sign and digits (PS3.5 Table 6.2-1).
_INTEGER = re.compile(r"[+-]?[0-9]+")


class _Unreadable(Exception):
    """An element that cannot be read as its pinned VR."""


def _int_tag(tag: str) -> int:
    return int(tag[1:5] + tag[6:10], 16)


def _read(dataset: pydicom.Dataset, tag: str) -> object:
    """Return an element's value as its pinned VR, or ``None`` if it is absent.

    A CS value is a list of its values, an IS value an int or ``None``, and
    an SQ value a list of data sets. The data set is left as it was, and
    :class:`_Unreadable` is raised, without a cause, for a value that cannot
    be read as its pinned VR.
    """
    vr = READ_VRS[tag]
    stored = dataset.get_item(_int_tag(tag), keep_deferred=True)
    if stored is None:
        return None
    if isinstance(stored, pydicom.dataelem.RawDataElement):
        if stored.VR not in (None, "UN", vr):
            raise _Unreadable
        if stored.value is None:
            # Deferred, or a zero-length value that pydicom reads as None.
            if stored.length:
                raise _Unreadable
            return _decoded(vr, b"", stored)
        if stored.length not in (len(stored.value), _UNDEFINED_LENGTH):
            raise _Unreadable
        return _decoded(vr, stored.value, stored)
    if stored.VR != vr:
        raise _Unreadable
    return _converted(vr, stored.value)


def _decoded(vr: str, value: bytes, stored) -> object:
    """Decode a stored value; CS, IS, and UI are ASCII (PS3.5 Section 6.2).

    SH is decoded as ASCII too, which every code value of the coding
    schemes compared is; a value with other bytes is unreadable.
    """
    if vr == "SQ":
        # A UN value is in Implicit VR Little Endian (PS3.5 Section 6.2.2).
        if stored.VR in (None, "UN"):
            stored = stored._replace(is_implicit_VR=True, is_little_endian=True)
        try:
            items = pydicom.values.convert_value("SQ", stored._replace(VR="SQ"))
        # pydicom raises many types for a malformed sequence, and its
        # message can quote what it read.
        except Exception:  # pylint: disable = broad-exception-caught
            raise _Unreadable from None
        if not all(_whole(item) for item in items):
            raise _Unreadable
        return list(items)
    try:
        text = value.decode("ascii")
    except UnicodeDecodeError:
        raise _Unreadable from None
    values = [part.strip(" \x00") for part in text.split("\\")] if text else []
    if vr == "CS":
        # CS is upper case, but a lower-case value must not hide an indicator.
        return [value.upper() for value in values]
    if vr in ("SH", "UI"):
        return values
    if not values:
        return None
    if len(values) > 1 or not _INTEGER.fullmatch(values[0]):
        raise _Unreadable
    try:
        return int(values[0])
    except ValueError:
        # Too many digits to convert (Python's integer string conversion limit).
        raise _Unreadable from None


def _whole(item: pydicom.Dataset) -> bool:
    """Return whether each element of an item read from bytes has all its value.

    pydicom reads past the end of a malformed sequence and keeps what it
    finds, so an element it reads there has an unknown VR or less value than
    its length. This is no check of the source's structure, which the engine
    establishes before it assesses an instance, but it stops such an element
    from passing as the item's content.
    """
    for tag in item.keys():
        stored = item.get_item(tag, keep_deferred=True)
        if not isinstance(stored, pydicom.dataelem.RawDataElement):
            continue
        if stored.VR is not None and stored.VR not in VRS:
            return False
        if stored.length != _UNDEFINED_LENGTH and stored.length != len(
            stored.value or b""
        ):
            return False
    return True


def _converted(vr: str, value: object) -> object:
    """Return a value that pydicom has already converted, as :func:`_read` does."""
    if vr == "SQ":
        if not isinstance(value, pydicom.Sequence):
            raise _Unreadable
        return list(value)
    if vr == "IS":
        if value is None or value == "":
            return None
        if isinstance(value, int):
            return int(value)
        raise _Unreadable
    if value is None or value == "":
        return []
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, MutableSequence) or not all(
        isinstance(each, str) for each in values
    ):
        raise _Unreadable
    stripped = [each.strip(" \x00") for each in values]
    return [each.upper() for each in stripped] if vr == "CS" else stripped


def assess_pixel_risk(dataset: pydicom.Dataset) -> PixelRiskAssessment:
    """Read an instance's indicators of risk in its pixel data.

    Parameters
    ----------
    dataset : pydicom.Dataset
        The instance as read, which is left as it was.

    Returns
    -------
    PixelRiskAssessment

    Examples
    --------
    >>> from pymedphys._imports import pydicom
    >>> dataset = pydicom.Dataset()
    >>> dataset.BurnedInAnnotation = "YES"
    >>> [str(finding) for finding in assess_pixel_risk(dataset).findings]
    ['burned-in-text: burned-in-annotation at (0028,0301)']
    """
    findings = [*_image_findings(dataset), *_overlay_findings(dataset)]
    findings.extend(_surface_findings(dataset))
    return PixelRiskAssessment(
        pixel_data=any(tag in dataset for tag in _PIXEL_DATA_TAGS),
        findings=tuple(sorted(findings, key=_order)),
    )


def _order(finding: Finding) -> list[tuple[int, int]]:
    """Order a finding by its whole path, so that one in a sequence sorts with it."""
    return [(_int_tag(tag), item) for tag, item in finding.path.items] + [
        (_int_tag(finding.path.tag), -1)
    ]


_IMAGE_ATTRIBUTES = (
    (_IMAGE_TYPE, Indicator.SECONDARY_IMAGE),
    (_CONVERSION_TYPE, Indicator.CONVERTED_IMAGE),
    (_BURNED_IN_ANNOTATION, Indicator.BURNED_IN_ANNOTATION),
    (_RECOGNIZABLE_VISUAL_FEATURES, Indicator.RECOGNIZABLE_VISUAL_FEATURES),
)


def _image_findings(dataset: pydicom.Dataset) -> Iterator[Finding]:
    for tag, indicator in _IMAGE_ATTRIBUTES:
        path = ElementPath((), tag)
        try:
            values = _read(dataset, tag)
        except _Unreadable:
            yield Finding(Indicator.UNREADABLE, path, indicator.risk)
            continue
        if values is None:
            continue
        assert isinstance(values, list)
        if (
            tag == _CONVERSION_TYPE
            or (tag == _IMAGE_TYPE and values[1:2] == ["SECONDARY"])
            or (tag not in (_IMAGE_TYPE, _CONVERSION_TYPE) and values == ["YES"])
        ):
            yield Finding(indicator, path)


def _overlay_findings(dataset: pydicom.Dataset) -> Iterator[Finding]:
    """Find the overlay groups that have no Overlay Data (60xx,3000)."""
    groups: dict[int, int] = {}
    for tag in dataset.keys():
        if 0x6000 <= tag.group <= 0x601E and tag.group % 2 == 0 and tag.element:
            groups.setdefault(tag.group, tag.element)
    for group, first in groups.items():
        if (group << 16 | _OVERLAY_DATA_ELEMENT) not in dataset:
            path = ElementPath((), f"({group:04X},{first:04X})")
            yield Finding(Indicator.EMBEDDED_OVERLAY, path)


def _surface_findings(dataset: pydicom.Dataset) -> Iterator[Finding]:
    """Find the contours of the ROIs that RT ROI Observations call EXTERNAL."""
    risk = Risk.RECONSTRUCTABLE_FACE
    external: set[int] = set()
    try:
        observations = _read(dataset, _RT_ROI_OBSERVATIONS_SEQUENCE) or []
    except _Unreadable:
        yield Finding(
            Indicator.UNREADABLE, ElementPath((), _RT_ROI_OBSERVATIONS_SEQUENCE), risk
        )
        observations = []
    assert isinstance(observations, list)
    for index, item in enumerate(observations):
        within = ((_RT_ROI_OBSERVATIONS_SEQUENCE, index),)
        try:
            kind = _read(item, _RT_ROI_INTERPRETED_TYPE)
            number = _read(item, _REFERENCED_ROI_NUMBER)
        except _Unreadable:
            # Which element failed is found again to say where it is.
            yield Finding(Indicator.UNREADABLE, _failing(item, within), risk)
            continue
        if kind == ["EXTERNAL"] and isinstance(number, int):
            external.add(number)
    try:
        contours = _read(dataset, _ROI_CONTOUR_SEQUENCE) or []
    except _Unreadable:
        yield Finding(
            Indicator.UNREADABLE, ElementPath((), _ROI_CONTOUR_SEQUENCE), risk
        )
        return
    assert isinstance(contours, list)
    for index, item in enumerate(contours):
        within = ((_ROI_CONTOUR_SEQUENCE, index),)
        try:
            number = _read(item, _REFERENCED_ROI_NUMBER)
            has_contours = (
                bool(_read(item, _CONTOUR_SEQUENCE)) if number in external else False
            )
        except _Unreadable:
            yield Finding(Indicator.UNREADABLE, _failing(item, within), risk)
            continue
        if has_contours:
            yield Finding(
                Indicator.PATIENT_SURFACE_CONTOUR,
                ElementPath(within, _CONTOUR_SEQUENCE),
            )


def _failing(item: pydicom.Dataset, within) -> ElementPath:
    """Return the path of the first element of ``item`` that cannot be read."""
    for tag in (_RT_ROI_INTERPRETED_TYPE, _REFERENCED_ROI_NUMBER, _CONTOUR_SEQUENCE):
        try:
            _read(item, tag)
        except _Unreadable:
            return ElementPath(within, tag)
    raise AssertionError("no element of the item is unreadable")  # pragma: no cover


HEAD_AND_NECK_REGIONS_PATH = (
    pathlib.Path(__file__).resolve().parent / "head_and_neck_regions.toml"
)
_REGIONS_SCHEMA = "pymedphys-deid-head-and-neck-regions/1"
_REGION_FIELDS = {"meaning", "sct"}
# CT Image Storage, and CT Image Storage - For Processing, each instance of
# which is one frame.
_SINGLE_FRAME_CT_SOP_CLASSES = frozenset(
    {"1.2.840.10008.5.1.4.1.1.2", "1.2.840.10008.5.1.4.1.1.2.3"}
)
# Enhanced CT Image Storage and Legacy Converted Enhanced CT Image Storage,
# and their For Processing classes, whose instances hold Number of Frames.
_MULTI_FRAME_CT_SOP_CLASSES = frozenset(
    {
        "1.2.840.10008.5.1.4.1.1.2.1",
        "1.2.840.10008.5.1.4.1.1.2.4",
        "1.2.840.10008.5.1.4.1.1.2.2",
        "1.2.840.10008.5.1.4.1.1.2.5",
    }
)
_TERM = re.compile(r"[A-Z0-9_ ]{1,16}")


@dataclasses.dataclass(frozen=True)
class HeadAndNeckRegions:
    """The reviewed anatomic regions that lie in or contain the head or neck.

    Attributes
    ----------
    edition : str
        The edition of PS3.16 whose Annex L the list was reviewed against.
    body_parts : frozenset of str
        Their Body Part Examined (0018,0015) terms.
    codes : frozenset of (str, str)
        Their codes, as (Coding Scheme Designator, Code Value): each region's
        SNOMED CT code under ``SCT``, and its SNOMED RT identifier, where it
        has one, under ``SRT`` and under ``SNM3``, since the identifiers
        carry forward the SNOMED 3 codes that older instances give.
    """

    edition: str
    body_parts: frozenset[str]
    codes: frozenset[tuple[str, str]]


@functools.lru_cache(maxsize=None)
def _load_regions(path: pathlib.Path) -> HeadAndNeckRegions:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        raise ValueError(f"{path.name} cannot be read") from None
    edition = data.get("edition")
    if (
        data.get("schema") != _REGIONS_SCHEMA
        or not isinstance(edition, str)
        or data.get("acknowledgement") != f"DICOM PS3.16 {edition}, © NEMA"
        or set(data) != {"schema", "edition", "acknowledgement", "region"}
        or not isinstance(data["region"], list)
    ):
        raise ValueError(f"{path.name} is not a list of head and neck regions")
    if edition != load_data_dictionary().edition:
        raise ValueError(f"{path.name} is not of the pinned edition")
    body_parts: set[str] = set()
    codes: set[tuple[str, str]] = set()
    for region in data["region"]:
        if (
            not isinstance(region, dict)
            or not _REGION_FIELDS
            <= set(region)
            <= _REGION_FIELDS | {"srt", "body_part"}
            or not all(isinstance(value, str) and value for value in region.values())
            or not region["sct"].isdigit()
            or not _TERM.fullmatch(region.get("body_part", "X"))
        ):
            raise ValueError(f"{path.name} has a malformed region")
        codes.add(("SCT", region["sct"]))
        if "srt" in region:
            codes.update({("SRT", region["srt"]), ("SNM3", region["srt"])})
        if "body_part" in region:
            body_parts.add(region["body_part"])
    return HeadAndNeckRegions(edition, frozenset(body_parts), frozenset(codes))


def load_head_and_neck_regions(
    path: pathlib.Path | None = None,
) -> HeadAndNeckRegions:
    """Load the reviewed regions of PS3.16 Annex L that lie in the head or neck.

    Each file is read once and cached, keyed by its resolved path.

    Parameters
    ----------
    path : pathlib.Path, optional
        The regions file. Defaults to the one shipped with PyMedPhys.

    Raises
    ------
    ValueError
        If the file cannot be read; has another schema, an edition other
        than the pinned data dictionary's, an acknowledgement other than that
        of its edition, or other fields; or
        has a region without exactly a meaning, a numeric SNOMED CT code, an
        optional SNOMED RT identifier, and an optional Body Part Examined
        term of at most 16 upper-case letters, digits, underscores, and
        spaces.
    """
    return _load_regions((path or HEAD_AND_NECK_REGIONS_PATH).resolve())


@dataclasses.dataclass(frozen=True)
class SeriesFinding:
    """One indicator of a series, and the instances that show it.

    Attributes
    ----------
    indicator : Indicator
    instances : tuple of int
        The positions, counting from 0, of the instances that show it, in
        the order given.
    path : ElementPath, optional
        The attribute that shows it; ``None`` for a CT volume, which no one
        attribute shows.
    risk : Risk, optional
        As for :class:`Finding`.
    """

    indicator: Indicator
    instances: tuple[int, ...]
    path: ElementPath | None = None
    risk: Risk | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "risk", _checked_risk(self.indicator, self.risk))


def assess_ct_series(instances: Sequence[pydicom.Dataset]) -> tuple[SeriesFinding, ...]:
    """Read a series' indicators of a reconstructable face.

    Without inspecting pixel data, the engine cannot tell whether a series
    covers the face, so every CT volume is reported: a series whose CT
    images, of any CT Image Storage SOP Class, hold at least two frames that
    are not localizers, whose Image Type (0008,0008) has a third value of
    LOCALIZER (PS3.3 Sections C.8.2.1.1.1 and C.8.16.1.3). A single-frame CT
    image is one frame; an Enhanced or Legacy Converted Enhanced CT image
    holds its Number of Frames (0028,0008), one if it is absent, and is a
    volume by itself if that cannot be read. An instance whose SOP Class
    UID (0008,0016) cannot be read counts as a frame. A volume whose Body
    Part Examined (0018,0015) or Anatomic Region Sequence (0008,2218) names
    a region in :func:`load_head_and_neck_regions` is also reported as
    showing the head or neck. How finely a series samples the face changes
    how readily it can be recognised (MIDI report Section 1.18.3.2), but no
    spacing makes it safe, so spacing decides nothing here.

    Parameters
    ----------
    instances : sequence of pydicom.Dataset
        The instances of one series, as read, which are left as they were.

    Returns
    -------
    tuple of SeriesFinding
        The CT volume first, then the head or neck by attribute, then
        unreadable evidence by instance, which is reported whether or not
        the series is a CT volume.
    """
    regions = load_head_and_neck_regions()
    volume: list[int] = []
    frames = 0
    head: dict[ElementPath, list[int]] = {}
    unreadable: list[SeriesFinding] = []
    for index, dataset in enumerate(instances):
        try:
            multi_frame = _multi_frame_ct(dataset)
        except _Unreadable:
            unreadable.append(_unreadable_in(index, ElementPath((), _SOP_CLASS_UID)))
            multi_frame = False
        else:
            if multi_frame is None:
                continue
        try:
            image_type = _read(dataset, _IMAGE_TYPE) or []
        except _Unreadable:
            image_type = []  # the instance assessment reports it
        assert isinstance(image_type, list)
        if image_type[2:3] == ["LOCALIZER"]:
            continue
        frames += _frames(dataset, index, unreadable) if multi_frame else 1
        volume.append(index)
        for path in _head_or_neck(dataset, regions, index, unreadable):
            head.setdefault(path, []).append(index)
    if frames < 2:
        return tuple(unreadable)
    return (
        SeriesFinding(Indicator.CT_VOLUME, tuple(volume)),
        *(
            SeriesFinding(Indicator.HEAD_OR_NECK, tuple(where), path)
            for path, where in sorted(head.items(), key=lambda item: str(item[0]))
        ),
        *unreadable,
    )


def _unreadable_in(index: int, path: ElementPath) -> SeriesFinding:
    return SeriesFinding(
        Indicator.UNREADABLE, (index,), path, Risk.RECONSTRUCTABLE_FACE
    )


def _multi_frame_ct(dataset: pydicom.Dataset) -> bool | None:
    """Return whether a CT image is multi-frame, or ``None`` for another class."""
    uids = _read(dataset, _SOP_CLASS_UID) or []
    assert isinstance(uids, list)
    if len(uids) > 1:
        raise _Unreadable
    uid = normalise_uid(uids[0]) if uids else None
    if uid in _SINGLE_FRAME_CT_SOP_CLASSES:
        return False
    if uid in _MULTI_FRAME_CT_SOP_CLASSES:
        return True
    return None


def _frames(dataset: pydicom.Dataset, index: int, unreadable: list) -> int:
    """Return how many frames a multi-frame CT image holds, for a volume."""
    try:
        frames = _read(dataset, _NUMBER_OF_FRAMES)
        if frames is None:
            return 1
        assert isinstance(frames, int)
        if frames < 1:
            raise _Unreadable
    except _Unreadable:
        unreadable.append(_unreadable_in(index, ElementPath((), _NUMBER_OF_FRAMES)))
        return 2
    return frames


def _head_or_neck(
    dataset: pydicom.Dataset,
    regions: HeadAndNeckRegions,
    index: int,
    unreadable: list[SeriesFinding],
) -> Iterator[ElementPath]:
    """Yield the paths at which an instance names the head or neck."""
    path = ElementPath((), _BODY_PART_EXAMINED)
    try:
        body_parts = _read(dataset, _BODY_PART_EXAMINED) or []
    except _Unreadable:
        unreadable.append(_unreadable_in(index, path))
        body_parts = []
    assert isinstance(body_parts, list)
    if regions.body_parts.intersection(body_parts):
        yield path
    try:
        items = _read(dataset, _ANATOMIC_REGION_SEQUENCE) or []
    except _Unreadable:
        unreadable.append(
            _unreadable_in(index, ElementPath((), _ANATOMIC_REGION_SEQUENCE))
        )
        return
    assert isinstance(items, list)
    for number, item in enumerate(items):
        within = ((_ANATOMIC_REGION_SEQUENCE, number),)
        # Code Value is Type 1C, absent where Long Code Value or URN Code
        # Value holds a code too long for it, which no code of the list is
        # (PS3.3 Section 8.8).
        values = []
        for tag in (_CODING_SCHEME_DESIGNATOR, _CODE_VALUE):
            try:
                value = _read(item, tag) or []
                assert isinstance(value, list)
                if len(value) > 1:
                    raise _Unreadable
            except _Unreadable:
                unreadable.append(_unreadable_in(index, ElementPath(within, tag)))
                break
            values.append(value)
        else:
            scheme, code = values
            # SH is case sensitive, but a lower-case code must not hide the
            # head or neck.
            if (
                scheme
                and code
                and (scheme[0].upper(), code[0].upper()) in regions.codes
            ):
                yield ElementPath(within, _CODE_VALUE)
