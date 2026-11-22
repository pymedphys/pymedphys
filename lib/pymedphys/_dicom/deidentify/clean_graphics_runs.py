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

"""The runs and expectations of the check of the Clean Graphics Option on
public human DICOM (:mod:`.clean_graphics_check`).

:func:`run_instance` gives an instance to de-identification transforms as a
run does, under Retain Longitudinal Temporal Information with Modified
Dates, alone and with Clean Graphics, and gives each file that a transform
writes to a release gate, with the instance's own evidence as its
subject's. The Basic Profile alone would sequester a Presentation State for
its creation date (D-020). A Presentation State is run without a reviewed
annotations list (D-062), and with lists built in memory from its own
annotations, as a reviewer would decide on them (:data:`RUNS`): an empty
list; each annotation kept; each annotation kept and each set of
annotations that a display shows together kept too, by the digests of the
sets that a first pass holds, as a reviewer takes them from the QC pack;
each annotation removed; each annotation that holds a text object removed,
the rest and their sets kept; and, where keeping them all holds an
annotation for echoing an identifier, those removed, the rest and their
sets kept. An image is run without a list, and its two written files are
compared.

For each run, :func:`instance_summary` counts the outcome and its reasons,
as the release report names them, what is decided for each annotation and
each set, and what the written file holds. :func:`evaluate` tests the runs
against what Table E.1-1 and the design give the option
(:data:`EXPECTATIONS`): Graphic Annotation Sequence takes D without a list,
which sequesters a Presentation State, since the Type 1 sequence has no
dummy value (D-021); with a list, each annotation is kept as received but
for its UIDs, removed, or held, as the list decides, and kept annotations
shown together need a decision on them together; curves are removed, as
under the Basic Profile; and every file written under the option claims it
(D-041). A run that raises is counted by the exception's type and place,
never its message.

The annotations' digests, which the reviewed annotations list keeps
confidential, and the written files stay in memory: no summary holds them.
"""

from __future__ import annotations

import collections
import dataclasses
import io
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from pymedphys._imports import pydicom

from . import policy
from .face_validation import crash_site
from .graphic_annotations import (
    AnnotationMaterial,
    ImageReference,
    annotation_images,
    enclosing_images,
    shown_together,
)
from .instance_transform import InstanceTransform, ReleaseGate
from .keys import DeidKey
from .midi_benchmark_errors import uid_name
from .midi_benchmark_graphics import graphics_of
from .references import InstanceRecord
from .release_report import held_for_review, sequestration_reason
from .reviewed_annotations import (
    Held,
    Outcome,
    Review,
    ReviewedAnnotation,
    ReviewedAnnotations,
    annotation_digest,
)
from .run_results import HoldForReview, Release, Sequestered, Transformed
from .source import read_source

GRAYSCALE_SOFTCOPY_PRESENTATION_STATE = "1.2.840.10008.5.1.4.1.1.11.1"
PSEUDO_COLOR_SOFTCOPY_PRESENTATION_STATE = "1.2.840.10008.5.1.4.1.1.11.3"
PRESENTATION_STATES = frozenset(
    {GRAYSCALE_SOFTCOPY_PRESENTATION_STATE, PSEUDO_COLOR_SOFTCOPY_PRESENTATION_STATE}
)
CLEAN_GRAPHICS_CODE = "113103"

