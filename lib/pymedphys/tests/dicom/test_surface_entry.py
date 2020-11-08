# Copyright (C) 2019 Cancer Care Associates

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import pathlib

import pytest

import pydicom

from pymedphys._dicom.collection import DicomBase
from pymedphys._dicom.rtplan import (
    get_surface_entry_point,
    get_surface_entry_point_with_fallback,
)
from pymedphys._dicom.rtplan.core import DICOMEntryMissing

HERE = pathlib.Path(__file__).parent
DATA_DIR = HERE.joinpath("data", "rtplan")
DICOM_PLAN_FILEPATH = DATA_DIR.joinpath("06MV_plan.dcm")


@pytest.mark.pydicom
def test_surface_entry_with_fallback():
    should_fail_with_unsupported_gantry = DicomBase.from_dict(
        {"BeamSequence": [{"ControlPointSequence": [{"GantryAngle": "5.0"}]}]}
    )

    with pytest.raises(ValueError):
        get_surface_entry_point_with_fallback(
            should_fail_with_unsupported_gantry.dataset
        )

    plan_dataset = pydicom.read_file(str(DICOM_PLAN_FILEPATH), force=True)
    for beam in plan_dataset.BeamSequence:
        for control_point in beam.ControlPointSequence:
            try:
                del control_point.SurfaceEntryPoint
            except AttributeError:
                pass

    with pytest.raises(DICOMEntryMissing):
        get_surface_entry_point(plan_dataset)

    assert get_surface_entry_point_with_fallback(plan_dataset) == (0.0, -300.0, 0.0)


@pytest.mark.pydicom
def test_surface_entry():
    plan = pydicom.read_file(str(DICOM_PLAN_FILEPATH), force=True)

    assert get_surface_entry_point(plan) == (0.0, -300.0, 0.0)

    should_pass = DicomBase.from_dict(
        {
            "BeamSequence": [
                {
                    "ControlPointSequence": [
                        {"SurfaceEntryPoint": ["10.0", "20.0", "30.0"]}
                    ]
                }
            ]
        }
    )

    assert get_surface_entry_point(should_pass.dataset) == (10.0, 20.0, 30.0)

    should_fail_with_no_points = DicomBase.from_dict(
        {"BeamSequence": [{"ControlPointSequence": []}]}
    )

    with pytest.raises(DICOMEntryMissing):
        get_surface_entry_point(should_fail_with_no_points.dataset)

    should_fail_with_differing_points = DicomBase.from_dict(
        {
            "BeamSequence": [
                {
                    "ControlPointSequence": [
                        {"SurfaceEntryPoint": ["10.0", "20.0", "30.0"]}
                    ]
                },
                {
                    "ControlPointSequence": [
                        {"SurfaceEntryPoint": ["20.0", "20.0", "30.0"]}
                    ]
                },
            ]
        }
    )

    with pytest.raises(ValueError):
        get_surface_entry_point(should_fail_with_differing_points.dataset)
