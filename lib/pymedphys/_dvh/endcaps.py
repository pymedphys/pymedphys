# pymedphys/_dvh/endcaps.py
"""
End-cap policies for inter-slice structure volume (Sprint 1).

Provides interval construction for 'truncate' and 'half_slice' modes. The result
defines z-intervals (in mm) for which each available in-slice polygon should be
applied by a right-prism voxeliser.

Conventions
-----------
- Input plane positions `z_planes_mm` must be sorted ascending.
- Intervals are half-open: [z_low, z_high)
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import List, Literal, Optional, Sequence, Tuple

import numpy as np

Mode = Literal["truncate", "half_slice"]

__all__ = ["compute_intervals"]


def compute_intervals(
    z_planes_mm: Sequence[float],
    mode: Mode = "truncate",
    single_slice_half_mm: Optional[float] = None,
) -> List[Tuple[float, float]]:
    """
    Compute [z_low, z_high) intervals per plane according to the chosen policy.

    Parameters
    ----------
    z_planes_mm : sorted sequence of z in mm
    mode : 'truncate' | 'half_slice'
    single_slice_half_mm : optional half-length to use when there is a single plane
        and mode is 'half_slice'. If omitted, emits a WARNING and uses 0.0 mm.

    Returns
    -------
    intervals : list of (z_low, z_high) for each plane (same length as z_planes_mm)
    """
    zs = np.asarray(z_planes_mm, dtype=float)
    if zs.ndim != 1 or zs.size == 0:
        raise ValueError("z_planes_mm must be a non-empty 1D sequence.")
    if not np.all(np.diff(zs) >= -1e-9):
        raise ValueError("z_planes_mm must be sorted ascending.")

    n = zs.size
    if mode == "truncate":
        # [z_k, z_{k+1}) for all but the last; last has empty interval
        intervals: List[Tuple[float, float]] = []
        for k in range(n):
            if k < n - 1:
                intervals.append((float(zs[k]), float(zs[k + 1])))
            else:
                intervals.append((float(zs[k]), float(zs[k])))  # empty
        return intervals

    if mode == "half_slice":
        if n == 1:
            if single_slice_half_mm is None:
                warnings.warn(
                    "half_slice requested for a single-plane structure but no "
                    "`single_slice_half_mm` provided; using 0 mm end-caps.",
                    stacklevel=2,
                )
                half_inf = half_sup = 0.0
            else:
                half_inf = half_sup = float(single_slice_half_mm)
            z0 = float(zs[0])
            return [(z0 - half_inf, z0 + half_sup)]

        # Multiple planes: local half-distances
        dz = np.diff(zs)
        intervals = []
        for k in range(n):
            if k == 0:
                half_inf = 0.5 * float(dz[0])
            else:
                half_inf = 0.5 * float(dz[k - 1])
            if k == n - 1:
                half_sup = 0.5 * float(dz[-1])
            else:
                half_sup = 0.5 * float(dz[k])
            intervals.append((float(zs[k] - half_inf), float(zs[k] + half_sup)))
        return intervals

    raise ValueError(f"Unknown end-cap mode: {mode}")