# The runs, by the names that the summary gives them, and what each is.
RUNS: Mapping[str, str] = {
    "modified_dates": "Modified Dates alone, without a list",
    "no_list": "Clean Graphics, without a list",
    "empty_list": "Clean Graphics, an empty list",
    "each_kept": "Clean Graphics, each annotation kept",
    "each_and_sets_kept": "Clean Graphics, each annotation and each set kept",
    "each_removed": "Clean Graphics, each annotation removed",
    "text_removed": (
        "Clean Graphics, each annotation with a text object removed, the rest "
        "and their sets kept"
    ),
    "echoes_removed": (
        "Clean Graphics, each annotation held for echoing an identifier "
        "removed, the rest and their sets kept"
    ),
}
# The runs without a list, which are an image's runs.
WITHOUT_A_LIST = ("modified_dates", "no_list")
# The reason that the walker gives for sequestering a Presentation State
# whose Graphic Annotation Sequence takes D, as the release report names it.
NO_DUMMY_VALUE = "walker: no-dummy-value at (0070,0001), D"
# The tags in which a file written with Clean Graphics may differ from one
# written without it: De-identification Method and its Code Sequence.
MARKERS = ("(0012,0063)", "(0012,0064)")
# What no file written under the option may hold: three of its four rows of
# Table E.1-1, as midi_benchmark_graphics names them, and an overlay that may
# lie in Pixel Data.
REMOVED_GRAPHICS = frozenset(
    {"curve_data", "overlay_data", "overlay_comments", "overlay_in_pixel_data"}
)

_KEY = DeidKey(bytes(range(32)))
_BASELINE = (policy.MODIFIED_DATES,)
_OPTION = (policy.MODIFIED_DATES, policy.CLEAN_GRAPHICS)
_GRAPHIC_ANNOTATION_SEQUENCE = 0x00700001
_METHOD_CODES = 0x00120064
# A first pass, then a second with the decisions on the sets that it held.
_PASSES = 2
# Why a kept annotation can be held for itself, whatever the list decides on
# the annotations shown with it: for its text, or for its drawing.
_HELD_FOR_ITSELF = frozenset({Held.ECHOES_IDENTIFIER, Held.NOT_DRAWN})
_HELD_CODES = frozenset(
    f"annotations: {reason.value}"
    for reason in (Held.NOT_REVIEWED_TOGETHER, *_HELD_FOR_ITSELF)
)


@dataclasses.dataclass(frozen=True)
class _Annotations:
    """A Presentation State's annotations, as the engine reads them.

    Their digests are what a reviewed annotations list decides by, and stay
    in memory: no summary holds them.
    """

    digests: tuple[str, ...]
    with_text: tuple[bool, ...]
    images: tuple[tuple[ImageReference, ...] | None, ...]

    def sets(self, shown: Sequence[int]) -> tuple[tuple[int, ...], ...]:
        """Each set of two or more of the annotations ``shown`` that a
        display shows together, as the engine decides on them: all of them
        where any one's images are not known."""
        shown = list(shown)
        found = shown_together([self.images[index] for index in shown])
        groups = (tuple(range(len(shown))),) if found is None else found
        return tuple(
            tuple(shown[place] for place in each) for each in groups if len(each) > 1
        )


@dataclasses.dataclass(frozen=True)
class _Written:
    """What a transform wrote, in memory: the digests of the annotations
    that its file holds, in order, never leave the check."""

    data: bytes
    digests: tuple[str, ...]
    text_objects: int
    graphic_objects: int
    graphics: frozenset[str]
    nested_graphics: int
    claims_clean_graphics: bool


@dataclasses.dataclass
class _Ran:
    """One run of one instance."""

    outcome: str
    reasons: collections.Counter[str] = dataclasses.field(
        default_factory=collections.Counter
    )
    passes: int = 0
    decisions: collections.Counter[str] | None = None
    annotations: dict[int, ReviewedAnnotation] = dataclasses.field(default_factory=dict)
    sets: list[ReviewedAnnotation] = dataclasses.field(default_factory=list)
    written: _Written | None = None

    def survivors(self, count: int) -> list[int] | None:
        """The annotations, of ``count``, that the run did not remove, or
        None where it did not decide on each of them."""
        if sorted(self.annotations) != list(range(count)):
            return None
        return [
            index
            for index in range(count)
            if self.annotations[index].outcome is not Outcome.REMOVED
        ]

    def held_for_itself(self) -> frozenset[int]:
        return frozenset(
            index
            for index, result in self.annotations.items()
            if result.held_because in _HELD_FOR_ITSELF
        )

    def kept_as_received(self, source: _Annotations) -> int:
        """How many kept annotations the written file holds as received but
        for their UIDs, by their digests, which leave out UIDs."""
        survivors = self.survivors(len(source.digests))
        written = self.written
        if survivors is None or written is None:
            return 0
        if len(written.digests) != len(survivors):
            return 0
        return sum(
            1
            for place, index in enumerate(survivors)
            if self.annotations[index].outcome is Outcome.KEPT
            and written.digests[place] == source.digests[index]
        )


