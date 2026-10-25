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

import io
from types import SimpleNamespace

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest, shapely

from pymedphys.dicom import merge_contours
from pymedphys._dicom.structure import pull_structure
from pymedphys._dicom.structure.merge import merge_contours_cli

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]


def _structure(implicit):
    # A 15 mm square, off-centre, with 1,500 points along each edge.
    t = np.arange(1500) / 100
    x = np.concatenate((-3 + t, np.full(1500, 12), 12 - t, np.full(1500, -3)))
    y = np.concatenate((np.full(1500, 5), 5 + t, np.full(1500, 20), 20 - t))
    expected = np.column_stack((x, y, np.full(6000, 7)))
    contour = pydicom.Dataset()
    contour.ContourData = [f"{v:.6f}" for v in expected.ravel()]
    contour.NumberOfContourPoints = len(expected)
    contour.ContourGeometricType = "CLOSED_PLANAR"
    image = pydicom.Dataset()
    image.ReferencedSOPClassUID = pydicom.uid.CTImageStorage
    image.ReferencedSOPInstanceUID = "2.25.20081"
    contour.ContourImageSequence = [image]
    roi = pydicom.Dataset()
    roi.ReferencedROINumber = 1
    roi.ContourSequence = [contour]
    name = pydicom.Dataset()
    name.ROINumber = 1
    name.ROIName = "SYNTHETIC"
    ds = pydicom.Dataset()
    ds.SOPClassUID = pydicom.uid.RTStructureSetStorage
    ds.SOPInstanceUID = "2.25.2008"
    ds.StructureSetROISequence = [name]
    ds.ROIContourSequence = [roi]
    ds.file_meta = pydicom.dataset.FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = (
        pydicom.uid.ImplicitVRLittleEndian
        if implicit
        else pydicom.uid.ExplicitVRLittleEndian
    )
    buffer = io.BytesIO()
    if implicit:
        pydicom.dcmwrite(buffer, ds, enforce_file_format=True)
    else:
        with pytest.warns(UserWarning, match="64 kByte"):
            pydicom.dcmwrite(buffer, ds, enforce_file_format=True)
    return pydicom.dcmread(io.BytesIO(buffer.getvalue())), expected


@pytest.mark.parametrize("implicit", [False, True], ids=["explicit-un", "implicit-ds"])
def test_extract_large_contour(implicit):
    ds, expected = _structure(implicit)
    element = ds.ROIContourSequence[0].ContourSequence[0]["ContourData"]
    original = element.value
    if not implicit:
        assert element.VR == "UN"
        assert len(original) > 65534
    x, y, z = pull_structure("SYNTHETIC", ds)
    np.testing.assert_allclose(
        np.column_stack((x[0], y[0], z[0])), expected, atol=1e-12
    )
    assert element.value is original
    assert element.VR == ("DS" if implicit else "UN")


def _assert_square(roi):
    assert len(roi.ContourSequence) == 1
    contour = roi.ContourSequence[0]
    points = np.asarray(contour.ContourData, dtype=float).reshape(-1, 3)
    assert contour.NumberOfContourPoints == len(points)
    np.testing.assert_array_equal(points[:, 2], 7)
    polygon = shapely.geometry.Polygon(points[:, :2])
    assert polygon.area == pytest.approx(225)
    assert polygon.bounds == (-3, 5, 12, 20)


@pytest.mark.parametrize("inplace", [False, True])
def test_merge_large_un_contour(inplace):
    ds, _ = _structure(False)
    roi = ds.ROIContourSequence[0]
    source = roi.ContourSequence[0]["ContourData"]
    original = source.value
    result = merge_contours(roi, inplace=inplace)
    _assert_square(roi if inplace else result)
    assert source.VR == "UN"
    assert source.value is original
    assert ds.file_meta.TransferSyntaxUID == pydicom.uid.ExplicitVRLittleEndian


def test_merge_command_large_un_contour(tmp_path):
    ds, _ = _structure(False)
    input_path = tmp_path / "input.dcm"
    output_path = tmp_path / "output.dcm"
    ds.save_as(input_path, enforce_file_format=True)
    with pytest.warns(UserWarning, match="64 kByte"):
        merge_contours_cli(
            SimpleNamespace(
                input_file=input_path, output_file=output_path, structures=None
            )
        )
    reloaded = pydicom.dcmread(output_path)
    assert reloaded.file_meta.TransferSyntaxUID == pydicom.uid.ExplicitVRLittleEndian
    # Exercise output re-ingestion as well as the command's write.
    _assert_square(merge_contours(reloaded.ROIContourSequence[0]))


@pytest.mark.parametrize(
    "bad",
    [
        b"SENTINEL",
        b"1\\2",
        b"1\\2\\3",  # triplets, but fewer than Number of Contour Points
        b"1\\2\\nan",
        b"1\\2\\1e999",
        b"1\\2\\\xff",
        b"1\\2\\12345678901234567",
    ],
)
def test_malformed_un_coordinates_are_rejected_without_values(bad):
    ds, _ = _structure(False)
    contour = ds.ROIContourSequence[0].ContourSequence[0]
    contour["ContourData"].value = bad
    with pytest.raises(ValueError, match="Contour Data") as caught:
        pull_structure("SYNTHETIC", ds)
    assert "SENTINEL" not in str(caught.value)
    assert repr(bad) not in str(caught.value)


def test_un_decimal_notation_and_padding():
    ds, _ = _structure(False)
    contour = ds.ROIContourSequence[0].ContourSequence[0]
    contour["ContourData"].value = b" +1.25E+1 \\-.5\\2. "
    contour.NumberOfContourPoints = 1
    x, y, z = pull_structure("SYNTHETIC", ds)
    np.testing.assert_array_equal([x[0][0], y[0][0], z[0][0]], [12.5, -0.5, 2])


@pytest.mark.parametrize("length", [65534, 65536])
def test_explicit_contour_length_boundary(length):
    ds, _ = _structure(False)
    contour = ds.ROIContourSequence[0].ContourSequence[0]
    # 32,766 coordinates, with the first one extended to reach the boundary.
    first = "1" * (length - 65531)
    values = [first] + ["1"] * 32765
    contour["ContourData"].VR = "DS"
    contour.ContourData = values
    contour.NumberOfContourPoints = 10922
    buffer = io.BytesIO()
    if length > 65534:
        with pytest.warns(UserWarning, match="64 kByte"):
            pydicom.dcmwrite(buffer, ds, enforce_file_format=True)
    else:
        pydicom.dcmwrite(buffer, ds, enforce_file_format=True)
    reloaded = pydicom.dcmread(io.BytesIO(buffer.getvalue()))
    element = reloaded.ROIContourSequence[0].ContourSequence[0]["ContourData"]
    assert element.VR == ("UN" if length > 65534 else "DS")
    x, y, z = pull_structure("SYNTHETIC", reloaded)
    assert x[0][0] == float(first)
    np.testing.assert_array_equal(x[0][1:], 1)
    np.testing.assert_array_equal(y[0], 1)
    np.testing.assert_array_equal(z[0], 1)
