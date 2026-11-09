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

"""Graphic annotations under the Clean Graphics Option, kept as a reviewer decides.

Table E.1-1 gives Graphic Annotation Sequence (0070,0001) D, and C under the
Clean Graphics Option. Only the softcopy Presentation State IODs define it,
and they make it Type 1 in the Graphic Annotation Module, so its D, which a
sequence has no dummy value for, sequesters a Presentation State that holds
it (D-021). Under the option, with a reviewed annotations list
(:mod:`.reviewed_annotations`), :func:`annotation_plan` gives the walker
what to do with each of its items in place, as the maintainer chose on
7 November 2026 (D-062):

- an annotation that the list keeps is written as it was received, but for
  its UIDs and private data elements: each of its standard elements other
  than a UI takes K, and each UI, such as the Referenced SOP Instance UID of
  the image that it is drawn on, takes its own rule, which replaces it as
  the image's own is replaced, as each private element takes its own;
- an annotation that the list removes is removed on its own, with
  everything in it, as an item of Content Sequence is under Clean
  Structured Content (:mod:`.removed_items`);
- an annotation that the list has no decision on, or keeps but whose text
  echoes one of its instance's identifiers, is held for review: its
  elements take their own rules, which write a dummy value in place of its
  text in the staged file, and its instance is held, so it is not released;
- the sequence itself takes K wherever an item is not removed. Where the
  list removes every item, the sequence takes its rule, the Basic Profile's
  D, so its instance is sequestered, since the Type 1 sequence would be
  left with no item.

Without the option, without a list, or where an item cannot be read, the
sequence takes its rule, as before (D-041).
"""

from __future__ import annotations

import dataclasses
import types
from collections.abc import Mapping, Sequence

from pymedphys._imports import pydicom

from .content_items import ContentItemPlan
from .file_layout import ElementPath
from .iods import IOD
from .policy import CLEAN_GRAPHICS, Policy
from .removed_items import Item
from .reviewed_annotations import (
    Outcome,
    ReviewedAnnotation,
    ReviewedAnnotations,
    annotation_digest,
    annotation_texts,
    review_annotation,
)
from .source import SourceEvidence

GRAPHIC_ANNOTATION_SEQUENCE = "(0070,0001)"
_KEPT = "K"
# Patient ID, Issuer of Patient ID, and Other Patient IDs, which a kept
# annotation's text is checked for, beside every person name, as descriptor
# cleaning checks a kept descriptor (D-009).
_IDENTIFIER_TAGS = frozenset({0x00100020, 0x00100021, 0x00101000})

# How Clean Graphics cleans Graphic Annotation Sequence, as the conformance
# statement gives it.
METHOD = (
    "Only the softcopy Presentation State IODs define it, as Type 1, so a "
    "run gives it its Basic Profile action, D, which sequesters a "
    "Presentation State that holds it, unless the run is given the "
    "custodian's reviewed annotations list. With the list, each item, one "
    "annotation of text objects and graphic objects, is cleaned by the "
    "reviewer's decision on it, found by a digest of its content other than "
    "its UIDs: an annotation that the list keeps is written as it was "
    "received, but for its UIDs, which are replaced as the instance's own "
    "are, and its private data elements, which take their own actions; one "
    "that the list removes is removed, with everything in it; and "
    "one that the list has no decision on, or keeps but whose text holds one "
    "of the instance's patient or other person identifiers, holds its "
    "instance for review, with its text and a drawing of its graphics in "
    "the QC pack, from which the reviewer decides on it. Where the list "
    "removes every item, the sequence takes its Basic Profile action, so "
    "the instance is sequestered, since the Type 1 sequence would be left "
    "with no item. The reviewer decides whether an annotation encodes "
    "information that the Profile and the selected options remove, as "
    "PS3.15 E.3.3 requires the option to remove, so a released instance "
    "meets the option."
)


@dataclasses.dataclass(frozen=True, repr=False)
class AnnotationMaterial:
    """What the run decided for one annotation, for the confidential QC pack.

    Attributes
    ----------
    path : ElementPath
        Its sequence's element, whose ``items`` end with the annotation's
        item; the element is Graphic Annotation Sequence itself.
    digest : str
        Its :func:`~.reviewed_annotations.annotation_digest`.
    texts : tuple of str
        Its text values (:func:`~.reviewed_annotations.annotation_texts`).
    result : ReviewedAnnotation
        What is written for it.
    item : pydicom.Dataset
        The annotation's item as received, which the QC pack draws.
    """

    path: ElementPath
    digest: str
    texts: tuple[str, ...]
    result: ReviewedAnnotation
    item: pydicom.Dataset

    def __repr__(self) -> str:
        return (
            f"AnnotationMaterial(path={str(self.path)!r}, "
            f"outcome={self.result.outcome.value!r})"
        )


@dataclasses.dataclass(frozen=True)
class AnnotationPlan:
    """What Clean Graphics does with one instance's graphic annotations.

    Attributes
    ----------
    actions : mapping of ElementPath to str
        The action of each element that takes one in place of its rule's:
        K for the sequence, where an item is not removed, and for each
        element but a UI of each kept annotation.
    removed_items : frozenset of tuple of (str, int)
        Each annotation that the list removes, by the items tuple of a path
        that ends with it.
    material : tuple of AnnotationMaterial
        Each annotation, in order, with what is written for it.
    """

    actions: Mapping[ElementPath, str] = dataclasses.field(
        default_factory=lambda: types.MappingProxyType({})
    )
    removed_items: frozenset[Item] = frozenset()
    material: tuple[AnnotationMaterial, ...] = ()

    @property
    def held(self) -> tuple[AnnotationMaterial, ...]:
        """Return each annotation that is held for review."""
        return tuple(
            each for each in self.material if each.result.outcome is Outcome.HELD
        )


