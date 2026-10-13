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
Features (0028,0302) set to NO, whether or not its IOD defines it.
"""

from .._corpus_run import CorpusRun, every_face_absent

RUN = CorpusRun(
    "clean-recognizable-visual-features",
    options=("clean_recognizable_visual_features",),
    face_review=every_face_absent,
)
