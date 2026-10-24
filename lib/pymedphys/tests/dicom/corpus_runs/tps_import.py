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

Retain Device Identity, Retain Patient Characteristics, Modified Dates, and
Clean Descriptors, run as each runs alone: the Option's free text emptied,
as for Retain Patient Characteristics alone, and the structure set's names
cleaned, as for ``basic-clean-descriptors``. The rows kept are those that
every selected option that gives an action keeps, which leaves out the
eleven device dates and times that Retain Device Identity keeps and Modified
Dates modifies, which the preset modifies (D-007), and the times that
Modified Dates keeps. The preset claims no conformance, so its instances
gain no code. Patient's Birth Date is still emptied by Z, as under every
other policy, until the synthetic birth date (D-008) is built.
"""

from pymedphys._dicom.deidentify.policy import PRESETS

from .._corpus_run import (
    MAPPED_NAME,
    VOCABULARY_NAME,
    CorpusRun,
    kept_rows,
    mapped_planted_name,
    with_a_second_roi,
)
from .retain_longitudinal_modified_dates import RUN as MODIFIED_DATES_RUN
from .retain_patient_characteristics import KEPT_DIFFERENCES, with_empty_free_text

PRESET = "tps-import"


def _corpus(corpus):
    return with_a_second_roi(with_empty_free_text(corpus))


RUN = CorpusRun(
    PRESET,
    preset=PRESET,
    corpus=_corpus,
    reviewed_roi_names=mapped_planted_name,
    kept=kept_rows(PRESETS[PRESET]) | MODIFIED_DATES_RUN.kept_rows(),
    codes=frozenset(),
    roi_names=(MAPPED_NAME, VOCABULARY_NAME),
    inconsistent=KEPT_DIFFERENCES | MODIFIED_DATES_RUN.inconsistent,
)
