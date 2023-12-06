# Copyright (C) 2020 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from pymedphys._imports import pytest

import pymedphys

from . import utilities


@pytest.mark.cypress
def test_cypress():
    pymedphys.zip_data_paths(
        "metersetmap-gui-e2e-data.zip", extract_directory=utilities.HERE
    )

    pymedphys.zip_data_paths(
        "dummy-ct-and-struct.zip",
        extract_directory=utilities.HERE.joinpath("cypress", "fixtures"),
    )

    utilities.run_test_commands_with_gui_process(["yarn", "yarn cypress run"])
