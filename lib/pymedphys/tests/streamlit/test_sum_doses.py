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

"""The sum doses app shows grid-mismatch warnings that Streamlit only logs."""

from unittest import mock

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.dose import dose_from_dataset
from pymedphys.tests.dicom._synthetic_rtdose import rtdose

pytest.importorskip("streamlit")

# pylint: disable = wrong-import-position, protected-access
from pymedphys._experimental.streamlit.apps import sum_doses  # noqa: E402


def _datasets(shift_mm):
    reference = rtdose("HFS")
    shifted = rtdose("HFS", position=(100.0 + shift_mm, -200.0, 300.0))
    for ds in (reference, shifted):
        ds.PatientID = "SYNTHETIC"
    return reference, shifted


@pytest.mark.pydicom
def test_accepted_grid_mismatch_is_shown_to_the_user():
    reference, shifted = _datasets(0.05)

    with mock.patch.object(sum_doses, "st") as st:
        summed = sum_doses._sum_doses_showing_warnings([reference, shifted])

    st.warning.assert_called_once()
    message = st.warning.call_args.args[0]
    assert "differ by up to 0.05 mm" in message
    np.testing.assert_allclose(
        dose_from_dataset(summed), 2 * dose_from_dataset(reference), rtol=1e-6
    )


@pytest.mark.pydicom
def test_coincident_grids_show_no_warning():
    reference, shifted = _datasets(0.0)

    with mock.patch.object(sum_doses, "st") as st:
        sum_doses._sum_doses_showing_warnings([reference, shifted])

    st.warning.assert_not_called()


@pytest.mark.pydicom
def test_rejected_grid_mismatch_states_the_limit():
    reference, shifted = _datasets(0.2)

    with (
        mock.patch.object(sum_doses, "st"),
        pytest.raises(ValueError, match="within 0.1 mm"),
    ):
        sum_doses._sum_doses_showing_warnings([reference, shifted])
