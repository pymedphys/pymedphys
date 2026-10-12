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

"""Verify that a run's written instances refer to each other as its inputs did.

This is the second pass of the reference graph (Architecture item 8). The
first pass records each input as an
:class:`~pymedphys._dicom.deidentify.references.InstanceRecord` and builds a
:class:`~pymedphys._dicom.deidentify.reference_graph.ReferenceGraph` before
anything is written. Once the run has written its instances, each written
file is recorded in the same way, with
:meth:`~pymedphys._dicom.deidentify.references.InstanceRecord.from_file`,
and :func:`verify_written_references` compares those records with the
graph. It reads only the written files' records, never the plan or the
edits that produced them, so it checks what was written rather than what
was meant to be.

For each written instance, it checks that:

1. its SOP Instance UID (0008,0018), Series Instance UID (0020,000E), and
   Study Instance UID (0020,000D) are each the replacement of its input's
   under the run's key, as
   :func:`~pymedphys._dicom.deidentify.uids.transform_uid` gives it, so
   that every written instance of one input series or study has the same
   replacement;
2. each value at one of its IOD's reference sites is the replacement of a
   value at the same site in its input, and so neither an input's UID nor
   any other value;
3. where that input value named inputs of the run at the site's level, the
   written value names a written instance, series, or study, so that each
   reference that resolved before writing still resolves after it.

Across the run, it checks that the replacement is one-to-one: no two input
UIDs have the same written value; and that no two written instances have the
same SOP Instance UID, as copies of one input instance are written once.

Values are compared site by site, not item by item: a written value at a
site passes the checks above if it replaces any value at that site in its
input. So a value that is missing from a site that holds others, or values
that have moved between the items of one sequence, are not reported.

A UID that the pinned tables register
(:func:`~pymedphys._dicom.deidentify.uids.well_known_uids`) is its own
replacement, as :func:`~pymedphys._dicom.deidentify.uids.transform_uid`
retains it. A reference that named no input before writing, whether the
graph reported it as dangling or not, need not name a written instance, but
its value must still be the replacement of its input's. A written reference
whose input named only inputs that were not written, such as sequestered
ones, names nothing in the written collection, and is reported, as how the
pipeline treats it is not yet decided. Where an input lacks one of its
identifiers, which the graph reports, that identifier is not checked, as
what the pipeline does with such an input is not yet decided (D-026),
though a written value there that is one of the inputs' UIDs is still
reported. A reference site that is in an input and not in what was written
is not reported, since a rule may remove the sequence that holds it.

A :class:`WrittenFinding` names instances only by their inputs' positions in
the graph, and attributes only by their tags, so it holds no UID, no name,
and no path. Verifying neither logs nor warns.
"""

from __future__ import annotations

import collections
import dataclasses
import enum
from collections.abc import Mapping

from .keys import DeidKey
from .reference_graph import ReferenceGraph
from .references import IDENTITY_TAGS, InstanceRecord, Level
from .uid_roles import UIDRole
from .uids import transform_uid, well_known_uids


