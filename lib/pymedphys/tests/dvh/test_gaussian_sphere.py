from pymedphys._dvh.config import DVHConfig
from pymedphys._dvh.validate.harness import validate_gaussian_sphere


def test_gaussian_sphere_rigour():
    cfg = DVHConfig(
        inplane_supersample=4,
        axial_supersample=2,
        subvoxel_dose_sample=True,
        dvh_bins=2000,
    )
    rms = validate_gaussian_sphere(cfg, R_mm=10.0)
    assert rms < 1.0  # percent RMS
