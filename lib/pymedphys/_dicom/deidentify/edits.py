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

"""Work out what each planned element of a data set becomes.

The walker's second step takes an instance's plan
(:func:`~pymedphys._dicom.deidentify.walker.plan_instance`) and its source
evidence, decodes only the values that the plan's consumers need, and gives
each element of the data set, in file order, an :class:`Edit`:

- K keeps the element, which is to be written from its source bytes;
- X removes it, as it does each descendant of a removed sequence, whose
  values are still decoded and collected where they can be;
- Z empties it (D-021);
- D replaces it with its VR's dummy value, or the second one where the
  source value equals the first, or, for a UI value, its keyed replacement
  (:func:`~pymedphys._dicom.deidentify.dummy_values.values_for_d`); D
  replaces Person Identification Code Sequence (0040,1101), whose source
  items are removed with it, with its reviewed dummy item, compared with
  each source item's Code Value (0008,0100) and Code Meaning (0008,0104)
  (:func:`~pymedphys._dicom.deidentify.dummy_values.items_for_d`, D-021);
- U replaces each UID that the pinned tables do not register with its keyed
  replacement, and keeps each that they do
  (:func:`~pymedphys._dicom.deidentify.uids.transform_uid`).

Patient's Name (0010,0010) and Patient ID (0010,0020) at the top level of
the data set take the subject's keyed pseudonyms under Z and D (D-005),
given the subject's identity, which the run resolves across its instances;
without one, their edits are pending. C cleans the value (D-009), so its
edit is pending, for a later step to give.

It also collects, for the residual search
(:mod:`~pymedphys._dicom.deidentify.residuals`), each value that is removed
or replaced, with the VR and character set it was read in. A value that is
only collected and cannot be decoded is listed as not collected, with a
reason that holds no value: the transformation may proceed, but whether the
instance may be released is for the release gate to decide. Where a value
that the action needs cannot be decoded, or a Specific Character Set is not
supported (D-010), the instance is sequestered, and has no edits. Text
outside ISO 646 where no Specific Character Set applies is the exception, as
the maintainer decided on 1 October 2026: where its rule removes or replaces
it, it is read as ISO 8859-1, in which every byte is a character, to be
collected and compared, and the instance is de-identified, with its path in
:attr:`InstanceEdits.read_as_latin_1`; where it is to be cleaned, the
instance is sequestered.

A kept sequence's items are read, so that each element in them can be
written or kept; where they cannot be, the instance is sequestered. Nothing
is written to a data set here. Values are read from one fresh
data set of the source (:meth:`.SourceEvidence.dataset`), each against the
source's own bytes (:func:`~pymedphys._dicom.deidentify.elements.read_element`),
so a read never replaces the source evidence. The edits, their ``repr``, and
the reasons name paths, actions, VRs, and outcomes, never a value.
"""

from __future__ import annotations

import dataclasses
import enum

from . import elements
from .dummy_values import DummyElement, NoDummyValueError, items_for_d, values_for_d
from .elements import ElementValue, OutsideDefaultRepertoire, UndecodableElement
from .file_layout import ElementPath
from .keys import DeidKey
from .pseudonyms import SubjectIdentity, patient_pseudonym
from .residuals import SourceValue
from .source import SourceEvidence
from .standard import dictionary_attribute
from .uid_roles import load_uid_roles
from .uids import UIDOutcome, normalise_uid, transform_uid, well_known_uids
from .walker import (
    DESCENDED,
    Consumer,
    ElementPlan,
    InstancePlan,
    SequesterReason,
    Sequestration,
)

# The attributes that take the subject's pseudonyms under Z and D (D-005).
PSEUDONYM_TAGS = frozenset({"(0010,0010)", "(0010,0020)"})
_CHARACTER_SET = "(0008,0005)"
# The consumers that need the value itself, rather than only collecting it.
_NEEDS_VALUE = frozenset(
    {Consumer.UID_REPLACEMENT, Consumer.DUMMY_COMPARISON, Consumer.CLEANING}
)


