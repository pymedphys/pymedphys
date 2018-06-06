import numpy as np
from pymedphys.level1.mudensity import calc_mu_density
# import matplotlib.pyplot as plt

regress_test_arrays = np.load('mu_density_example_arrays.npz')

mu = regress_test_arrays['mu']
mlc = regress_test_arrays['mlc']
jaw = regress_test_arrays['jaw']

cached_grid_xx, cached_grid_yy, cached_mu_density = regress_test_arrays['mu_density']

grid_xx, grid_yy, mu_density = calc_mu_density(mu, mlc, jaw)

assert np.all(grid_xx == cached_grid_xx)
assert np.all(grid_yy == cached_grid_yy)
assert np.all(mu_density == cached_mu_density)

# plt.pcolormesh(
#     grid_xx,
#     grid_yy,
#     mu_density)
# plt.colorbar()
# plt.title('MU density')
# plt.xlabel('MLC direction (mm)')
# plt.ylabel('Jaw direction (mm)')
# plt.gca().invert_yaxis()