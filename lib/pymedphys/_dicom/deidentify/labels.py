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

"""The form of a sequestered instance's label (D-026).

The release report gives each sequestered instance a label, and the QC pack
maps each label to its file. The pattern is here, in a module that imports
nothing of the engine, so that both can use it without the release report
importing the QC pack's modules in a cycle.
"""

import re

# A label, such as ``S-0007``, from ``S-0001`` to ``S-n``, all with the same
# number of digits and at least four.
LABEL_PATTERN = re.compile(r"S-[0-9]{4,}")
