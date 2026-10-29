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

"""The ``tps-import`` preset, with a reviewed ROI Name.

Retain Device Identity, Retain Patient Characteristics, Modified Dates,
Clean Descriptors, and Clean Structured Content, run as each runs alone: the
Option's free text emptied, as for Retain Patient Characteristics alone, the
structure set's names cleaned, as for ``basic-clean-descriptors``, and the
acquisition context items made content items, as for Clean Structured
Content alone, so that the preset keeps and cleans them. The two Structured
Reports are released with their content trees cleaned, and each content
item's value takes its concept's action under the preset's options (D-047),
so Retain Device Identity keeps a Device Observer UID. The rows kept are those that
every selected option that gives an action keeps, which leaves out the
eleven device dates and times that Retain Device Identity keeps and Modified
Dates modifies, which the preset modifies (D-007), and the times that
Modified Dates keeps. The preset claims no conformance, so its instances
gain no code. The corpus gives every Patient's Age in weeks, which gives
no synthetic birth date (D-008), so Patient's Birth Date is emptied, as Z
empties it; ``test_deidentify_birth_dates.py`` covers the synthetic dates.
"""

from pymedphys._dicom.deidentify.policy import PRESETS

from .._corpus_run import (
    CONTENT_SEQUENCE,
    MAPPED_NAME,
    VOCABULARY_NAME,
    WITHHELD_WITHOUT_REPORTS,
    CorpusRun,
    kept_rows,
    mapped_planted_name,
    with_a_second_roi,
)
from .all_composable_options import ACQUISITION_CONTEXT
from .clean_structured_content import with_acquisition_context_items
from .retain_longitudinal_modified_dates import RUN as MODIFIED_DATES_RUN
from .retain_patient_characteristics import KEPT_DIFFERENCES, with_empty_free_text

PRESET = "tps-import"


def _corpus(corpus):
    return with_a_second_roi(
        with_empty_free_text(with_acquisition_context_items(corpus))
    )


RUN = CorpusRun(
    PRESET,
    preset=PRESET,
    corpus=_corpus,
    reviewed_roi_names=mapped_planted_name,
    kept=kept_rows(PRESETS[PRESET]) | MODIFIED_DATES_RUN.kept_rows(),
    codes=frozenset(),
    roi_names=(MAPPED_NAME, VOCABULARY_NAME),
    kept_content=frozenset({ACQUISITION_CONTEXT, CONTENT_SEQUENCE}),
    withheld=WITHHELD_WITHOUT_REPORTS,
    # Without Retain UIDs, Referenced Study Sequence is removed, so only
    # Accession Number of REPORT_ENTITIES differs for the reports.
    inconsistent=KEPT_DIFFERENCES
    | MODIFIED_DATES_RUN.inconsistent
    | frozenset({"(0008,0050)"}),
)