class WrittenFindingKind(enum.Enum):
    """What a :class:`WrittenFinding` reports.

    Attributes
    ----------
    ORIGINAL_UID
        A written SOP Instance UID, Series Instance UID, Study Instance UID,
        or value at a reference site is a UID of one of the run's inputs, at
        an identity or reference site of any input, that the pinned tables
        do not register: a source UID was written where its replacement was
        required. There is one finding for each written instance and
        attribute, whose ``count`` is the number of distinct such values
        there. It is reported in place of the mismatch that it also is.
    MISMATCHED_IDENTIFIER
        A written instance's SOP Instance UID, Series Instance UID, or
        Study Instance UID is absent, or is not the replacement of its
        input's. Its ``count`` is 1.
    MISMATCHED_REFERENCE
        A value at one of a written instance's reference sites is not the
        replacement of any value at the same site in its input. Its
        ``count`` is the number of distinct such values at that site.
    UNWRITTEN_TARGET
        A value at a reference site is the replacement of an input value
        that named inputs of the run, none of which was written, so the
        written reference names nothing in the written collection. Its
        ``count`` is the number of distinct such values at that site.
    UNRESOLVED_REFERENCE
        A value at a reference site is the replacement of an input value
        that named an input that was written, but no written instance has
        it as its SOP Instance UID, Series Instance UID, or Study Instance
        UID at the site's level. Its ``count`` is the number of distinct
        such values at that site.
    SHARED_REPLACEMENT
        Different input UIDs have the same written value. Its groups hold,
        for each input UID, the positions of the written instances where
        its replacement was found, and its ``attribute`` is empty, since
        the values may be at several attributes.
    DUPLICATE_INSTANCE
        Several written instances have the same SOP Instance UID. Its one
        group holds their positions, its ``attribute`` is SOP Instance UID
        (0008,0018), and its ``count`` is 1.
    """

    ORIGINAL_UID = "original-uid"
    MISMATCHED_IDENTIFIER = "mismatched-identifier"
    MISMATCHED_REFERENCE = "mismatched-reference"
    UNWRITTEN_TARGET = "unwritten-target"
    UNRESOLVED_REFERENCE = "unresolved-reference"
    SHARED_REPLACEMENT = "shared-replacement"
    DUPLICATE_INSTANCE = "duplicate-instance"


_RANK = {kind: rank for rank, kind in enumerate(WrittenFindingKind)}


@dataclasses.dataclass(frozen=True)
class WrittenFinding:
    """A problem in what a run wrote, without any of its values.

    Attributes
    ----------
    kind : WrittenFindingKind
    instances : tuple of tuple of int
        The positions in the graph of the inputs whose written instances are
        concerned: ``((position,),)``, except for a shared replacement or a
        duplicate instance, whose groups :class:`WrittenFindingKind` gives,
        each in ascending order.
    attribute : tuple of str
        The tags from the outermost sequence to the attribute concerned,
        such as ``("(300C,0060)", "(0008,1155)")``, or ``()`` for a shared
        replacement.
    count : int
        The number of distinct values concerned, as
        :class:`WrittenFindingKind` gives it; 0 for a shared replacement.
    """

    kind: WrittenFindingKind
    instances: tuple[tuple[int, ...], ...]
    attribute: tuple[str, ...]
    count: int = 0


