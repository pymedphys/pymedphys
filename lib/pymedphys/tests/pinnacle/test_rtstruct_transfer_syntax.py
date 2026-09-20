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

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.compat import ensure_transfer_syntax
from pymedphys._pinnacle.constants import (
    GImplementationClassUID,
    GTransferSyntaxUID,
    RTSTRUCTModality,
    RTStructSOPClassUID,
)

# Enough contour points for the DS-encoded ContourData to exceed the 16-bit
# length field of an explicit VR transfer syntax (65 535 bytes).
NUMBER_OF_CONTOUR_POINTS = 10_000


def _rtstruct_like_convert_struct():
    """Build a dataset the way ``pymedphys._pinnacle.rtstruct.convert_struct`` does."""
    file_meta = pydicom.dataset.FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = RTStructSOPClassUID
    file_meta.TransferSyntaxUID = GTransferSyntaxUID
    file_meta.MediaStorageSOPInstanceUID = pydicom.uid.generate_uid()
    file_meta.ImplementationClassUID = GImplementationClassUID

    ds = pydicom.dataset.FileDataset(
        "RS.dcm", {}, file_meta=file_meta, preamble=b"\x00" * 128
    )
    ds.SOPClassUID = RTStructSOPClassUID
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    ds.Modality = RTSTRUCTModality

    contour = pydicom.dataset.Dataset()
    contour.ContourGeometricType = "CLOSED_PLANAR"
    contour.NumberOfContourPoints = NUMBER_OF_CONTOUR_POINTS
    contour.ContourData = [float(i) / 1000 for i in range(3 * NUMBER_OF_CONTOUR_POINTS)]

    roi_contour = pydicom.dataset.Dataset()
    roi_contour.ReferencedROINumber = 1
    roi_contour.ContourSequence = [contour]
    ds.ROIContourSequence = [roi_contour]

    return ds


@pytest.mark.pydicom
def test_rtstruct_export_keeps_implicit_vr_for_large_contours(tmp_path):
    """The Pinnacle RT Structure Set export must stay Implicit VR Little Endian.

    ContourData has VR DS, whose length field is only 16 bits wide in the
    explicit VR transfer syntaxes, so a contour with more than 65 535
    characters cannot be encoded with explicit VR (see the test below for
    what pydicom does instead). Implicit VR has a 32-bit length field.
    ``convert_struct`` declares the transfer syntax in ``file_meta`` before
    calling ``ensure_transfer_syntax``, which must leave that declaration
    alone.
    """
    ds = _rtstruct_like_convert_struct()
    contour_data = ds.ROIContourSequence[0].ContourSequence[0].ContourData
    assert len("\\".join(str(value) for value in contour_data)) > 0xFFFF

    ensure_transfer_syntax(ds)
    assert ds.file_meta.TransferSyntaxUID == pydicom.uid.ImplicitVRLittleEndian

    filepath = tmp_path / "RS.dcm"
    ds.save_as(filepath)
    reloaded = pydicom.dcmread(filepath)

    assert reloaded.file_meta.TransferSyntaxUID == pydicom.uid.ImplicitVRLittleEndian
    reloaded_contour_data = (
        reloaded.ROIContourSequence[0].ContourSequence[0].ContourData
    )
    assert len(reloaded_contour_data) == 3 * NUMBER_OF_CONTOUR_POINTS
    assert reloaded_contour_data[-1] == contour_data[-1]


@pytest.mark.pydicom
def test_large_contours_are_corrupted_by_explicit_vr(tmp_path):
    """Documents why the export is pinned to Implicit VR Little Endian.

    Asked to write the same dataset with an explicit VR transfer syntax,
    pydicom 3 cannot encode the over-long DS element. It warns and rewrites
    the VR as UN, so the contour coordinates come back as an opaque byte
    string instead of numbers.
    """
    ds = _rtstruct_like_convert_struct()
    ds.file_meta.TransferSyntaxUID = pydicom.uid.ExplicitVRLittleEndian
    filepath = tmp_path / "RS_explicit.dcm"

    with pytest.warns(UserWarning, match="64 kByte"):
        ds.save_as(filepath)

    reloaded = pydicom.dcmread(filepath)
    contour_data = reloaded.ROIContourSequence[0].ContourSequence[0]["ContourData"]
    assert contour_data.VR == "UN"
    assert isinstance(contour_data.value, bytes)
