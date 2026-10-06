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

"""The QC material that a run's transform and gate hand it, and the pack built from it.

A transform's or gate's result carries, besides its value-free reasons, the
confidential material that a reviewer needs of the instance, as ``qc``: a
tuple of the objects below, which hold source values and so are left out of
every ``repr``. The run never reads them; :func:`qc_pack_of` turns them, by
run position, into the entries of the run's
:class:`~pymedphys._dicom.deidentify.qc_pack.QcPack`, with an entry for every
input from its outcome and source path (D-016, D-026, D-027).
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath

from . import pixel_risk, qc_pack, qc_previews, residuals
from .file_layout import ElementPath
from .qc_pack import Disposition, DropReason, QcPack, RoiNameOutcome
from .roi_names import Reason


@dataclasses.dataclass(frozen=True, repr=False)
class SearchMaterial:
    """The residual search of a gated file, and the file it searched.

    Attributes
    ----------
    search : ~pymedphys._dicom.deidentify.residuals.ResidualSearch
    written : bytes
        The file as the gate read it, to cut each finding's excerpt from.
    """

    search: residuals.ResidualSearch
    written: bytes

    def __repr__(self) -> str:
        return "SearchMaterial()"


@dataclasses.dataclass(frozen=True)
class Dropped:
    """A source value left out of the instance's residual search, and why."""

    source: ElementPath
    reason: DropReason


@dataclasses.dataclass(frozen=True, repr=False)
class RoiNameMaterial:
    """What descriptor cleaning wrote for one ROI Name, as the QC pack lists it.

    Attributes are those of :class:`~.qc_pack.RoiNameEntry` but its position.
    """

    path: ElementPath
    source: str
    outcome: RoiNameOutcome
    held_because: Reason | None = None
    written: str | None = None

    def __repr__(self) -> str:
        return (
            f"RoiNameMaterial(path={str(self.path)!r}, outcome={self.outcome.value!r})"
        )


@dataclasses.dataclass(frozen=True, repr=False)
class RetainedText:
    """A string that the policy retains, at its place in the instance."""

    value: str
    path: ElementPath

    def __repr__(self) -> str:
        return f"RetainedText(path={str(self.path)!r})"


@dataclasses.dataclass(frozen=True)
class PixelRiskMaterial:
    """The indicators of risk in an instance's pixel data, read from its source.

    An instance with any finding is in a high-risk category (D-017): the pack
    lists it with its findings, and previews its written file at full
    resolution. The source is assessed, since the Basic Profile removes some
    of the evidence, such as an overlay group whose graphics lie in the
    pixel data.
    """

    assessment: pixel_risk.PixelRiskAssessment


# The QC pack's disposition of each run status, by the status's value.
_DISPOSITIONS = {disposition.value: disposition for disposition in Disposition}
# The dispositions whose written files are previewed for the reviewer.
_PREVIEWED = frozenset({Disposition.RELEASED, Disposition.HELD_FOR_REVIEW})


