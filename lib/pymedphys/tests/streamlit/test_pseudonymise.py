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

"""The pseudonymisation app warns about its limitations before it is used."""

from pymedphys._imports import pytest

from . import apptest_utilities as utl

pytest.importorskip("streamlit")


def test_pseudonymise_app_shows_limitation_warning_first():
    app_test = utl.load_app("pseudonymise")
    utl.assert_no_exception(app_test)

    element_types = [
        type(element).__name__ for element in app_test.main.children.values()
    ]
    assert element_types.index("Warning") < element_types.index("FileUploader")

    warnings = [warning.value for warning in app_test.warning]
    assert len(warnings) == 1
    assert "without a secret key" in warnings[0]
    assert "deprecated" not in warnings[0].lower()
    assert "users/background/dicom-deidentification.html" in warnings[0]
