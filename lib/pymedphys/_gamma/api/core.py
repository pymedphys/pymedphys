# Copyright (C) 2018 Simon Biggs
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from pymedphys._dicom.dose import zyx_and_dose_from_dataset

from ..calculate import gamma


def gamma_dicom(
    dicom_dataset_ref,
    dicom_dataset_eval,
    dose_criterion_percent,
    distance_criterion_mm,
    **kwargs,
):
    """Gamma between two RT Dose datasets, on the reference dataset's grid.

    The axes are in (z, y, x) order, as
    :func:`pymedphys.dicom.zyx_and_dose_from_dataset` returns them. The
    options and the return value are those of :func:`pymedphys.gamma`.
    """
    axes_reference, dose_reference = zyx_and_dose_from_dataset(dicom_dataset_ref)
    axes_evaluation, dose_evaluation = zyx_and_dose_from_dataset(dicom_dataset_eval)

    return gamma(
        axes_reference,
        dose_reference,
        axes_evaluation,
        dose_evaluation,
        dose_criterion_percent,
        distance_criterion_mm,
        **kwargs,
    )
