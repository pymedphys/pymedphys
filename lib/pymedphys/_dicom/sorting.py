# Copyright (C) 2021 Cancer Care Associates
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom  # pylint: disable=unused-import

# ==========================================================================
# The remainder of this file is under the LGPL 2.1 or later license.
# This code was vendored and adjusted from the OnkoDICOM library at the
# following location:
# https://github.com/didymo/OnkoDICOM/blob/cfab3aefb1427ab251a5de3df1b04d729ecd4b5d/src/Model/ImageLoading.py#L112-L130
#
# This was undergone by Simon Biggs.
# TODO: Get permission to re-license under the Apache-2.0.
# ==========================================================================


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
    orient_z = np.cross(orient_x, orient_y)  # type: ignore

    img_pos_patient = np.array(position, dtype=float)
    displacement: float = np.dot(orient_z, img_pos_patient)

    return displacement
