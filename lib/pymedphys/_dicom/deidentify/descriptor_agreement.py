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

"""Descriptors of a patient, study, series, or frame of reference, cleaned alike.

An attribute of an information entity that spans instances, such as Series
Description (0008,103E) of the General Series module or Study Description
(0008,1030) of the General Study module, describes the entity rather than
the instance, so the instances of the entity hold it alike, as dicom3tools'
dcentvfy checks. Descriptor cleaning (:mod:`.descriptor_cleaning`) decides
on one instance's values at a time: by its own values, and by its own
patient and other person identifiers, which the echo check reads. Where the
values of a series differ between its instances, as where text was added to
some of them, or where one instance names a person whose name is a word of
the value, it would write the attribute in some instances of the series and
remove it from the others, which dcentvfy reports as an attribute present in
one instance but not another.

So, under a policy with Clean Descriptors, a run's
:meth:`~.instance_transform.InstanceTransform.prepare` gives
:class:`DescriptorAgreement` what cleaning would write for each such
descriptor of each instance, before any is written. A descriptor is a
top-level attribute that
:func:`~.reviewed_descriptors.descriptor_attributes` names and that a module
of the instance's IOD defines for the Patient, Study, Series, or Frame of
Reference information entity, as the pinned PS3.3 gives them
(:func:`entity_tags`). Its instances are those of the run that hold the same
Patient ID and Issuer of Patient ID, Study Instance UID, Series Instance
UID, or Frame of Reference UID, as their records read them. Cleaning writes
it, in any of them, only where every instance that the run prepared would
write the same values; otherwise, every instance takes its action under the
policy without Clean Descriptors, as for any descriptor that is not cleaned
(D-009). An instance without the attribute counts as one that would write
something else, so that no instance is written with it beside one without.
One that the run sequesters before cleaning, since its source, character
set, or SOP Class refuses it, or its edits sequester it, is written by
nobody and is left out; one whose preparation fails otherwise counts as one
that would not write it. A kept value that is not written only because its
entity disagrees is left out of the residual search, as it is where it is
written, while a mapped value's source, and a value held in its own
instance, stay in it.

A value of an attribute that another option's cleaner leaves to the reviewed
descriptors list, such as Allergies (0010,2110) under Retain Patient
Characteristics, is left out: a held value there holds its instance for
review rather than falling back (D-038), and a held instance is not
released. An instance that the run did not prepare, such as a copy that is
written as the first copy is, writes a descriptor only where it agrees with
the instances of its entity that the run prepared, and one whose entity has
no prepared instance, as where a transform is called alone, is decided on
alone. The agreement holds the SHA-256 of what each instance would write,
never a value, and its ``repr`` shows only counts.
"""

from __future__ import annotations

import collections
import hashlib
import json
from collections.abc import Callable, Collection, Mapping

from .file_layout import ElementPath
from .iods import IOD
from .references import InstanceRecord
from .reviewed_descriptors import descriptor_attributes

# The information entities that span instances, whose attributes every
# instance of the entity holds alike, and how a record names its entity.
_ENTITIES: Mapping[str, Callable[[InstanceRecord], object]] = {
    "Patient": lambda record: record.patient,
    "Study": lambda record: record.study,
    "Series": lambda record: record.series,
    "Frame of Reference": lambda record: record.frame_of_reference,
}
ENTITIES = tuple(_ENTITIES)
# A vote of an instance that would not write the attribute: without it, or
# where cleaning falls back.
_ABSENT = b"absent"
_FALLS_BACK = b"falls back"

# What an instance's descriptor is checked by: whether the values that
# cleaning would write at the path agree with its entity's other instances.
Agrees = Callable[[ElementPath, tuple[str, ...]], bool]


def always_agrees(path: ElementPath, values: tuple[str, ...]) -> bool:
    """Agree with every value, as for an instance that is decided on alone."""
    del path, values
    return True


