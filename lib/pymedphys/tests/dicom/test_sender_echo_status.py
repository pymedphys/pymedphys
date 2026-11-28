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

"""C-ECHO verification must require success and clean up its association."""

from types import SimpleNamespace
from unittest.mock import Mock

from pymedphys._imports import pynetdicom, pytest
from pymedphys._dicom.connect.send import DicomSender


@pytest.mark.pydicom
@pytest.mark.parametrize(
    ("status_code", "established", "expected"),
    [
        (0x0000, True, True),
        (0xA700, True, False),
        (0x0122, True, False),
        (None, True, False),
        (0x0000, False, False),
    ],
)
def test_verify_requires_successful_echo_and_releases(
    monkeypatch, status_code, established, expected
):
    assoc = Mock()
    assoc.is_established = established
    assoc.send_c_echo.return_value = (
        None if status_code is None else SimpleNamespace(Status=status_code)
    )
    ae = Mock()
    ae.associate.return_value = assoc
    monkeypatch.setattr(pynetdicom, "AE", lambda **_kwargs: ae)

    assert DicomSender(host="127.0.0.1").verify() is expected

    if established:
        assoc.release.assert_called_once_with()
    else:
        assoc.send_c_echo.assert_not_called()


@pytest.mark.pydicom
def test_verify_releases_association_after_echo_exception(monkeypatch):
    assoc = Mock()
    assoc.is_established = True
    assoc.send_c_echo.side_effect = OSError("synthetic transport error")
    ae = Mock()
    ae.associate.return_value = assoc
    monkeypatch.setattr(pynetdicom, "AE", lambda **_kwargs: ae)

    with pytest.raises(OSError, match="synthetic transport error"):
        DicomSender(host="127.0.0.1").verify()

    assoc.release.assert_called_once_with()
