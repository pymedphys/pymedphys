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

"""Clean Recognizable Visual Features alone, with every file marked free of a face.

Every released instance claims the option, and so has Recognizable Visual
Features (0028,0302) set to NO, whether or not its IOD defines it. The
deformable registration is held whatever its verdict, since no preview of
the QC pack draws its grid.
"""

from pymedphys._dicom.deidentify import run
from pymedphys._dicom.deidentify.reasons import (
    HeldVisualFeatures,
    VisualFeaturesReason,
)

from .._corpus_run import BASIC_WITHHELD, CorpusRun, Withheld, every_face_absent

# The deformable registration, which the option holds.
DEFORMABLE_REGISTRATION = "19-registration-deformable.dcm"

RUN = CorpusRun(
    "clean-recognizable-visual-features",
    options=("clean_recognizable_visual_features",),
    face_review=every_face_absent,
    withheld={
        **BASIC_WITHHELD,
        DEFORMABLE_REGISTRATION: Withheld(
            run.Status.HELD_FOR_REVIEW,
            frozenset({HeldVisualFeatures(VisualFeaturesReason.NO_FACE_VERDICT)}),
        ),
    },
)
