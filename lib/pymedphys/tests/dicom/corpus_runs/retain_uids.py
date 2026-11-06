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

"""The Retain UIDs Option alone (PS3.15 E.3.9, D-040).

The X-ray report's scope of accumulation names the study by its Study
Instance UID, which the option keeps everywhere else. Without Clean
Structured Content, the Basic Profile's D on the report's Content Sequence
sequesters the report, whose removed UID is still searched for in its
subject's other instances. The UID's only source is an instance that the
run does not write, so finding it in a kept Study Instance UID explains it
(D-042), and the other instances are released.
"""

from .._corpus_run import CorpusRun

RUN = CorpusRun("retain-uids", options=("retain_uids",))
