# Copyright (C) 2018 PyMedPhys Contributors

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

import warnings

from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())

MILLENIUM = (10,)*10 + (5,)*40 + (10,)*10
BRAINLAB = (5.5,)*3 + (4.5,)*3 + (3,)*14 + (4.5,)*3 + (5.5,)*3
AGILITY = (5,)*80


ALL_TYPES = {
    'Millenium': MILLENIUM,
    'BrainLab': BRAINLAB,
    'Agility': AGILITY
}

LENGTH_MAP = {
    len(leaf_pair_widths): (name, leaf_pair_widths)
    for name, leaf_pair_widths in ALL_TYPES.items()
}


def autodetect_leaf_pair_widths(number_of_mlc_pairs):
    try:
        collimator_name, leaf_pair_widths = LENGTH_MAP[number_of_mlc_pairs]
        warnings.warn(
            (
                'Based on number of segments provided the collimator type '
                '{} has automatically been chosen. Please define '
                'leaf_widths parameter if this is not correct.'
            ).format(collimator_name), UserWarning)
    except KeyError:
        raise ValueError(
            'Please define leaf_widths parameter')

    return leaf_pair_widths
