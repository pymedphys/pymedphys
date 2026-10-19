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

"""The Retain Institution Identity Option alone.

The Option keeps each of its ten rows of Table E.1-1 but one: Clinical
Trial Protocol Ethics Committee Name (0012,0081). It is Type 1C, required
only where Clinical Trial Protocol Ethics Committee Approval Number
(0012,0082) is present, which Table E.1-1 removes under the Basic Profile
and every option, so PS3.5 Section 7.4.2 does not allow it in the output,
and the engine removes it whatever its action (D-020).
"""

from .._corpus_run import CorpusRun, kept_rows

OPTIONS = ("retain_institution_identity",)
ETHICS_COMMITTEE_NAME = "(0012,0081)"
# Clinical Trial Site ID, Site Name, and Coordinating Center Name are Patient
# attributes that the Option keeps, so each instance keeps its own planted
# value, and they differ among one patient's instances in the outputs as in
# the inputs.
KEPT_DIFFERENCES = frozenset({"(0012,0030)", "(0012,0031)", "(0012,0060)"})

RUN = CorpusRun(
    "retain-institution-identity",
    options=OPTIONS,
    kept=kept_rows(OPTIONS) - {ETHICS_COMMITTEE_NAME},
    inconsistent=KEPT_DIFFERENCES,
)