def verify_written_references(
    key: DeidKey, graph: ReferenceGraph, written: Mapping[int, InstanceRecord]
) -> tuple[WrittenFinding, ...]:
    """Check that what a run wrote refers to itself as its inputs did.

    Parameters
    ----------
    key : DeidKey
        The run's key, which replaced the inputs' UIDs.
    graph : ReferenceGraph
        The first pass's graph of the run's inputs.
    written : mapping of int to InstanceRecord
        The record of each written file, by the position in ``graph`` of
        the input it was written from. An input that was not written, such
        as one that was sequestered or a duplicate that was written once,
        has no entry.

    Returns
    -------
    tuple of WrittenFinding
        As :class:`WrittenFindingKind` defines them, ordered by kind in the
        order it lists them, then by position, then by attribute. Empty if
        everything written refers to itself as its inputs did.

    Raises
    ------
    ValueError
        If a key of ``written`` is not a position in ``graph``.
    """
    records = graph.records
    for position in written:
        if (
            isinstance(position, bool)
            or not isinstance(position, int)
            or not 0 <= position < len(records)
        ):
            raise ValueError(
                "a key of written is not one of the graph's inputs' positions"
            )
    registered = well_known_uids()
    replacements: dict[str, str] = {}

    def replace(value: str) -> str:
        if not value:
            return ""
        if value not in replacements:
            replacements[value] = transform_uid(key, UIDRole.INSTANCE, value)[0]
        return replacements[value]

    named: dict[Level, dict[str, list[int]]] = {
        level: collections.defaultdict(list) for level in Level
    }
    for position, record in enumerate(records):
        for level in Level:
            identifier = record.identifier(level)
            if identifier is not None:
                named[level][identifier].append(position)
    originals = {
        value
        for record in records
        for value in (
            *(record.identifier(level) for level in Level),
            *(reference.target for reference in record.references),
        )
        if value and value not in registered
    }
    written_identifiers = {
        level: {
            identifier
            for record in written.values()
            if (identifier := record.identifier(level)) is not None
        }
        for level in Level
    }

    findings: list[WrittenFinding] = []
    # Each written value, the input UIDs it replaced, and where.
    replaced: dict[str, dict[str, set[int]]] = collections.defaultdict(
        lambda: collections.defaultdict(set)
    )
    for position, record in sorted(written.items()):
        source = records[position]
        for level, tag in IDENTITY_TAGS.items():
            value = source.identifier(level)
            identifier = record.identifier(level)
            if value is None:
                if identifier in originals:
                    findings.append(
                        WrittenFinding(
                            WrittenFindingKind.ORIGINAL_UID, ((position,),), (tag,), 1
                        )
                    )
                continue
            if identifier == replace(value):
                replaced[identifier][value].add(position)
                continue
            kind = WrittenFindingKind.MISMATCHED_IDENTIFIER
            if identifier in originals:
                kind = WrittenFindingKind.ORIGINAL_UID
            findings.append(WrittenFinding(kind, ((position,),), (tag,), 1))

        # The input values that each written value at a site replaces.
        expected: dict[tuple[str, ...], dict[str, set[str]]] = {}
        for reference in source.references:
            expected.setdefault(reference.site.attribute, {}).setdefault(
                replace(reference.target), set()
            ).add(reference.target)
        problems: dict[tuple[WrittenFindingKind, tuple[str, ...]], set[str]] = (
            collections.defaultdict(set)
        )
        for reference in record.references:
            site, value = reference.site, reference.target
            sources = expected.get(site.attribute, {})
            if value not in sources:
                kind = WrittenFindingKind.MISMATCHED_REFERENCE
                if value in originals:
                    kind = WrittenFindingKind.ORIGINAL_UID
                problems[kind, site.attribute].add(value)
                continue
            targets: set[int] = set()
            for each in sources[value]:
                if each:
                    replaced[value][each].add(position)
                targets.update(named[site.level].get(each, ()))
            if not targets:
                continue
            if not any(target in written for target in targets):
                problems[WrittenFindingKind.UNWRITTEN_TARGET, site.attribute].add(value)
            elif value not in written_identifiers[site.level]:
                problems[WrittenFindingKind.UNRESOLVED_REFERENCE, site.attribute].add(
                    value
                )
        findings.extend(
            WrittenFinding(kind, ((position,),), attribute, len(values))
            for (kind, attribute), values in problems.items()
        )

    for inputs in replaced.values():
        if len(inputs) > 1:
            groups = sorted(tuple(sorted(positions)) for positions in inputs.values())
            findings.append(
                WrittenFinding(WrittenFindingKind.SHARED_REPLACEMENT, tuple(groups), ())
            )
    copies: dict[str, list[int]] = collections.defaultdict(list)
    for position, record in sorted(written.items()):
        identifier = record.identifier(Level.INSTANCE)
        if identifier:
            copies[identifier].append(position)
    findings.extend(
        WrittenFinding(
            WrittenFindingKind.DUPLICATE_INSTANCE,
            (tuple(positions),),
            (IDENTITY_TAGS[Level.INSTANCE],),
            1,
        )
        for positions in copies.values()
        if len(positions) > 1
    )
    findings.sort(
        key=lambda finding: (_RANK[finding.kind], finding.instances, finding.attribute)
    )
    return tuple(findings)
