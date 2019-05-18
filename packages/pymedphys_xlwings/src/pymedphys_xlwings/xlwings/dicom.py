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
from scipy.interpolate import RegularGridInterpolator

import pydicom
import xlwings as xw

from pymedphys_utilities.utilities import wildcard_file_resolution
from pymedphys_dicom.dicom import (
    extract_depth_dose, extract_profiles, load_dicom_data)


def arbitrary_profile_from_dicom_dose(
        ds,
        depth_adjust,
        inplane_ref,
        crossplane_ref,
        depth_ref):
    inplane, crossplane, depth, dose = load_dicom_data(ds, depth_adjust)

    interpolation_function = RegularGridInterpolator(
        (depth, crossplane, inplane), dose)
    points = [
        (a_depth_val, a_crossplane_val, an_inplane_val)
        for a_depth_val, a_crossplane_val, an_inplane_val
        in zip(depth_ref, crossplane_ref, inplane_ref)
    ]

    interpolated_dose = interpolation_function(points)

    return interpolated_dose


@xw.func
@xw.arg('dicom_path')
@xw.arg('depth_adjust')
@xw.arg('averaging_distance')
@xw.ret(expand='table')
def depth_dose(dicom_path, depth_adjust, averaging_distance=0):
    dicom_path_found = wildcard_file_resolution(dicom_path)

    ds = pydicom.read_file(dicom_path_found, force=True)

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
    dicom_path_found = wildcard_file_resolution(dicom_path)

    ds = pydicom.read_file(dicom_path_found, force=True)

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
    dicom_path_found = wildcard_file_resolution(dicom_path)

    ds = pydicom.read_file(dicom_path_found, force=True)

    _, _, crossplane, crossplane_dose = extract_profiles(
        ds, depth_adjust, depth_lookup, averaging_distance)

    return np.vstack([crossplane, crossplane_dose]).T


@xw.func
@xw.arg('dicom_path')
@xw.arg('depth_adjust')
@xw.arg('inplane', np.array, empty=np.nan)
@xw.arg('crossplane', np.array, empty=np.nan)
@xw.arg('depth', np.array, empty=np.nan)
@xw.ret(expand='table')
def arbitrary_profile(dicom_path, depth_adjust, inplane, crossplane, depth):
    dicom_path_found = wildcard_file_resolution(dicom_path)

    inplane_ref = np.invert(np.isnan(inplane))
    crossplane_ref = np.invert(np.isnan(crossplane))
    depth_ref = np.invert(np.isnan(depth))

    reference = inplane_ref & crossplane_ref & depth_ref

    ds = pydicom.read_file(dicom_path_found, force=True)

    dose = arbitrary_profile_from_dicom_dose(
        ds, depth_adjust, inplane[reference], crossplane[reference],
        depth[reference])

    result = np.ones_like(inplane) * np.nan
    result[reference] = dose

    return np.vstack([result]).T
