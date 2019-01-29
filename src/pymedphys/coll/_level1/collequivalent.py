# Copyright (C) 2018 Paul King

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


from ...libutils import get_imports
IMPORTS = get_imports(globals())


def abutted(a, b, tolerance=1):
    """ Returns True iff leaf-tips a and b are within 1 mm. """
    if abs(a + b) < tolerance:
        return True
    else:
        return False


def mlc_equivalent_square_fs(mlc_segments, leaf_pair_widths):
    """
    Returns a weighted average effective field size from the leaf pattern,
    `mlc_segments`, where `mlc_segments` is a list of tuples (A-leaf, B-leaf)
    whose elements give the distance of the leaf from from the center-line
    with distance defined in mm.
    https://aapm.onlinelibrary.wiley.com/doi/10.1118/1.4814441
    """

    assert len(leaf_pair_widths) == len(mlc_segments), (
        'Length of `leaf_pair_widths` ({}) needs to match length of '
        '`mlc_segments` ({})'.format(len(leaf_pair_widths), len(mlc_segments))
    )

    # y_component: y component of distance from (0,0) to leaf center by leaf
    # pair
    y_component = [
        (
            -0.5*sum(leaf_pair_widths) +
            sum(leaf_pair_widths[:i]) +
            0.5*leaf_pair_widths[i])
        for i in range(len(leaf_pair_widths))
    ]

    # effective field size from effective width and length
    area, eff_x, eff_y, numer, denom = 0.0, 0.0, 0.0, 0.0, 0.0
    for i in range(len(mlc_segments)):
        segment_a, segment_b = mlc_segments[i][0], mlc_segments[i][1]
        # zero for closed leaf-pairs
        if not abutted(segment_a, segment_b):
            area += leaf_pair_widths[i]*(segment_a+segment_b)
            # zero for leaf past mid-line
            segment_a, segment_b = max(0.0, segment_a), max(0.0, segment_b)
            distSqrA = y_component[i]**2 + segment_a**2
            distSqrB = y_component[i]**2 + segment_b**2
            numer += leaf_pair_widths[i] * segment_a / \
                distSqrA + leaf_pair_widths[i] * segment_b/distSqrB
            denom += (leaf_pair_widths[i] / distSqrA) + \
                (leaf_pair_widths[i] / distSqrB)
    try:
        eff_x = 2.0 * numer / denom
        eff_y = area / eff_x
        return 2.0*eff_x*eff_y/(eff_x+eff_y)
    except ZeroDivisionError:
        return 0.0