@dataclasses.dataclass
class InstanceRuns:
    """An instance's runs, in memory, and what it holds, by counts.

    Attributes
    ----------
    label : str
        Its name in the summary, which names no file.
    sop_class : str
        Its SOP Class UID.
    holds : dict
        Counts of the graphics that it holds, and no value.
    annotations : _Annotations or None
        A Presentation State's annotations; None for an image.
    runs : dict of str to _Ran
        Each of its runs, by the name that :data:`RUNS` gives it.
    crashed : str or None
        Where reading it raised, by the exception's type and place, if it
        did.
    """

    label: str
    sop_class: str
    holds: dict[str, Any]
    annotations: _Annotations | None
    runs: dict[str, _Ran]
    crashed: str | None = None

    @property
    def presentation_state(self) -> bool:
        """Whether it is a softcopy Presentation State."""
        return self.sop_class in PRESENTATION_STATES


def run_instance(label: str, sop_class: str, data: bytes) -> InstanceRuns:
    """Run one instance, a Presentation State or an image, as the module
    describes."""
    try:
        dataset = pydicom.dcmread(io.BytesIO(data), stop_before_pixels=True)
        annotations = _annotations(data) if sop_class in PRESENTATION_STATES else None
        holds = _holds(dataset, annotations)
    # Anything that reading the instance raises is counted, by where; its
    # message, which could quote a value, is dropped.
    except Exception as error:  # pylint: disable = broad-exception-caught
        return InstanceRuns(label, sop_class, {}, None, {}, crashed=crash_site(error))
    ran = InstanceRuns(label, sop_class, holds, annotations, {})
    if annotations is None:
        for name in WITHOUT_A_LIST:
            ran.runs[name] = _run(data, name, None, None)
        return ran
    count = len(annotations.digests)
    plans: list[tuple[str, dict[int, Review] | None]] = [
        ("modified_dates", None),
        ("no_list", None),
        ("empty_list", {}),
        ("each_kept", dict.fromkeys(range(count), Review.KEEP)),
        ("each_and_sets_kept", dict.fromkeys(range(count), Review.KEEP)),
        ("each_removed", dict.fromkeys(range(count), Review.REMOVE)),
        (
            "text_removed",
            {
                index: Review.REMOVE if text else Review.KEEP
                for index, text in enumerate(annotations.with_text)
            },
        ),
    ]
    for name, decisions in plans:
        ran.runs[name] = _run(data, name, annotations, decisions)
    echoes = {
        index
        for index, result in ran.runs["each_and_sets_kept"].annotations.items()
        if result.held_because is Held.ECHOES_IDENTIFIER
    }
    if echoes:
        decisions = {
            index: Review.REMOVE if index in echoes else Review.KEEP
            for index in range(count)
        }
        ran.runs["echoes_removed"] = _run(
            data, "echoes_removed", annotations, decisions
        )
    return ran


def _annotations(data: bytes) -> _Annotations:
    """A Presentation State's annotations, read as the transform reads them."""
    dataset = read_source(data).dataset()
    element = dataset.get(_GRAPHIC_ANNOTATION_SEQUENCE)
    items = list(element.value) if element is not None and element.value else []
    enclosing = enclosing_images(dataset)
    return _Annotations(
        tuple(annotation_digest(item) for item in items),
        tuple(bool(item.get("TextObjectSequence")) for item in items),
        tuple(annotation_images(item, enclosing) for item in items),
    )


