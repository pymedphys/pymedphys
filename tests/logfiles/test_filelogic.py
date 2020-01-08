# Copyright (C) 2019 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import os

from pymedphys.labs.managelogfiles import already_indexed_path


def test_file_logic():
    diagnostics = "/a/path/to/diagnostics"
    to_be_indexed = os.path.join(diagnostics, "to_be_indexed")
    already_indexed = os.path.join(diagnostics, "already_indexed")

    machine_zip_file_path = "machine/archive.zip"
    current_location = os.path.join(to_be_indexed, machine_zip_file_path)
    expected_new = os.path.abspath(os.path.join(already_indexed, machine_zip_file_path))

    converted = already_indexed_path(current_location, to_be_indexed, already_indexed)

    assert converted == expected_new
