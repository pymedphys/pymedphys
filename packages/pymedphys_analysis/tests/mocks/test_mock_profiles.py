# Copyright (C) 2019 Cancer Care Associates

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

from pymedphys_analysis.mocks.profiles import (
    scaled_penumbra_sig, gaussian_cdf, create_dummy_profile_function)


def test_scaled_penumbra():
    profile_shoulder_edges = [0.7, 0.8, 0.9]

    for profile_shoulder_edge in profile_shoulder_edges:
        sig = scaled_penumbra_sig(profile_shoulder_edge)
        np.testing.assert_allclose(
            gaussian_cdf([-0.5, 0, 0.5], sig=sig),
            [1 - profile_shoulder_edge, 0.5, profile_shoulder_edge]
        )


def test_dummy_profile():
    x = [-5, -1, 0, 1, 3, 5, 7, 9, 10, 11, 15]
    centre = 5
    field_width = 10
    penumbra_width = 2
    expected_dummy_profile_values = [
        0, 0.2, 0.5, 0.8, 1, 1, 1, 0.8, 0.5, 0.2, 0]

    dummy_profile = create_dummy_profile_function(
        centre, field_width, penumbra_width)

    np.testing.assert_allclose(
        expected_dummy_profile_values, dummy_profile(x), atol=0.01
    )