def _holds(
    dataset: pydicom.Dataset, annotations: _Annotations | None
) -> dict[str, Any]:
    """Counts of the graphics that an instance holds, and no value."""
    holds: dict[str, Any] = {
        "graphics": sorted(graphics_of(dataset)),
        "curve_groups": len(
            {
                tag.group
                for tag in dataset.keys()
                if 0x5000 <= tag.group <= 0x501E and tag.group % 2 == 0 and tag.element
            }
        ),
    }
    if annotations is None:
        return holds
    element = dataset.get(_GRAPHIC_ANNOTATION_SEQUENCE)
    items = list(element.value) if element is not None and element.value else []
    sets = annotations.sets(range(len(annotations.digests)))
    holds.update(
        {
            "graphic_annotations": len(items),
            "with_text_objects": sum(annotations.with_text),
            "text_objects": _objects(items, "TextObjectSequence"),
            "graphic_objects": _objects(items, "GraphicObjectSequence"),
            "compound_graphics": _objects(items, "CompoundGraphicSequence"),
            "sets_shown_together": len(sets),
            "set_sizes": sorted(len(each) for each in sets),
        }
    )
    return holds


def _objects(items: Iterable[pydicom.Dataset], keyword: str) -> int:
    return sum(len(item.get(keyword) or ()) for item in items)


def _run(
    data: bytes,
    name: str,
    annotations: _Annotations | None,
    decisions: Mapping[int, Review] | None,
) -> _Ran:
    """Run an instance once, or twice where the run keeps the sets that its
    first pass holds, and count what the run decides and writes."""
    options = _BASELINE if name == "modified_dates" else _OPTION
    keeps_sets = name in ("each_and_sets_kept", "text_removed", "echoes_removed")
    try:
        reviewed = None
        counted: collections.Counter[str] | None = None
        if decisions is not None and annotations is not None:
            reviewed = ReviewedAnnotations.empty()
            counted = collections.Counter()
            for index, review in decisions.items():
                reviewed.record(annotations.digests[index], review)
                counted[review.value] += 1
        passes = 1
        result = _transform(options, reviewed)(data, InstanceRecord.from_file(data))
        while keeps_sets and reviewed is not None and counted is not None:
            held = sorted(
                {
                    each.digest
                    for each in _materials(result)
                    if each.together
                    and each.result.held_because is Held.NOT_REVIEWED_TOGETHER
                    and reviewed.get(each.digest) is None
                }
            )
            if not held or passes == _PASSES:
                break
            for digest in held:
                reviewed.record(digest, Review.KEEP)
            counted["keep together"] += len(held)
            passes += 1
            result = _transform(options, reviewed)(data, InstanceRecord.from_file(data))
        ran = _outcome(result)
        ran.passes = passes if reviewed is not None else 0
        ran.decisions = counted
        for each in _materials(result):
            if each.together:
                ran.sets.append(each.result)
            else:
                ran.annotations[each.path.items[-1][1]] = each.result
        return ran
    # Anything that a run raises is counted, by where; its message, which
    # could quote a value, is dropped.
    except Exception as error:  # pylint: disable = broad-exception-caught
        return _Ran(f"raised: {crash_site(error)}")


def _transform(
    options: Sequence[str], reviewed: ReviewedAnnotations | None
) -> InstanceTransform:
    return InstanceTransform(
        policy.compose_custom_policy(options),
        _KEY,
        reviewed_annotations=reviewed,
        unvalidated_policy=True,
    )


def _materials(result: Transformed | Sequestered) -> list[AnnotationMaterial]:
    return [each for each in result.qc if isinstance(each, AnnotationMaterial)]


