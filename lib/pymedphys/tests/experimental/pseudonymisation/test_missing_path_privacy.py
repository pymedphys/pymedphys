# Copyright (C) 2026 Jeffrey D. Cooney

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Missing clinical input paths must not appear in exception messages."""

import pytest

from pymedphys._experimental.pseudonymisation import pseudonymise


def test_missing_pseudonymisation_input_does_not_disclose_patient_path(tmp_path):
    patient_id = "SYNTHETIC_PATIENT_123456"
    missing_path = tmp_path / patient_id / "study.dcm"

    with pytest.raises(FileNotFoundError) as captured:
        pseudonymise(missing_path)

    message = str(captured.value)
    assert "input path" in message
    assert patient_id not in message
    assert str(missing_path) not in message
