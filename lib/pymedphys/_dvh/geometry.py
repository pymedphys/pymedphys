# pymedphys/_dvh/geometry.py
from __future__ import annotations

from typing import Dict, List, Literal, Optional, Tuple

import numpy as np
from numpy.typing import NDArray

from .endcaps import compute_intervals
from .inclusion import polygon_mask
from .types import DoseGrid, Structure3D, StructureContour

Rule = Literal["even_odd", "winding"]

__all__ = ["voxelise_structure_right_prism", "mask_volume_cc"]


def _xy_mesh_on_dose(
    dose: DoseGrid,
) -> Tuple[NDArray[np.floating], NDArray[np.floating]]:
    """
    Build (X, Y) world-mm meshgrid of voxel centres for a dose frame.

    Assumes standard axial orientation (row→+X, col→+Y); full orientation
    support lands in Sprint 2.
    """
    nz, ny, nx = dose.shape
    dx, dy, _ = dose.spacing_mm
    x0 = dose.origin_ipp_mm[0]
    y0 = dose.origin_ipp_mm[1]
    xs = x0 + dx * np.arange(nx, dtype=float)
    ys = y0 + dy * np.arange(ny, dtype=float)
    X, Y = np.meshgrid(xs, ys)  # (ny, nx)
    return X, Y


def _group_rings_by_plane(
    struct: Structure3D,
) -> Tuple[List[float], List[List[StructureContour]]]:
    zs = struct.plane_zs()
    rings = [struct.planes[z] for z in zs]
    return zs, rings


def voxelise_structure_right_prism(
    struct: Structure3D,
    dose: DoseGrid,
    endcaps: str = "truncate",
    inclusion_rule: Rule = "even_odd",
    single_slice_half_mm: Optional[float] = None,
) -> Tuple[NDArray[np.bool_], Dict[str, object]]:
    """
    Voxelise a Structure3D onto a DoseGrid using right-prism inter-slice handling.

    Special case
    ------------
    For `endcaps="truncate"` with a *single* contour plane, we still assign the
    2-D mask to whichever dose slice centre lies exactly at that z-plane (to a
    small tolerance). This matches commissioning expectations for “area checks”.
    """
    X, Y = _xy_mesh_on_dose(dose)

    plane_zs, rings_per_plane = _group_rings_by_plane(struct)
    if not plane_zs:
        return np.zeros_like(dose.values, dtype=bool), {
            "z_intervals": [],
            "plane_zs": [],
            "used_planes": [-1] * dose.shape[0],
            "endcaps": endcaps,
            "inclusion": inclusion_rule,
        }

    # End-cap intervals per plane
    z_intervals = compute_intervals(
        plane_zs, mode=endcaps, single_slice_half_mm=single_slice_half_mm
    )

    # z-centres of dose frames
    z_worlds = dose.origin_ipp_mm[2] + dose.frame_offsets_mm

    # 2D masks per plane (union of outer rings minus holes)
    plane_masks_2d: List[NDArray[np.bool_]] = []
    for rings in rings_per_plane:
        outers = [r for r in rings if not r.is_hole]
        holes = [r for r in rings if r.is_hole]
        mask_union = np.zeros_like(X, dtype=bool)
        for outer in outers:
            mask_union |= polygon_mask(
                X,
                Y,
                outer.points_mm[:, :2],
                [h.points_mm[:, :2] for h in holes],
                rule=inclusion_rule,
            )
        plane_masks_2d.append(mask_union)

    used_plane_idx = np.full(dose.shape[0], -1, dtype=int)

    # Assign slabs: half-open [low, high)
    for pidx, (low, high) in enumerate(z_intervals):
        sel = (z_worlds >= low - 1e-9) & (z_worlds < high - 1e-9)
        used_plane_idx[sel] = pidx

    # Special-case: exact-on-plane assignment (helps `truncate` single-plane)
    tol = 1e-6
    for pidx, z in enumerate(plane_zs):
        eq = np.isclose(z_worlds, z, atol=tol)
        used_plane_idx[eq] = np.where(eq, pidx, used_plane_idx)[eq]  # assign where true

    # Compose 3D mask
    mask3d = np.zeros_like(dose.values, dtype=bool)
    for z in range(dose.shape[0]):
        pidx = int(used_plane_idx[z])
        if pidx >= 0:
            mask3d[z] = plane_masks_2d[pidx]

    meta = {
        "z_intervals": z_intervals,
        "plane_zs": plane_zs,
        "used_planes": used_plane_idx.tolist(),
        "endcaps": endcaps,
        "inclusion": inclusion_rule,
    }
    return mask3d, meta


def mask_volume_cc(mask: NDArray[np.bool_], dose: DoseGrid) -> float:
    """
    Compute volume (cc) from a boolean mask on the dose grid.

    We derive per-slice thicknesses from mid-plane distances, so non-uniform
    dz is handled correctly; on uniform grids this equals the nominal spacing.
    """
    nz, ny, nx = mask.shape
    dx, dy, _ = dose.spacing_mm

    offs = dose.frame_offsets_mm.astype(float)
    if nz == 1:
        dzs = np.array([dose.spacing_mm[2]], dtype=float)
    else:
        mids = np.zeros(nz + 1, dtype=float)
        mids[1:-1] = 0.5 * (offs[:-1] + offs[1:])
        mids[0] = offs[0] - 0.5 * (offs[1] - offs[0])
        mids[-1] = offs[-1] + 0.5 * (offs[-1] - offs[-2])
        dzs = mids[1:] - mids[:-1]

    voxel_areas = mask.reshape(nz, -1).sum(axis=1) * (dx * dy)
    vol_mm3 = float(np.dot(voxel_areas, dzs))
    return vol_mm3 / 1000.0
