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

"""The Retain UIDs Option alone (PS3.15 E.3.9, D-040), over the corpus without its reports.

The X-ray report's scope of accumulation names the study by its Study
Instance UID, which the option keeps everywhere else. Without Clean
Structured Content, the Basic Profile's D on the report's Content Sequence
removes it, and a removed UID found in a kept one withholds the file
(D-042), so with the reports every instance of the subject would be
withheld; the end-to-end tests show that apart, and this run checks the
option on the other instances.
"""

from .._corpus_run import WITHHELD_WITHOUT_REPORTS, CorpusRun, without_reports

RUN = CorpusRun(
    "retain-uids",
    options=("retain_uids",),
    corpus=without_reports,
    withheld=WITHHELD_WITHOUT_REPORTS,
)
