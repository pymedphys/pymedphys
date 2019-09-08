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


def field_points_to_compare(
    side_length,
    penumbra_width,
    rotation,
    num_points_across_penumbra=11,
    num_points_across_field_edge=51,
):
    """Points for comparison for field centre finding.

    Creates two sets of points centred around the origin designed
    so that by shifting the points by the centre to be tested and then
    comparing a function looked up at one set, to that at the other set
    a profile centre can be found.
    """


def penumbra_flip_diff(field, centre_to_test, side_length, penumbra_width, rotation):
    """Find sum of squares difference between penumbras when flipped

    Parameters
    ----------
    field : function
        A function that has x, and y as input, and intensity as output.
    centre_to_test : tuple
        The x and y coords of the centre being tested.
    field_width : float
        The square field width
    penumbra_width : float
        The penumbra width of the field.
    rotation : float
        The clockwise rotation in degrees that the field has undergone.

    Returns
    -------
    sum_of_squares_diff : float
        The sum of squares difference between the field edges flipped
        about the provided centre.
    """
