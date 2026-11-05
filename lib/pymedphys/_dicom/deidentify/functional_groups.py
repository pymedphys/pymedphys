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

"""The functional groups that describe one frame of a multi-frame instance.

An Enhanced CT, Legacy Converted Enhanced CT, Enhanced PET, Legacy Converted
Enhanced PET, or Segmentation instance describes its frames in the
Multi-frame Functional Groups Module (PS3.3 C.7.6.16): each functional
group, such as Plane Position (Patient), is either in the frame's item of
the Per-frame Functional Groups Sequence or in the Shared Functional Groups
Sequence, which applies to every frame. :func:`frame_group` gives a frame's
one item of a group's sequence, as the defacing modules read the groups
that place a frame and rescale its stored values, and
:func:`frame_group_items` the items of a group whose sequence may hold
more than one, such as Real World Value Mapping.

A group in both sequences is refused rather than one taken over the other,
since PS3.3 C.7.6.16.1.1 lets a group be in only one of them and gives
neither precedence; so is a group in neither, a sequence of other than one
item (of no item, for :func:`frame_group_items`), and a Per-frame
Functional Groups Sequence of other than one item for each frame, as is an
instance without it, but for a Segmentation explicitly read from shared
groups alone where PS3.3 A.51.5 permits its omission. A sequence that pydicom
cannot parse is refused too. Whatever is refused raises :class:`ValueError`,
without any value, so that a caller can leave the instance as it is.
"""

from __future__ import annotations

from pymedphys._imports import pydicom

from .diagnostics import redacted_diagnostics


def frame_group(
    dataset: pydicom.Dataset,
    frames: int,
    frame: int,
    keyword: str,
    *,
    shared_alone: bool = False,
) -> pydicom.Dataset:
    """Return the one item of a functional group's sequence for a frame.

    Parameters
    ----------
    dataset : pydicom.Dataset
        The multi-frame instance's data set.
    frames : int
        Its Number of Frames.
    frame : int
        The frame, from 0.
    keyword : str
        The functional group's sequence, such as
        ``"PlanePositionSequence"``.
    shared_alone : bool
        Whether an instance without the Per-frame Functional Groups Sequence
        is read from the Shared Functional Groups Sequence alone, as PS3.3
        A.51.5 lets a Segmentation omit it; one with the sequence, even of
        no items, still needs an item for each frame.

    Raises
    ------
    ValueError
        Where the Per-frame Functional Groups Sequence does not have one item
        for each of the ``frames`` frames, the Shared Functional Groups
        Sequence has more than one, or the group is not in exactly one of
        them, in one item, or a sequence cannot be read; without any
        value.
    """
    items = frame_group_items(
        dataset, frames, frame, keyword, shared_alone=shared_alone
    )
    if len(items) != 1:
        raise ValueError("not one item")
    return items[0]


def frame_group_items(
    dataset: pydicom.Dataset,
    frames: int,
    frame: int,
    keyword: str,
    *,
    shared_alone: bool = False,
) -> tuple[pydicom.Dataset, ...]:
    """Return the items of a functional group's sequence for a frame, of a
    group whose sequence may hold more than one, such as the Real World
    Value Mapping Sequence (PS3.3 C.7.6.16.2.11).

    Parameters
    ----------
    dataset, frames, frame, keyword
        As for :func:`frame_group`.

    Raises
    ------
    ValueError
        As for :func:`frame_group`, but where the group's sequence holds no
        item rather than other than one.
    """
    if not 0 <= frame < frames:
        raise ValueError("no such frame")
    try:
        with redacted_diagnostics():
            omitted = shared_alone and "PerFrameFunctionalGroupsSequence" not in dataset
            each = dataset.get("PerFrameFunctionalGroupsSequence") or []
            shared = dataset.get("SharedFunctionalGroupsSequence") or []
            if (not omitted and len(each) != frames) or len(shared) > 1:
                raise ValueError("not one item for each frame")
            own = () if omitted else (each[frame],)
            found = [
                groups[keyword].value for groups in (*own, *shared) if keyword in groups
            ]
            if len(found) != 1:
                raise ValueError("not one functional group")
            (items,) = found
            if items is None or len(items) == 0:
                raise ValueError("no item")
            items = tuple(items)
            if not all(isinstance(item, pydicom.Dataset) for item in items):
                raise ValueError("not an item")
            return items
    except ValueError:
        raise
    # pydicom raises many types for a sequence it cannot parse, such as
    # OSError for an item's bytes that hold no tag, and a message can quote
    # a value.
    except Exception:  # pylint: disable = broad-exception-caught
        raise ValueError("unreadable functional groups") from None