def _outcome(result: Transformed | Sequestered) -> _Ran:
    """The run's outcome: the transform's sequestration, or the release
    gate's decision on the written file, with the instance's own evidence as
    its subject's, and the reasons, as the release report names them."""
    if isinstance(result, Sequestered):
        return _Ran("sequestered", _sequestering(result.reasons))
    written = _written(result.data)
    decision = ReleaseGate()(result.data, result.evidence, (result.evidence,))
    if isinstance(decision, Release):
        return _Ran("released", written=written)
    if isinstance(decision, HoldForReview):
        held = held_for_review([decision.reasons])
        reasons = collections.Counter(f"{each.stage}: {each.code}" for each in held)
        return _Ran("held", reasons, written=written)
    return _Ran("sequestered", _sequestering(decision.reasons), written=written)


def _sequestering(reasons: Iterable[object]) -> collections.Counter[str]:
    counted: collections.Counter[str] = collections.Counter()
    for cause in reasons:
        found = sequestration_reason(cause)
        text = f"{found.stage}: {found.code}"
        if found.attribute is not None:
            text += f" at {found.attribute}"
        if found.action is not None:
            text += f", {found.action}"
        counted[text] += 1
    return counted


def _written(data: bytes) -> _Written:
    """What a written file holds, by counts; its annotations' digests stay in
    memory."""
    dataset = pydicom.dcmread(io.BytesIO(data), stop_before_pixels=True)
    element = dataset.get(_GRAPHIC_ANNOTATION_SEQUENCE)
    items = list(element.value) if element is not None and element.value else []
    codes = dataset.get(_METHOD_CODES)
    claims = any(
        str(item.get("CodeValue", "")) == CLEAN_GRAPHICS_CODE
        and str(item.get("CodingSchemeDesignator", "")) == "DCM"
        for item in (codes.value if codes is not None and codes.value else ())
    )
    return _Written(
        data,
        tuple(annotation_digest(item) for item in items),
        _objects(items, "TextObjectSequence"),
        _objects(items, "GraphicObjectSequence"),
        graphics_of(dataset),
        _nested_graphics(dataset),
        claims,
    )


def _nested_graphics(dataset: pydicom.Dataset) -> int:
    """How many sequence items, at any depth, hold any of the graphics that
    the option removes."""
    count = 0
    for element in dataset:
        if element.VR != "SQ":
            continue
        for item in element.value or ():
            count += bool(graphics_of(item) & REMOVED_GRAPHICS)
            count += _nested_graphics(item)
    return count


def differences(first: bytes, second: bytes) -> dict[str, list[str]]:
    """The tags of the elements of two files, their file meta information's
    included, that one holds and the other does not, and that both hold
    with different values, at any depth below them."""
    datasets = [pydicom.dcmread(io.BytesIO(each)) for each in (first, second)]
    found: dict[str, list[str]] = {"added": [], "removed": [], "differ": []}
    for before, after in (
        (datasets[0].file_meta, datasets[1].file_meta),
        (datasets[0], datasets[1]),
    ):
        tags = set(before.keys()) | set(after.keys())
        for tag in sorted(tags):
            name = f"({tag.group:04X},{tag.element:04X})"
            if tag not in before:
                found["added"].append(name)
            elif tag not in after:
                found["removed"].append(name)
            elif before[tag] != after[tag]:
                found["differ"].append(name)
    return found


def _name(result: ReviewedAnnotation) -> str:
    if result.held_because is None:
        return result.outcome.value
    return f"{result.outcome.value}: {result.held_because.value}"


