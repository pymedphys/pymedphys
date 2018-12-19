# Copyright (C) 2018 Cancer Care Associates

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

"""Working with delivery data from either logfiles or Mosaiq.
"""

from collections import namedtuple

# import attr
import numpy as np

from .._level0.libutils import get_imports
IMPORTS = get_imports(globals())


DeliveryData = namedtuple(
    'DeliveryData',
    ['monitor_units', 'gantry', 'collimator', 'mlc', 'jaw'])


# @attr.s
# class DeliveryData:
#     monitor_units = attr.ib()
#     gantry = attr.ib()
#     collimator = attr.ib()
#     mlc = attr.ib()
#     jaw = attr.ib()


def get_delivery_parameters(delivery_data):
    mu = np.array(delivery_data.monitor_units)  # pylint: disable=C0103
    mlc = np.array(delivery_data.mlc)
    jaw = np.array(delivery_data.jaw)

    return mu, mlc, jaw