def qc_pack_of(
    sources: Sequence[Path],
    outcomes: Sequence[object],
    material: Mapping[int, Sequence[object]],
    reference: str | None = None,
) -> QcPack:
    """Return the QC pack of a run.

    Parameters
    ----------
    sources : sequence of Path
        Each input's path, by run position.
    outcomes : sequence of Outcome
        The run's outcomes, by run position, each with its ``label`` where
        it was sequestered.
    material : mapping of int to sequence
        The QC material of each run position, as its transform and gate gave
        it.
    reference : str, optional
        The pack's reference; a new one by default.

    Notes
    -----
    The pack's image previews (:func:`~.qc_previews.previews_of`) are made
    from the file that each released or held instance's gate searched, in
    its :class:`SearchMaterial`, with the instances that a
    :class:`PixelRiskMaterial` gives findings for as high-risk.

    Raises
    ------
    QcPackError
        If an entry cannot be built, naming its field, never a value.
    TypeError
        If an item of material is none of this module's types.
    """
    instances = tuple(
        _instance(outcome, source)
        for outcome, source in zip(outcomes, sources, strict=True)
    )
    findings: list[qc_pack.ResidualEntry] = []
    omissions: list[qc_pack.NotSearchedEntry] = []
    drops: list[qc_pack.DropEntry] = []
    roi_names: list[qc_pack.RoiNameEntry] = []
    retained: list[tuple[str, int, ElementPath]] = []
    written: dict[int, bytes] = {}
    risks: dict[int, list[pixel_risk.Finding]] = {}
    for position in sorted(material):
        for item in material[position]:
            if isinstance(item, PixelRiskMaterial):
                risks.setdefault(position, []).extend(item.assessment.findings)
            elif isinstance(item, SearchMaterial):
                if instances[position].disposition in _PREVIEWED:
                    written.setdefault(position, item.written)
                found, omitted = qc_pack.entries_for_search(
                    position, item.search, item.written
                )
                findings.extend(found)
                omissions.extend(omitted)
            elif isinstance(item, Dropped):
                drops.append(qc_pack.DropEntry(position, item.source, item.reason))
            elif isinstance(item, RoiNameMaterial):
                roi_names.append(
                    qc_pack.RoiNameEntry(
                        position,
                        item.path,
                        item.source,
                        item.outcome,
                        item.held_because,
                        item.written,
                    )
                )
            elif isinstance(item, RetainedText):
                retained.append((item.value, position, item.path))
            else:
                raise TypeError("QC material must be of the run's QC material types")
    high_risk = {position: tuple(found) for position, found in risks.items() if found}
    previews = qc_previews.previews_of(written, high_risk)
    return QcPack(
        reference=qc_pack.new_reference() if reference is None else reference,
        instances=instances,
        residual_findings=tuple(findings),
        drops=tuple(drops),
        not_searched=tuple(omissions),
        retained_strings=qc_pack.retained_strings(retained),
        roi_names=tuple(roi_names),
        pixel_risks=tuple(
            qc_pack.PixelRiskEntry(position, found)
            for position, found in sorted(high_risk.items())
        ),
        previews=previews.previews,
        not_previewed=previews.not_previewed,
    )


def _instance(outcome: object, source: Path) -> qc_pack.InstanceEntry:
    status = getattr(outcome, "status")
    disposition = _DISPOSITIONS[status.value]
    with_output = disposition in (Disposition.RELEASED, Disposition.DUPLICATE)
    output: PurePosixPath | None = getattr(outcome, "output")
    return qc_pack.InstanceEntry(
        position=getattr(outcome, "position"),
        source=str(source),
        disposition=disposition,
        output=output if with_output else None,
        label=getattr(outcome, "label")
        if disposition is Disposition.SEQUESTERED
        else None,
        reasons=()
        if with_output
        else tuple(reason_text(reason) for reason in getattr(outcome, "reasons")),
    )


def reason_text(reason: object) -> str:
    """Return a value-free reason as text: an enum's member, or a dataclass's fields.

    An enum member is ``Type.MEMBER``. A dataclass instance is its type's
    name and its fields, each an enum member's value, a path as
    :class:`~.file_layout.ElementPath` gives it, or other text, number, or
    None as it is; the run accepts no other reason, since only these are
    value-free by the engine's contract.
    """
    if isinstance(reason, enum.Enum):
        return f"{type(reason).__name__}.{reason.name}"
    if dataclasses.is_dataclass(reason) and not isinstance(reason, type):
        # A field left unset, such as one with init=False, holds nothing to
        # write, and must not fail the whole run.
        fields = ", ".join(
            f"{field.name}={_field_text(getattr(reason, field.name))}"
            for field in dataclasses.fields(reason)
            if hasattr(reason, field.name)
        )
        return f"{type(reason).__name__}({fields})"
    raise TypeError("a reason must be an enum member or a dataclass instance")


def _field_text(value: object) -> str:
    if isinstance(value, enum.Enum):
        return str(value.value)
    if isinstance(value, ElementPath):
        return str(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return reason_text(value)
    return str(value)
