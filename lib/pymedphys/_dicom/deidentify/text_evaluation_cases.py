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

"""The text detector's results case by case, for the cases of openly
licensed public collections alone (D-056).

:func:`cases_report` gives, beside the counts-only summary
(:func:`~.text_evaluation.summarise`), which it leaves as it is, each case
whose source names it by public identifiers: a series of NCI's Imaging Data
Commons (:class:`~.text_evaluation_idc.IdcSeriesCase`), by its collection's
``collection_id`` and its Series Instance UID, with its licence and DOI.
For each point it gives the case's counts only: its texts fully covered,
partly covered, and missed; its frames without text, those with a region,
and the share of their tissue blacked out; and its frames whose text is
unknown, and those with a region. It holds no pixel value and no crop.
Every other case, such as a clinic's, MIDI-B's, or HaN-Seg's, is only
counted as withheld.

The seven openly licensed collections taken from The Cancer Imaging
Archive (:data:`TCIA_COLLECTIONS`) are reported by collection name and
Series Instance UID only where :data:`TCIA_PER_CASE` is set; it is not, as
that is not yet confirmed.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .text_evaluation import (
    _KINDS,
    Evaluation,
    Tally,
    _plain,
    _software,
)
from .text_evaluation_benchmarks import tier_of
from .text_evaluation_frames import EvaluationRefused
from .text_evaluation_idc import OPEN_COLLECTIONS, OPEN_LICENCES

FORMAT = "pymedphys-deid-text-detector-cases/1"
# Whether cases of TCIA_COLLECTIONS are reported; until confirmed, they are
# withheld. Removing the switch removes TCIA's cases from the report.
TCIA_PER_CASE = False
TCIA_COLLECTIONS = frozenset(
    {
        "4D-Lung",
        "ACRIN-NSCLC-FDG-PET",
        "Anti-PD-1_Lung",
        "Lung-PET-CT-Dx",
        "NSCLC-Radiomics",
        "Pancreatic-CT-CBCT-SEG",
        "Pediatric-CT-SEG",
    }
)
_UID = re.compile(r"[0-9]+(?:\.[0-9]+)*")
_DOI = re.compile(r"10\.[0-9]{4,9}/\S+")
# What every reported case is named by, beside its collection.
_IDENTITY = ("series_instance_uid", "licence", "doi")


def reported(public: Mapping[str, str] | None) -> dict[str, str] | None:
    """A case's public identity as the report gives it, or None where the
    case is withheld."""
    if public is None:
        return None
    keys = set(public)
    licence = public.get("licence", "")
    if keys == {"collection_id", *_IDENTITY}:
        allowed = OPEN_COLLECTIONS.get(public["collection_id"]) == licence
    elif keys == {"collection", *_IDENTITY}:
        allowed = TCIA_PER_CASE and public["collection"] in TCIA_COLLECTIONS
    else:
        allowed = False
    held_up = bool(
        _UID.fullmatch(public.get("series_instance_uid", ""))
        and licence in OPEN_LICENCES
        and _DOI.fullmatch(public.get("doi", ""))
    )
    return dict(public) if allowed and held_up else None


def cases_report(evaluation: Evaluation) -> dict[str, Any]:
    """Return each reported case's counts, as the module describes, for
    JSON, in the order of the cases."""
    points = evaluation.settings.points
    cases = []
    withheld = 0
    for result in evaluation.results:
        public = reported(result.public)
        if public is None:
            withheld += 1
            continue
        entry: dict[str, Any] = {
            **public,
            "split": result.split,
            "evaluated": result.evaluated,
            "crashed": result.crashed,
        }
        if result.evaluated and result.crashed is None:
            entry["frames"] = _by(result.tally, "frames")
            entry["skipped"] = _by(result.tally, "skipped")
            entry["points"] = [
                _point(result.tally, index) for index in range(len(points))
            ]
        cases.append(entry)
    seen = [(each.get("collection_id"), each["series_instance_uid"]) for each in cases]
    if len(set(seen)) != len(seen):
        raise EvaluationRefused("Each series must be one case.")
    return {
        "format": FORMAT,
        "software": _software(),
        "detector": _plain(evaluation.detector),
        "tier": tier_of(evaluation.detector),
        "cases": cases,
        "withheld": withheld,
    }


def _by(tally: Tally, kind: str) -> dict[str, int]:
    return dict(
        sorted((key[1], value) for key, value in tally.counts.items() if key[0] == kind)
    )


def _point(tally: Tally, index: int) -> dict[str, Any]:
    texts = tally.texts.get((index, (), ()))
    texts_found, full, _, missed = (list(texts) if texts else [0, 0, 0, 0])[:4]
    entry: dict[str, Any] = {
        "index": index,
        "texts": texts_found,
        "fully_covered": full,
        "partly_covered": texts_found - full - missed,
        "missed": missed,
    }
    for kind, name in _KINDS.items():
        row = tally.frames.get((index, kind, (), ()))
        frames, with_region, _, _, _, tissue, tissue_blacked = (
            list(row) if row else [0] * 7
        )[:7]
        entry[name] = {
            "frames": frames,
            "with_a_region": with_region,
            "tissue_blacked_out": tissue_blacked / tissue if tissue else None,
        }
    return entry
