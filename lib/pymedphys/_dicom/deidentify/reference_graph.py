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

"""The graph of a collection's instances and the references between them.

The first pass of a run records each input as an
:class:`~pymedphys._dicom.deidentify.references.InstanceRecord` and builds a
:class:`ReferenceGraph` from the records before anything is written. The
graph resolves each reference to the inputs it names, and reports each input
that lacks an identifier and each reference that names nothing in the
collection.

A reference resolves by the level of its site, to each input with that SOP
Instance UID, Series Instance UID, or Study Instance UID. Referenced SOP
Instance UID (0008,1155) in a Referenced Study Sequence or RT Referenced
Study Sequence item names a study, whatever its Referenced SOP Class UID
(0008,1150), which is the study's own class, such as the retired Detached
Study Management (PS3.3 Sections 10.6.1 and C.8.8.5.4).

Two kinds of reference that name no input are not reported. A reference to
an instance whose Referenced SOP Class UID is not a Standard Storage SOP
Class of PS3.4 Table B.5-1, such as a Private or retired SOP Class, resolves
if it names an input; otherwise it is not reported, because such a class may
name something that is not a stored instance, such as a performed procedure
step, or a patient through a retired or private management class. A UID that
the pinned tables register, such as a well-known colour palette, names a
public definition.

A :class:`Finding` names inputs only by their positions in the records given
to :func:`build_reference_graph`, and attributes only by their tags, so it
cannot hold a UID, a name, a date, or a path. The findings only report: how a
report presents them, and whether a finding blocks writing or sequesters an
input, are decided later with the rest of the pipeline.
"""

from __future__ import annotations

import collections
import dataclasses
import enum
from collections.abc import Sequence
from typing import NamedTuple

from .references import IDENTITY_TAGS, InstanceRecord, Level, ReferenceSite
from .sop_classes import load_storage_sop_classes
from .uids import well_known_uids


class FindingKind(enum.Enum):
    """What a :class:`Finding` reports.

    Attributes
    ----------
    MISSING_IDENTIFIER
        The input lacks one non-empty value of SOP Instance UID (0008,0018),
        Series Instance UID (0020,000E), or Study Instance UID (0020,000D)
        at the top level: the attribute is absent, empty, only padding, or
        has several values. There is one finding for each input and
        attribute, whose ``attribute`` is that tag alone. The input is left
        out of resolving references at that level.
    DANGLING_REFERENCE
        A value at one of the input's reference sites names no input at the
        site's level: no input has that SOP Instance UID, Series Instance
        UID, or Study Instance UID, without padding. Referenced SOP Instance
        UID in a Referenced Study Sequence or RT Referenced Study Sequence
        item names a study. An empty value, or one that is not a single UID,
        names nothing, except that an empty value at a Type 3 site means the
        same as an absent one. A value that names no input is not reported
        if the pinned tables register it, or if its site names an instance
        and its Referenced SOP Class UID is not a Standard Storage SOP Class
        of Table B.5-1. There is one finding for each input and site, whose
        ``count`` is the number of distinct values there that name nothing.
    """

    MISSING_IDENTIFIER = "missing-identifier"
    DANGLING_REFERENCE = "dangling-reference"


_RANK = {kind: rank for rank, kind in enumerate(FindingKind)}


@dataclasses.dataclass(frozen=True)
class Finding:
    """A problem in a collection, without any of its values.

    Attributes
    ----------
    kind : FindingKind
    instances : tuple of tuple of int
        The positions of the inputs concerned, in groups. Each kind so far
        concerns one input, as ``((position,),)``.
    attribute : tuple of str
        The tags from the outermost sequence to the attribute concerned,
        such as ``("(300C,0060)", "(0008,1155)")``.
    count : int
        For a dangling reference, the number of distinct values that name
        nothing; otherwise 0.
    """

    kind: FindingKind
    instances: tuple[tuple[int, ...], ...]
    attribute: tuple[str, ...]
    count: int = 0


class Edge(NamedTuple):
    """A reference from one input to an instance in the collection."""

    source: int
    attribute: tuple[str, ...]
    target: int


@dataclasses.dataclass(frozen=True)
class ReferenceGraph:
    """A collection's instances, the references between them, and its findings.

    Its ``repr`` shows only the findings.

    Attributes
    ----------
    records : tuple of InstanceRecord
        The inputs, in the order given.
    edges : frozenset of Edge
        Each reference to an instance, from the position of the input that
        makes it, at the site's attribute, to the position of each input with
        that SOP Instance UID. References to series and studies resolve to
        no edge.
    findings : tuple of Finding
        Ordered by kind, in the order :class:`FindingKind` lists them, then
        by the inputs' positions, then by attribute.
    """

    records: tuple[InstanceRecord, ...] = dataclasses.field(repr=False)
    edges: frozenset[Edge] = dataclasses.field(repr=False)
    findings: tuple[Finding, ...]


def build_reference_graph(records: Sequence[InstanceRecord]) -> ReferenceGraph:
    """Resolve the references between a collection's inputs, and report problems.

    Parameters
    ----------
    records : sequence of InstanceRecord
        One for each input of the run, in the order that positions in the
        findings refer to.

    Returns
    -------
    ReferenceGraph
        Its findings follow the definitions of :class:`FindingKind`. Building
        it neither logs nor warns.
    """
    records = tuple(records)
    findings: list[Finding] = []
    index: dict[Level, dict[str, list[int]]] = {
        level: collections.defaultdict(list) for level in Level
    }
    for position, record in enumerate(records):
        for level, tag in IDENTITY_TAGS.items():
            identifier = record.identifier(level)
            if identifier is None:
                findings.append(
                    Finding(FindingKind.MISSING_IDENTIFIER, ((position,),), (tag,))
                )
            else:
                index[level][identifier].append(position)

    storage = frozenset(row.uid for row in load_storage_sop_classes().rows)
    registered = well_known_uids()
    edges: set[Edge] = set()
    for position, record in enumerate(records):
        unresolved: dict[ReferenceSite, set[str]] = {}
        for reference in record.references:
            site = reference.site
            unlisted_class = (
                site.level is Level.INSTANCE
                and reference.target_class is not None
                and reference.target_class not in storage
            )
            targets = index[site.level].get(reference.target)
            if targets is not None:
                if site.level is Level.INSTANCE:
                    edges.update(
                        Edge(position, site.attribute, target) for target in targets
                    )
            elif not (unlisted_class or reference.target in registered):
                unresolved.setdefault(site, set()).add(reference.target)
        findings.extend(
            Finding(
                FindingKind.DANGLING_REFERENCE,
                ((position,),),
                site.attribute,
                len(values),
            )
            for site, values in unresolved.items()
        )

    findings.sort(
        key=lambda finding: (_RANK[finding.kind], finding.instances, finding.attribute)
    )
    return ReferenceGraph(records, frozenset(edges), tuple(findings))
