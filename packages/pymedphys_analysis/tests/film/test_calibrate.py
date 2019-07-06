# Copyright (C) 2019 Simon Biggs

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

from pymedphys_analysis.film import create_dose_function


def test_create_dose_function():
    net_od = [
        0.03321279, 0.16718541, 0.21453297, 0.25253895, 0.28419923, 0.30208024,
        0.3075344, 0.31008735, 0.3157614, 0.31611426, 0.32567696, 0.33727732,
        0.34633589, 0.36541121, 0.37880263, 0.39419754, 0.4152226, 0.43042048
    ]

    dose = [
        0., 200., 300., 400., 500., 550., 580., 600., 650., 620., 700., 750.,
        800., 900., 1000., 1100., 1250., 1400.
    ]

    baseline_fitted_dose = [
        31.12929272, 193.62365785, 289.34866228, 392.43366586, 501.12974266,
        573.27868306, 596.98144741, 608.35995856, 634.31168013, 635.95616367,
        681.91912861, 741.4117247, 790.84547747, 903.97412589, 991.13790282,
        1099.74637299, 1263.53372935, 1393.75250018
    ]

    dose_function = create_dose_function(net_od, dose)
    assert np.allclose(baseline_fitted_dose, dose_function(net_od), 0.01, 0.01)
