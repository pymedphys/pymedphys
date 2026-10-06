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

"""The results that a run's transform and gate return, and their signatures.

:mod:`~pymedphys._dicom.deidentify.run` takes a :class:`Transform` and a
:class:`Gate`, and gives these results the meanings that it describes. They
are importable from there too.
"""

from __future__ import annotations

import dataclasses
from pathlib import PurePosixPath
from typing import Protocol

from .references import InstanceRecord


@dataclasses.dataclass(frozen=True)
class Sequestered:
    """A transform's or gate's decision to withhold an instance.

    Attributes
    ----------
    reasons : tuple
        Why, as value-free objects of the engine: each an enum member, such
        as a :class:`~pymedphys._dicom.deidentify.source.SourceReason`, or a
        frozen dataclass instance, such as a walker's
        :class:`~pymedphys._dicom.deidentify.walker.Sequestration`. None may
        be text, which could hold a value: reasons that are not all such
        objects are replaced by :attr:`~pymedphys._dicom.deidentify.run.RunReason.INVALID_REASON`.
    evidence : object, optional
        From a transform, its evidence of the instance, for the gates of
        the other files of its subject. A gate's is ignored.
    qc : tuple
        The confidential material that a reviewer needs of the instance, of
        the types in :mod:`~pymedphys._dicom.deidentify.run_qc`, for the
        run's QC pack. The run reads none of it, and it is left out of the
        ``repr``.
    """

    reasons: tuple[object, ...]
    evidence: object = dataclasses.field(default=None, repr=False)
    qc: tuple[object, ...] = dataclasses.field(default=(), repr=False)


@dataclasses.dataclass(frozen=True)
class HoldForReview:
    """A gate's decision to withhold a file until it is reviewed.

    Attributes
    ----------
    reasons : tuple
        Why, as for :class:`Sequestered`.
    qc : tuple
        As for :class:`Sequestered`.
    """

    reasons: tuple[object, ...]
    qc: tuple[object, ...] = dataclasses.field(default=(), repr=False)


@dataclasses.dataclass(frozen=True)
class Release:
    """A gate's decision to release a file: the only one that releases it.

    Attributes
    ----------
    qc : tuple
        As for :class:`Sequestered`.
    """

    qc: tuple[object, ...] = dataclasses.field(default=(), repr=False)


@dataclasses.dataclass(frozen=True, repr=False)
class Transformed:
    """An instance's output file, and the transform's evidence of it.

    Its ``repr`` shows only the file's size.

    Attributes
    ----------
    path : PurePosixPath
        Where the file goes below the release directory, as
        :func:`~pymedphys._dicom.deidentify.output_names.instance_path` gives
        it from the instance's replacement values.
    data : bytes
        The whole output file.
    evidence : object, optional
        What the gate needs of the instance, such as the source values that
        were removed or replaced, which the run passes on unread.
    qc : tuple
        As for :class:`Sequestered`.
    """

    path: PurePosixPath
    data: bytes
    evidence: object = None
    qc: tuple[object, ...] = ()

    def __repr__(self) -> str:
        return f"Transformed(bytes={len(self.data)})"


class Transform(Protocol):
    """De-identify one instance: the walker, the writer, and verification."""

    def __call__(
        self, data: bytes, record: InstanceRecord
    ) -> Transformed | Sequestered: ...


class _NoEvidence:
    """The evidence of an instance of a subject that gave none."""

    def __repr__(self) -> str:
        return "NO_EVIDENCE"


NO_EVIDENCE = _NoEvidence()


class Gate(Protocol):
    """Decide whether a staged file may be released.

    ``written`` is the file as read back from the staging area; ``evidence``
    its transform's evidence; and ``subject`` the evidence of every instance
    of its subject in the run that the transform returned evidence for,
    ``evidence`` first and then in run order, sequestered instances
    included, and :data:`NO_EVIDENCE` for each other instance of its subject,
    whose values the gate therefore cannot know were searched for (D-027):
    one the transform refused or raised for, gave no evidence of, or that
    changed during the run.
    """

    def __call__(
        self, written: bytes, evidence: object, subject: tuple[object, ...]
    ) -> Release | HoldForReview | Sequestered: ...
