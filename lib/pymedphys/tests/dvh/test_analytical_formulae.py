import numpy as np

from pymedphys._dvh.analytical.nelms import nelms_cylinder_v


def test_nelms_means_match_pepin():
    # Linear 1D gradient from 4 to 28 Gy across a cylinder must give mean 16 Gy
    D = np.linspace(4.0, 28.0, 10001)
    for g in ("SI", "AP"):
        V = nelms_cylinder_v(D, 4.0, 28.0, g)
        # For a cumulative DVH, mean = Dmin + ∫ V(D) dD over [Dmin, Dmax]
        Dmean = 4.0 + np.trapz(V, D)
        assert abs(Dmean - 16.0) < 0.05


def test_gaussian_sphere_limits():
    # sanity: tails bounded [0,1] at extremes
    D = np.array([0.0, 1e-6, 10.0, 1e6])
    V = nelms_cylinder_v(D, 4.0, 28.0, "SI")
    assert V[0] == 1.0 and V[-1] == 0.0
