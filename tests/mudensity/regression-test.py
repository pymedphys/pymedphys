import numpy as np
from pymedphys.level1.mudensity import calc_mu_density

regress_test_arrays = np.load('mu_density_example_arrays.npz')

mu = regress_test_arrays['mu']
mlc = regress_test_arrays['mlc']
jaw = regress_test_arrays['jaw']

cached_mu_density = regress_test_arrays['mu_density']

mu_density = calc_mu_density(mu, mlc, jaw)
assert np.all(mu_density == cached_mu_density)