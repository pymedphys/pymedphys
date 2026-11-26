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

import traceback

import pytest

from pymedphys._dicom.anonymise import api as anonymise_api
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


def test_read_time_missing_input_does_not_disclose_patient_path(tmp_path, monkeypatch):
    patient_id = "SYNTHETIC_PATIENT_123456"
    input_path = tmp_path / patient_id / "study.dcm"
    input_path.parent.mkdir()
    input_path.write_bytes(b"synthetic placeholder")
    original_read = anonymise_api.pydicom.dcmread

    def remove_before_read(filename, *args, **kwargs):
        assert input_path.is_file()
        input_path.unlink()
        return original_read(filename, *args, **kwargs)

    monkeypatch.setattr(anonymise_api.pydicom, "dcmread", remove_before_read)

    with pytest.raises(FileNotFoundError) as captured:
        pseudonymise(input_path)

    message = str(captured.value)
    formatted_traceback = "".join(traceback.format_exception(captured.value))
    assert "input file was not found" in message
    assert patient_id not in message
    assert patient_id not in formatted_traceback
    assert str(input_path) not in formatted_traceback
    assert not input_path.exists()
