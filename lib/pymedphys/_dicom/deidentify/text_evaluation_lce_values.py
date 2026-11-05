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

"""The elements and values of classic images as
:mod:`~.text_evaluation_lce` reads and copies them (D-056)."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

# Private attributes are keyed by their group, their block's creator, and
# their element within the block, since PS3.3 lets each image use any block.
_Key = int | tuple[int, str, int]

# Laterality as Anatomic Region Modifier Sequence (0008,2220) codes it
# (PS3.16 CID 244), and as Frame Laterality (0020,9072) records it.
_MODIFIER_LATERALITY = {
    "7771000": "L",
    "24028007": "R",
    "51440002": "B",
    "66459002": "U",
}
_LATERALITIES = frozenset({"R", "L", "U", "B"})


# Elements --------------------------------------------------------------


def _elements(dataset: pydicom.Dataset) -> dict[_Key, pydicom.DataElement]:
    """A data set's top-level elements, private ones by their creator."""
    found: dict[_Key, pydicom.DataElement] = {}
    for element in dataset:
        tag = element.tag
        if tag.group == 0x0002 or tag.element == 0x0000:
            continue
        if not tag.is_private:
            found[int(tag)] = element
            continue
        if tag.is_private_creator or tag.element < 0x1000:
            continue
        creator_tag = pydicom.tag.Tag(tag.group, tag.element >> 8)
        creator = dataset.get(creator_tag)
        if creator is None or not isinstance(creator.value, str):
            continue
        found[(tag.group, creator.value.strip(), tag.element & 0xFF)] = element
    return found


def _place(
    item: pydicom.Dataset,
    key: _Key,
    element: pydicom.DataElement,
    creators: dict[tuple[int, str], int],
) -> None:
    copied = copy_element(element)
    if isinstance(key, int):
        item.add(copied)
        return
    group, creator, offset = key
    block = creators.get((group, creator))
    if block is None:
        block = 0x10 + sum(1 for each in creators if each[0] == group)
        creators[(group, creator)] = block
        item.add_new(pydicom.tag.Tag(group, block), "LO", creator)
    item.add(
        pydicom.DataElement(
            pydicom.tag.Tag(group, (block << 8) | offset),
            copied.VR,
            copied.value,
        )
    )


def copy_element(element: pydicom.DataElement) -> pydicom.DataElement:
    """A deep copy of an element, its value converted as pydicom reads it."""
    if element.VR == "SQ":
        return pydicom.DataElement(
            element.tag,
            "SQ",
            [_copied_item(item) for item in element.value],
        )
    return pydicom.DataElement(element.tag, element.VR, _value_copy(element.value))


def _value_copy(value: object) -> object:
    if isinstance(value, pydicom.multival.MultiValue):
        return list(value)
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    return value


def _copied_item(dataset: pydicom.Dataset) -> pydicom.Dataset:
    copied = pydicom.Dataset()
    for element in dataset:
        copied.add(copy_element(element))
    return copied


def _canonical(  # pylint: disable = too-many-return-statements
    value: object,
) -> object:
    """A value that two elements share if PS3.3 counts them the same: an
    absent element as an empty one, a sequence by its items' contents."""
    if isinstance(value, pydicom.DataElement):
        if value.VR == "SQ":
            return tuple(_canonical(item) for item in value.value)
        return _canonical(value.value)
    if isinstance(value, pydicom.Dataset):
        return tuple((int(element.tag), _canonical(element)) for element in value)
    if isinstance(value, pydicom.Sequence):
        return tuple(_canonical(item) for item in value)
    if value is None or value == "" or value == b"":
        return None
    if isinstance(value, (list, tuple, pydicom.multival.MultiValue)):
        if len(value) == 0:
            return None
        return tuple(_canonical(each) for each in value)
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, float):
        return value
    return str(value)


# Values ------------------------------------------------------------------


def _tag(keyword: str) -> int:
    tag = pydicom.datadict.tag_for_keyword(keyword)
    if tag is None:
        raise KeyError(keyword)
    return int(tag)


def _tag_number(text: str) -> int:
    return int(text[1:5] + text[6:10], 16)


def _items_of(group: pydicom.Dataset, keyword: str) -> list[pydicom.Dataset]:
    """The items of a sequence in a functional group, or in the items of its
    Derivation Image Sequence."""
    items = list(group.get(keyword, []))
    for derivation in group.get("DerivationImageSequence", []):
        items.extend(derivation.get(keyword, []))
    return items