NO_ANNOTATIONS = AnnotationPlan()


def annotation_plan(
    source: SourceEvidence,
    dataset: pydicom.Dataset,
    policy: Policy,
    iod: IOD,
    reviewed: ReviewedAnnotations | None,
    identifiers: Sequence[str] = (),
) -> AnnotationPlan:
    """Return what the walker does with an instance's graphic annotations.

    Parameters
    ----------
    source : SourceEvidence
        The instance's source.
    dataset : pydicom.Dataset
        Its data set, as ``source`` reads it, with its character sets.
    policy : Policy
        The run's policy.
    iod : IOD
        The instance's IOD.
    reviewed : ReviewedAnnotations or None
        The reviewed annotations list, if the run was given one.
    identifiers : sequence of str, optional
        Identifiers that a kept annotation's text is checked for echoes of,
        beside those that the instance holds (:func:`dataset_identifiers`),
        so that one that echoes them is held, and its text written as a
        dummy value, from the first.

    Returns
    -------
    AnnotationPlan
        Empty without Clean Graphics, without ``reviewed``, where the IOD
        does not define the sequence at the top level, where the instance
        does not hold it, where an item cannot be read, or where the list
        removes every item; otherwise as the module describes.
    """
    sequence = ElementPath((), GRAPHIC_ANNOTATION_SEQUENCE)
    if (
        CLEAN_GRAPHICS not in policy.options
        or reviewed is None
        or not any(
            definition.tag == GRAPHIC_ANNOTATION_SEQUENCE and not definition.path
            for definition in iod.definitions
        )
    ):
        return NO_ANNOTATIONS
    paths = list(source.paths())
    if sequence not in paths:
        return NO_ANNOTATIONS
    try:
        items = list(dataset[0x00700001].value)
        digests = [annotation_digest(item) for item in items]
        texts = [annotation_texts(item) for item in items]
    except (KeyError, TypeError, ValueError, UnicodeError, AttributeError):
        return NO_ANNOTATIONS
    try:
        echoed = (*identifiers, *dataset_identifiers(dataset))
    except (TypeError, ValueError, UnicodeError, AttributeError):
        return NO_ANNOTATIONS
    results = [
        review_annotation(digest, text, reviewed, echoed)
        for digest, text in zip(digests, texts)
    ]
    if all(result.outcome is Outcome.REMOVED for result in results):
        return NO_ANNOTATIONS
    actions: dict[ElementPath, str] = {sequence: _KEPT}
    removed: set[Item] = set()
    for index, result in enumerate(results):
        item: Item = ((GRAPHIC_ANNOTATION_SEQUENCE, index),)
        if result.outcome is Outcome.REMOVED:
            removed.add(item)
        elif result.outcome is Outcome.KEPT:
            for path in paths:
                if (
                    path.items[:1] == item
                    and source.element(path).vr != "UI"
                    and not _private(path.tag)
                ):
                    actions[path] = _KEPT
    material = tuple(
        AnnotationMaterial(
            ElementPath(((GRAPHIC_ANNOTATION_SEQUENCE, index),), sequence.tag),
            digest,
            text,
            result,
            item,
        )
        for index, (digest, text, result, item) in enumerate(
            zip(digests, texts, results, items)
        )
    )
    return AnnotationPlan(types.MappingProxyType(actions), frozenset(removed), material)


def _private(tag: str) -> bool:
    """Return whether a tag, as ``(gggg,eeee)``, is in an odd, private group."""
    return int(tag[1:5], 16) % 2 == 1


def dataset_identifiers(dataset: pydicom.Dataset) -> tuple[str, ...]:
    """Return the person names and patient identifiers that a data set holds.

    Each value of every element whose VR is PN, and of Patient ID, Issuer of
    Patient ID, and Other Patient IDs, at any depth outside Graphic
    Annotation Sequence, without padding and leaving out empty values.
    """
    found: list[str] = []
    for element in dataset:
        if element.tag == 0x00700001:
            continue
        if element.VR == "SQ":
            for item in element.value or ():
                found.extend(dataset_identifiers(item))
        elif element.VR == "PN" or element.tag in _IDENTIFIER_TAGS:
            values = element.value
            if values is None:
                continue
            if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
                values = [values]
            found.extend(
                text
                for text in (str(value).rstrip(" \x00") for value in values)
                if text
            )
    return tuple(found)


def with_annotations(
    content_items: ContentItemPlan, annotations: AnnotationPlan
) -> ContentItemPlan:
    """Return the walker's plan of content items with the annotations' added.

    The two never name the same element: Clean Structured Content cleans no
    sequence that a Presentation State's annotations are in.
    """
    if not annotations.actions:
        return content_items
    actions = dict(content_items.actions)
    if set(actions) & set(annotations.actions):
        raise ValueError("an element cannot be both a content item and an annotation")
    actions.update(annotations.actions)
    return dataclasses.replace(
        content_items,
        actions=types.MappingProxyType(actions),
        removed_items=content_items.removed_items | annotations.removed_items,
        annotations=frozenset(annotations.actions),
    )
