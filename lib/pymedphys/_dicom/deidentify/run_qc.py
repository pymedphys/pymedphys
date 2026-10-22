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
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath

from pymedphys._imports import pydicom

from . import pixel_risk, qc_contours, qc_pack, qc_previews, residuals
from .iod_conformance import SourceGap
from .face_review import contour_data_sha256, pixel_data_sha256
from .file_layout import ElementPath
from .qc_pack import Disposition, DropReason, QcPack, RoiNameOutcome
from .reasons import PixelDataReason
from .reference_graph import Finding, FindingKind
from .release_report import REPORTED_FINDINGS
from .reviewed_descriptors import CleanedDescriptor
from .run_written import REPORTED_ONLY
from .roi_names import Reason
from .source import read_source
from .text_detection import TextBox
from .written_references import WrittenFinding, WrittenFindingKind


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
    institutional_matches: tuple[str, ...] = ()

    def __repr__(self) -> str:
        return (
            f"RoiNameMaterial(path={str(self.path)!r}, outcome={self.outcome.value!r})"
        )


@dataclasses.dataclass(frozen=True, repr=False)
class DescriptorMaterial:
    """What descriptor cleaning decided for the values of one free-text descriptor.

    Attributes are those of :class:`~.qc_pack.DescriptorEntry` but its position.
    """

    path: ElementPath
    sources: tuple[str, ...]
    results: tuple[CleanedDescriptor, ...]
    applied: bool
    attribute: str | None = None

    def __repr__(self) -> str:
        return f"DescriptorMaterial(path={str(self.path)!r}, applied={self.applied!r})"


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


@dataclasses.dataclass(frozen=True, repr=False)
class RedactionMaterial:
    """What the Clean Pixel Data Option did to an instance's Pixel Data.

    The pack lists it with its regions, if the instance was released or held
    for review, and previews each of its frames as written, and each frame
    with regions also as received.

    Attributes
    ----------
    reason : ~pymedphys._dicom.deidentify.reasons.PixelDataReason
    frames, rows, columns : int
    regions : tuple of (int, tuple of ~.text_detection.TextBox)
        As :class:`~pymedphys._dicom.deidentify.qc_pack.RedactionEntry`
        gives them.
    source : bytes or None
        The source file, from which each frame with regions is shown as
        received, or None where no frame has regions, so that a run keeps no
        source that no preview shows.
    """

    reason: PixelDataReason
    frames: int
    rows: int
    columns: int
    regions: tuple[tuple[int, tuple[TextBox, ...]], ...]
    source: bytes | None

    def __repr__(self) -> str:
        return (
            f"RedactionMaterial(reason={self.reason.value!r}, frames={self.frames}, "
            f"rows={self.rows}, columns={self.columns}, "
            f"regions={len(self.regions)})"
        )


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


@dataclasses.dataclass(frozen=True)
class WrittenFindingMaterial:
    """A second-pass finding at an input that the run reports without acting on it.

    The run gives one to each input that a finding of a kind in
    :data:`~pymedphys._dicom.deidentify.run_written.REPORTED_ONLY` names,
    such as a written reference to an instance that was not written. Its
    attributes are those of
    :class:`~pymedphys._dicom.deidentify.written_references.WrittenFinding`
    but its positions, and hold no value.
    """

    kind: WrittenFindingKind
    attribute: tuple[str, ...]
    count: int = 0


