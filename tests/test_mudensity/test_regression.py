import os

import numpy as np
import matplotlib.pyplot as plt

from pymedphys.level1.mudensity import calc_mu_density


DATA_DIRECTORY = os.path.join(os.path.dirname(__file__), "../data")
DELIVERY_DATA_FILEPATH = os.path.join(DATA_DIRECTORY, 'mu_density_example_arrays.npz')

def test_regression(plot=False):
    """The results of MU Density calculation should not change
    """
    regress_test_arrays = np.load(DELIVERY_DATA_FILEPATH)

    mu = regress_test_arrays['mu']
    mlc = regress_test_arrays['mlc']
    jaw = regress_test_arrays['jaw']

    cached_grid_xx, cached_grid_yy, cached_mu_density = regress_test_arrays['mu_density']

    grid_xx, grid_yy, mu_density = calc_mu_density(mu, mlc, jaw)

    assert np.all(grid_xx == cached_grid_xx)
    assert np.all(grid_yy == cached_grid_yy)
    assert np.allclose(mu_density, cached_mu_density)

    if plot:
        plt.pcolormesh(grid_xx, grid_yy, mu_density)
        plt.colorbar()
        plt.title('MU density')
        plt.xlabel('MLC direction (mm)')
        plt.ylabel('Jaw direction (mm)')
        plt.gca().invert_yaxis()

