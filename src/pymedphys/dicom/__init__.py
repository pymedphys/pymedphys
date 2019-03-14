# Copyright (C) 2018 Simon Biggs

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


"""A Dicom toolbox built ontop of the pydicom library.

Available Functions
-------------------
>>> from pymedphys.dicom import (
...     anonymise_dicom,
...     extract_iec_patient_xyz,
...     extract_iec_fixed_xyz,
...     extract_dicom_patient_xyz,
...     load_dose_from_dicom,
...     load_xyz_from_dicom,
...     find_dose_within_structure,
...     create_dvh,
...     get_structure_aligned_cube)
"""

# pylint: disable=W0401,W0614

from ..libutils import clean_and_verify_levelled_modules

from ._level1.dicom_dict_baseline import *
from ._level1.dicom_struct import *
from ._level1.dicom_create import *
from ._level2.header_tweaks import *
from ._level2.dicom_anonymise import *
from ._level2.dicom_dose import *

clean_and_verify_levelled_modules(globals(), [
    '._level2.dicom_dose', '._level1.dicom_create', '._level2.header_tweaks',
    '._level2.dicom_anonymise', '._level1.dicom_struct'
], package='pymedphys.dicom')
