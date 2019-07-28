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
