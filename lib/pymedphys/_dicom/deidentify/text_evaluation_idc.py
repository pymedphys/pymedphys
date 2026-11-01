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

"""Series from NCI's Imaging Data Commons for the text detector's
evaluation (D-056): tier T3, real patients' scans in openly licensed
collections.

:data:`OPEN_COLLECTIONS` names each collection that may be taken, by its
IDC ``collection_id``, with the licence it was vetted under.
:func:`select_series` reads rows of IDC's index, as ``idc-index`` gives
them, and takes a series only where its collection is named, IDC gives the
series the same licence, that licence is one of :data:`OPEN_LICENCES`, the
series carries a DOI, and its modality is one of :data:`IMAGE_MODALITIES`;
where IDC's licence and the vetted one differ, the series is refused, so
that the stricter terms are never missed. Every refusal is counted by its
reason. Each collection's series are taken in an order fixed by a SHA-256
of the series, up to a number and a size, so that a selection is the same
on every run of the same index.

:func:`manifest` writes the selected series as an ``s5cmd`` manifest, and
:class:`IdcSeriesCase` reads a downloaded series as a case of tier T3,
named by its public identifiers, collection and Series Instance UID, with
its licence and DOI, for the per-case report
(:mod:`~.text_evaluation_cases`).

``idc-index`` and ``s5cmd`` run only on CI, pinned there; neither is a
dependency of PyMedPhys.
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
import pathlib
import re
from collections.abc import Iterable, Iterator, Mapping
from types import MappingProxyType

from .text_evaluation_frames import EvaluationFrame, EvaluationRefused
from .text_evaluation_sources import (
    DicomCase,
    Skipped,
    case_name,
    dicom_folder_cases,
)

TIER = "T3"
SOURCE = "NCI Imaging Data Commons"
# Licences, as IDC's ``license_short_name`` gives them once canonical
# (:func:`canonical_licence`), under which a collection may be taken.
OPEN_LICENCES = frozenset(
    {
        "CC BY 3.0",
        "CC BY 4.0",
        "CC BY NC 3.0",
        "CC BY NC 4.0",
        "CC0 1.0",
        "PDDL 1.0",
    }
)
# The collections vetted for T3, by IDC collection_id, with the licence of
# each as vetted on 1 November 2026.
OPEN_COLLECTIONS: Mapping[str, str] = MappingProxyType(
    {
        **dict.fromkeys(
            (
                "acrin_contralateral_breast_mr",
                "advanced_mri_breast_lesions",
                "b_mode_and_ceus_liver",
                "cmb_aml",
                "cmb_brca",
                "cmb_crc",
                "cmb_lca",
                "cmb_mel",
                "cmb_mml",
                "cmb_ov",
                "cmb_pca",
                "cmmd",
                "covid_19_ar",
                "covid_19_ny_sbu",
                "ea1141",
                "eay131",
                "prostate_mri_us_biopsy",
                "pseudo_phi_dicom_data",
                "psma_pet_ct_lesions",
                "remind",
                "varepop_apollo",
            ),
            "CC BY 4.0",
        ),
        **dict.fromkeys(
            ("cbis_ddsm", "lidc_idri", "soft_tissue_sarcoma", "tcga_blca", "tcga_ov"),
            "CC BY 3.0",
        ),
        **dict.fromkeys(
            ("breast_cancer_screening_dbt", "midrc_ricord_1c"), "CC BY NC 4.0"
        ),
    }
)
# Its images that MIDI-B's answer key marks as holding burned-in text are
# MIDI-B's evidence, so this collection is taken only less them.
ANSWER_KEYED = frozenset({"pseudo_phi_dicom_data"})
# Modalities of images that may hold burned-in text and that the detector
# reads; others, such as SEG, RTSTRUCT, SR, and slide microscopy, are not
# images of its kind.
IMAGE_MODALITIES = frozenset(
    {"CR", "CT", "DX", "MG", "MR", "NM", "OT", "PT", "RF", "RTIMAGE", "US", "XA"}
)
SALT = "pymedphys-text-detector-evaluation-idc/1"
# The columns of IDC's index that a selection reads.
COLUMNS = (
    "collection_id",
    "SeriesInstanceUID",
    "crdc_series_uuid",
    "Modality",
    "license_short_name",
    "source_DOI",
    "series_size_MB",
    "series_aws_url",
)
_UID = re.compile(r"[0-9]+(?:\.[0-9]+)*")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_DOI = re.compile(r"10\.[0-9]{4,9}/\S+")
_BUCKET = re.compile(r"s3://[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]/")


def canonical_licence(name: str) -> str:
    """A licence's short name in one spelling: upper case, with hyphens,
    underscores, and runs of spaces as one space."""
    return re.sub(r"[\s_-]+", " ", str(name).upper()).strip()


@dataclasses.dataclass(frozen=True)
class IdcSeries:
    """A series of IDC's, by its public identifiers.

    Attributes
    ----------
    collection_id : str
    series_instance_uid : str
    crdc_series_uuid : str
        IDC's own identifier of the series' files.
    modality : str
    licence : str
        Canonical, one of :data:`OPEN_LICENCES`.
    doi : str
        The DOI of the series' source.
    size_mb : float
    aws_url : str
        Where IDC keeps its files, ``s3://<bucket>/<crdc_series_uuid>/*``.
    """

    collection_id: str
    series_instance_uid: str
    crdc_series_uuid: str
    modality: str
    licence: str
    doi: str
    size_mb: float
    aws_url: str

    def __post_init__(self):
        if self.collection_id not in OPEN_COLLECTIONS:
            raise EvaluationRefused("A series must be of a vetted collection.")
        if self.licence not in OPEN_LICENCES:
            raise EvaluationRefused("A series must be openly licensed.")
        if not _UID.fullmatch(self.series_instance_uid):
            raise EvaluationRefused("A series needs its Series Instance UID.")
        if not _UUID.fullmatch(self.crdc_series_uuid):
            raise EvaluationRefused("A series needs IDC's identifier of it.")
        if not _DOI.fullmatch(self.doi):
            raise EvaluationRefused("A series needs its DOI.")
        if not (math.isfinite(self.size_mb) and self.size_mb >= 0):
            raise EvaluationRefused("A series' size must be in range.")
        bucket = _BUCKET.match(self.aws_url)
        if (
            bucket is None
            or self.aws_url[bucket.end() :] != f"{self.crdc_series_uuid}/*"
        ):
            raise EvaluationRefused("A series' files must be IDC's own.")

    @property
    def public(self) -> dict[str, str]:
        """What the per-case report names the series by."""
        return {
            "collection_id": self.collection_id,
            "series_instance_uid": self.series_instance_uid,
            "licence": self.licence,
            "doi": self.doi,
        }


@dataclasses.dataclass(frozen=True)
class Selection:
    """The series selected, and the rows refused, by reason."""

    series: tuple[IdcSeries, ...]
    refused: Mapping[str, int]

    def described(self) -> dict[str, object]:
        """Counts of the selection, by collection, with no series named."""
        names = sorted({each.collection_id for each in self.series})
        collections: dict[str, dict[str, object]] = {}
        for name in names:
            members = [each for each in self.series if each.collection_id == name]
            collections[name] = {
                "series": len(members),
                "size_mb": sum(each.size_mb for each in members),
                "licence": members[0].licence,
                "dois": sorted({each.doi for each in members}),
            }
        return {
            "source": SOURCE,
            "collections": collections,
            "refused": dict(sorted(self.refused.items())),
        }


def select_series(
    rows: Iterable[Mapping[str, object]],
    *,
    per_collection: int = 50,
    max_mb: float = 20_000.0,
    answer_keyed_series: Mapping[str, frozenset[str]] | None = None,
) -> Selection:
    """Select series from rows of IDC's index, as the module describes.

    Parameters
    ----------
    rows : iterable of mapping
        Each with at least :data:`COLUMNS`.
    per_collection : int
        The most series taken from one collection.
    max_mb : float
        The most megabytes taken in all.
    answer_keyed_series : mapping, optional
        For each collection of :data:`ANSWER_KEYED`, the Series Instance
        UIDs that MIDI-B's answer key marks; without one, that collection
        is refused whole.
    """
    if per_collection < 1 or not (math.isfinite(max_mb) and max_mb > 0):
        raise EvaluationRefused("A selection must take something.")
    keyed = dict(answer_keyed_series or {})
    refused: dict[str, int] = {}
    found: dict[str, list[IdcSeries]] = {}
    seen: set[str] = set()
    for row in rows:
        reason, series = _series(row, keyed)
        if series is not None and series.series_instance_uid in seen:
            reason, series = "repeated", None
        if series is None:
            refused[reason] = refused.get(reason, 0) + 1
            continue
        seen.add(series.series_instance_uid)
        found.setdefault(series.collection_id, []).append(series)
    taken: list[IdcSeries] = []
    total = 0.0
    for name in sorted(found):
        ordered = sorted(found[name], key=_order)
        for position, series in enumerate(ordered):
            if position >= per_collection:
                refused["over-collection-limit"] = (
                    refused.get("over-collection-limit", 0) + 1
                )
            elif total + series.size_mb > max_mb:
                refused["over-size-limit"] = refused.get("over-size-limit", 0) + 1
            else:
                taken.append(series)
                total += series.size_mb
    return Selection(tuple(taken), MappingProxyType(refused))


def _order(series: IdcSeries) -> bytes:
    return hashlib.sha256(
        "\0".join((SALT, series.collection_id, series.series_instance_uid)).encode()
    ).digest()


def _series(
    row: Mapping[str, object], keyed: Mapping[str, frozenset[str]]
) -> tuple[str, IdcSeries | None]:
    """A row's series, or why it is refused."""
    if not all(column in row for column in COLUMNS):
        return "missing-column", None
    collection = str(row["collection_id"])
    licence = canonical_licence(str(row["license_short_name"]))
    uid = str(row["SeriesInstanceUID"])
    # The first reason that holds, in order.
    reasons = (
        ("collection-not-vetted", collection not in OPEN_COLLECTIONS),
        ("licence-not-open", licence not in OPEN_LICENCES),
        ("licence-differs", licence != OPEN_COLLECTIONS.get(collection)),
        ("not-an-image-modality", str(row["Modality"]) not in IMAGE_MODALITIES),
        ("needs-answer-key", collection in ANSWER_KEYED and collection not in keyed),
        ("answer-keyed", uid in keyed.get(collection, frozenset())),
    )
    reason = next((name for name, holds in reasons if holds), None)
    if reason is not None:
        return reason, None
    doi = str(row["source_DOI"] or "").strip()
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    try:
        return "", IdcSeries(
            collection_id=collection,
            series_instance_uid=uid,
            crdc_series_uuid=str(row["crdc_series_uuid"]),
            modality=str(row["Modality"]),
            licence=licence,
            doi=doi,
            size_mb=float(str(row["series_size_MB"])),
            aws_url=str(row["series_aws_url"]),
        )
    except (EvaluationRefused, ValueError):
        return "malformed", None


