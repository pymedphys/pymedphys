# Copyright (C) 2026 Jeffrey D. Cooney
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

"""Identical retransmissions must not rewrite already-stored DICOM records."""

from types import SimpleNamespace

from pymedphys._imports import pydicom, pytest
from pymedphys._dicom.connect.listen import DicomListener


@pytest.mark.pydicom
def test_identical_dicom_resend_does_not_rewrite_existing_record(
    monkeypatch, tmp_path
):
    dataset = pydicom.Dataset()
    dataset.PatientID = "SYNTHETIC_PATIENT"
    dataset.StudyInstanceUID = pydicom.uid.generate_uid()
    dataset.SeriesInstanceUID = pydicom.uid.generate_uid()
    dataset.SOPClassUID = pydicom.uid.RTPlanStorage
    dataset.SOPInstanceUID = pydicom.uid.generate_uid()

    event = SimpleNamespace(
        dataset=dataset,
        context=SimpleNamespace(transfer_syntax=pydicom.uid.ImplicitVRLittleEndian),
    )
    listener = DicomListener(storage_directory=tmp_path)

    first_status = listener.on_c_store(event)
    assert first_status.Status == 0x0000
    (original,) = tmp_path.rglob("*.dcm")
    original_bytes = original.read_bytes()

    def forbidden_write(*_args, **_kwargs):
        raise AssertionError("An identical DICOM object must not be rewritten")

    monkeypatch.setattr(pydicom.FileDataset, "save_as", forbidden_write)

    again_status = listener.on_c_store(event)
    assert again_status.Status == 0x0000
    assert original.read_bytes() == original_bytes
    assert list(tmp_path.rglob("*.dcm")) == [original]
