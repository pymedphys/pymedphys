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

"""A case of classic CT, MR, and PET images, read as the Legacy Converted
Enhanced instances that :mod:`~.text_evaluation_lce` converts them to
(D-056).

:class:`ConvertedCase` reads each file of a :class:`~.text_evaluation_sources.DicomCase`
as a run reads it (:func:`~.text_evaluation_sources.decoded_frames`),
converts its images in memory, group by group
(:func:`~.text_evaluation_lce.convertible_groups`), and gives the frames of
each converted instance as a run reads that instance
(:func:`~.text_evaluation_sources.dicom_frames`), so that every frame's
stored values are those of the classic image it came from, and its IOD is
the Legacy Converted Enhanced one. Nothing is written to disk. An image
that cannot be converted is counted as skipped by
``conversion-refused/<code>``, its code as
:class:`~.text_evaluation_lce.ConversionRefused` gives it.
"""

from __future__ import annotations

import dataclasses
import pathlib
from collections.abc import Iterator

from .text_evaluation_frames import EvaluationFrame, EvaluationRefused
from .text_evaluation_lce import (
    ClassicImage,
    ConversionRefused,
    convert,
    convertible_groups,
    encode,
)
from .text_evaluation_sources import DicomCase, Skipped, decoded_frames, dicom_frames

# The most bytes of stored values in one converted instance, so that a
# runner holds a long series' images, its instance, and the instance's
# frames as read at once.
MAX_CONVERTED_BYTES = 1 << 30
_PIXEL_KEYWORDS = ("PixelData", "FloatPixelData", "DoubleFloatPixelData")


@dataclasses.dataclass(frozen=True)
class ConvertedCase:
    """A case of DICOM files whose classic CT, MR, and PET images are read
    as the Legacy Converted Enhanced instances that they convert to.

    Attributes
    ----------
    source : DicomCase
        The case as read unconverted; its collection, case, tier, and what
        is known of its text are the converted case's. It may hold no
        annotations, which name the classic instances.
    """

    source: DicomCase

    def __post_init__(self):
        if self.source.annotations is not None:
            raise EvaluationRefused("A converted case cannot carry annotations.")

    @property
    def collection(self) -> str:
        return self.source.collection

    @property
    def case(self) -> str:
        return self.source.case

    @property
    def subject(self) -> str | None:
        return self.source.subject

    @property
    def subject_namespace(self) -> str | None:
        return getattr(self.source, "subject_namespace", None)

    def read(self) -> Iterator[EvaluationFrame | Skipped]:
        images: list[ClassicImage] = []
        known = []
        for path in self.source.paths:
            try:
                data = pathlib.Path(path).read_bytes()
            except OSError:
                yield Skipped("not-opened")
                continue
            decoded = decoded_frames(data)
            del data
            if isinstance(decoded, Skipped):
                yield decoded
                continue
            dataset, _, frames = decoded
            for keyword in _PIXEL_KEYWORDS:
                if keyword in dataset:
                    del dataset[keyword]
            known.append(dataset)
            if len(frames) != 1:
                yield Skipped("conversion-refused/not-single-frame")
                continue
            images.append(ClassicImage(dataset, frames[0]))
        groups, refused = convertible_groups(images)
        for _, reason in refused:
            yield Skipped(f"conversion-refused/{reason}")
        number = 0
        for group in groups:
            found = _converted_frames(self.source, group, known, number)
            if isinstance(found, Skipped):
                yield from (found for _ in group)
                continue
            number += len(found)
            yield from found


def _converted_frames(
    source: DicomCase,
    group: list[ClassicImage],
    known: list,
    first: int,
) -> list[EvaluationFrame] | Skipped:
    if sum(image.stored.nbytes for image in group) > MAX_CONVERTED_BYTES:
        return Skipped("conversion-refused/too-large")
    try:
        data = encode(convert(group, known))
    except ConversionRefused as refused:
        return Skipped(f"conversion-refused/{refused.reason}")
    return dicom_frames(
        data,
        collection=source.collection,
        case=source.case,
        first=first,
        known_text=source.known_text,
        tier=source.tier,
    )
