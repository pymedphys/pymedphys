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

"""Retain Longitudinal Temporal Information with Full Dates alone."""

from .._corpus_run import CorpusRun

# The dates and times that the corpus makes differ among instances of one
# study or series, and that the option keeps: Study Date and Time, Last
# Menstrual Date, Series Date and Time, and the Performed Procedure Step
# Start and End Dates and Times.
INCONSISTENT = frozenset(
    {
        "(0008,0020)",
        "(0008,0030)",
        "(0010,21D0)",
        "(0008,0021)",
        "(0008,0031)",
        "(0040,0244)",
        "(0040,0245)",
        "(0040,0250)",
        "(0040,0251)",
    }
)

RUN = CorpusRun(
    "retain-longitudinal-full-dates",
    options=("retain_longitudinal_full_dates",),
    inconsistent=INCONSISTENT,
)
