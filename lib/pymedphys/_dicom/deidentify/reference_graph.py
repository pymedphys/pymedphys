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
that lacks an identifier, each reference that names nothing in the
collection, and an inconsistent hierarchy: inputs that share a SOP Instance
UID, a series in several studies, and a study of several patients.

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
cannot hold a UID, a name, a date, or a path. The graph only reports. Each
kind of finding has a consequence in the design, which its description in
:class:`FindingKind` gives and the pipeline is to carry out, from writing an
input with a dangling reference as usual to stopping the run for a study of
several patients. How a report presents findings is decided with the rest of
the pipeline.
"""

from __future__ import annotations

import collections
import dataclasses
import enum
from collections.abc import Callable, Hashable, Iterator, Sequence
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
        It is reported only, and the input is written as usual.
    DUPLICATE_INSTANCE
        Several inputs have one SOP Instance UID, without padding, and the
        same source bytes, as :mod:`~pymedphys._dicom.deidentify.references`
        defines them: the same Transfer Syntax UID, and the same bytes of
        the data set, without the preamble, the File Meta Information, and
        the top-level group lengths and Data Set Trailing Padding. Its one
        group holds them all. The instance is written once.
    CONFLICTING_INSTANCE
        Several inputs have one SOP Instance UID and different source bytes,
        including copies that differ only in their encoding, such as one in
        Implicit VR and one in Explicit VR Little Endian. Its groups hold the
        inputs with the same source bytes, except that an input whose bytes
        cannot be shown to be sound, such as one whose structure cannot be
        read to its end, is a group of its own. Every one of them is
        sequestered.
    SERIES_IN_SEVERAL_STUDIES
        The inputs with one Series Instance UID have different Study
        Instance UIDs. Its groups hold the inputs of each study. The series
        is sequestered.
    STUDY_WITH_SEVERAL_PATIENTS
        The inputs with one Study Instance UID have different patients, each
        the identity of a Patient ID with its Issuer of Patient ID (0010,0021),
        from which pseudonyms are derived. The same Patient ID from another
        issuer, or from none, is another patient. The inputs without a
        Patient ID together count as one more patient, apart from every
        identity, so a study that mixes inputs with and without a Patient ID
        has several patients, and a study whose inputs all lack one has one.
        Such an input needs a curated identity before it can have a
        pseudonym, and that identity would give it a different pseudonym
        from the rest of its study. Its groups hold the inputs of each
        patient. The run stops before anything is written.

    A finding that compares inputs leaves out each input that lacks a UID
    that it compares, which is reported as missing. Its ``attribute`` is the
    tag of the UID that its inputs share: SOP Instance UID for duplicates and
    conflicts, Series Instance UID for a series, and Study Instance UID for a
    study. The run (:mod:`~pymedphys._dicom.deidentify.run`) sequesters an
    input that lacks one of these UIDs.
    """

    MISSING_IDENTIFIER = "missing-identifier"
    DANGLING_REFERENCE = "dangling-reference"
    DUPLICATE_INSTANCE = "duplicate-instance"
    CONFLICTING_INSTANCE = "conflicting-instance"
    SERIES_IN_SEVERAL_STUDIES = "series-in-several-studies"
    STUDY_WITH_SEVERAL_PATIENTS = "study-with-several-patients"


_RANK = {kind: rank for rank, kind in enumerate(FindingKind)}
# The patient of every input without a Patient ID, apart from every identity.
_WITHOUT_PATIENT_ID = object()


@dataclasses.dataclass(frozen=True)
class Finding:
    """A problem in a collection, without any of its values.

    Attributes
    ----------
    kind : FindingKind
    instances : tuple of tuple of int
        The positions of the inputs concerned, in groups: ``((position,),)``
        for a missing identifier or a dangling reference, and otherwise the
        groups that :class:`FindingKind` gives, by first position, each in
        ascending order.
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

    findings.extend(_hierarchy_findings(records, index))
    findings.sort(
        key=lambda finding: (_RANK[finding.kind], finding.instances, finding.attribute)
    )
    return ReferenceGraph(records, frozenset(edges), tuple(findings))


def _hierarchy_findings(
    records: tuple[InstanceRecord, ...], index: dict[Level, dict[str, list[int]]]
) -> Iterator[Finding]:
    """Yield the findings of inputs that share an identifier but disagree."""
    sop_instance, series, study = (IDENTITY_TAGS[level] for level in Level)
    for positions in index[Level.INSTANCE].values():
        if len(positions) > 1:
            groups = _grouped(positions, lambda position: _source(records, position))
            kind = FindingKind.CONFLICTING_INSTANCE
            if len(groups) == 1:
                kind = FindingKind.DUPLICATE_INSTANCE
            yield Finding(kind, groups, (sop_instance,))
    for positions in index[Level.SERIES].values():
        groups = _grouped(positions, lambda position: records[position].study)
        if len(groups) > 1:
            yield Finding(FindingKind.SERIES_IN_SEVERAL_STUDIES, groups, (series,))
    for positions in index[Level.STUDY].values():
        groups = _grouped(positions, lambda position: _patient(records[position]))
        if len(groups) > 1:
            yield Finding(FindingKind.STUDY_WITH_SEVERAL_PATIENTS, groups, (study,))


def _source(records: tuple[InstanceRecord, ...], position: int) -> Hashable:
    """Return the record's digest, or a key of its own if it has none."""
    digest = records[position].digest
    return ("unshown", position) if digest is None else digest


def _patient(record: InstanceRecord) -> Hashable:
    """Return the record's patient, the same for every input without a Patient ID."""
    return _WITHOUT_PATIENT_ID if record.patient is None else record.patient


def _grouped(
    positions: list[int], key: Callable[[int], Hashable | None]
) -> tuple[tuple[int, ...], ...]:
    """Group the positions by their key, leaving out those whose key is None."""
    groups: dict[Hashable, list[int]] = {}
    for position in positions:
        value = key(position)
        if value is not None:
            groups.setdefault(value, []).append(position)
    return tuple(tuple(group) for group in groups.values())