def instance_summary(ran: InstanceRuns) -> dict[str, Any]:
    """An instance's runs as the summary gives them: counts, codes, and tag
    numbers, and no value."""
    summary: dict[str, Any] = {
        "member": ran.label,
        "sop_class": uid_name(ran.sop_class),
        "holds": ran.holds,
        "runs": {},
    }
    if ran.crashed is not None:
        summary["crashed"] = ran.crashed
    for name, each in ran.runs.items():
        entry: dict[str, Any] = {"outcome": each.outcome}
        if each.reasons:
            entry["reasons"] = _sorted(each.reasons)
        if each.decisions is not None:
            entry["list"] = _sorted(each.decisions)
            entry["passes"] = each.passes
        if ran.annotations is not None and each.annotations:
            entry["annotations"] = _sorted(
                collections.Counter(
                    _name(result) for result in each.annotations.values()
                )
            )
        if ran.annotations is not None and each.sets:
            entry["sets"] = _sorted(
                collections.Counter(_name(result) for result in each.sets)
            )
        if each.written is not None:
            entry["written"] = _written_summary(each, ran.annotations)
        summary["runs"][name] = entry
    files = [ran.runs[name].written for name in WITHOUT_A_LIST if name in ran.runs]
    if not ran.presentation_state and len(files) == 2 and None not in files:
        first, second = (each.data for each in files if each is not None)
        summary["differences"] = differences(first, second)
    return summary


def _written_summary(ran: _Ran, source: _Annotations | None) -> dict[str, Any]:
    written = ran.written
    if written is None:
        return {}
    found: dict[str, Any] = {}
    if source is not None:
        found = {
            "graphic_annotations": len(written.digests),
            "text_objects": written.text_objects,
            "graphic_objects": written.graphic_objects,
            "kept_as_received": ran.kept_as_received(source),
        }
    return {
        **found,
        "graphics": sorted(written.graphics),
        "nested_graphics": written.nested_graphics,
        "claims_clean_graphics": written.claims_clean_graphics,
    }


EXPECTATIONS: tuple[str, ...] = (
    "Without a reviewed annotations list, each Presentation State is "
    "sequestered for its Graphic Annotation Sequence alone, under Modified "
    "Dates alone and with Clean Graphics.",
    "With an empty list, each annotation is held as not reviewed and each set "
    "of annotations shown together is held, so each Presentation State is "
    "held for review, for its annotations alone.",
    "With each annotation kept and no decision on those shown together, each "
    "annotation shown with others is held, and so is each set; an annotation "
    "shown alone is kept unless it is held for its own text or drawing.",
    "With each annotation and each set kept, each annotation is kept unless "
    "it is held for its own text or drawing, as the same ones are without the "
    "decisions on the sets; each kept one is written as received but for its "
    "UIDs, and the Presentation State is released unless one is held.",
    "With each annotation removed, each Presentation State is sequestered, "
    "since its Type 1 Graphic Annotation Sequence would be left with no item.",
    "With each annotation that holds a text object removed, and the rest and "
    "their sets kept, only those are removed; the rest are kept unless held "
    "for their own text or drawing, each kept one is written as received but "
    "for its UIDs, and the Presentation State is released unless one is "
    "held. One whose annotations all hold text is sequestered.",
    "Where keeping every annotation holds one for echoing an identifier, "
    "removing those, and keeping the rest and their sets, removes only them "
    "and holds none of the rest that keeping them all did not; each kept one "
    "is written as received but for its UIDs, and the Presentation State is "
    "released unless one is held.",
    "Each image is released with its curves removed, under Modified Dates "
    "alone and with Clean Graphics.",
    "Clean Graphics changes nothing in an image's written file but its "
    "De-identification Method (0012,0063) and De-identification Method Code "
    "Sequence (0012,0064).",
    "Every file written under Clean Graphics claims it, with DCM 113103, and "
    "holds no Curve Data, Overlay Data, Overlay Comments, or overlay in Pixel "
    "Data, at any depth; no file written under Modified Dates alone claims it.",
    "No run raised.",
)


