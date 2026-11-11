# Copyright (C) 2026 Marchant Van der Walt
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

"""Exercise Pinnacle export edge cases without downloading patient datasets."""

import functools
import logging
import struct
from types import SimpleNamespace

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._pinnacle import pinnacle_image, rtstruct
from pymedphys._pinnacle.pinnacle_exceptions import (
    MissingBeamDoseError,
    MissingCTImageError,
    MissingTrialBeamsError,
)
from pymedphys.pinnacle import PinnacleExport, PinnacleImage

pytestmark = pytest.mark.pydicom

VALID_DOSE = struct.pack(">8f", *([1.0] * 8))
ZERO_DOSE = bytes(32)


def _make_plan(path, payloads):
    """Supply a two-voxel-per-axis plan with 1 Gy per valid beam.

    Each beam has 1 cGy/MU at every voxel and is prescribed 100 cGy in
    one fraction. The prescription point lies at the grid centre, so
    normalisation and DICOM scaling should preserve that 1 Gy dose.
    A None payload represents an absent file.
    """
    beams = []
    for index, payload in enumerate(payloads, 1):
        if payload is not None:
            (path / f"plan.Trial.binary.{index:03}").write_bytes(payload)
        beams.append(
            {
                "Name": f"beam{index}",
                "DoseVolume": str(index),
                "PrescriptionName": "rx",
                "PrescriptionPointName": "point",
                "MonitorUnitInfo": {"PrescriptionDose": 100},
            }
        )

    version = {"WriteTimeStamp": "2026-09-25 10:00:00"}
    trial = {
        "ObjectVersion": version,
        "BeamList": beams,
        "PrescriptionList": [{"Name": "rx", "NumberOfFractions": 1}],
    }
    for axis in "XYZ":
        trial[f"DoseGrid .Dimension .{axis}"] = 2
        trial[f"DoseGrid .VoxelSize .{axis}"] = 1
        trial[f"DoseGrid .Origin .{axis}"] = 0

    return SimpleNamespace(
        path=str(path),
        logger=logging.getLogger(__name__),
        patient_position="HFS",
        primary_image=SimpleNamespace(
            image_info=[{"StudyInstanceUID": "1.2.3.4", "FrameUID": "1.2.3.5"}],
            image={"StudyID": "1"},
        ),
        dose_inst_uid="1.2.3.6",
        plan_inst_uid="1.2.3.7",
        struct_inst_uid="1.2.3.8",
        machine_info={},
        plan_info={
            "ObjectVersion": version,
            "PinnacleVersionDescription": "16",
            "PlanName": "Synthetic",
        },
        trial_info=trial,
        pinnacle=SimpleNamespace(
            patient_info={
                "RadiationOncologist": "",
                "FullName": "Synthetic^Test",
                "DOB": "20000101",
                "MedicalRecordNumber": "synthetic",
                "Gender": "M",
                "Comment": "",
            }
        ),
        points=[{"Name": "point", "XCoord": 0, "YCoord": 0, "ZCoord": 0}],
        convert_point=lambda point: [5, -5, -5],
    )


@pytest.mark.parametrize(
    "payloads, expected_dose",
    [
        pytest.param([VALID_DOSE], 1, id="one-valid"),
        pytest.param([VALID_DOSE, VALID_DOSE], 2, id="two-valid"),
        pytest.param([b"", VALID_DOSE], 1, id="empty-first"),
        pytest.param([VALID_DOSE, b""], 1, id="empty-last"),
        pytest.param([ZERO_DOSE, VALID_DOSE], 1, id="zero-first"),
        pytest.param([VALID_DOSE, ZERO_DOSE], 1, id="zero-last"),
        pytest.param([b"", VALID_DOSE, ZERO_DOSE, VALID_DOSE, b""], 2, id="mixed"),
    ],
)
def test_export_dose_preserves_valid_beam_sum(tmp_path, payloads, expected_dose):
    """Read back the actual RTDOSE, checking dose values and its plan reference."""
    plan = _make_plan(tmp_path, payloads)

    PinnacleExport.export_dose(plan, export_path=tmp_path)

    files = list(tmp_path.glob("RD.*.dcm"))
    assert len(files) == 1
    dose = pydicom.dcmread(files[0])
    assert dose.Modality == "RTDOSE"
    assert dose.DoseUnits == "GY"
    assert dose.DoseSummationType == "PLAN"
    assert dose.pixel_array.shape == (2, 2, 2)
    np.testing.assert_allclose(
        dose.pixel_array * dose.DoseGridScaling, expected_dose, rtol=0, atol=1e-6
    )
    assert (
        dose.ReferencedRTPlanSequence[0].ReferencedSOPInstanceUID == plan.plan_inst_uid
    )


@pytest.mark.parametrize("payloads", [[b""], [ZERO_DOSE], [b"", ZERO_DOSE]])
def test_export_dose_rejects_all_empty_beams(tmp_path, payloads):
    plan = _make_plan(tmp_path, payloads)

    with pytest.raises(MissingBeamDoseError, match="All beams"):
        PinnacleExport.export_dose(plan, export_path=tmp_path)

    assert not list(tmp_path.glob("*.dcm"))


