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

"""The largest set of Table E.1-1's options that compose: nine together.

Every option of Table E.1-1 but Modified Dates, which PS3.15 E.3.6 makes
exclusive of Full Dates, and whose C conflicts with Retain Device Identity's
K outside ``tps-import``. Neither pixel option, which the table has no
column for, is selected; each has runs of its own. The corpus is changed as
each option's own run changes it: Retain Patient Characteristics' attributes
of free text are emptied, Clean Structured Content's acquisition context
items are content items, and Clean Descriptors has its technique
descriptions and the structure set of its run.

Each option's kept rows are kept, but Clinical Trial Protocol Ethics
Committee Name (0012,0081), which is removed whatever its action (D-020),
and the attributes that each option's run keeps alike differ as before.
"""

from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module

from .._corpus_run import (
    MAPPED_NAME,
    VOCABULARY_NAME,
    CorpusRun,
    kept_rows,
    mapped_planted_name,
)
from . import (
    clean_descriptors_free_text,
    clean_structured_content,
    retain_institution_identity,
    retain_longitudinal_full_dates,
    retain_patient_characteristics,
)

OPTIONS = (
    "retain_safe_private",
    "retain_uids",
    "retain_device_identity",
    "retain_institution_identity",
    "retain_patient_characteristics",
    "retain_longitudinal_full_dates",
    "clean_descriptors",
    "clean_structured_content",
    "clean_graphics",
)


def with_every_options_changes(
    corpus: corpus_module.SyntheticCorpus,
) -> corpus_module.SyntheticCorpus:
    """Return the corpus with the changes of each option's own run."""
    corpus = retain_patient_characteristics.with_empty_free_text(corpus)
    corpus = clean_structured_content.with_acquisition_context_items(corpus)
    return clean_descriptors_free_text.with_technique_descriptions(corpus)


RUN = CorpusRun(
    "all-composable-options",
    options=OPTIONS,
    corpus=with_every_options_changes,
    reviewed_roi_names=mapped_planted_name,
    kept=kept_rows(OPTIONS) - {retain_institution_identity.ETHICS_COMMITTEE_NAME},
    roi_names=(MAPPED_NAME, VOCABULARY_NAME),
    inconsistent=(
        retain_patient_characteristics.KEPT_DIFFERENCES
        | retain_institution_identity.KEPT_DIFFERENCES
        | retain_longitudinal_full_dates.INCONSISTENT
    ),
)
