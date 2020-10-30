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


from copy import deepcopy

from .core import (
    get_fraction_group_beam_sequence_and_meterset,
    get_fraction_group_index,
)


def convert_to_one_fraction_group(dicom_dataset, fraction_group_number):
    created_dicom = deepcopy(dicom_dataset)

    beam_sequence, _ = get_fraction_group_beam_sequence_and_meterset(
        dicom_dataset, fraction_group_number
    )

    created_dicom.BeamSequence = beam_sequence

    fraction_group_index = get_fraction_group_index(
        dicom_dataset, fraction_group_number
    )

    fraction_group = created_dicom.FractionGroupSequence[fraction_group_index]
    created_dicom.FractionGroupSequence = [fraction_group]

    return created_dicom
