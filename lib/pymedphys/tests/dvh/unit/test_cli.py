# tests/dvh/unit/test_cli.py
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pydicom
import pytest
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.sequence import Sequence as DicomSequence
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from pymedphys.cli.__init__ import define_parser  # the real CLI parser (top level)


def _write_rtdose(path: Path) -> Path:
    # Minimal 2-frame, 4x4 RTDOSE in Gy
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.481.2"
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.is_little_endian = True
    ds.is_implicit_VR = False

    ds.SOPClassUID = meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.Modality = "RTDOSE"
    ds.FrameOfReferenceUID = "1.2.3.4"
    ds.Rows = 4
    ds.Columns = 4
    ds.NumberOfFrames = 2
    ds.ImagePositionPatient = [0.0, 0.0, 0.0]
    ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
    ds.PixelSpacing = [2.0, 2.0]  # (dy, dx)
    ds.GridFrameOffsetVector = [0.0, 2.0]  # mm
    ds.DoseUnits = "GY"
    ds.DoseGridScaling = 0.01
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1

    arr = np.arange(2 * 4 * 4, dtype=np.uint16).reshape(2, 4, 4)
    ds.PixelData = arr.tobytes()
    pydicom.dcmwrite(path, ds, write_like_original=False)
    return path


def _write_rtstruct(path: Path, for_uid: str, z_mm: float = 0.0) -> Path:
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.481.3"
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian

    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.is_little_endian = True
    ds.is_implicit_VR = False

    ds.SOPClassUID = meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.Modality = "RTSTRUCT"

    # Per-ROI mapping to FOR
    roi_item = pydicom.Dataset()
    roi_item.ROINumber = 1
    roi_item.ROIName = "PTV66"
    roi_item.ReferencedFrameOfReferenceUID = for_uid
    ds.StructureSetROISequence = DicomSequence([roi_item])

    # ROIContourSequence with one square at z=z_mm
    roi_contour = pydicom.Dataset()
    roi_contour.ReferencedROINumber = 1

    sq = [
        1.0,
        1.0,
        z_mm,
        5.0,
        1.0,
        z_mm,
        5.0,
        5.0,
        z_mm,
        1.0,
        5.0,
        z_mm,
    ]
    c0 = pydicom.Dataset()
    c0.ContourGeometricType = "CLOSED_PLANAR"
    c0.NumberOfContourPoints = 4
    c0.ContourData = sq
    roi_contour.ContourSequence = DicomSequence([c0])
    ds.ROIContourSequence = DicomSequence([roi_contour])

    # Optional top-level FOR for completeness
    rfor = pydicom.Dataset()
    rfor.FrameOfReferenceUID = for_uid
    ds.ReferencedFrameOfReferenceSequence = DicomSequence([rfor])

    pydicom.dcmwrite(path, ds, write_like_original=False)
    return path


def _parser():
    return define_parser()  # integrates dvh_cli via the top-level CLI


def test_cli_presets_list_and_show(capsys):
    parser = _parser()
    args = parser.parse_args(["dvh", "presets"])
    args.func(args)  # prints list
    out = capsys.readouterr().out
    assert "Available DVH presets" in out

    args = parser.parse_args(["dvh", "presets", "--show", "clinical_qa"])
    args.func(args)
    out = capsys.readouterr().out
    assert '"preset": "clinical_qa"' in out


def test_cli_config_override(capsys):
    parser = _parser()
    args = parser.parse_args(
        [
            "dvh",
            "config",
            "--preset",
            "clinical_qa",
            "--override",
            "target_points=200000",
            "--override",
            "precision_analysis=false",
        ]
    )
    args.func(args)
    out = capsys.readouterr().out
    assert '"target_points": 200000' in out
    assert '"precision_analysis": false' in out


def test_cli_audit_writes_json(tmp_path, capsys):
    parser = _parser()
    out = tmp_path / "audit.json"
    dummy = tmp_path / "foo.bin"
    dummy.write_bytes(b"abc")

    args = parser.parse_args(
        [
            "dvh",
            "audit",
            "--preset",
            "clinical_qa",
            "--out",
            str(out),
            str(dummy),
        ]
    )
    args.func(args)
    out_text = out.read_text()
    assert '"package_versions"' in out_text
    captured = capsys.readouterr().out
    assert "Wrote audit JSON" in captured


@pytest.mark.filterwarnings(
    "ignore:Structure .* has only"
)  # depending on test geometry
def test_cli_inspect_struct_json(tmp_path, capsys):
    # Write tiny RTDOSE & RTSTRUCT that overlap at z=0
    rd = _write_rtdose(tmp_path / "RD.dcm")
    rs = _write_rtstruct(tmp_path / "RS.dcm", for_uid="1.2.3.4", z_mm=0.0)
    out = tmp_path / "inspect.json"

    parser = _parser()
    args = parser.parse_args(
        [
            "dvh",
            "inspect-struct",
            "--rtstruct",
            str(rs),
            "--rtdose",
            str(rd),
            "--structure",
            "PTV66",
            "--endcaps",
            "truncate",
            "--json-out",
            str(out),
            "--quiet",
        ]
    )
    args.func(args)

    info = json.loads(out.read_text())
    assert info["name"] == "PTV66"
    assert "volume_cc" in info
