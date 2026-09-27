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

import logging
import struct
from types import SimpleNamespace

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._pinnacle.pinnacle_exceptions import (
    MissingBeamDoseError,
    MissingCTImageError,
    MissingTrialBeamsError,
)
from pymedphys.pinnacle import PinnacleExport

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
