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

"""Retain Longitudinal Temporal Information with Modified Dates alone.

Modified Dates gives C to every date and time of Table E.1-1 but Patient's
Birth Date, Patient's Birth Time, and GPS Time Stamp. Its cleaner keeps the
time of each subject event and radiation source, since whole weeks keep the
time of day (D-006, D-039), so those TM rows are kept, although the table
gives them C, which leaves the manner of cleaning to the engine.
"""

from pymedphys._dicom.deidentify import standard
from pymedphys._dicom.deidentify.modified_dates import TAGS
from pymedphys._dicom.deidentify.temporal_roles import (
    TemporalAction,
    load_temporal_roles,
)

from .._corpus_run import CorpusRun

_ROLES = load_temporal_roles().rules

RUN = CorpusRun(
    "retain-longitudinal-modified-dates",
    options=("retain_longitudinal_modified_dates",),
    kept=frozenset(
        row.tag
        for row in standard.load_table_e1_1().attributes
        if row.tag in TAGS
        and standard.dictionary_attribute(row.tag).vrs == ("TM",)
        and _ROLES[row.tag].role.action is TemporalAction.SHIFT
    ),
)