def with_written_findings(
    material: Mapping[int, Sequence[object]], findings: Sequence[WrittenFinding]
) -> dict[int, tuple[object, ...]]:
    """Return a run's material with the second pass's findings that it reports only.

    Each distinct finding of a kind in
    :data:`~pymedphys._dicom.deidentify.run_written.REPORTED_ONLY` is added
    as a :class:`WrittenFindingMaterial` to the material of each input, by
    run position, in its groups, once.
    """
    added = {position: tuple(items) for position, items in material.items()}
    for finding in dict.fromkeys(findings):
        if finding.kind not in REPORTED_ONLY:
            continue
        item = WrittenFindingMaterial(finding.kind, finding.attribute, finding.count)
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
    digests: Mapping[int, bytes] | None = None,
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
    digests : mapping of int to bytes, optional
        The SHA-256 of each source file that the run's first pass read, by
        run position, which the pack records with each instance.

    Notes
    -----
    The pack's image previews (:func:`~.qc_previews.previews_of`) are made
    from the file that each released or held instance's gate searched, in
    its :class:`SearchMaterial`, with the instances that a
    :class:`PixelRiskMaterial` gives findings for as high-risk, and the
    frames of each instance that a :class:`RedactionMaterial` gives, which
    the pack lists in ``redactions``. A released or held instance without
    one is listed as not previewed. Each such file's pixel
    data and contours are recorded with its instance as
    :func:`~.face_review.pixel_data_sha256` and
    :func:`~.face_review.contour_data_sha256` give them, unless the file
    cannot be read again, or, for its contours, unless it has contours that
    no contour sheet shows.

    The released and held instances that give :class:`SeriesEvidence` are
    grouped by series, in run position order, and each series is assessed
    with :func:`~.pixel_risk.assess_series`; one with any finding is
    listed in ``series_risks``. Only these instances are assessed, since
    only they reach a recipient, so a series of which one image was
    released is not a volume. Each series of them whose instances all have a
    digest is listed in ``series``, for the reviewer's face verdicts.

    Raises
    ------
    QcPackError
        If an entry cannot be built, naming its field, never a value.
    TypeError
        If an item of material is none of this module's types.
    """
    digests = {} if digests is None else digests
    instances = tuple(
        _instance(outcome, source, digests.get(position))
        for position, (outcome, source) in enumerate(
            zip(outcomes, sources, strict=True)
        )
    )
    findings: list[qc_pack.ResidualEntry] = []
    omissions: list[qc_pack.NotSearchedEntry] = []
    drops: list[qc_pack.DropEntry] = []
    roi_names: list[qc_pack.RoiNameEntry] = []
    descriptors: list[qc_pack.DescriptorEntry] = []
    reference_findings: list[qc_pack.ReferenceFindingEntry] = []
    retained: list[tuple[str, int, ElementPath]] = []
    written: dict[int, bytes] = {}
    risks: dict[int, list[pixel_risk.Finding]] = {}
    gaps: dict[int, list[SourceGap]] = {}
    series: dict[int, SeriesEvidence] = {}
    redactions: dict[int, RedactionMaterial] = {}
    for position in sorted(material):
        for item in material[position]:
            if isinstance(item, PixelRiskMaterial):
                risks.setdefault(position, []).extend(item.assessment.findings)
            elif isinstance(item, SourceGap):
                gaps.setdefault(position, []).append(item)
            elif isinstance(item, SeriesEvidence):
                series.setdefault(position, item)
            elif isinstance(item, RedactionMaterial):
                if instances[position].disposition in _PREVIEWED:
                    redactions.setdefault(position, item)
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
                        item.institutional_matches,
                    )
                )
            elif isinstance(item, DescriptorMaterial):
                descriptors.append(
                    qc_pack.DescriptorEntry(
                        position,
                        item.path,
                        item.sources,
                        item.results,
                        item.applied,
                        item.attribute,
                    )
                )
            elif isinstance(item, (ReferenceFindingMaterial, WrittenFindingMaterial)):
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
    cleaned = {
        position: (
            item.source,
            qc_pack.RedactionEntry(
                position,
                item.reason,
                item.frames,
                item.rows,
                item.columns,
                item.regions,
            ),
        )
        for position, item in redactions.items()
    }
    previews = qc_previews.previews_of(written, high_risk, cleaned)
    instances = tuple(
        dataclasses.replace(
            entry,
            **_written_sha256(written[position], position in previews.contours_shown),
        )
        if position in written
        else entry
        for position, entry in enumerate(instances)
    )
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
        descriptors=tuple(descriptors),
        reference_findings=tuple(reference_findings),
        pixel_risks=tuple(
            qc_pack.PixelRiskEntry(position, found)
            for position, found in sorted(high_risk.items())
        ),
        series_risks=_series_risks(instances, series),
        redactions=tuple(cleaned[position][1] for position in sorted(cleaned)),
        series=tuple(
            qc_pack.SeriesEntry(grouped)
            for grouped in _series_groups(_reviewed(instances, series), series)
            if all(instances[position].source_sha256 for position in grouped)
        ),
        previews=previews.previews,
        not_previewed=not_previewed,
        source_gaps=tuple(
            qc_pack.SourceGapEntry(position, tuple(found))
            for position, found in sorted(gaps.items())
        ),
    )


def _series_risks(
    instances: Sequence[qc_pack.InstanceEntry], evidence: Mapping[int, SeriesEvidence]
) -> tuple[qc_pack.SeriesRiskEntry, ...]:
    """Assess each series of the released and held instances, by first position."""
    return tuple(
        qc_pack.SeriesRiskEntry(positions, found)
        for positions, found in assessed_series(
            _reviewed(instances, evidence), evidence
        )
    )


def _reviewed(
    instances: Sequence[qc_pack.InstanceEntry], evidence: Mapping[int, SeriesEvidence]
) -> list[int]:
    """Return the positions of the released and held instances with evidence."""
    return [
        position
        for position in evidence
        if instances[position].disposition in _PREVIEWED
    ]


def _series_groups(
    positions: Iterable[int], evidence: Mapping[int, SeriesEvidence]
) -> list[tuple[int, ...]]:
    """Group the instances at ``positions`` with evidence by series, by first position."""
    groups: dict[str | None, list[int]] = {}
    for position in sorted(set(positions) & set(evidence)):
        groups.setdefault(evidence[position].series, []).append(position)
    return [tuple(grouped) for grouped in groups.values()]


def assessed_series(
    positions: Iterable[int], evidence: Mapping[int, SeriesEvidence]
) -> list[tuple[tuple[int, ...], tuple[pixel_risk.SeriesFinding, ...]]]:
    """Assess each series of some instances, and return those with findings.

    The instances at ``positions`` that give :class:`SeriesEvidence` are
    grouped by series, in run position order, and each series is assessed
    with :func:`~.pixel_risk.assess_series`. Each series with a finding
    is returned, by first position, as the run positions of its instances
    and its findings, whose ``instances`` count from 0 within those
    positions.
    """
    assessed = []
    for grouped in _series_groups(positions, evidence):
        found = pixel_risk.assess_series(
            [evidence[position].evidence for position in grouped]
        )
        if found:
            assessed.append((grouped, found))
    return assessed


def _written_sha256(written: bytes, contours_shown: bool) -> dict[str, str | None]:
    """Return the SHA-256 of a written file's pixel data and contours, as an
    instance entry's fields, each None if unreadable.

    The contours' is None too where the file has contours that the pack's
    contour sheet does not show, so that no verdict releases them unseen.
    """
    digests: dict[str, str | None] = {"pixel_sha256": None, "contour_sha256": None}
    try:
        dataset = read_source(written).dataset()
    # Whatever reading the file raises, its instance has no digests, so no
    # verdict clears it, and the pack is still written.
    except Exception:  # pylint: disable = broad-exception-caught
        return digests
    taken = [("pixel_sha256", pixel_data_sha256)]
    if contours_shown or not qc_contours.has_contours(dataset):
        taken.append(("contour_sha256", contour_data_sha256))
    for field, digest in taken:
        try:
            digests[field] = digest(dataset).hex()
        # Likewise, for the digest that cannot be taken.
        except Exception:  # pylint: disable = broad-exception-caught
            pass
    return digests


def _instance(
    outcome: object, source: Path, digest: bytes | None
) -> qc_pack.InstanceEntry:
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
        source_sha256=None if digest is None else digest.hex(),
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