def evaluate(members: Sequence[InstanceRuns]) -> list[tuple[str, list[str]]]:
    """Each expectation, with the labels of the instances for which it is
    not met, or ``no instance`` where it applies to none."""
    states = [each for each in members if each.presentation_state]
    images = [each for each in members if not each.presentation_state]
    tests: list[tuple[Sequence[InstanceRuns], Callable[[InstanceRuns], bool]]] = [
        (states, _sequestered_without_a_list),
        (states, _held_with_an_empty_list),
        (states, _held_without_the_sets),
        (states, _released_as_reviewed),
        (states, _sequestered_with_each_removed),
        (states, _released_without_the_text),
        (states, _released_without_the_echoes),
        (images, _curves_removed),
        (images, _only_the_markers_change),
        (members, _claimed_and_clean),
        (members, _nothing_raised),
    ]
    found = []
    for text, (scope, test) in zip(EXPECTATIONS, tests, strict=True):
        if not scope:
            found.append((text, ["no instance"]))
            continue
        found.append((text, [each.label for each in scope if not _met(test, each)]))
    return found


def _met(test: Callable[[InstanceRuns], bool], member: InstanceRuns) -> bool:
    return member.crashed is None and test(member)


def _sequestered(ran: _Ran | None) -> bool:
    return (
        ran is not None
        and ran.outcome == "sequestered"
        and ran.written is None
        and ran.reasons == collections.Counter({NO_DUMMY_VALUE: 1})
    )


def _sequestered_without_a_list(member: InstanceRuns) -> bool:
    return all(_sequestered(member.runs.get(name)) for name in WITHOUT_A_LIST)


def _held_with_an_empty_list(member: InstanceRuns) -> bool:
    ran, source = member.runs.get("empty_list"), member.annotations
    if ran is None or source is None or ran.written is None:
        return False
    count = len(source.digests)
    not_reviewed = ReviewedAnnotation(Outcome.HELD, Held.NOT_REVIEWED)
    return (
        ran.outcome == "held"
        and ran.reasons == collections.Counter({"annotations: not-reviewed": 1})
        and sorted(ran.annotations) == list(range(count))
        and all(result == not_reviewed for result in ran.annotations.values())
        and len(ran.sets) == len(source.sets(range(count)))
        and all(result.outcome is Outcome.HELD for result in ran.sets)
        and len(ran.written.digests) == count
    )


def _held_without_the_sets(member: InstanceRuns) -> bool:
    ran, source = member.runs.get("each_kept"), member.annotations
    if ran is None or source is None or ran.written is None:
        return False
    count = len(source.digests)
    sets = source.sets(range(count))
    together = {index for each in sets for index in each}
    if sorted(ran.annotations) != list(range(count)):
        return False
    for index, result in ran.annotations.items():
        if result.outcome is Outcome.REMOVED:
            return False
        if index in together and result.outcome is not Outcome.HELD:
            return False
        if result.outcome is Outcome.HELD and index not in together:
            if result.held_because not in _HELD_FOR_ITSELF:
                return False
    return (
        len(ran.sets) == len(sets)
        and all(result.outcome is Outcome.HELD for result in ran.sets)
        and _gated(ran)
        and len(ran.written.digests) == count
    )


def _released_as_reviewed(member: InstanceRuns) -> bool:
    ran, first = member.runs.get("each_and_sets_kept"), member.runs.get("each_kept")
    source = member.annotations
    if ran is None or first is None or source is None:
        return False
    count = len(source.digests)
    return (
        _kept_unless_held_for_itself(ran, range(count), source)
        and ran.held_for_itself() == first.held_for_itself()
    )


def _sequestered_with_each_removed(member: InstanceRuns) -> bool:
    return _sequestered(member.runs.get("each_removed"))


def _released_without_the_text(member: InstanceRuns) -> bool:
    ran, source = member.runs.get("text_removed"), member.annotations
    if ran is None or source is None:
        return False
    kept = [index for index, text in enumerate(source.with_text) if not text]
    return _removed(ran, kept, source)


