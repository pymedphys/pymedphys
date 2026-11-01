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

"""Items removed on their own from a kept sequence, and how the output numbers the rest.

Under Clean Structured Content, an item of Content Sequence (0040,A730)
that cannot be kept is removed on its own, with everything in it, while the
sequence and its other items are kept, and so is a TABLE's cell, an item of
Cell Values Sequence (0040,A808), that names a removed item (D-047). The plan names every element
by its path in the source; the written file numbers the items of such a
sequence without the removed ones, so the items after a removed item move
up. :class:`RemovedItems` maps a path between the two numberings, for the
writer, the verification of what it preserved, and the check of the IOD's
requirements.

An item is named by the items tuple of an
:class:`~pymedphys._dicom.deidentify.file_layout.ElementPath` that ends with
it: its sequence's tag and its index there, after the items that hold the
sequence, in the source's numbering.

Examples
--------
>>> from pymedphys._dicom.deidentify.file_layout import ElementPath
>>> content = "(0040,A730)"
>>> removed = RemovedItems({((content, 1),)})
>>> str(removed.output_path(ElementPath(((content, 2),), "(0040,A040)")))
'(0040,A730)[1] > (0040,A040)'
>>> removed.output_path(ElementPath(((content, 1),), "(0040,A040)")) is None
True
>>> str(removed.source_path(ElementPath(((content, 1),), "(0040,A040)")))
'(0040,A730)[2] > (0040,A040)'
"""

from __future__ import annotations

from collections.abc import Collection

from .file_layout import ElementPath

Item = tuple[tuple[str, int], ...]


class RemovedItems:
    """The items removed on their own, each by its path in the source.

    Parameters
    ----------
    items : collection of tuple of (str, int)
        Each removed item, as the items tuple of a path that ends with it.
        An item inside another removed item is removed with it, so it
        changes no numbering of its own.

    Raises
    ------
    ValueError
        If an item is empty, which names the data set rather than an item.
    """

    def __init__(self, items: Collection[Item] = ()) -> None:
        if any(not item for item in items):
            raise ValueError("a removed item needs its sequence and index")
        self.items = frozenset(items)
        # Each sequence's removed indices, ascending, by the sequence's path.
        by_sequence: dict[ElementPath, list[int]] = {}
        for item in self.items:
            *outer, (tag, index) = item
            by_sequence.setdefault(ElementPath(tuple(outer), tag), []).append(index)
        self._by_sequence = {
            sequence: tuple(sorted(indices))
            for sequence, indices in by_sequence.items()
        }

    def __bool__(self) -> bool:
        return bool(self.items)

    def __repr__(self) -> str:
        return f"RemovedItems(items={len(self.items)})"

    def count(self, sequence: ElementPath) -> int:
        """Return how many items of the sequence at ``sequence`` are removed."""
        return len(self._by_sequence.get(sequence, ()))

    def holds(self, path: ElementPath) -> bool:
        """Return whether a removed item holds ``path``, at any depth."""
        return any(
            path.items[:depth] in self.items for depth in range(1, len(path.items) + 1)
        )

    def output_path(self, path: ElementPath) -> ElementPath | None:
        """Return where the output holds a source element, or None if removed.

        Each item index of ``path`` is reduced by the removed items before
        it in the same sequence.
        """
        if self.holds(path):
            return None
        items: list[tuple[str, int]] = []
        for depth, (tag, index) in enumerate(path.items):
            removed = self._by_sequence.get(ElementPath(path.items[:depth], tag), ())
            items.append((tag, index - sum(1 for each in removed if each < index)))
        return ElementPath(tuple(items), path.tag)

    def source_path(self, path: ElementPath) -> ElementPath:
        """Return the source's path of an output element, the inverse of
        :meth:`output_path`.

        Each item index of ``path`` is raised past the removed items of the
        same sequence, in the source's numbering, at or before it.
        """
        items: list[tuple[str, int]] = []
        for tag, index in path.items:
            for removed in self._by_sequence.get(ElementPath(tuple(items), tag), ()):
                if removed <= index:
                    index += 1
            items.append((tag, index))
        return ElementPath(tuple(items), path.tag)
