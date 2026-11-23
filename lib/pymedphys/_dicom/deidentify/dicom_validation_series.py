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

"""Find the series whose inputs mix modalities, for the DICOM validation.

PS3.3 Section A.1.2.3 requires the instances of a series to be of one
modality and to have the same Series information. Where a source series
mixes modalities, each instance's own IOD decides each attribute's action,
so outputs that each conform to their IOD can differ in an attribute that
``dcentvfy`` expects a series to share. The comparison
(:mod:`~pymedphys._dicom.deidentify.dicom_validation`) explains such a
finding under the mixed-modality premise,
:data:`~pymedphys._dicom.deidentify.dicom_validation.MIXED_MODALITY_SERIES`,
for the attributes that :func:`mixed_modality_series` finds, and for no
more occurrences than :func:`series_allowances` counts. The values that
this module reads are compared in memory and never leave it.
"""

from __future__ import annotations

import collections
import dataclasses
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from pymedphys._imports import pydicom

from . import dicom_validators as validators
from .diagnostics import redacted_diagnostics
from .dicom_validators import Finding, Status

_SOP_CLASS = 0x00080016
_MODALITY = 0x00080060
_SERIES_INSTANCE_UID = 0x0020000E
# The information entity that dcentvfy names for a series' attributes.
SERIES_ENTITY = "Series"


class Paired(Protocol):
    """A released instance's input and output files, such as
    :class:`~pymedphys._dicom.deidentify.dicom_validation.Pair`."""

    @property
    def source(self) -> Path: ...

    @property
    def output(self) -> Path: ...


@dataclasses.dataclass(frozen=True)
class _Top:
    """A file's SOP Class, Modality, Series Instance UID, and top-level tags."""

    sop_class: str
    modality: str
    series: str
    tags: frozenset[int]


def _top_level(path: Path) -> _Top | None:
    """Read a file's top level, or return None if it cannot be read or has
    no SOP Class UID.

    Its values are compared by the caller and never leave this module.
    """
    # pydicom converts, and validates, each value as it is first read, so
    # the values are read within the context too.
    try:
        with redacted_diagnostics():
            dataset = pydicom.dcmread(path, stop_before_pixels=True, force=True)
            tags = frozenset(
                int(element.tag) for element in dataset if not element.tag.is_private
            )
            values = [
                str(dataset[tag].value).strip(" \x00") if tag in dataset else ""
                for tag in (_SOP_CLASS, _MODALITY, _SERIES_INSTANCE_UID)
            ]
    except Exception:  # pylint: disable = broad-exception-caught
        return None
    # A file that is not DICOM, such as an empty one, reads as a data set
    # without a SOP Class UID.
    return _Top(*values, tags=tags) if values[0] else None


@dataclasses.dataclass(frozen=True)
class MixedSeries:
    """A series whose inputs mix modalities, and the attributes that each
    instance's own IOD decides in it.

    Attributes
    ----------
    members : tuple of int
        The positions, in the pairs given, of the series' instances.
    paths : frozenset of str
        The tags, as ``dcentvfy``'s findings give them, of the attributes
        for which the mixed-modality premise holds.
    """

    members: tuple[int, ...]
    paths: frozenset[str]


def mixed_modality_series(pairs: Sequence[Paired]) -> tuple[MixedSeries, ...]:
    """Return a patient's series for which the mixed-modality premise holds
    for an attribute.

    It holds for an attribute of a series, the inputs that share one Series
    Instance UID, where the inputs give more than one Modality (0008,0060),
    which PS3.3 Section A.1.2.3 does not allow; every input holds the
    attribute at its top level; and the outputs of each SOP Class all hold
    it, or all lack it, while those of another SOP Class differ. Each
    instance's own IOD then decides the attribute's action, and each
    output's conformance to it is what the per-file validators check. A
    series without a Series Instance UID or Modality in an input holds none,
    and a patient with a file that cannot be read, or that has no SOP Class
    UID, holds none, as ``dcentvfy`` stops at such a file. The values are
    compared here and never leave this function.
    """
    series: dict[str, list[tuple[int, _Top, _Top]]] = collections.defaultdict(list)
    for index, pair in enumerate(pairs):
        source, output = _top_level(pair.source), _top_level(pair.output)
        if source is None or output is None:
            return ()
        series[source.series].append((index, source, output))
    found = []
    for uid, read in series.items():
        if not uid or not all(source.modality for _, source, _ in read):
            continue
        if len({source.modality for _, source, _ in read}) < 2:
            continue
        held = frozenset.intersection(*(source.tags for _, source, _ in read))
        paths = set()
        for tag in held:
            by_class: dict[str, set[bool]] = collections.defaultdict(set)
            for _, source, output in read:
                by_class[source.sop_class].add(tag in output.tags)
            if all(len(kept) == 1 for kept in by_class.values()) and {
                kept for (kept,) in by_class.values()
            } == {True, False}:
                paths.add(f"({tag >> 16:04X},{tag & 0xFFFF:04X})")
        if paths:
            found.append(
                MixedSeries(tuple(index for index, _, _ in read), frozenset(paths))
            )
    return tuple(found)


def series_allowances(
    pairs: Sequence[Paired], dcentvfy: str
) -> collections.Counter[Finding]:
    """Return how many occurrences of each ``dcentvfy`` finding a patient's
    mixed-modality series give on their own.

    ``dcentvfy`` counts a patient's findings together, whatever series gave
    them, so each series of :func:`mixed_modality_series` is checked again
    alone, inputs and then outputs, and only the Series findings that its
    outputs give more often than its inputs, on an attribute for which the
    mixed-modality premise holds there, are counted. No more of a patient's
    occurrences than these can be explained by it, so an occurrence that
    another series gives stays unexplained.
    """
    allowances: collections.Counter[Finding] = collections.Counter()
    for series in mixed_modality_series(pairs):
        source = validators.run_dcentvfy(
            dcentvfy, [pairs[index].source for index in series.members]
        )
        output = validators.run_dcentvfy(
            dcentvfy, [pairs[index].output for index in series.members]
        )
        if (
            source.status is not Status.VALIDATED
            or output.status is not Status.VALIDATED
        ):
            continue
        for finding, count in output.findings.items():
            gained = count - source.findings.get(finding, 0)
            if (
                gained > 0
                and finding.context == SERIES_ENTITY
                and finding.path in series.paths
            ):
                allowances[finding] += gained
    return allowances
