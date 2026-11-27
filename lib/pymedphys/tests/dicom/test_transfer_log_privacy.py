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

"""DICOM diagnostics must not disclose patient-bearing filenames or UIDs."""

import importlib
import logging
from types import SimpleNamespace
from unittest.mock import Mock

from pymedphys._imports import pydicom, pynetdicom, pytest
from pymedphys._dicom.connect.listen import DicomListener
from pymedphys._dicom.connect.send import DicomSender


@pytest.mark.pydicom
def test_received_dicom_paths_are_not_logged(tmp_path, caplog):
    ds = pydicom.Dataset()
    ds.PatientID = "SYNTHETIC_PRIVATE_PATIENT"
    ds.StudyInstanceUID = pydicom.uid.generate_uid()
    ds.SeriesInstanceUID = pydicom.uid.generate_uid()
    ds.SOPClassUID = pydicom.uid.RTPlanStorage
    ds.SOPInstanceUID = pydicom.uid.generate_uid()
    event = SimpleNamespace(
        dataset=ds,
        context=SimpleNamespace(transfer_syntax=pydicom.uid.ImplicitVRLittleEndian),
    )
    listener = DicomListener(
        storage_directory=tmp_path / "SYNTHETIC_PRIVATE_STORAGE"
    )

    with caplog.at_level(logging.DEBUG):
        status = listener.on_c_store(event)

    assert status.Status == 0x0000
    assert "SYNTHETIC_PRIVATE" not in caplog.text
    assert str(ds.SOPInstanceUID) not in caplog.text


@pytest.mark.pydicom
def test_sent_dicom_uid_is_not_logged(monkeypatch, caplog):
    association = Mock()
    association.is_established = True
    ae = Mock()
    ae.associate.return_value = association
    monkeypatch.setattr(pynetdicom, "AE", lambda: ae)
    ds = pydicom.Dataset()
    ds.SOPInstanceUID = pydicom.uid.generate_uid()

    with caplog.at_level(logging.DEBUG):
        DicomSender().send([ds])

    assert str(ds.SOPInstanceUID) not in caplog.text


@pytest.mark.pydicom
def test_invalid_input_filename_is_not_logged(monkeypatch, caplog):
    send_module = importlib.import_module("pymedphys._dicom.connect.send")

    class FakeSender:
        def __init__(self, **_kwargs):
            pass

        def verify(self):
            return True

    def invalid_dicom(_):
        raise pydicom.errors.InvalidDicomError("synthetic invalid DICOM")

    monkeypatch.setattr(send_module, "DicomSender", FakeSender)
    monkeypatch.setattr(pydicom, "dcmread", invalid_dicom)
    args = SimpleNamespace(
        host="127.0.0.1",
        port=11112,
        aetitle="TEST",
        dcmfiles=["SYNTHETIC_PRIVATE_PATIENT.dcm"],
    )

    with caplog.at_level(logging.ERROR):
        send_module.send_cli(args)

    assert "Invalid DICOM file provided" in caplog.text
    assert "SYNTHETIC_PRIVATE" not in caplog.text
