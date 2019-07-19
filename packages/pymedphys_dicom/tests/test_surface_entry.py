# Copyright (C) 2019 Cancer Care Associates

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version (the "AGPL-3.0+").

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License and the additional terms for more
# details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# ADDITIONAL TERMS are also included as allowed by Section 7 of the GNU
# Affero General Public License. These additional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


import pathlib

import pytest

import pydicom

from pymedphys_dicom.rtplan import get_surface_entry_point
from pymedphys_dicom.dicom import DicomBase

HERE = pathlib.Path(__file__).parent
DATA_DIR = HERE.joinpath('data', 'rtplan')
DICOM_PLAN_FILEPATH = DATA_DIR.joinpath('06MV_plan.dcm')


def test_surface_entry():
    plan = pydicom.read_file(str(DICOM_PLAN_FILEPATH), force=True)

    assert get_surface_entry_point(plan) == (0.0, -300.0, 0.0)

    should_pass = DicomBase.from_dict({
        'BeamSequence': [
            {
                'ControlPointSequence': [
                    {
                        'SurfaceEntryPoint': ["10.0", "20.0", "30.0"]
                    }
                ]
            }
        ]
    })

    assert get_surface_entry_point(should_pass.dataset) == (10.0, 20.0, 30.0)

    should_fail_with_no_points = DicomBase.from_dict({
        'BeamSequence': [
            {
                'ControlPointSequence': []
            }
        ]
    })

    with pytest.raises(ValueError):
        assert get_surface_entry_point(should_fail_with_no_points.dataset)

    should_fail_with_differing_points = DicomBase.from_dict({
        'BeamSequence': [
            {
                'ControlPointSequence': [
                    {
                        'SurfaceEntryPoint': ["10.0", "20.0", "30.0"]
                    }
                ]
            },
            {
                'ControlPointSequence': [
                    {
                        'SurfaceEntryPoint': ["20.0", "20.0", "30.0"]
                    }
                ]
            },
        ]
    })

    with pytest.raises(ValueError):
        assert get_surface_entry_point(
            should_fail_with_differing_points.dataset)