def manifest(selection: Selection, destination: str = ".") -> str:
    """The selected series as an ``s5cmd run`` manifest: each copied to a
    folder of its own, named by IDC's identifier of it, under
    ``destination``."""
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", destination):
        raise EvaluationRefused("The destination must be a plain path.")
    folder = destination.rstrip("/") or "."
    return "".join(
        f"cp '{series.aws_url}' '{folder}/{series.crdc_series_uuid}/'\n"
        for series in selection.series
    )


@dataclasses.dataclass(frozen=True)
class IdcSeriesCase:
    """A downloaded IDC series, read as a case of tier T3.

    Its files are those under ``folder`` named by IDC's identifier of the
    series, as :func:`manifest` places them.
    """

    series: IdcSeries
    folder: pathlib.Path

    @property
    def collection(self) -> str:
        return self.series.collection_id

    @property
    def case(self) -> str:
        return self.series.series_instance_uid

    @property
    def public(self) -> dict[str, str]:
        """The series' public identifiers, licence, and DOI."""
        return self.series.public

    def read(self) -> Iterator[EvaluationFrame | Skipped]:
        found = pathlib.Path(self.folder) / self.series.crdc_series_uuid
        if not found.is_dir():
            yield Skipped("not-downloaded")
            return
        # Grouped by series, the folder must hold the one series it is named
        # for, whose case dicom_folder_cases names by the series' UID; its
        # text is unknown.
        expected = case_name("series", self.series.series_instance_uid)
        cases = dicom_folder_cases(
            found,
            collection=self.series.collection_id,
            group_by="series",
            tier=TIER,
        )
        series = [each for each in cases if isinstance(each, DicomCase)]
        if [each.case for each in series] != [expected]:
            yield Skipped("not-the-series")
            return
        for each in cases:
            yield from each.read()