class EditKind(enum.Enum):
    """What an element becomes."""

    KEEP = "keep"
    REMOVE = "remove"
    EMPTY = "empty"
    REPLACE = "replace"
    PENDING = "pending"  # a pseudonym or cleaning to come


@dataclasses.dataclass(frozen=True, repr=False)
class Edit:
    """What one element becomes. Its ``repr`` leaves out the values.

    Attributes
    ----------
    path : ElementPath
    action : str
        The plan's action, such as ``"D"``.
    kind : EditKind
    values : tuple of str, int, or float
        The values that replace the element's, for :attr:`EditKind.REPLACE`
        of an element other than a sequence; otherwise ``()``.
    uid_outcomes : tuple of UIDOutcome
        For U, what :func:`~pymedphys._dicom.deidentify.uids.transform_uid`
        did with each value; otherwise ``()``.
    removed_with : ElementPath or None
        The outermost sequence that removes the element, whose own edit
        covers it, or ``None``.
    items : tuple of tuple of DummyElement
        The items that replace a sequence's, each its elements in the order
        of their tags, for :attr:`EditKind.REPLACE` of a sequence, such as
        D's on Person Identification Code Sequence (0040,1101); otherwise
        ``()``. The source items are removed with the sequence.
    """

    path: ElementPath
    action: str
    kind: EditKind
    values: tuple[str | int | float, ...] = ()
    uid_outcomes: tuple[UIDOutcome, ...] = ()
    removed_with: ElementPath | None = None
    items: tuple[tuple[DummyElement, ...], ...] = ()

    def __repr__(self) -> str:
        return (
            f"Edit(path={str(self.path)!r}, action={self.action!r}, "
            f"kind={self.kind.value!r})"
        )


@dataclasses.dataclass(frozen=True)
class NotCollected:
    """A value to collect for the residual search that could not be decoded.

    Attributes
    ----------
    path : ElementPath
    reason : str
        Why, naming no value.
    """

    path: ElementPath
    reason: str


@dataclasses.dataclass(frozen=True, repr=False)
class InstanceEdits:
    """What every element of one data set becomes, and the values collected.

    Its ``repr`` shows only counts.

    Attributes
    ----------
    edits : tuple of Edit
        One for each element of the plan, in file order; ``()`` if the
        instance must be sequestered.
    source_values : tuple of SourceValue
        The values collected for the residual search, in file order.
    not_collected : tuple of NotCollected
    sequestrations : tuple of Sequestration
        Each reason that the instance must be sequestered.
    read_as_latin_1 : tuple of ElementPath
        In file order, the path of each value, removed or replaced, that was
        read as ISO 8859-1, being text outside ISO 646 where no Specific
        Character Set applies, so that its writer knows; ``()`` if there is
        none, or the instance must be sequestered.
    registered_uids : tuple of ElementPath
        In file order, the path of each UI value with a UID that the pinned
        tables register, which is left out of ``source_values``, since it
        names no one and stays wherever it is kept; ``()`` if there is none,
        or the instance must be sequestered.
    """

    edits: tuple[Edit, ...]
    source_values: tuple[SourceValue, ...]
    not_collected: tuple[NotCollected, ...]
    sequestrations: tuple[Sequestration, ...]
    read_as_latin_1: tuple[ElementPath, ...] = ()
    registered_uids: tuple[ElementPath, ...] = ()

    def __repr__(self) -> str:
        return (
            f"InstanceEdits(edits={len(self.edits)}, source_values="
            f"{len(self.source_values)}, not_collected={len(self.not_collected)}, "
            f"sequestrations={len(self.sequestrations)}, "
            f"read_as_latin_1={len(self.read_as_latin_1)}, "
            f"registered_uids={len(self.registered_uids)})"
        )


class _Sequester(Exception):
    def __init__(self, sequestration: Sequestration) -> None:
        super().__init__(sequestration)
        self.sequestration = sequestration


