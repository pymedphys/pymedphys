# -*- coding: utf-8 -*-
"""
Validation harness:

- Nelms cylinder & cone in 1D linear gradients (SI/AP)
- Gaussian-in-sphere (Walker & Byrne-style synthetic) for small-volume rigour

All numerical DVHs are produced via `compute_dvh` and compared to
closed-form ground truth. RMS differences are returned for assertions.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..analytical.nelms import nelms_cone_v, nelms_cylinder_v
from ..dvh import DVHConfig, compute_dvh

__all__ = ["validate_nelms_cone_cyl", "validate_gaussian_sphere"]


def _linear_gradient_dose(shape, dmin, dmax, axis):
    """Create a 1D linear gradient dose grid in Gy across `axis` (0,1,2)."""
    K, R, C = shape
    grid = np.linspace(float(dmin), float(dmax), shape[axis], dtype=np.float64)
    if axis == 0:
        grad = grid[:, None, None]
    elif axis == 1:
        grad = grid[None, :, None]
    else:
        grad = grid[None, None, :]
    return np.broadcast_to(grad, shape).copy()


def _mask_cylinder(
    shape, radius_mm=12.0, height_mm=24.0, vox_mm=(1.0, 1.0, 1.0), axis="Y"
):
    """Voxelised right circular cylinder, centred in the grid."""
    K, R, C = shape
    dz, dy, dx = vox_mm
    kz = (np.arange(K) + 0.5) * dz
    ry = (np.arange(R) + 0.5) * dy
    cx = (np.arange(C) + 0.5) * dx

    zc = kz.mean()
    yc = ry.mean()
    xc = cx.mean()

    Z, Y, X = np.meshgrid(kz, ry, cx, indexing="ij")

    if axis.upper() == "Y":
        # Axis along Y (SI): circular cross-section in XZ; height along Y
        radial2 = (X - xc) ** 2 + (Z - zc) ** 2
        cond_r = radial2 <= radius_mm**2
        cond_h = np.abs(Y - yc) <= height_mm / 2.0
        return np.where(cond_r & cond_h, 1.0, 0.0).astype(np.float64)
    else:
        # Axis along Z (AP): circular cross-section in XY; height along Z
        radial2 = (X - xc) ** 2 + (Y - yc) ** 2
        cond_r = radial2 <= radius_mm**2
        cond_h = np.abs(Z - zc) <= height_mm / 2.0
        return np.where(cond_r & cond_h, 1.0, 0.0).astype(np.float64)


def _mask_cone(shape, radius_mm=12.0, height_mm=24.0, vox_mm=(1.0, 1.0, 1.0), axis="Y"):
    """Voxelised right circular cone, base radius R, height H, centred, apex at -H/2 along axis."""
    K, R, C = shape
    dz, dy, dx = vox_mm
    kz = (np.arange(K) + 0.5) * dz
    ry = (np.arange(R) + 0.5) * dy
    cx = (np.arange(C) + 0.5) * dx

    zc = kz.mean()
    yc = ry.mean()
    xc = cx.mean()

    Z, Y, X = np.meshgrid(kz, ry, cx, indexing="ij")

    if axis.upper() == "Y":
        # Axis along Y (SI): radius grows linearly from apex (yc - H/2) to base (yc + H/2)
        y0 = yc - height_mm / 2.0
        t = (Y - y0) / height_mm  # 0..1 across the cone
        t = np.clip(t, 0.0, 1.0)
        r_here = t * radius_mm
        radial2 = (X - xc) ** 2 + (Z - zc) ** 2
        return np.where(radial2 <= r_here**2, 1.0, 0.0).astype(np.float64)
    else:
        # Axis along Z (AP)
        z0 = zc - height_mm / 2.0
        t = (Z - z0) / height_mm
        t = np.clip(t, 0.0, 1.0)
        r_here = t * radius_mm
        radial2 = (X - xc) ** 2 + (Y - yc) ** 2
        return np.where(radial2 <= r_here**2, 1.0, 0.0).astype(np.float64)


def validate_nelms_cone_cyl(
    cfg: DVHConfig,
    shape: str = "cylinder",
    grad: str = "SI",
    radius_mm: float = 12.0,
    height_mm: float = 24.0,
    vox_mm: tuple[float, float, float] = (1.0, 1.0, 1.0),
    grid: tuple[int, int, int] = (47, 47, 47),
) -> tuple[float, float]:
    """
    Build Nelms cylinder or cone with a 1D linear dose gradient and compare
    numerical DVH to analytical curve. Returns (RMS, dx95) where dx95 is
    the absolute difference at D95.

    grad:
      - "SI" -> gradient along IEC Y (superior/inferior)
      - "AP" -> gradient along IEC Z (anterior/posterior)
    """
    K, R, C = grid
    # Dose range as in Nelms: 4..28 Gy across the 24 mm structure extent
    dmin, dmax = 4.0, 28.0
    axis = 1 if grad.upper() == "SI" else 2

    dose = _linear_gradient_dose((K, R, C), dmin, dmax, axis=axis)

    if shape.lower() == "cylinder":
        mask = _mask_cylinder(
            (K, R, C),
            radius_mm,
            height_mm,
            vox_mm,
            axis=("Y" if grad.upper() == "SI" else "Z"),
        )
        if grad.upper() == "SI":

            def f_true(D):
                return nelms_cylinder_v(D, dmin, dmax, "SI")
        else:

            def f_true(D):
                return nelms_cylinder_v(D, dmin, dmax, "AP")
    elif shape.lower() == "cone":
        mask = _mask_cone((K, R, C), radius_mm, height_mm, vox_mm)
        if grad.upper() == "SI":

            def f_true(D):
                return nelms_cone_v(D, dmin, dmax, "SI")
        else:

            def f_true(D):
                return nelms_cone_v(D, dmin, dmax, "AP")
    else:
        raise ValueError("shape must be 'cylinder' or 'cone'")

    edges, cum = compute_dvh(dose, mask, vox_mm, cfg)

    # Compare on a dense, common dose grid
    Dgrid = edges
    Vtrue = f_true(Dgrid)
    Vnum = cum

    diffs = Vnum - Vtrue
    rms = float(np.sqrt(np.mean(diffs * diffs)))

    # D95 comparison (volume 95% → dose where cumulative crosses 0.95)
    # We invert the cumulative DVH numerically.
    def inv_cum(V):
        return np.interp(V, Vnum[::-1], Dgrid[::-1], left=Dgrid[-1], right=Dgrid[0])

    d95_num = inv_cum(0.95)
    d95_true = float(
        np.interp(0.95, Vtrue[::-1], Dgrid[::-1], left=Dgrid[-1], right=Dgrid[0])
    )
    dx95 = float(abs(d95_num - d95_true))

    return rms, dx95


def validate_gaussian_sphere(
    cfg: DVHConfig,
    R_mm: float = 10.0,
    vox_mm: float = 1.0,
    grid: int = 160,
    A: float = 10.0,
) -> float:
    """
    Gaussian dose centred in a spherical ROI: analytic reference and numerical DVH.

    Dose: D(r) = A * exp(-r^2 / (2 σ^2)) with σ = R, centred on the grid.
    Returns RMS difference between analytic and numerical cumulative DVH.

    Reference derivation aligns with Walker & Byrne (Gaussian-in-sphere).  :contentReference[oaicite:7]{index=7}
    """
    K = R = C = grid
    dz = dy = dx = float(vox_mm)
    z = (np.arange(K) + 0.5) * dz
    y = (np.arange(R) + 0.5) * dy
    x = (np.arange(C) + 0.5) * dx
    zc, yc, xc = z.mean(), y.mean(), x.mean()

    Z, Y, X = np.meshgrid(z, y, x, indexing="ij")
    r = np.sqrt((X - xc) ** 2 + (Y - yc) ** 2 + (Z - zc) ** 2)

    dose = A * np.exp(-(r**2) / (2.0 * (R_mm**2)))
    mask = (r <= R_mm).astype(np.float64)

    edges, cum = compute_dvh(dose, mask, (dz, dy, dx), cfg)

    # Analytic cumulative DVH: within a sphere of radius R with centre at peak,
    # the tail at dose D corresponds to radius r(D) = σ sqrt(2 ln(A/D)), and
    # V(D) = 4π/3 * r(D)^3 / (4π/3 * R^3) for 0 <= r(D) <= R ; else 1 (D<=A*e^{-R^2/(2σ^2)}) or 0.
    σ = R_mm

    def r_of_D(D):
        D = np.clip(D, a_min=1e-16, a_max=A)
        return σ * np.sqrt(2.0 * np.log(A / D))

    Dgrid = edges
    rD = r_of_D(Dgrid)
    Vtrue = np.where(rD <= 0.0, 1.0, np.where(rD >= R_mm, 0.0, (rD / R_mm) ** 3))
    # That's fractional volume within r(D); but our cumulative is ≥ D (i.e., r <= r(D)),
    # so Vtrue as computed is correct.

    diffs = cum - Vtrue
    rms = float(np.sqrt(np.mean(diffs * diffs)))
    return rms
