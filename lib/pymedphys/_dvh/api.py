# pymedphys/_dvh/api.py
"""
Public-facing helpers (subset) for Sprint 1.

Provides `inspect_structure` to derive basic geometry stats, end-cap policy and
evidence-based warnings before DVH calculation.

This is intentionally light; larger DVH APIs land in later sprints.
"""

from __future__ import annotations

import statistics
import warnings
from typing import Dict, Literal, Optional, Tuple

import numpy as np

from .geometry import mask_volume_cc, voxelise_structure_right_prism
from .types import DoseGrid, Structure3D

EndCaps = Literal["truncate", "half_slice"]

__all__ = ["inspect_structure"]


def inspect_structure(
    dose: DoseGrid,
    struct: Structure3D,
    endcaps: EndCaps = "truncate",
    inclusion_rule: Literal["even_odd", "winding"] = "even_odd",
    single_slice_half_mm: Optional[float] = None,
) -> Dict[str, object]:
    """
    Voxelise a structure and report volume and spacing stats with clinical warnings.

    Warnings
    --------
    - Non-uniform z spacings varying > 0.2 mm
    - Few-slice structures (<= 7 planes)
    - Small-volume structures (< 1 cc)
    """
    zs = struct.plane_zs()
    slice_count = len(zs)
    z_spacings = [float(b - a) for a, b in zip(zs[:-1], zs[1:])]

    # Non-uniform spacing warning
    if len(z_spacings) >= 2:
        if (max(z_spacings) - min(z_spacings)) > 0.2:
            warnings.warn(
                f"Non-uniform inter-slice spacing for '{struct.name}' varies by "
                f"{(max(z_spacings) - min(z_spacings)):.3f} mm (>0.2 mm). "
                "This can affect DVH precision.",
                stacklevel=2,
            )

    # Few-slice warning
    if slice_count <= 7:
        warnings.warn(
            f"Structure '{struct.name}' has only {slice_count} axial slice(s) (<= 7). "
            "Expect increased DVH variability, particularly for SRS-sized volumes.",
            stacklevel=2,
        )

    # Voxelise and compute volume
    mask, meta = voxelise_structure_right_prism(
        struct,
        dose,
        endcaps=endcaps,
        inclusion_rule=inclusion_rule,
        single_slice_half_mm=single_slice_half_mm,
    )
    vol_cc = mask_volume_cc(mask, dose)

    # Small-volume warning
    if vol_cc < 1.0:
        warnings.warn(
            f"Structure '{struct.name}' volume is {vol_cc:.3f} cc (< 1 cc). "
            "DVH metrics can vary materially; consider SRS settings/tolerances.",
            stacklevel=2,
        )

    z_stats = {
        "count": slice_count,
        "min_mm": min(z_spacings) if z_spacings else 0.0,
        "median_mm": statistics.median(z_spacings) if z_spacings else 0.0,
        "max_mm": max(z_spacings) if z_spacings else 0.0,
    }

    return {
        "name": struct.name,
        "volume_cc": vol_cc,
        "z_spacing_mm": z_stats,
        "endcaps": endcaps,
        "inclusion": inclusion_rule,
        "warnings": [],  # warnings emitted via warnings.warn; retained here for future structured logging
        "meta": meta,
    }
