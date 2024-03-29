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


def convert_IEC_angle_to_bipolar(input_angle):
    angle = np.copy(input_angle)
    if np.all(angle == 180):
        return angle

    angle[angle > 180] = angle[angle > 180] - 360

    is_180 = np.where(angle == 180)[0]
    not_180 = np.where(np.invert(angle == 180))[0]

    where_closest_left_leaning = np.argmin(
        np.abs(is_180[:, None] - not_180[None, :]), axis=1
    )
    where_closest_right_leaning = (
        len(not_180)
        - 1
        - np.argmin(np.abs(is_180[::-1, None] - not_180[None, ::-1]), axis=1)[::-1]
    )

    closest_left_leaning = not_180[where_closest_left_leaning]
    closest_right_leaning = not_180[where_closest_right_leaning]

    if not np.all(
        np.sign(angle[closest_left_leaning]) == np.sign(angle[closest_right_leaning])
    ):
        raise ValueError(
            "While trying to convert IEC angles to bipolar angles, "
            "unable to automatically determine whether angle is 180 or "
            f" -180. The input angles were {input_angle}"
        )

    angle[is_180] = np.sign(angle[closest_left_leaning]) * angle[is_180]

    return angle
