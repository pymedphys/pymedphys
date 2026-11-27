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

"""A failed DICOM transfer must release its network association."""

from unittest.mock import Mock

from pymedphys._imports import pydicom, pynetdicom, pytest
from pymedphys._dicom.connect.send import DicomSender


@pytest.mark.pydicom
@pytest.mark.parametrize("failure", ["invalid-input", "unreadable-file", "send-error"])
def test_sender_releases_association_on_failure(monkeypatch, failure):
    association = Mock()
    association.is_established = True
    ae = Mock()
    ae.associate.return_value = association
    monkeypatch.setattr(pynetdicom, "AE", lambda: ae)

    sender = DicomSender(host="127.0.0.1", port=1234)

    if failure == "invalid-input":
        objects = [object()]
        expected_exception = TypeError
    elif failure == "unreadable-file":
        objects = ["missing.dcm"]
        expected_exception = OSError

        def fail_read(_):
            raise OSError("synthetic DICOM parse failure")

        monkeypatch.setattr(pydicom, "dcmread", fail_read)
    else:
        dataset = pydicom.Dataset()
        dataset.SOPInstanceUID = pydicom.uid.generate_uid()
        objects = [dataset]
        expected_exception = OSError
        association.send_c_store.side_effect = OSError("synthetic transfer error")

    with pytest.raises(expected_exception):
        sender.send(objects)

    association.release.assert_called_once_with()
