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

"""The phases of a series whose slices repeat a position.

A series can hold more than one slice at a position along its slices'
normal: the time points of a respiratory-correlated (4D) CT or of a
perfusion scan, the phases of a contrast study, or two acquisitions that
overlap where they meet. A face block is found, and a volume is previewed,
only from slices at distinct positions, since two slices at one position
are two images of one place, and a volume of both would show neither as
it is. :func:`split` parts such slices into phases, each at distinct
positions, by what each slice's data set names of its time point or
acquisition, and never by its order, so that no phase mixes two time
points at one position, and each slice is in exactly one phase:

- where no two slices lie within :data:`COINCIDENT` millimetres of each
  other along the normal, the slices are one phase, whatever they name, as
  a series without repeated positions always was;
- otherwise each slice's phase is the first of these that every slice of
  its kind names (:func:`named_by_instance`, :func:`named_by_frame`): for a
  single-frame instance, its Temporal Position Identifier (0020,0100), or
  else its Acquisition Number (0020,0012); for a frame of a multi-frame
  instance, the Stack ID (0020,9056) and Temporal Position Index
  (0020,9128) of its Frame Content functional group, as the QC pack groups
  a multi-frame instance's frames into volumes, or else that group's Frame
  Acquisition Number (0020,9156); a single-frame instance and a frame are
  never in one phase; and
- no phases are given, and the caller treats the slices as it would any
  others that do not form one stack, where a kind of slice has none of
  these that every slice of the kind names, or where two slices of one
  phase still lie at one position.

Each value is compared as an integer where it reads as one, and otherwise
as its text without surrounding spaces, so that ``"1"`` and ``"01"`` name
one time point. The phases are in the order of their first slices.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence

from pymedphys._imports import pydicom

from .diagnostics import redacted_diagnostics

# Millimetres along the slices' normal within which two slices lie at one
# position: far below any slice spacing, and far above the rounding of a
# position written as decimal text.
COINCIDENT = 1e-3

INSTANCE = "instance"
FRAME = "frame"


@dataclasses.dataclass(frozen=True)
class Named:
    """What one slice names of its phase.

    Attributes
    ----------
    kind : str
        :data:`INSTANCE` for a single-frame instance, :data:`FRAME` for a
        frame of a multi-frame instance.
    values : tuple of str
        Each attribute that may name its phase, in order of preference, as
        normalised text, or empty where it names none.
    """

    kind: str
    values: tuple[str, ...]


def named_by_instance(dataset: pydicom.Dataset) -> Named:
    """What a single-frame instance names of its phase: its Temporal
    Position Identifier, then its Acquisition Number."""
    return Named(
        INSTANCE,
        (
            _value(dataset, "TemporalPositionIdentifier"),
            _value(dataset, "AcquisitionNumber"),
        ),
    )


def named_by_frame(content: pydicom.Dataset | None) -> Named:
    """What a frame names of its phase, from its Frame Content functional
    group's item, or None where it has none: its Stack ID and Temporal
    Position Index together, where it names either, then its Frame
    Acquisition Number."""
    if content is None:
        return Named(FRAME, ("", ""))
    stack = _value(content, "StackID")
    time = _value(content, "TemporalPositionIndex")
    return Named(
        FRAME,
        (
            f"{stack}\\{time}" if stack or time else "",
            _value(content, "FrameAcquisitionNumber"),
        ),
    )


def repeated(heights: Sequence[float]) -> bool:
    """Whether two of the heights, along the slices' normal in
    millimetres, lie within :data:`COINCIDENT` of each other."""
    ordered = sorted(float(height) for height in heights)
    return any(
        later - earlier <= COINCIDENT for earlier, later in zip(ordered, ordered[1:])
    )


def split(heights: Sequence[float], named: Sequence[Named]) -> list[list[int]] | None:
    """Split slices into phases, as the module describes.

    Parameters
    ----------
    heights : sequence of float
        Each slice's position along the slices' normal, in millimetres.
    named : sequence of Named
        What each slice names of its phase, in the order of ``heights``.

    Returns
    -------
    list of list of int or None
        The indices of each phase's slices, ascending, the phases in the
        order of their first slices; or None where the slices cannot be
        split.

    Raises
    ------
    ValueError
        If ``heights`` and ``named`` differ in length.
    """
    if len(heights) != len(named):
        raise ValueError("one name for each slice")
    if not repeated(heights):
        return [list(range(len(heights)))]
    chosen: dict[str, int] = {}
    for kind in {each.kind for each in named}:
        given = [each.values for each in named if each.kind == kind]
        choice = next(
            (
                index
                for index in range(len(given[0]))
                if all(len(values) > index and values[index] for values in given)
            ),
            None,
        )
        if choice is None:
            return None
        chosen[kind] = choice
    groups: dict[tuple[str, str], list[int]] = {}
    for index, each in enumerate(named):
        key = (each.kind, each.values[chosen[each.kind]])
        groups.setdefault(key, []).append(index)
    found = sorted(groups.values(), key=lambda members: members[0])
    if any(repeated([heights[index] for index in members]) for members in found):
        return None
    return found


def _value(dataset: pydicom.Dataset, keyword: str) -> str:
    """An attribute's one value as normalised text, or empty where it is
    absent, empty, of more than one value, or cannot be read."""
    try:
        with redacted_diagnostics():
            if keyword not in dataset:
                return ""
            value = dataset[keyword].value
    # pydicom raises many types for a value it cannot read, and a message
    # can quote it.
    except Exception:  # pylint: disable = broad-exception-caught
        return ""
    if isinstance(value, (list, tuple, pydicom.multival.MultiValue)):
        return ""
    text = str(value).strip() if value is not None else ""
    if not text:
        return ""
    try:
        return str(int(text))
    except ValueError:
        return text
