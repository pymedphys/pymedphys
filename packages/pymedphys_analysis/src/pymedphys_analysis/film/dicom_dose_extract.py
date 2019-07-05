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

from pymedphys.dicom import (
    xyz_axes_from_dataset, dose_from_dataset)


def dicom_dose_extract(dicom_dose_dataset, grid_axes):
    """Interpolates across a DICOM dose dataset.

    Parameters
    ----------
    dicom_dose_dataset : pydicom.Dataset
        An RT DICOM Dose object
    grid_axes : tuple(z, y, x)
        A tuple of coordinates in DICOM order, z axis first, then y, then x
        where x, y, and z are DICOM axes.
    """

    interp_z = np.array(grid_axes[0], copy=False)[:, None, None]
    interp_y = np.array(grid_axes[1], copy=False)[None, :, None]
    interp_x = np.array(grid_axes[2], copy=False)[None, None, :]

    x, y, z = xyz_axes_from_dataset(dicom_dose_dataset)  # pylint: disable=invalid-name
    dose = dose_from_dataset(dicom_dose_dataset, reshape=False)

    interpolation = RegularGridInterpolator((z, y, x), dose)
    result = interpolation((interp_z, interp_y, interp_x))

    return result
