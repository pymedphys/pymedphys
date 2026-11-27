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

"""A symlinked DICOM patient folder must not escape the receiving directory."""

from types import SimpleNamespace

from pymedphys._imports import pydicom, pytest
from pymedphys._dicom.connect.listen import DicomListener
from pymedphys._utilities.filesystem import encode_file_name


@pytest.mark.pydicom
def test_receiver_rejects_symlinked_patient_directory(tmp_path):
    root = tmp_path / "incoming"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    protected = outside / "protected.txt"
    protected.write_text("original", encoding="utf-8")

    dataset = pydicom.Dataset()
    dataset.PatientID = "SYNTHETIC_PATIENT"
    dataset.StudyInstanceUID = pydicom.uid.generate_uid()
    dataset.SeriesInstanceUID = pydicom.uid.generate_uid()
    dataset.SOPClassUID = pydicom.uid.RTPlanStorage
    dataset.SOPInstanceUID = pydicom.uid.generate_uid()

    try:
        (root / encode_file_name(dataset.PatientID)).symlink_to(
            outside, target_is_directory=True
        )
    except (OSError, NotImplementedError):
        pytest.skip("This filesystem does not permit creating symlinks")

    event = SimpleNamespace(
        dataset=dataset,
        context=SimpleNamespace(transfer_syntax=pydicom.uid.ImplicitVRLittleEndian),
    )
    listener = DicomListener(storage_directory=root)

    response = listener.on_c_store(event)

    assert response.Status == 0xA700
    assert protected.read_text(encoding="utf-8") == "original"
    assert sorted(outside.iterdir()) == [protected]


@pytest.mark.pydicom
def test_receiver_accepts_ordinary_nested_patient_path(tmp_path):
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

    response = DicomListener(storage_directory=tmp_path).on_c_store(event)

    assert response.Status == 0x0000
    (stored,) = tmp_path.rglob("*.dcm")
    assert stored.is_relative_to(tmp_path)
