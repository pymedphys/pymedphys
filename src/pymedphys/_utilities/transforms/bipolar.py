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


def convert_IEC_angle_to_bipolar(angle):
    angle = np.copy(angle)
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

    assert np.all(
        np.sign(angle[closest_left_leaning]) == np.sign(angle[closest_right_leaning])
    ), "Unable to automatically determine whether angle is 180 or -180"

    angle[is_180] = np.sign(angle[closest_left_leaning]) * angle[is_180]

    return angle