class _Reader:
    """Read planned values against the source, through the items that hold them.

    Each sequence is read once, however many of its items are reached.
    """

    def __init__(self, source: SourceEvidence, plan: InstancePlan) -> None:
        self._source = source
        self._planned = {element.path: element for element in plan.elements}
        self._sequences: dict[ElementPath, ElementValue] = {}
        root = source.dataset()
        self._holders: dict[tuple, tuple] = {(): (root, (), self._codecs(root, ()))}

    def _codecs(self, dataset, items, inherited=elements.DEFAULT_CODECS):
        try:
            return elements.dataset_codecs(
                dataset, inherited, items, source=self._source
            )
        except UndecodableElement as error:
            planned = self._planned.get(error.path)
            raise _Sequester(
                Sequestration(
                    error.path,
                    planned.action if planned is not None else "K",
                    "CS",
                    SequesterReason.UNSUPPORTED_CHARACTER_SET,
                )
            ) from None

    def sequence(self, path: ElementPath) -> ElementValue:
        """Return a sequence, read once, with its items."""
        if path not in self._sequences:
            dataset, ancestors, codecs = self._holder(path.items)
            self._sequences[path] = elements.read_element(
                dataset, path, codecs, ancestors, source=self._source
            )
        return self._sequences[path]

    def _holder(self, items: tuple) -> tuple:
        """Return the data set at ``items``, its ancestors, and its codecs."""
        if items not in self._holders:
            dataset, ancestors, codecs = self._holder(items[:-1])
            tag, index = items[-1]
            item = self.sequence(ElementPath(items[:-1], tag)).items[index]
            self._holders[items] = (
                item,
                (dataset, *ancestors),
                self._codecs(item, items, codecs),
            )
        return self._holders[items]

    def check_items(self, path: ElementPath) -> None:
        """Read a sequence's items and resolve each one's character set."""
        for index, _ in enumerate(self.sequence(path).items):
            self._holder((*path.items, (path.tag, index)))

    def read(self, path: ElementPath, latin_1: bool = False) -> ElementValue:
        dataset, ancestors, codecs = self._holder(path.items)
        return elements.read_element(
            dataset,
            path,
            codecs,
            ancestors,
            source=self._source,
            outside_repertoire_as_latin_1=latin_1,
        )


def _read_planned(
    reader: _Reader, element: ElementPlan
) -> tuple[ElementValue | None, NotCollected | None, bool]:
    """Read a planned value, or say why it is not collected.

    Text outside ISO 646 where no Specific Character Set applies is read as
    ISO 8859-1 where its rule removes or replaces it, as the maintainer
    decided on 1 October 2026; text to be cleaned cannot be decoded. The
    flag says whether the value was read as ISO 8859-1.
    """
    try:
        try:
            return reader.read(element.path), None, False
        except OutsideDefaultRepertoire:
            if Consumer.CLEANING in element.consumers:
                raise
            return reader.read(element.path, latin_1=True), None, True
    except UndecodableElement as error:
        if element.consumers & _NEEDS_VALUE or _takes_pseudonym(element):
            # A value that a reviewed dummy item is compared with is needed
            # by the D of the sequence that removes it.
            compared = Consumer.DUMMY_COMPARISON in element.consumers
            raise _Sequester(
                Sequestration(
                    element.path,
                    "D" if compared else element.action,
                    element.vr,
                    SequesterReason.UNDECODABLE,
                )
            ) from None
        return None, NotCollected(element.path, error.reason), False


def _text(value: ElementValue) -> str | bytes:
    """Return the value as :class:`~.residuals.SourceValue` takes it."""
    if len(value.values) == 1 and isinstance(value.values[0], bytes):
        return value.values[0]
    return "\\".join(str(each) for each in value.values)


def _kept_container(element: ElementPlan, container: bool) -> bool:
    return container and element.removed_with is None and element.action in DESCENDED


def _check_items(reader: _Reader, element: ElementPlan) -> None:
    """Sequester the instance unless a kept sequence's items can be read."""
    try:
        reader.check_items(element.path)
    except UndecodableElement:
        raise _Sequester(
            Sequestration(
                element.path, element.action, element.vr, SequesterReason.UNDECODABLE
            )
        ) from None


