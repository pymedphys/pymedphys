# Copyright (C) 2018 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# pylint: disable=C0103,C1801


"""End to end regression testing.
"""

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

import pymedphys


@pytest.mark.slow
def test_regression():
    """The results of MetersetMap calculation should not change"""

    data_filepath = pymedphys.data_path("metersetmap_example_arrays.npz")
    regress_test_arrays = np.load(data_filepath)

    mu = regress_test_arrays["mu"]
    mlc = regress_test_arrays["mlc"]
    jaw = regress_test_arrays["jaw"]

    # MetersetMap used to be called mu_density. The regression test data
    # still retains the old name.
    cached_metersetmap = regress_test_arrays["mu_density"]
    metersetmap = pymedphys.metersetmap.calculate(mu, mlc, jaw)
    assert np.allclose(metersetmap, cached_metersetmap, atol=0.1)
