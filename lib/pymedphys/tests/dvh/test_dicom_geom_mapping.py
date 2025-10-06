# lib/pymedphys/tests/dvh/test_dicom_geom_mapping.py
import numpy as np

from pymedphys._dvh.dicom_io import DoseGridGeom


def test_world_ijk_roundtrip_nonuniform_gfo():
    # 3 slices with non-uniform offsets along w
    gfo = np.array([0.0, 1.7, 3.9], dtype=float)
    geom = DoseGridGeom(
        ipp=np.array([10.0, 20.0, -5.0]),
        u=np.array([1.0, 0.0, 0.0]),
        v=np.array([0.0, 1.0, 0.0]),
        w=np.array([0.0, 0.0, 1.0]),
        ps_row=1.0,
        ps_col=2.0,
        gfo=gfo,
        shape=(3, 32, 40),
    )

    # random ijk in [0, K/R/C)
    rng = np.random.default_rng(42)
    ijk = np.stack(
        [
            rng.uniform(0.0, 2.9, size=1000),
            rng.uniform(0.0, 31.0, size=1000),
            rng.uniform(0.0, 39.0, size=1000),
        ],
        axis=-1,
    )
    world = geom.ijk_to_world(ijk)
    ijk_rt = geom.world_to_ijk(world)

    # round-trip within small tolerance
    diff = np.abs(ijk - ijk_rt)
    assert np.max(diff) < 1e-6