def _takes_pseudonym(element: ElementPlan) -> bool:
    """Return whether an element takes one of the subject's pseudonyms."""
    path = element.path
    return (
        element.removed_with is None
        and element.action in ("Z", "D")
        and not path.items
        and path.tag in PSEUDONYM_TAGS
    )


def _kind(element: ElementPlan, container: bool) -> EditKind:
    """Return what an element becomes, before any value is worked out.

    A sequence under K or U is kept as a container, its items edited
    element by element.
    """
    action = element.action
    if element.removed_with is not None or action == "X":
        kind = EditKind.REMOVE
    elif action == "K" or (container and action in DESCENDED):
        kind = EditKind.KEEP
    elif action == "C" or _takes_pseudonym(element):
        kind = EditKind.PENDING
    elif action == "Z":
        kind = EditKind.EMPTY
    else:
        kind = EditKind.REPLACE
    return kind


def _dummy(path: ElementPath, value: ElementValue, key: DeidKey) -> Edit:
    attribute = dictionary_attribute(path.tag)
    vm = attribute.vm if attribute is not None else "1"
    try:
        values = values_for_d(value.vr, vm, value.values, key)
    except NoDummyValueError:
        raise _Sequester(
            Sequestration(path, "D", value.vr, SequesterReason.NO_DUMMY_VALUE)
        ) from None
    return Edit(path, "D", EditKind.REPLACE, values)


def _uids(path: ElementPath, value: ElementValue, key: DeidKey) -> Edit:
    attribute = dictionary_attribute(path.tag)
    role = load_uid_roles().role(attribute.tag if attribute else path.tag)
    replaced = [
        transform_uid(key, role, str(uid))
        if normalise_uid(str(uid))
        else (str(uid), UIDOutcome.RETAINED)
        for uid in value.values
    ]
    return Edit(
        path,
        "U",
        EditKind.REPLACE,
        tuple(uid for uid, _ in replaced),
        tuple(outcome for _, outcome in replaced),
    )


def _pseudonym(
    path: ElementPath, action: str, key: DeidKey, identity: SubjectIdentity
) -> Edit:
    pseudonym = patient_pseudonym(key, identity)
    if path.tag == "(0010,0010)":
        value = pseudonym.patients_name
    else:
        value = pseudonym.patient_id
    return Edit(path, action, EditKind.REPLACE, (value,))


def _edit(
    element: ElementPlan,
    container: bool,
    value: ElementValue | None,
    key: DeidKey,
    identity: SubjectIdentity | None,
) -> Edit:
    """Return the edit of an element whose needed value, if any, is read."""
    kind = _kind(element, container)
    path = element.path
    if identity is not None and _takes_pseudonym(element):
        return _pseudonym(path, element.action, key, identity)
    if kind is not EditKind.REPLACE:
        return Edit(
            element.path, element.action, kind, removed_with=element.removed_with
        )
    if container:  # a reviewed dummy sequence, given its items later
        return Edit(path, element.action, kind)
    assert value is not None  # every U and D leaf has a consumer that reads it
    if element.action == "D":
        return _dummy(element.path, value, key)
    return _uids(element.path, value, key)


def _compared_text(element: ElementPlan, value: ElementValue) -> str:
    """Return a value that a reviewed dummy item is compared with, as text."""
    if not all(isinstance(each, str) for each in value.values):
        raise _Sequester(
            Sequestration(element.path, "D", element.vr, SequesterReason.UNDECODABLE)
        )
    return "\\".join(str(each) for each in value.values)


def _with_items(edit: Edit, compared: dict[int, dict[str, str]]) -> Edit:
    """Give a reviewed dummy sequence's edit its items (D-021)."""
    source_items = [compared[index] for index in sorted(compared)]
    items = items_for_d(edit.path.tag, source_items)
    return dataclasses.replace(edit, items=items)


