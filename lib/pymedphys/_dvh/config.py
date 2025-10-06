# pymedphys/_dvh/config.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(slots=True, frozen=True)
class DVHConfig:
    """
    Configuration for DVH calculation and voxelisation.

    Notes
    -----
    - endcap_mode='half_slice' mirrors common TPS handling and provides a stable
      baseline for validation; change explicitly if testing alternatives.
    - dose_range=None will derive bins from sampled dose values within the mask.
    """

    voxelise_mode: Literal["right_prism", "marching_tetra"] = "right_prism"
    endcap_mode: Literal["half_slice", "truncate", "extrapolate"] = "half_slice"

    inplane_supersample: int = 1
    axial_supersample: int = 1

    # Number of DVH bins (returned axis are bin centres, length == dvh_bins)
    dvh_bins: int = 1000

    # Optional explicit dose range for histogramming (min Gy, max Gy).
    # If None, it will be inferred from sampled dose values within the mask.
    dose_range: tuple[float, float] | None = None

    # Interpolate dose at sub-voxel points when supersampling mask voxels
    subvoxel_dose_sample: bool = False

    # Compute options (kept for parity; numba not required by the tests)
    numba_parallel: bool = True

    # Optional RNG seed for deterministic any stochastic samplers (unused here)
    seed: int | None = None
