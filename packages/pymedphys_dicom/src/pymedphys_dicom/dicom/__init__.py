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

"""A DICOM toolbox. Available functions include:

>>> from pymedphys.dicom import (
...
...     # General functions
...     anonymise_dataset,
...     anonymise_file,
...     anonymise_directory,
...     is_anonymised_dataset,
...     is_anonymised_file,
...     is_anonymised_directory,
...     coords_from_xyz_axes
...     xyz_axes_from_dataset,
...
...     # RT Structure related functions
...     get_structure_aligned_cube,
...
...     # Functions using a combination of DICOM Modalities
...     find_dose_within_structure,
...     create_dvh)
"""

# pylint: disable=W0401,W0614

from pymedphys_utilities.libutils import clean_and_verify_levelled_modules

from ._level1.constants import *
from ._level1.coords import *
from ._level1.create import *
from ._level1.structure import *
from ._level2.header_tweaks import *
from ._level2.anonymise import *
from ._level2.dose import *
from ._level3.dicom_collection import *


clean_and_verify_levelled_modules(globals(), [
    '._level1.coords',
    '._level1.create',
    '._level2.header_tweaks',
    '._level1.structure',
    '._level2.anonymise',
    '._level2.dose',
    '._level3.dicom_collection'
], package='pymedphys_dicom.dicom')