class _Gathered:
    """The values read for an instance's edits, and what reading them found."""

    def __init__(self) -> None:
        self.collected: list[SourceValue] = []
        self.missing: list[NotCollected] = []
        self.latin_1: list[ElementPath] = []
        self.registered: list[ElementPath] = []
        # The source values that each reviewed dummy sequence's items are
        # compared with, by item and tag.
        self.compared: dict[ElementPath, dict[int, dict[str, str]]] = {}

    def read(self, reader: _Reader, element: ElementPlan) -> ElementValue | None:
        """Read a planned value, collect it, and keep it for comparing."""
        value, not_read, as_latin_1 = _read_planned(reader, element)
        if not_read is not None:
            self.missing.append(not_read)
        if as_latin_1:
            self.latin_1.append(element.path)
        if value is None:
            return None
        if (
            element.removed_with is not None
            and Consumer.DUMMY_COMPARISON in element.consumers
        ):
            index = element.path.items[-1][1]
            item = self.compared.setdefault(element.removed_with, {})
            item.setdefault(index, {})[element.path.tag] = _compared_text(
                element, value
            )
        if Consumer.RESIDUAL_COLLECTION in element.consumers:
            searched = self._unregistered(element.path, value)
            try:
                if searched is not None:
                    self.collected.append(
                        SourceValue(
                            element.path, searched.vr, _text(searched), searched.codecs
                        )
                    )
            except ValueError:
                self.missing.append(
                    NotCollected(element.path, "could not be collected")
                )
        return value

    def _unregistered(
        self, path: ElementPath, value: ElementValue
    ) -> ElementValue | None:
        """Leave out of a UI value each UID that the pinned tables register.

        Such a UID names no one, and stays wherever it is kept, so searching
        for it would find it in every instance. The path is recorded, and
        None returned where no other UID is left to collect.
        """
        if value.vr != "UI":
            return value
        registered = well_known_uids()
        left = tuple(
            uid for uid in value.values if normalise_uid(str(uid)) not in registered
        )
        if len(left) == len(value.values):
            return value
        self.registered.append(path)
        if not any(normalise_uid(str(uid)) for uid in left):
            return None
        return dataclasses.replace(value, values=left)

    def result(
        self, found: list[Edit], reviewed: dict[ElementPath, int]
    ) -> InstanceEdits:
        """Return the edits, each reviewed dummy sequence's with its items."""
        for path, position in reviewed.items():
            found[position] = _with_items(found[position], self.compared.get(path, {}))
        return InstanceEdits(
            tuple(found),
            tuple(self.collected),
            tuple(self.missing),
            (),
            tuple(self.latin_1),
            tuple(self.registered),
        )


def edit_instance(
    source: SourceEvidence,
    plan: InstancePlan,
    key: DeidKey,
    identity: SubjectIdentity | None = None,
) -> InstanceEdits:
    """Return what each element of a planned data set becomes.

    Parameters
    ----------
    source : SourceEvidence
        The source file that ``plan`` was made from.
    plan : InstancePlan
        Its plan, from :func:`~pymedphys._dicom.deidentify.walker.plan_instance`.
    key : DeidKey
        The run's key, for keyed replacement UIDs and pseudonyms.
    identity : SubjectIdentity, optional
        The subject's identity, as the run resolves it, for the pseudonyms
        of Patient's Name and Patient ID. Without one, their edits are
        pending.

    Returns
    -------
    InstanceEdits
        With no edits or values if the plan, or reading a value it needs,
        sequesters the instance.
    """
    if plan.sequestrations:
        return InstanceEdits((), (), (), plan.sequestrations)
    found: list[Edit] = []
    gathered = _Gathered()
    # Each reviewed dummy sequence's edit, by its position in ``found``.
    reviewed: dict[ElementPath, int] = {}
    try:
        reader = _Reader(source, plan)
        for element in plan.elements:
            container = source.element(element.path).items is not None
            if _kept_container(element, container):
                _check_items(reader, element)
            value = gathered.read(reader, element) if element.consumers else None
            edit = _edit(element, container, value, key, identity)
            if container and edit.kind is EditKind.REPLACE:
                reviewed[edit.path] = len(found)
            found.append(edit)
    except _Sequester as raised:
        return InstanceEdits((), (), (), (raised.sequestration,))
    return gathered.result(found, reviewed)
