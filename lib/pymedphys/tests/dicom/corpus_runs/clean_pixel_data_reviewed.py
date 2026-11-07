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

"""Clean Pixel Data, with a review that accepts the corner of every frame.

Every instance with Pixel Data has the corner blacked out, as the review
approved, without the finder, and every released instance claims the option,
and so has Burned In Annotation (0028,0301) set to NO, whether or not its IOD
defines it. The run withholds what the Basic Profile's run withholds, and
the BINARY Segmentation, whose single bits the option does not clean
(D-037).
"""

from .._corpus_run import BASIC_WITHHELD, CorpusRun, every_corner_accepted
from .clean_pixel_data import RUN as UNREVIEWED
from .clean_pixel_data import SINGLE_BITS

RUN = CorpusRun(
    "clean-pixel-data-reviewed",
    options=("clean_pixel_data",),
    # The option needs a finder, which the review leaves unasked.
    finder=UNREVIEWED.finder,
    redaction_review=every_corner_accepted,
    withheld={**BASIC_WITHHELD, **SINGLE_BITS},
)
