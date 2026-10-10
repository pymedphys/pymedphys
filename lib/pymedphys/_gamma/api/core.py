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

from ..implementation import gamma_shell


def gamma_dicom(
    dicom_dataset_ref,
    dicom_dataset_eval,
    dose_percent_threshold,
    distance_mm_threshold,
    **kwargs,
):
    axes_reference, dose_reference = zyx_and_dose_from_dataset(dicom_dataset_ref)
    axes_evaluation, dose_evaluation = zyx_and_dose_from_dataset(dicom_dataset_eval)

    gamma = gamma_shell(
        axes_reference,
        dose_reference,
        axes_evaluation,
        dose_evaluation,
        dose_percent_threshold,
        distance_mm_threshold,
        **kwargs,
    )

    return gamma
