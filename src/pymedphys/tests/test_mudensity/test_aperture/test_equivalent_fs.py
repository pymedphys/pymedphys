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


from pymedphys.aperture import mlc_equivalent_square_fs


def test_equivalent_fs():
    """ Compare effective field size for known pattern against benchmark. """
    shape = [(0.0, 0.0) for i in range(14)]
    shape += [(3.03, 2.47), (2.88, 2.46), (3.08, 2.51), (2.86, 2.46),
              (2.88, 2.46), (2.91, 5.04), (2.5, 5.04), (2.55, 4.87),
              (2.38, 4.61), (2.38, 7.04), (2.61, 7.46), (2.48, 6.55),
              (3.02, 6.52), (3.9, 7.2), (4.5, 7.5), (4.5, 7.5), (4.5, 7.5),
              (4.5, 7.5), (4.45, 7.5), (4.0, 7.5), (3.5, 7.5), (3.49, 7.5),
              (3.0, 7.5), (3.0, 7.5), (3.0, 7.5), (2.5, 7.5), (2.5, 7.5),
              (2.49, 6.52)]
    shape += [(0.0, 0.0) for i in range(18)]

    assert abs(mlc_equivalent_square_fs(shape) - 10.725) < 0.05
