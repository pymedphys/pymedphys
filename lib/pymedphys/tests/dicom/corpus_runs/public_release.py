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

"""The ``public-release`` preset, with a reviewed ROI Name.

Retain Safe Private, Modified Dates, Clean Descriptors, and Clean
Recognizable Visual Features. The corpus's private blocks are reserved by a
creator that no reviewed rule names, so every private attribute is removed;
Modified Dates keeps the TM rows that its cleaner keeps, as in its own run;
the structure set is as the ``basic-clean-descriptors`` run has it; and
every file is marked free of a face, so every released instance claims
Clean Recognizable Visual Features, and the deformable registration is held,
as in that option's own run.
"""

from .._corpus_run import (
    MAPPED_NAME,
    VOCABULARY_NAME,
    CorpusRun,
    every_face_absent,
    mapped_planted_name,
    with_a_second_roi,
)
from .clean_recognizable_visual_features import RUN as VISUAL_FEATURES
from .retain_longitudinal_full_dates import INCONSISTENT
from .retain_longitudinal_modified_dates import RUN as MODIFIED_DATES

RUN = CorpusRun(
    "public-release",
    preset="public-release",
    corpus=with_a_second_roi,
    reviewed_roi_names=mapped_planted_name,
    face_review=every_face_absent,
    withheld=VISUAL_FEATURES.withheld,
    kept=MODIFIED_DATES.kept,
    roi_names=(MAPPED_NAME, VOCABULARY_NAME),
    inconsistent=INCONSISTENT,
)
