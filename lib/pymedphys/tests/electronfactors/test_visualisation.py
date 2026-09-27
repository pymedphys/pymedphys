# Copyright (C) 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Plotting the electron insert factor model."""

from pymedphys._imports import numpy as np
from pymedphys._imports import pandas as pd
from pymedphys._imports import plt, pytest

from pymedphys._electronfactors import visualisation

# Synthetic inserts (cm): every length is at least its width, and the factor
# varies smoothly with both.
WIDTHS = np.array([4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0, 9.5])
LENGTHS = WIDTHS + np.array(
    [0.0, 2.0, 1.0, 3.0, 0.5, 2.5, 1.5, 3.5, 0.0, 2.0, 1.0, 3.0]
)
FACTORS = 0.95 + 0.008 * WIDTHS + 0.002 * (LENGTHS - WIDTHS)


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _scatter_colour_limits(width, length, factor):
    plt.figure()
    visualisation.plot_model(width, length, factor)
    scatter = plt.gca().collections[0]

    return scatter.get_clim()


@pytest.mark.filterwarnings(
    "ignore:Deviations within the electron factor algorithm:UserWarning"
)
def test_plot_model_accepts_pandas_series():
    """Columns of a DataFrame plot exactly as the equivalent NumPy arrays do."""
    from_arrays = _scatter_colour_limits(WIDTHS, LENGTHS, FACTORS)
    from_series = _scatter_colour_limits(
        pd.Series(WIDTHS), pd.Series(LENGTHS), pd.Series(FACTORS)
    )

    assert from_series == pytest.approx(from_arrays)
    assert from_arrays[0] <= FACTORS.min()
    assert from_arrays[1] >= FACTORS.max()