def entity_tags(iod: IOD) -> Mapping[str, frozenset[str]]:
    """Return the IOD's descriptors of an entity that spans instances.

    Each tag of :func:`~.reviewed_descriptors.descriptor_attributes` that a
    module of the IOD defines at the top level of the data set for one of
    :data:`ENTITIES`, with those entities, such as Series Description
    (0008,103E) for the Series entity of the CT Image IOD.
    """
    descriptors = descriptor_attributes()
    entities = {module.module: module.information_entity for module in iod.modules}
    found: dict[str, set[str]] = collections.defaultdict(set)
    for definition in iod.definitions:
        entity = entities.get(definition.module)
        if (
            not definition.path
            and definition.tag in descriptors
            and entity in _ENTITIES
        ):
            found[definition.tag].add(entity)
    return {tag: frozenset(names) for tag, names in found.items()}


def _digest(values: tuple[str, ...]) -> bytes:
    return hashlib.sha256(json.dumps(list(values)).encode("ascii")).digest()


class DescriptorAgreement:
    """What the instances of each entity would write for its descriptors."""

    def __init__(self) -> None:
        self._tags: dict[str, Mapping[str, frozenset[str]]] = {}
        self._votes: dict[tuple[str, object, str], set[bytes]] = (
            collections.defaultdict(set)
        )
        self._failed: set[tuple[str, object]] = set()

    def __repr__(self) -> str:
        agreed = sum(
            len(votes) == 1 and not votes & {_ABSENT, _FALLS_BACK}
            for votes in self._votes.values()
        )
        return f"DescriptorAgreement(descriptors={len(self._votes)}, agreed={agreed})"

    def tags(self, iod: IOD) -> Mapping[str, frozenset[str]]:
        """Return :func:`entity_tags` for the IOD, found once."""
        if iod.name not in self._tags:
            self._tags[iod.name] = entity_tags(iod)
        return self._tags[iod.name]

    def vote(
        self,
        record: InstanceRecord,
        iod: IOD,
        written: Mapping[str, tuple[str, ...] | None],
        left_out: Collection[str] = frozenset(),
    ) -> None:
        """Record what one instance would write for its entities' descriptors.

        Parameters
        ----------
        record : InstanceRecord
            The instance's record, which names its entities.
        iod : IOD
            The instance's IOD.
        written : mapping of str to tuple of str or None
            For each descriptor of :meth:`tags` that the instance holds, by
            tag, the values that cleaning would write, or None where the
            attribute would take its action without Clean Descriptors.
        left_out : collection of str, optional
            The tags that cleaning does not decide on, such as those another
            option's cleaner cleans, which no instance votes on.
        """
        for tag, entities in self.tags(iod).items():
            if tag in left_out:
                continue
            if tag not in written:
                vote = _ABSENT
            else:
                values = written[tag]
                vote = _FALLS_BACK if values is None else _digest(values)
            for entity in entities:
                key = _ENTITIES[entity](record)
                if key is not None:
                    self._votes[(entity, key, tag)].add(vote)

    def failed(self, record: InstanceRecord) -> None:
        """Record an instance whose preparation failed: none of its entities agree."""
        for entity, key_of in _ENTITIES.items():
            key = key_of(record)
            if key is not None:
                self._failed.add((entity, key))

    def agrees(self, record: InstanceRecord, iod: IOD) -> Agrees:
        """Return what checks the values that one instance's cleaning would write.

        A top-level descriptor of :meth:`tags` agrees where every instance
        of each of its entities that was prepared would write the same
        values, and an entity that no prepared instance belongs to agrees
        with any; every other attribute agrees.
        """
        tags = self.tags(iod)

        def agrees(path: ElementPath, values: tuple[str, ...]) -> bool:
            if path.items or path.tag not in tags:
                return True
            vote = _digest(values)
            for entity in tags[path.tag]:
                key = _ENTITIES[entity](record)
                if key is None:
                    continue
                if (entity, key) in self._failed:
                    return False
                votes = self._votes.get((entity, key, path.tag))
                if votes is not None and votes != {vote}:
                    return False
            return True

        return agrees
