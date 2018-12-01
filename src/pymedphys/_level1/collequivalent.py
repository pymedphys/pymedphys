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
# Affrero General Public License. These aditional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.


def mlc_equivalent_square_fs(seg):
    """
    Returns a weighted average effective field size from the leaf pattern,
    'seg', where 'seg' is a list of tuples (A-leaf, B-leaf) whose elements
    give the distance of the leaf from from the center-line.
    https://aapm.onlinelibrary.wiley.com/doi/10.1118/1.4814441
    """

    def abutted(a, b):
        """ Returns True iff leaf-tips a and b are within 1 mm. """
        TOLERANCE = 0.1
        if abs(a + b) < TOLERANCE:
            return True
        else:
            return False

    MILLENIUM, BRAINLAB = 120, 52
    numLeaves = 2*len(seg)

    # T: leaf thicknesses by leaf pair for MLC models
    if numLeaves == MILLENIUM:
        T = [1.0 for i in range(10)] + \
            [0.5 for i in range(40)] + \
            [1.0 for i in range(10)]
    elif numLeaves == BRAINLAB:
        T = [0.55 for i in range(3)] + \
            [0.45 for i in range(3)] + \
            [0.3 for i in range(14)] + \
            [0.45 for i in range(3)] + \
            [0.55 for i in range(3)]

    # Y: y component of distance from (0,0) to leaf center by leaf pair
    Y = [(-0.5*sum(T) + sum(T[:i]) + 0.5*T[i]) for i in range(len(T))]

    # effective field size from effective width and length
    area, effX, effY, numer, denom = 0.0, 0.0, 0.0, 0.0, 0.0
    for i in range(len(seg)):
        A, B = seg[i][0], seg[i][1]
        # zero for closed leaf-pairs
        if not abutted(A, B):
            area += T[i]*(A+B)
            # zero for leaf past mid-line
            A, B = max(0.0, A), max(0.0, B)
            distSqrA = Y[i]**2 + A**2
            distSqrB = Y[i]**2 + B**2
            numer += T[i] * A/distSqrA + T[i] * B/distSqrB
            denom += (T[i] / distSqrA) + (T[i] / distSqrB)
    try:
        effX = 2.0 * numer / denom
        effY = area / effX
        return 2.0*effX*effY/(effX+effY)
    except ZeroDivisionError:
        return 0.0
