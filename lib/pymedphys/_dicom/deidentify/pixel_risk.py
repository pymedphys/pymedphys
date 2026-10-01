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

An attribute that cannot be read as its VR in the pinned data dictionary is
itself reported, as unreadable evidence of the risk that it bears on, since
reading it could otherwise hide an indicator. Findings name attribute paths,
never values.

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
from collections.abc import Iterator, MutableSequence

from pymedphys._imports import pydicom

from .file_layout import ElementPath
from .standard import VRS


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
    Indicator.UNREADABLE: None,
}


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
        expected = self.indicator.risk
        if self.risk is None:
            if expected is None:
                raise ValueError("unreadable evidence needs the risk it bears on")
            object.__setattr__(self, "risk", expected)
        elif expected is not None and self.risk is not expected:
            raise ValueError(f"{self.indicator.value} bears on {expected.value}")

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
}

_PIXEL_DATA_TAGS = (0x7FE00008, 0x7FE00009, 0x7FE00010)
_OVERLAY_DATA_ELEMENT = 0x3000
_UNDEFINED_LENGTH = 0xFFFFFFFF


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
    """Decode a stored value; CS and IS are ASCII (PS3.5 Section 6.2)."""
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
        return values
    if len(values) > 1 or (values and not values[0].lstrip("+-").isdigit()):
        raise _Unreadable
    return int(values[0]) if values and values[0] else None


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
    if isinstance(value, str):
        return [value.strip(" ")]
    if not isinstance(value, MutableSequence) or not all(
        isinstance(each, str) for each in value
    ):
        raise _Unreadable
    return [each.strip(" ") for each in value]


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


def _order(finding: Finding) -> tuple:
    return (
        [(_int_tag(tag), item) for tag, item in finding.path.items],
        _int_tag(finding.path.tag),
    )


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
