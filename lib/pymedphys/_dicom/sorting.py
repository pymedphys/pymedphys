# OnkoDICOM
# Copyright (C) 2020 Matthew Archer, Stuart Swerdloff

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301
# USA

# ==========================================================================
# The following code was vendored and adjusted from the following location by Simon Biggs
# https://github.com/didymo/OnkoDICOM/blob/cfab3aefb1427ab251a5de3df1b04d729ecd4b5d/src/Model/ImageLoading.py#L112-L130
# ==========================================================================


from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom


def stack_displacement(ds: "pydicom.Dataset") -> float:
    """Create a sorting key for a DICOM file

    Calculate the projection of the image position patient along the
    axis perpendicular to the images themselves, i.e. along the stack
    axis. Intended use is for the sorting key to sort a stack of image
    datasets so that they are in order, regardless of whether the images
    are axial, coronal, or sagittal, and independent from the order in
    which the images were read in.

    Parameters
    ----------
    ds : pydicom.Dataset

    Returns
    -------
    displacement : float
    """
    orientation = ds.ImageOrientationPatient
    position = ds.ImagePositionPatient

    orient_x = np.array(orientation[0:3], dtype=float)
    orient_y = np.array(orientation[3:6], dtype=float)
    orient_z = np.cross(orient_x, orient_y)

    img_pos_patient = np.array(position, dtype=float)
    displacement: float = np.dot(orient_z, img_pos_patient)

    return displacement
