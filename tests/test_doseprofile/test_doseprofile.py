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

import os
import numpy as np

from pymedphys.devices import read_mapcheck_txt

DATA_DIRECTORY = os.path.abspath(
    os.path.join(os.path.dirname(__file__),
                 os.pardir, 'data', 'doseprofile'))


def test_crossings():
    """ """
    simple_cross = read.Scan()
    simple_cross.x, simple_cross.y, t = [0, 1], [0, 1], 0.5
    assert crossings(simple_cross, t) == [0.5]

    flat_section = read.Scan()
    flat_section.x, flat_section.y, t = [0, 1, 2], [0, 0, 1], 0.5
    assert crossings(flat_section, t) == [1.5]

    double_cross = read.Scan()
    double_cross.x, double_cross.y, t = [0, 1, 2], [0, 0, 1], 0.5
    assert crossings(double_cross, t) == [1.5]

    above_bounds = read.Scan()
    above_bounds.x, above_bounds.y, t = [0, 1, 2], [0, 0, 1], 0.5
    assert crossings(above_bounds, t) == [1.5]

    below_bounds = read.Scan()
    below_bounds.x, below_bounds.y, t = [0, 1, 2], [0, 0, 1], 0.5
    assert crossings(below_bounds, t) == [1.5]

    simple_pulse = read.Scan()
    simple_pulse.x = [-10.1, -9.9, 9.9, 10.1]
    simple_pulse.y = [0.0, 1.0, 1.0, 0.0]
    assert crossings(simple_pulse, 0.5) == [-10.0, 10.0]

    print 'crossings passed'


if __name__ == "__main__":
    test_read_mapcheck_txt()
