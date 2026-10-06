# Copyright (C) 2026 Vishu

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Check that deformability output is unchanged by the shared bbox patch."""

import numpy as np

from pymedphys._electronfactors.core import calculate_deformability

X_DATA = np.array([4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 5.5, 7.5, 6.5, 8.5])
Y_DATA = np.array([0.90, 1.20, 0.70, 1.00, 0.80, 1.10, 0.60, 0.95, 0.75, 1.15])
Z_DATA = np.array([0.95, 0.93, 1.00, 0.98, 1.01, 0.99, 1.02, 1.00, 1.03, 1.01])

# The first two points sit inside the data. The last two sit outside it,
# which is where the bounding box matters.
X_TEST = np.array([6.0, 7.0, 9.5, 3.0])
Y_TEST = np.array([0.85, 0.90, 1.00, 1.30])

# Recorded from the code before the patch
EXPECTED = np.array(
    [0.18750347930052147, 0.19007797486220168, 0.6699885700149011, 0.9841461896200665]
)


def test_deformability_unchanged():
    result = calculate_deformability(X_TEST, Y_TEST, X_DATA, Y_DATA, Z_DATA)

    np.testing.assert_array_equal(result, EXPECTED)
