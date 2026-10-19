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

"""The ``basic-clean-descriptors`` preset, with a reviewed ROI Name.

The structure set's one ROI Name, a marker, is mapped by a reviewer's
decision; the second ROI's name, added here, the automatic tier writes in
the vocabulary's spelling.
"""

from .._corpus_run import (
    CLEAN_DESCRIPTORS,
    MAPPED_NAME,
    VOCABULARY_NAME,
    CorpusRun,
    mapped_planted_name,
    with_a_second_roi,
)

RUN = CorpusRun(
    CLEAN_DESCRIPTORS,
    preset=CLEAN_DESCRIPTORS,
    corpus=with_a_second_roi,
    reviewed_roi_names=mapped_planted_name,
    roi_names=(MAPPED_NAME, VOCABULARY_NAME),
)
