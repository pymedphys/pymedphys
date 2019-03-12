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


import numpy as np

import pydicom

try:
    import xlwings as xw
    HAS_XLWINGS = True
except ImportError:
    HAS_XLWINGS = False

from ...dicom import (
    extract_depth_dose, extract_profiles, interpolating_profile_extract)

from ...libutils import get_imports
IMPORTS = get_imports(globals())


if HAS_XLWINGS:
    @xw.func
    @xw.arg('dicom_path')
    @xw.arg('depth_adjust')
    @xw.arg('averaging_distance')
    @xw.ret(expand='table')
    def depth_dose(dicom_path, depth_adjust, averaging_distance=0):
        ds = pydicom.read_file(dicom_path, force=True)

        depth, depth_dose_values = extract_depth_dose(
            ds, depth_adjust, averaging_distance)

        return np.vstack([depth, depth_dose_values]).T

    @xw.func
    @xw.arg('dicom_path')
    @xw.arg('depth_adjust')
    @xw.arg('depth_lookup')
    @xw.arg('averaging_distance')
    @xw.ret(expand='table')
    def inplane_profile(dicom_path, depth_adjust, depth_lookup, averaging_distance=0):
        ds = pydicom.read_file(dicom_path, force=True)

        inplane, inplane_dose, _, _ = extract_profiles(
            ds, depth_adjust, depth_lookup, averaging_distance)

        return np.vstack([inplane, inplane_dose]).T

    @xw.func
    @xw.arg('dicom_path')
    @xw.arg('depth_adjust')
    @xw.arg('depth_lookup')
    @xw.arg('averaging_distance')
    @xw.ret(expand='table')
    def crossplane_profile(dicom_path, depth_adjust, depth_lookup, averaging_distance=0):
        ds = pydicom.read_file(dicom_path, force=True)

        _, _, crossplane, crossplane_dose = extract_profiles(
            ds, depth_adjust, depth_lookup, averaging_distance)

        return np.vstack([crossplane, crossplane_dose]).T

    @xw.func
    @xw.arg('dicom_path')
    @xw.arg('depth_adjust')
    @xw.arg('depth_lookup')
    @xw.arg('averaging_distance')
    @xw.ret(expand='table')
    def arbitrary_profile(dicom_path, depth_adjust, inplane, crossplane, depth):
        ds = pydicom.read_file(dicom_path, force=True)

        dose = interpolating_profile_extract(
            ds, depth_adjust, inplane, crossplane, depth)

        return np.vstack([dose]).T
