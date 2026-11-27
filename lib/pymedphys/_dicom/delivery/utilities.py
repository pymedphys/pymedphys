# Copyright (C) 2019 Cancer Care Associates

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


def jaw_dd2dcm(jaw):
    jaw = np.array(jaw, copy=True)
    jaw[:, 1] = -jaw[:, 1]

    converted_jaw = jaw.astype(str)
    converted_jaw[:, 1] = jaw.astype(str)[:, 0]
    converted_jaw[:, 0] = jaw.astype(str)[:, 1]
    converted_jaw = converted_jaw.tolist()

    return converted_jaw


def mlc_dd2dcm(mlc):
    mlc = np.asarray(mlc)

    dicom_mlc_format = []
    for control_point in mlc:
        concatenated = np.hstack([-control_point[-1::-1, 1], control_point[-1::-1, 0]])
        dicom_mlc_format.append(concatenated.astype(str).tolist())

    return dicom_mlc_format


def angle_dd2dcm(angle):
    # Take each step the short way round, so that a drift across the
    # +/-180 degree boundary, such as 179.9 to -179.9, is a 0.2 degree
    # clockwise step rather than 359.8 degrees counter-clockwise.
    diff = np.diff(angle)
    diff = np.where(np.abs(diff) > 180, diff - np.sign(diff) * 360, diff)
    diff = np.append(diff, 0)
    movement = (np.empty_like(angle)).astype(str)  # pylint: disable = no-member

    movement[diff > 0] = "CW"
    movement[diff < 0] = "CC"
    movement[diff == 0] = "NONE"

    # Copy, so that adding 360 to negative angles leaves the caller's array
    # unchanged.
    converted_angle = np.array(angle)
    converted_angle[converted_angle < 0] = converted_angle[converted_angle < 0] + 360

    converted_angle = converted_angle.astype(str).tolist()

    return converted_angle, movement.tolist()


def gantry_tol_from_gantry_angles(gantry_angles):
    min_diff = np.min(np.diff(sorted(gantry_angles)))
    # The beams lie on a circle, so the gap from the largest angle round to
    # the smallest, across the +/-180 degree boundary, is a spacing too.
    closing_gap = np.min(gantry_angles) + 360 - np.max(gantry_angles)
    min_diff = np.min([min_diff, closing_gap])
    gantry_tol = np.min([min_diff / 2 - 0.1, 3])

    return gantry_tol