def _released_without_the_echoes(member: InstanceRuns) -> bool:
    first, source = member.runs.get("each_and_sets_kept"), member.annotations
    if first is None or source is None:
        return False
    echoes = {
        index
        for index, result in first.annotations.items()
        if result.held_because is Held.ECHOES_IDENTIFIER
    }
    ran = member.runs.get("echoes_removed")
    if not echoes:
        return ran is None
    if ran is None:
        return False
    kept = [index for index in range(len(source.digests)) if index not in echoes]
    return _removed(ran, kept, source) and not (
        ran.held_for_itself() - first.held_for_itself()
    )


def _removed(ran: _Ran, kept: Sequence[int], source: _Annotations) -> bool:
    """Whether a run whose list removes every annotation but ``kept``, and
    keeps those and their sets, removes those alone and keeps the rest, as
    :func:`_kept_unless_held_for_itself` gives; or, where it keeps none,
    sequesters the instance."""
    if not kept:
        return _sequestered(ran)
    count = len(source.digests)
    removed = {
        index
        for index, result in ran.annotations.items()
        if result.outcome is Outcome.REMOVED
    }
    return removed == set(range(count)) - set(kept) and _kept_unless_held_for_itself(
        ran, kept, source
    )


def _kept_unless_held_for_itself(
    ran: _Ran, kept: Iterable[int], source: _Annotations
) -> bool:
    """Whether a run whose list keeps the annotations ``kept`` and their
    sets keeps each of them, unless it is held for its own text or drawing,
    keeps or holds as not drawn each set of them, writes them, and those
    kept as received, and releases the instance unless one is held."""
    kept = list(kept)
    if ran.written is None or ran.survivors(len(source.digests)) != kept:
        return False
    results = [ran.annotations[index] for index in kept]
    if any(
        result.outcome is not Outcome.KEPT
        and result.held_because not in _HELD_FOR_ITSELF
        for result in results
    ):
        return False
    sets_kept = len(ran.sets) == len(source.sets(kept)) and all(
        result.outcome is Outcome.KEPT or result.held_because is Held.NOT_DRAWN
        for result in ran.sets
    )
    received = ran.kept_as_received(source) == sum(
        result.outcome is Outcome.KEPT for result in results
    )
    return (
        sets_kept and received and len(ran.written.digests) == len(kept) and _gated(ran)
    )


def _gated(ran: _Ran) -> bool:
    """Whether the gate released a written file whose annotations are all
    kept or removed, and otherwise held it for its annotations alone."""
    held = any(result.outcome is Outcome.HELD for result in ran.annotations.values())
    if not held:
        return ran.outcome == "released"
    return (
        ran.outcome == "held" and bool(ran.reasons) and set(ran.reasons) <= _HELD_CODES
    )


def _curves_removed(member: InstanceRuns) -> bool:
    if "curve_data" not in member.holds.get("graphics", ()):
        return False
    for name in WITHOUT_A_LIST:
        ran = member.runs.get(name)
        if ran is None or ran.outcome != "released" or ran.written is None:
            return False
        if "curve_data" in ran.written.graphics or ran.written.nested_graphics:
            return False
    return True


def _only_the_markers_change(member: InstanceRuns) -> bool:
    first, second = (member.runs.get(name) for name in WITHOUT_A_LIST)
    if first is None or second is None:
        return False
    if first.written is None or second.written is None:
        return False
    return differences(first.written.data, second.written.data) == {
        "added": [],
        "removed": [],
        "differ": list(MARKERS),
    }


def _claimed_and_clean(member: InstanceRuns) -> bool:
    for name, ran in member.runs.items():
        if ran.written is None:
            continue
        if name == "modified_dates":
            if ran.written.claims_clean_graphics:
                return False
            continue
        if not ran.written.claims_clean_graphics:
            return False
        if ran.written.graphics & REMOVED_GRAPHICS or ran.written.nested_graphics:
            return False
    return True


def _nothing_raised(member: InstanceRuns) -> bool:
    return member.crashed is None and not any(
        ran.outcome.startswith("raised: ") for ran in member.runs.values()
    )


def _sorted(counter: Mapping[str, int]) -> dict[str, int]:
    return dict(sorted(counter.items()))