def _study_item(study: str, series: Mapping[str, Mapping[str, str]]) -> pydicom.Dataset:
    """An item of the Hierarchical SOP Instance Reference Macro."""
    item = pydicom.Dataset()
    item.StudyInstanceUID = study
    item.ReferencedSeriesSequence = []
    for uid in sorted(series):
        series_item = pydicom.Dataset()
        series_item.SeriesInstanceUID = uid
        series_item.ReferencedSOPSequence = []
        for instance in sorted(series[uid]):
            reference = pydicom.Dataset()
            reference.ReferencedSOPClassUID = series[uid][instance]
            reference.ReferencedSOPInstanceUID = instance
            series_item.ReferencedSOPSequence.append(reference)
        item.ReferencedSeriesSequence.append(series_item)
    return item


def _tag_text(tag: int) -> str:
    return f"({tag >> 16:04X},{tag & 0xFFFF:04X})"


def _key_order(key: _Key) -> tuple:
    if isinstance(key, int):
        return (key, "", 0)
    group, creator, offset = key
    return ((group << 16) | 0x1000 | offset, creator, offset)


def _has(dataset: pydicom.Dataset, keyword: str) -> bool:
    return keyword in dataset and not dataset[keyword].is_empty


def _values(dataset: pydicom.Dataset, keyword: str) -> list:
    if keyword not in dataset:
        return []
    value = dataset[keyword].value
    if value is None:
        return []
    if isinstance(value, (list, tuple, pydicom.multival.MultiValue)):
        return list(value)
    return [value]


def _string(dataset: pydicom.Dataset, keyword: str) -> str:
    values = _values(dataset, keyword)
    return str(values[0]).strip() if len(values) == 1 else ""


def _number(
    dataset: pydicom.Dataset, keyword: str, index: int | None = None
) -> float | None:
    values = _values(dataset, keyword)
    try:
        if index is None:
            if len(values) != 1:
                return None
            number = float(values[0])
        else:
            number = float(values[index])
    except (IndexError, TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _datetime(dataset: pydicom.Dataset, prefix: str) -> str | None:
    """``prefix`` Date and Time as a DT value, comparable as text."""
    date, time = _string(dataset, f"{prefix}Date"), _string(dataset, f"{prefix}Time")
    if len(date) != 8 or not date.isdigit():
        return None
    return date + _time(time)


def _time(value: str) -> str:
    """A TM value padded to HHMMSS.FFFFFF, so that times compare as text."""
    whole, _, fraction = value.partition(".")
    if not whole.isdigit() or len(whole) not in (2, 4, 6):
        return ""
    return (whole + "0000")[:6] + "." + (fraction + "000000")[:6]


def _acquisition_datetime(dataset: pydicom.Dataset) -> str | None:
    given = _string(dataset, "AcquisitionDateTime")
    if len(given) >= 8 and given[:8].isdigit():
        return given
    dated = _datetime(dataset, "Acquisition")
    return dated if dated and len(dated) > 8 else None


def _laterality(dataset: pydicom.Dataset, item: pydicom.Dataset) -> str:
    """Frame Laterality: from the anatomic region's modifier, else the
    image's Frame, Image, or series Laterality, else U, since classic
    images record Laterality only for paired body parts."""
    for region in item.get("AnatomicRegionSequence", []):
        for modifier in region.get("AnatomicRegionModifierSequence", []):
            found = _MODIFIER_LATERALITY.get(_string(modifier, "CodeValue"))
            if found:
                return found
    for keyword in ("FrameLaterality", "ImageLaterality", "Laterality"):
        value = _string(dataset, keyword)
        if value in _LATERALITIES:
            return value
    return "U"


def _geometry(  # pylint: disable = too-many-return-statements
    datasets: Sequence[pydicom.Dataset],
) -> str:
    """Image Type Value 3 for frames whose images give none (PS3.3 Table
    C.8-129): VOLUME for parallel frames regularly spaced, PARALLEL for
    parallel frames otherwise, and NON_PARALLEL else."""
    orientations = [
        np.array([float(each) for each in _values(dataset, "ImageOrientationPatient")])
        for dataset in datasets
    ]
    if any(each.shape != (6,) for each in orientations):
        return "NON_PARALLEL"
    normals = [np.cross(each[:3], each[3:]) for each in orientations]
    if any(np.linalg.norm(each) == 0 for each in normals):
        return "NON_PARALLEL"
    normal = normals[0] / np.linalg.norm(normals[0])
    if any(
        abs(abs(np.dot(normal, each / np.linalg.norm(each))) - 1) > 1e-4
        for each in normals
    ):
        return "NON_PARALLEL"
    positions = [
        [float(each) for each in _values(dataset, "ImagePositionPatient")]
        for dataset in datasets
    ]
    if any(len(each) != 3 for each in positions):
        return "PARALLEL"
    distances = np.sort([float(np.dot(normal, each)) for each in positions])
    steps = np.diff(distances)
    if len(steps) == 0:
        return "VOLUME"
    if steps.min() <= 1e-3 or steps.max() - steps.min() > 1e-2 * max(steps.max(), 1e-3):
        return "PARALLEL"
    return "VOLUME"
