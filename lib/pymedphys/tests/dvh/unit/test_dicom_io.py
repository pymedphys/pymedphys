# tests/dvh/unit/test_dicom_io.py
from __future__ import annotations

import numpy as np
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence as DicomSequence

from pymedphys._dvh.dicom_io import load_rt_dose, load_rtstruct, load_study


def _make_test_rtdose() -> Dataset:
    ds = Dataset()
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.481.2"  # RT Dose
    ds.SOPInstanceUID = "1.2.826.0.1.3680043.2.1125.1"
    ds.Modality = "RTDOSE"
    ds.FrameOfReferenceUID = "1.2.3.4"
    ds.Rows = 2
    ds.Columns = 3
    ds.NumberOfFrames = 2
    ds.ImagePositionPatient = [10.0, 20.0, 30.0]
    ds.ImageOrientationPatient = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    ds.PixelSpacing = [2.0, 3.0]  # (dy, dx)
    ds.GridFrameOffsetVector = [0.0, 5.0]
    ds.DoseUnits = "GY"
    ds.DoseGridScaling = 0.01
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1

    arr = np.asarray(
        [
            [[100, 110, 120], [130, 140, 150]],  # frame 0
            [[200, 210, 220], [230, 240, 250]],  # frame 1
        ],
        dtype=np.uint16,
    )
    ds.PixelData = arr.tobytes()
    return ds


def _make_test_rtstruct(for_uid: str) -> Dataset:
    ds = Dataset()
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.481.3"  # RT Struct
    ds.Modality = "RTSTRUCT"
    # ReferencedFrameOfReferenceSequence
    fr_item = Dataset()
    fr_item.FrameOfReferenceUID = for_uid
    ds.ReferencedFrameOfReferenceSequence = DicomSequence([fr_item])

    # StructureSetROISequence: one ROI
    roi_item = Dataset()
    roi_item.ROINumber = 1
    roi_item.ROIName = "PTV66"
    roi_item.ReferencedFrameOfReferenceUID = for_uid
    ds.StructureSetROISequence = DicomSequence([roi_item])

    # ROIContourSequence + ContourSequence
    roi_contour = Dataset()
    roi_contour.ReferencedROINumber = 1

    c0 = Dataset()
    c0.ContourGeometricType = "CLOSED_PLANAR"
    # square on z = 30 mm
    c0.ContourData = [
        10.0,
        20.0,
        30.0,
        16.0,
        20.0,
        30.0,
        16.0,
        26.0,
        30.0,
        10.0,
        26.0,
        30.0,
    ]
    c1 = Dataset()
    c1.ContourGeometricType = "CLOSED_PLANAR"
    # square on z = 35 mm
    c1.ContourData = [
        10.5,
        20.5,
        35.0,
        15.5,
        20.5,
        35.0,
        15.5,
        25.5,
        35.0,
        10.5,
        25.5,
        35.0,
    ]
    roi_contour.ContourSequence = DicomSequence([c0, c1])

    ds.ROIContourSequence = DicomSequence([roi_contour])
    return ds


def test_load_rt_dose_values_and_geometry():
    ds = _make_test_rtdose()
    grid = load_rt_dose(ds)

    assert grid.values.shape == (2, 2, 3)
    # Scaling to Gy
    assert np.isclose(grid.values[0, 0, 0], 100 * 0.01)
    assert np.isclose(grid.values[1, 1, 2], 250 * 0.01)

    # Geometry checks
    p000 = grid.index_to_world(0, 0, 0)
    assert np.allclose(p000, np.array([10.0, 20.0, 30.0]))

    # (0,0,1) adds 3 mm in x (row)
    p001 = grid.index_to_world(0, 0, 1)
    assert np.allclose(p001, np.array([13.0, 20.0, 30.0]))

    # (0,1,0) adds 2 mm in y (col)
    p010 = grid.index_to_world(0, 1, 0)
    assert np.allclose(p010, np.array([10.0, 22.0, 30.0]))

    # frame 1 adds 5 mm in z (normal)
    p100 = grid.index_to_world(1, 0, 0)
    assert np.allclose(p100, np.array([10.0, 20.0, 35.0]))


def test_load_rtstruct_two_planes_and_names():
    dose = _make_test_rtdose()
    rtstruct = _make_test_rtstruct(for_uid=str(dose.FrameOfReferenceUID))
    structs = load_rtstruct(rtstruct)

    assert "PTV66" in structs
    s = structs["PTV66"]
    zs = s.plane_zs()
    assert np.allclose(zs, [30.0, 35.0])
    assert s.num_contours() == 2
    assert s.frame_of_reference_uid == str(dose.FrameOfReferenceUID)


def test_load_study_basic_integration():
    dose = _make_test_rtdose()
    rtstruct = _make_test_rtstruct(for_uid=str(dose.FrameOfReferenceUID))
    study = load_study(rtstruct=rtstruct, rtdose=dose)

    assert study.dose.values.shape == (2, 2, 3)
    assert "PTV66" in study.structures

    # A structure point should lie inside the spatial span of the dose grid
    pt = np.array([10.0, 20.0, 30.0])
    corners = study.dose.corners_world()
    mins = corners.min(axis=0)
    maxs = corners.max(axis=0)
    assert np.all(pt >= mins - 1e-6)
    assert np.all(pt <= maxs + 1e-6)
