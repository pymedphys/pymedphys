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

"""Clean Pixel Data alone, with a finder that marks a corner of every frame.

Every instance with Pixel Data has the corner blacked out and is held for
review (D-037): the RT Dose that the Basic Profile's run holds for residual
text is held for both, and the CT slice that it sequesters is sequestered
first. No instance claims the option until a reviewer's decision can release
its pixel data, so every released instance claims the Basic Profile alone.
"""

from pymedphys._dicom.deidentify import run
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module
from pymedphys._dicom.deidentify.reasons import PixelDataReason
from pymedphys._dicom.deidentify.text_detection import TextBox

from .._corpus_run import BASIC_PROFILE_CODE, BASIC_WITHHELD, CorpusRun, Withheld


class _CornerFinder:
    """Finds text in the top left corner of every frame, two rows by three
    columns, which every frame of the corpus has."""

    def find(self, frame):
        del frame
        return (TextBox(0, 0, 2, 3),)


# The corpus's instances with Pixel Data, but the one that every run
# sequesters.
_IMAGES = (
    "01-ct-1.dcm",
    "02-ct-2.dcm",
    "06-rtdose.dcm",
    "08-ct-enhanced.dcm",
    "09-ct-legacy-enhanced.dcm",
    "10-mr.dcm",
    "11-mr-enhanced.dcm",
    "12-mr-enhanced-color.dcm",
    "13-mr-legacy-enhanced.dcm",
    "15-pet.dcm",
    "16-pet-enhanced.dcm",
    "17-pet-legacy-enhanced.dcm",
)
_BLACKED_OUT = Withheld(
    run.Status.HELD_FOR_REVIEW, frozenset({PixelDataReason.TEXT_BLACKED_OUT})
)
_REVIEW = BASIC_WITHHELD[corpus_module.REVIEW_FILE]

RUN = CorpusRun(
    "clean-pixel-data",
    options=("clean_pixel_data",),
    finder=_CornerFinder(),
    withheld={
        **BASIC_WITHHELD,
        **{name: _BLACKED_OUT for name in _IMAGES},
        corpus_module.REVIEW_FILE: Withheld(
            run.Status.HELD_FOR_REVIEW, _REVIEW.reasons | _BLACKED_OUT.reasons
        ),
    },
    # No instance claims Clean Pixel Data yet (D-037).
    codes=frozenset({BASIC_PROFILE_CODE}),
)
