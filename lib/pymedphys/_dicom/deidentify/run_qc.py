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
every ``repr``, and of :class:`~pymedphys._dicom.deidentify.residuals.NotSearched`
records of the instance's own values. The run never reads them; :func:`qc_pack_of` turns them, by
run position, into the entries of the run's
:class:`~pymedphys._dicom.deidentify.qc_pack.QcPack`, with an entry for every
input from its outcome and source path (D-016, D-026, D-027). The run adds
a :class:`ReferenceFindingMaterial` of its own to each input that the first
pass reports a finding at without acting on it.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath

from pymedphys._imports import pydicom

from . import pixel_risk, qc_pack, qc_previews, residuals
from .file_layout import ElementPath
from .qc_pack import Disposition, DropReason, QcPack, RoiNameOutcome
from .reference_graph import Finding, FindingKind
from .release_report import REPORTED_FINDINGS
from .roi_names import Reason


@dataclasses.dataclass(frozen=True, repr=False)
class SearchMaterial:
    """The residual search of a gated file, and the file it searched.

    Each of its findings is listed at the file's position, and each form it
    did not search, which is better given as a
    :class:`~pymedphys._dicom.deidentify.residuals.NotSearched` item of the
    instance that holds the value, since a search covers the subject's
    other instances' values too.

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


@dataclasses.dataclass(frozen=True)
class ReferenceFindingMaterial:
    """A reference finding at an input that the run reports without acting on it.

    The run gives one to each input that a first-pass finding of a kind in
    :data:`~pymedphys._dicom.deidentify.release_report.REPORTED_FINDINGS`
    names, in any of its groups. Its attributes are those of
    :class:`~pymedphys._dicom.deidentify.reference_graph.Finding` but its
    positions, and hold no value.
    """

    kind: FindingKind
    attribute: tuple[str, ...]
    count: int = 0


def with_reported_findings(
    material: Mapping[int, Sequence[object]], findings: Sequence[Finding]
) -> dict[int, tuple[object, ...]]:
    """Return a run's material with the findings that it reports only.

    Each finding of a kind in
    :data:`~pymedphys._dicom.deidentify.release_report.REPORTED_FINDINGS`
    is added as a :class:`ReferenceFindingMaterial` to the material of each
    input in its groups, once.
    """
    added = {position: tuple(items) for position, items in material.items()}
    for finding in findings:
        if finding.kind not in REPORTED_FINDINGS:
            continue
        item = ReferenceFindingMaterial(finding.kind, finding.attribute, finding.count)
        for position in sorted({p for group in finding.instances for p in group}):
            added[position] = (*added.get(position, ()), item)
    return added


@dataclasses.dataclass(frozen=True, repr=False)
class SeriesEvidence:
    """What an instance gives the assessment of its series, read from its source.

    Attributes
    ----------
    series : str, optional
        The source's Series Instance UID (0020,000E), by which the pack
        groups instances into series, and which it never writes; ``None``
        where it cannot be read, and the instances without one are assessed
        as one series, so that a volume is not missed. That series can join
        instances of different patients or studies into a volume, which
        only adds findings, each naming its instances.
    evidence : pydicom.Dataset
        As :func:`~.pixel_risk.series_evidence` gives it.
    """

    series: str | None
    evidence: pydicom.Dataset

    def __repr__(self) -> str:
        return "SeriesEvidence()"


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
    :class:`PixelRiskMaterial` gives findings for as high-risk. A released or
    held instance without one is listed as not previewed.

    The released and held instances that give :class:`SeriesEvidence` are
    grouped by series, in run position order, and each series is assessed
    with :func:`~.pixel_risk.assess_ct_series`; one with any finding is
    listed in ``series_risks``. Only these instances are assessed, since
    only they reach a recipient, so a series of which one image was
    released is not a volume.

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
    reference_findings: list[qc_pack.ReferenceFindingEntry] = []
    retained: list[tuple[str, int, ElementPath]] = []
    written: dict[int, bytes] = {}
    risks: dict[int, list[pixel_risk.Finding]] = {}
    series: dict[int, SeriesEvidence] = {}
    for position in sorted(material):
        for item in material[position]:
            if isinstance(item, PixelRiskMaterial):
                risks.setdefault(position, []).extend(item.assessment.findings)
            elif isinstance(item, SeriesEvidence):
                series.setdefault(position, item)
            elif isinstance(item, SearchMaterial):
                if instances[position].disposition in _PREVIEWED:
                    written.setdefault(position, item.written)
                found, omitted = qc_pack.entries_for_search(
                    position, item.search, item.written
                )
                findings.extend(found)
                omissions.extend(omitted)
            elif isinstance(item, residuals.NotSearched):
                omissions.append(qc_pack.NotSearchedEntry(position, item))
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
            elif isinstance(item, ReferenceFindingMaterial):
                reference_findings.append(
                    qc_pack.ReferenceFindingEntry(
                        position, item.kind, item.attribute, item.count
                    )
                )
            elif isinstance(item, RetainedText):
                retained.append((item.value, position, item.path))
            else:
                raise TypeError("QC material must be of the run's QC material types")
    high_risk = {position: tuple(found) for position, found in risks.items() if found}
    previews = qc_previews.previews_of(written, high_risk)
    # A released or held file that no gate handed over is listed, not lost.
    missing = [
        qc_pack.NotPreviewedEntry(
            entry.position, qc_pack.NotPreviewedReason.NOT_AVAILABLE
        )
        for entry in instances
        if entry.disposition in _PREVIEWED and entry.position not in written
    ]
    not_previewed = tuple(
        sorted((*previews.not_previewed, *missing), key=lambda entry: entry.position)
    )
    return QcPack(
        reference=qc_pack.new_reference() if reference is None else reference,
        instances=instances,
        residual_findings=tuple(findings),
        drops=tuple(drops),
        not_searched=tuple(omissions),
        retained_strings=qc_pack.retained_strings(retained),
        roi_names=tuple(roi_names),
        reference_findings=tuple(reference_findings),
        pixel_risks=tuple(
            qc_pack.PixelRiskEntry(position, found)
            for position, found in sorted(high_risk.items())
        ),
        series_risks=_series_risks(instances, series),
        previews=previews.previews,
        not_previewed=not_previewed,
    )


def _series_risks(
    instances: Sequence[qc_pack.InstanceEntry], evidence: Mapping[int, SeriesEvidence]
) -> tuple[qc_pack.SeriesRiskEntry, ...]:
    """Assess each series of the released and held instances, by first position."""
    groups: dict[str | None, list[int]] = {}
    for position in sorted(evidence):
        if instances[position].disposition in _PREVIEWED:
            groups.setdefault(evidence[position].series, []).append(position)
    entries = []
    for positions in groups.values():
        found = pixel_risk.assess_ct_series(
            [evidence[position].evidence for position in positions]
        )
        if found:
            entries.append(qc_pack.SeriesRiskEntry(tuple(positions), found))
    return tuple(entries)


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
