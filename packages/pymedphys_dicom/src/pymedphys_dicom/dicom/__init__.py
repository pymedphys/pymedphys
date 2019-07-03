# Copyright (C) 2019 Simon Biggs, Matthew Jennings

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

"""A DICOM toolbox. Available functions include:

>>> from pymedphys.dicom import (
...
...     # Anonymisation functions
...     anonymise_dataset,
...     anonymise_file,
...     anonymise_directory,
...     is_anonymised_dataset,
...     is_anonymised_file,
...     is_anonymised_directory,
...
...     # Coordinate functions
...     coords_from_xyz_axes,
...     xyz_axes_from_dataset,
...
...     # Dose related functions
...     create_dvh,
...     dose_from_dataset,
...     find_dose_within_structure,
...     )
"""

from .anonymise import (
    anonymise_dataset,
    anonymise_file,
    anonymise_directory,
    is_anonymised_dataset,
    is_anonymised_file,
    is_anonymised_directory,
    BASELINE_KEYWORD_VR_DICT,
    IDENTIFYING_KEYWORDS,
    label_dicom_filepath_as_anonymised
)

from .coords import (
    coords_from_xyz_axes,
    xyz_axes_from_dataset
)

from .dose import (
    create_dvh,
    dose_from_dataset,
    find_dose_within_structure,
    extract_depth_dose,
    extract_profiles,
    load_dicom_data,
    axes_and_dose_from_dicom,
    zyx_and_dose_from_dataset
)

from .create import dicom_dataset_from_dict

from .structure import pull_structure, create_contour_sequence_dict, Structure

from .constants import BaselineDicomDictionary
from .collection import DicomBase, DicomDose
from .header import (
    adjust_machine_name, adjust_rel_elec_density, adjust_RED_by_structure_name,
    RED_adjustment_map_from_structure_names)
