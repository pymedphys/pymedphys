# Copyright (C) 2021 Cancer Care Associates
# Copyright (C) 2020 Matthew Archer, Stuart Swerdloff
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# ======================================================================
# The code within this file was vendored and adjusted from
# https://github.com/didymo/OnkoDICOM/blob/cfab3aefb1427ab251a5de3df1b04d729ecd4b5d/src/Model/ImageLoading.py#L112-L130
# The original code was under an LGPL 2.1 or later license. It was
# relicensed to be under the Apache-2.0 with permission from Stuart
# Swerdloff, see
# https://github.com/pymedphys/pymedphys/pull/1458#discussion_r598630630
# ======================================================================


from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom  # pylint: disable=unused-import


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
