# Copyright (C) 2019 Cancer Care Associates and Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import functools

import pymedphys._utilities.filesystem


@functools.lru_cache(maxsize=1)
def create_read_monaco_file():
    def read_monaco_file(filepath):
        with pymedphys._utilities.filesystem.open_no_lock(  # pylint: disable = protected-access
            filepath, "r"
        ) as a_file:
            data = a_file.read()

        return data

    return read_monaco_file
