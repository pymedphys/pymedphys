# Copyright (C) 2024 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Fast linear interpolation for 1D, 2D, and 3D data. Available functions include:

This module provides functions for efficient linear interpolation of 1D, 2D, and 3D
data using NumPy and Numba. It includes both a high-level interface (`interp`) and
lower-level functions for specific dimensionalities.

Key Features:
- Fast linear interpolation for 1D, 2D, and 3D data
- Support for both grid-based and point-based interpolation
- Numba-accelerated core interpolation functions
- Input validation and error checking
- Visualization tool for comparing original and interpolated data

Main Functions:
- interp: High-level interface for linear interpolation
- interp_linear_1d, interp_linear_2d, interp_linear_3d: Dimension-specific interpolation
- plot_interp_comparison_heatmap: Visualize original vs interpolated data

Dependencies:
- NumPy
- Numba
- Matplotlib
- SciPy (for comparison function)

Example:
    import numpy as np
    from pymedphys import interp

    # Define known data
    x = np.linspace(0, 10, 11)
    y = np.linspace(0, 10, 11)
    z = np.linspace(0, 10, 11)
    values = np.random.rand(11, 11, 11)

    # Define interpolation points
    x_interp = np.linspace(0, 10, 21)
    y_interp = np.linspace(0, 10, 21)
    z_interp = np.linspace(0, 10, 21)

    # Perform interpolation
    interpolated_values = interp(
        [x, y, z], values, axes_interp=[x_interp, y_interp, z_interp]
    )

For more detailed information, refer to the individual function docstrings.
"""

# ruff: noqa: F401
from ._interp.interp import (
    interp,
    interp_linear_1d,
    interp_linear_2d,
    interp_linear_3d,
    plot_interp_comparison_heatmap,
)
