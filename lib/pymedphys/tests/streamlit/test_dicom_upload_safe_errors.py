# Copyright (C) 2026 PyMedPhys contributors
#
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

"""Invalid DICOM uploads must not disclose their filenames or decoder details."""

import io
from types import SimpleNamespace
from unittest.mock import MagicMock

from pymedphys._imports import pytest

pytest.importorskip("streamlit")
pytest.importorskip("pydicom")

from pymedphys._experimental.streamlit.utilities.dicom import loader  # noqa: E402


class StopRendering(Exception):
    pass


@pytest.mark.parametrize("multiple", [False, True])
def test_failed_dicom_upload_omits_patient_filenames_and_decoder_values(
    monkeypatch, multiple
):
    sensitive_filename = "SYNTHETIC-PATIENT-12345-RTPLAN.dcm"
    sensitive_decoder_value = "DICOM field contained SYNTHETIC-PATIENT-12345"

    file = io.BytesIO(b"invalid synthetic DICOM")
    file.name = sensitive_filename
    left, right = MagicMock(), MagicMock()
    fake_st = SimpleNamespace(
        columns=MagicMock(return_value=[left, right]),
        write=MagicMock(),
        file_uploader=MagicMock(return_value=[file] if multiple else file),
        warning=MagicMock(),
        error=MagicMock(),
        stop=MagicMock(side_effect=StopRendering),
    )

    def fail_decode(*_args, **_kwargs):
        raise ValueError(sensitive_decoder_value)

    monkeypatch.setattr(loader, "st", fake_st)
    monkeypatch.setattr(loader.pydicom, "dcmread", fail_decode)

    with pytest.raises(StopRendering):
        loader.dicom_file_loader(multiple, stop_before_pixels=True)

    combined = str(fake_st.error.call_args) + str(fake_st.warning.call_args)
    assert sensitive_filename not in combined
    assert sensitive_decoder_value not in combined
    assert "patient information" in combined
    fake_st.stop.assert_called_once()
