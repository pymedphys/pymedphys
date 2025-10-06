import numpy as np

from pymedphys._dvh.config import DVHConfig
from pymedphys._dvh.validate.harness import validate_nelms_cone_cyl


def test_nelms_cylinder_SI_rigour():
    cfg = DVHConfig(inplane_supersample=4, subvoxel_dose_sample=True)
    rms, dx = validate_nelms_cone_cyl(cfg, shape="cylinder", grad="SI")
    assert rms < 1.0  # % RMS
    assert dx < 3.0  # %


def test_nelms_cone_AP_rigour():
    cfg = DVHConfig(inplane_supersample=4, subvoxel_dose_sample=True)
    rms, dx = validate_nelms_cone_cyl(cfg, shape="cone", grad="AP")
    assert rms < 1.5
    assert dx < 4.0
