# lib/pymedphys/tests/dvh/test_metrics_and_precision.py
import numpy as np

from pymedphys._dvh.dvh import dvh_metrics, precision_band


def test_dvh_metrics_and_precision_band():
    # Build a toy cumulative DVH (fraction), decreasing linearly 1 -> 0 over [0..10] Gy
    d = np.linspace(0.0, 10.0, 1001)
    v = 1.0 - d / 10.0

    m = dvh_metrics(
        d, v, vtot_cc=10.0, percent_metrics=(50,), abs_volume_metrics_cc=(0.03,)
    )
    assert abs(m["Dmean"] - 5.0) < 1e-3
    assert abs(m["D50"] - 5.0) < 1e-3
    assert m["Vtotal_cc"] == 10.0

    # Precision band with n_eff samples should be +/- 0.5/n around v
    n_eff = 2000
    lo, hi = precision_band(d, v, n_eff)
    # first bin
    assert abs((hi[0] - lo[0]) - (1.0 / n_eff)) < 1e-12
    # bands monotone
    assert np.all(np.diff(lo) <= 1e-12)
    assert np.all(np.diff(hi) <= 1e-12)
