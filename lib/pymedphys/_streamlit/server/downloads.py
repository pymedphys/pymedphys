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
from typing import Dict

from pymedphys._streamlit.utilities.session import SessionID, get_session_id

FileName = str
FilePath = pathlib.Path
FileLocationMap = Dict[SessionID, Dict[FileName, FilePath]]


# Assuming CPython with the GIL is being used. This implies that Dicts
# are thread-safe:
#
#    <https://docs.python.org/3/glossary.html#term-global-interpreter-lock>

file_location_map: FileLocationMap = {}

# TODO: Adjust this object later to hook into when Streamlit sessions are closed.
# Potentially utilise an object similar to, or based on, session state objects?


def add_filepath(filename, filepath):
    session_id = get_session_id()
