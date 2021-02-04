# Copyright (C) 2021 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pathlib
import uuid
from typing import Dict

SessionID = uuid.UUID
FileName = str
FilePath = pathlib.Path
FileLocationMap = Dict[SessionID, Dict[FileName, FilePath]]


# Assuming CPython with the GIL is being used. This implies that Dicts
# are thread-safe:
#
#    <https://docs.python.org/3/glossary.html#term-global-interpreter-lock>

file_location_map: FileLocationMap = {}