@pytest.mark.parametrize("payloads", [[None], [None, VALID_DOSE], [VALID_DOSE, None]])
def test_missing_dose_file_aborts_export(tmp_path, caplog, payloads):
    """A missing file must not crash or result in a partial summed RTDOSE."""
    plan = _make_plan(tmp_path, payloads)

    PinnacleExport.export_dose(plan, export_path=tmp_path)

    assert "Dose file not found:" in caplog.text
    assert "Skipping generating RTDOSE" in caplog.text
    assert not list(tmp_path.glob("*.dcm"))


@pytest.mark.parametrize(
    "exporter",
    [
        PinnacleExport.export_dose,
        PinnacleExport.export_plan,
        PinnacleExport.export_struct,
    ],
)
def test_exports_reject_missing_primary_image(tmp_path, exporter):
    plan = _make_plan(tmp_path, [])
    plan.primary_image = None

    with pytest.raises(MissingCTImageError, match="no primary image"):
        exporter(plan, export_path=tmp_path)

    assert not list(tmp_path.glob("*.dcm"))


@pytest.mark.parametrize(
    "exporter", [PinnacleExport.export_dose, PinnacleExport.export_plan]
)
@pytest.mark.parametrize("beam_list", [[], None])
def test_exports_reject_missing_trial_beams(tmp_path, exporter, beam_list):
    plan = _make_plan(tmp_path, [])
    plan.trial_info["BeamList"] = beam_list

    with pytest.raises(MissingTrialBeamsError, match="No Beams"):
        exporter(plan, export_path=tmp_path)

    assert not list(tmp_path.glob("*.dcm"))


@pytest.fixture
def utf8_default_open(monkeypatch):
    """Make UTF-8 the default encoding of the Pinnacle readers' ``open``.

    ``open`` without an encoding uses the locale's, which is UTF-8 on Linux
    and macOS but usually code page 1252 on Windows, where every Latin-1
    letter decodes as in ISO 8859-1. A UTF-8 default makes the tests below
    fail without an explicit encoding on every platform. An encoding given
    in the call takes precedence over this default.
    """
    utf8_open = functools.partial(open, encoding="utf-8")
    for module in (pinnacle_image, rtstruct):
        monkeypatch.setattr(module, "open", utf8_open, raising=False)


@pytest.mark.usefixtures("utf8_default_open")
def test_image_header_is_read_as_latin_1(tmp_path):
    """Read the image header as ISO 8859-1 (Latin-1), whatever the default encoding.

    The exporter reads Pinnacle's other text files as ISO 8859-1, the
    character set that its DICOM files declare (ISO_IR 100). Decoded with
    the locale's encoding instead, these letters cannot be read where that
    encoding is UTF-8, as on Linux and macOS, and the image, RTSTRUCT,
    RTPLAN and RTDOSE exports read this header. Byte 0x81, which code page
    1252 cannot decode, is the control character U+0081 in ISO 8859-1.
    """
    header = "patient_position : HFS\ndb_name : Synthétique^Zoë\x81\n"
    (tmp_path / "ImageSet_0.header").write_bytes(header.encode("iso-8859-1"))
    pinnacle = SimpleNamespace(logger=logging.getLogger(__name__))

    image = PinnacleImage(pinnacle, str(tmp_path), {"ImageSetID": 0})

    assert image.image_header == {
        "patient_position": "HFS",
        "db_name": "Synthétique^Zoë\x81",
    }


@pytest.mark.usefixtures("utf8_default_open")
def test_struct_export_reads_latin_1_roi_names(tmp_path):
    """Export an ROI name from an ISO 8859-1 plan.roi to the RTSTRUCT unchanged.

    Decoded with the locale's encoding instead, the name cannot be read
    where that encoding is UTF-8, as on Linux and macOS.
    """
    roi_name = "Moelle épinière"
    roi_file = (
        f"//  Beginning of ROI: {roi_name}\n"
        "roi={\n"
        "  roiinterpretedtype: ORGAN\n"
        "  color: red\n"
        "//  Curve 1 of 1\n"
        "  curve={\n"
        "    num_points =  3;\n"
        "    points={\n"
        "0 0 0\n"
        "1 0 0\n"
        "1 1 0\n"
        "    };  // End of points for curve 1\n"
        "  }; // End of curve 1\n"
        "}; // End of ROI\n"
    )
    (tmp_path / "plan.roi").write_bytes(roi_file.encode("iso-8859-1"))
    plan = _make_plan(tmp_path, [])
    plan.points = []
    plan.pinnacle.patient_info["ReferringPhysician"] = ""
    plan.primary_image.image_header = {"patient_position": "HFS"}
    plan.primary_image.image_info[0].update(
        TablePosition=0, SeriesUID="1.2.3.9", InstanceUID="1.2.3.10"
    )

    PinnacleExport.export_struct(plan, export_path=tmp_path)

    (struct_file,) = tmp_path.glob("RS.*.dcm")
    structure_set = pydicom.dcmread(struct_file)
    assert structure_set.SpecificCharacterSet == "ISO_IR 100"
    assert structure_set.StructureSetROISequence[0].ROIName == roi_name
