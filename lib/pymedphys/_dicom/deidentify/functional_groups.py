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
that place a frame and rescale its stored values.

A group in both sequences is refused rather than one taken over the other,
since PS3.3 C.7.6.16.1.1 lets a group be in only one of them and gives
neither precedence; so is a group in neither, a sequence of other than one
item, and a Per-frame Functional Groups Sequence of other than one item for
each frame, as is an instance without it, which PS3.3 A.51.5 permits a
Segmentation where it would be empty. Whatever is refused raises
:class:`ValueError`, without any value, so that a caller can leave the
instance as it is.
"""

from __future__ import annotations

from pymedphys._imports import pydicom

from .diagnostics import redacted_diagnostics


def frame_group(
    dataset: pydicom.Dataset, frames: int, frame: int, keyword: str
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

    Raises
    ------
    ValueError
        Where the Per-frame Functional Groups Sequence does not have one item
        for each of the ``frames`` frames, the Shared Functional Groups
        Sequence has more than one, or the group is not in exactly one of
        them, in one item; without any value.
    """
    if not 0 <= frame < frames:
        raise ValueError("no such frame")
    with redacted_diagnostics():
        each = dataset.get("PerFrameFunctionalGroupsSequence") or []
        shared = dataset.get("SharedFunctionalGroupsSequence") or []
        if len(each) != frames or len(shared) > 1:
            raise ValueError("not one item for each frame")
        found = [
            groups[keyword].value
            for groups in (each[frame], *shared)
            if keyword in groups
        ]
        if len(found) != 1:
            raise ValueError("not one functional group")
        (items,) = found
        if items is None or len(items) != 1:
            raise ValueError("not one item")
        return items[0]
