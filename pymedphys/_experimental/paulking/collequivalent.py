# Copyright (C) 2018 Paul King

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# The following needs to be removed before leaving the experimental module
# pylint: skip-file

from pymedphys._utilities.constants import AGILITY


def abutted(a, b, tolerance=1):
    """ Returns True iff leaf-tips a and b are within 1 mm. """
    if abs(a + b) < tolerance:
        return True
    else:
        return False


def get_leaf_pair_widths(model):
    model_map = {"agility": AGILITY}

    try:
        return model_map[model]
    except KeyError:
        raise ValueError(
            "{} not implemented only the following are"
            " implemented:\n{}".format(model, model_map.keys())
        )


def mlc_equivalent_square_fs(mlc_segments, leaf_pair_widths):
    """
    Returns a weighted average effective field size from the leaf pattern,
    `mlc_segments`, where `mlc_segments` is a list of tuples (A-leaf, B-leaf)
    whose elements give the distance of the leaf from from the center-line
    with distance defined in mm.
    https://aapm.onlinelibrary.wiley.com/doi/10.1118/1.4814441
    """

    assert len(leaf_pair_widths) == len(mlc_segments), (
        "Length of `leaf_pair_widths` ({}) needs to match length of "
        "`mlc_segments` ({})".format(len(leaf_pair_widths), len(mlc_segments))
    )

    # y_component: y component of distance from (0,0) to leaf center by leaf
    # pair
    y_component = [
        (
            -0.5 * sum(leaf_pair_widths)
            + sum(leaf_pair_widths[:i])
            + 0.5 * leaf_pair_widths[i]
        )
        for i in range(len(leaf_pair_widths))
    ]

    # effective field size from effective width and length
    area, eff_x, eff_y, numer, denom = 0.0, 0.0, 0.0, 0.0, 0.0
    for i in range(len(mlc_segments)):
        segment_a, segment_b = mlc_segments[i][0], mlc_segments[i][1]
        # zero for closed leaf-pairs
        if not abutted(segment_a, segment_b):
            area += leaf_pair_widths[i] * (segment_a + segment_b)
            # zero for leaf past mid-line
            segment_a, segment_b = max(0.0, segment_a), max(0.0, segment_b)
            distSqrA = y_component[i] ** 2 + segment_a ** 2
            distSqrB = y_component[i] ** 2 + segment_b ** 2
            numer += (
                leaf_pair_widths[i] * segment_a / distSqrA
                + leaf_pair_widths[i] * segment_b / distSqrB
            )
            denom += (leaf_pair_widths[i] / distSqrA) + (leaf_pair_widths[i] / distSqrB)
    try:
        eff_x = 2.0 * numer / denom
        eff_y = area / eff_x
        return 2.0 * eff_x * eff_y / (eff_x + eff_y)
    except ZeroDivisionError:
        return 0.0
