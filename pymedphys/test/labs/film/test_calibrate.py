# Copyright (C) 2019 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import numpy as np

from pymedphys.labs.film import create_dose_function


def test_create_dose_function():
    net_od = [
        0.03321279,
        0.16718541,
        0.21453297,
        0.25253895,
        0.28419923,
        0.30208024,
        0.3075344,
        0.31008735,
        0.3157614,
        0.31611426,
        0.32567696,
        0.33727732,
        0.34633589,
        0.36541121,
        0.37880263,
        0.39419754,
        0.4152226,
        0.43042048,
    ]

    dose = [
        0.0,
        200.0,
        300.0,
        400.0,
        500.0,
        550.0,
        580.0,
        600.0,
        650.0,
        620.0,
        700.0,
        750.0,
        800.0,
        900.0,
        1000.0,
        1100.0,
        1250.0,
        1400.0,
    ]

    baseline_fitted_dose = [
        31.12929272,
        193.62365785,
        289.34866228,
        392.43366586,
        501.12974266,
        573.27868306,
        596.98144741,
        608.35995856,
        634.31168013,
        635.95616367,
        681.91912861,
        741.4117247,
        790.84547747,
        903.97412589,
        991.13790282,
        1099.74637299,
        1263.53372935,
        1393.75250018,
    ]

    dose_function = create_dose_function(net_od, dose)
    assert np.allclose(baseline_fitted_dose, dose_function(net_od), 0.0001, 0.0001)
