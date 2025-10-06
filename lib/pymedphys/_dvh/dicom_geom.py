from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DoseGridGeom:
    """
    DICOM-style dose grid geometry with arbitrary non-uniform frame offsets (gfo).

    Parameters
    ----------
    ipp : (3,) array-like
        ImagePositionPatient (mm) at index (i=0, j=0, k=0).
    u, v, w : (3,) array-like
        Orthonormal direction unit vectors for columns (u), rows (v), and slice normal (w).
    ps_row, ps_col : float
        Pixel spacing (mm) in row (v) and column (u) directions.
    gfo : (K,) array-like
        Grid frame offsets (mm along +w) for each slice k=0..K-1. Must be strictly increasing.
    shape : tuple[int, int, int]
        Grid shape (K, R, C) in (k, i, j) order.
    """

    ipp: np.ndarray
    u: np.ndarray
    v: np.ndarray
    w: np.ndarray
    ps_row: float
    ps_col: float
    gfo: np.ndarray
    shape: tuple

    def __post_init__(self):
        object.__setattr__(self, "ipp", np.asarray(self.ipp, dtype=float))
        u = np.asarray(self.u, dtype=float)
        v = np.asarray(self.v, dtype=float)
        w = np.asarray(self.w, dtype=float)

        # Normalise direction cosines (robust to tiny deviations)
        u = u / np.linalg.norm(u)
        v = v / np.linalg.norm(v)
        w = w / np.linalg.norm(w)
        object.__setattr__(self, "u", u)
        object.__setattr__(self, "v", v)
        object.__setattr__(self, "w", w)

        gfo = np.asarray(self.gfo, dtype=float)
        if gfo.ndim != 1:
            raise ValueError("gfo must be 1D (slice offsets along w, in mm).")
        if not np.all(np.diff(gfo) > 0):
            raise ValueError("gfo must be strictly increasing (non-uniform OK).")
        if len(gfo) != int(self.shape[0]):
            raise ValueError("len(gfo) must equal shape[0] (K).")
        object.__setattr__(self, "gfo", gfo.copy())

        # Coerce to floats once
        object.__setattr__(self, "ps_row", float(self.ps_row))
        object.__setattr__(self, "ps_col", float(self.ps_col))

    @property
    def K(self) -> int:
        return int(self.shape[0])

    @property
    def R(self) -> int:
        return int(self.shape[1])

    @property
    def C(self) -> int:
        return int(self.shape[2])

    # ---------- helpers ----------

    def _gfo_interpolate(self, kf: np.ndarray) -> np.ndarray:
        """Map fractional k -> physical w-offset via linear interpolation over gfo."""
        kf = np.asarray(kf, dtype=float)
        k0 = np.floor(kf).astype(int)
        t = kf - k0

        k0 = np.clip(k0, 0, self.K - 1)
        k1 = np.clip(k0 + 1, 0, self.K - 1)

        w0 = self.gfo[k0]
        w1 = self.gfo[k1]

        # If at the last slice, k1==k0 and t=0 effectively
        w_off = w0 + t * (w1 - w0)
        w_off = np.where(k1 == k0, w0, w_off)
        return w_off

    def _invert_gfo(self, gamma: np.ndarray) -> np.ndarray:
        """Map physical w-offset -> fractional k by inverting piecewise-linear gfo."""
        gamma = np.asarray(gamma, dtype=float)
        # Clamp to domain
        gamma_c = np.clip(gamma, self.gfo[0], self.gfo[-1])

        # idx such that gfo[idx] <= gamma < gfo[idx+1]
        idx = np.searchsorted(self.gfo, gamma_c, side="right") - 1
        idx = np.clip(idx, 0, self.K - 2)

        g0 = self.gfo[idx]
        g1 = self.gfo[idx + 1]
        t = (gamma_c - g0) / (g1 - g0)

        kf = idx.astype(float) + t
        # Handle exact upper boundary
        kf = np.where(gamma >= self.gfo[-1], self.K - 1.0, kf)
        return kf

    # ---------- public API ----------

    def ijk_to_world(self, ijk: np.ndarray) -> np.ndarray:
        ijk = np.asarray(ijk, dtype=float)
        if ijk.shape[-1] != 3:
            raise ValueError("ijk must have last dimension of size 3")
        i = ijk[..., 0]
        j = ijk[..., 1]
        kf = ijk[..., 2]

        u_off = j * self.ps_col
        v_off = i * self.ps_row
        w_off = self._gfo_interpolate(kf)

        # Broadcast-friendly
        p = (
            self.ipp
            + np.expand_dims(u_off, -1) * self.u
            + np.expand_dims(v_off, -1) * self.v
            + np.expand_dims(w_off, -1) * self.w
        )
        return p

    def world_to_ijk(self, world: np.ndarray) -> np.ndarray:
        world = np.asarray(world, dtype=float)
        if world.shape[-1] != 3:
            raise ValueError("world must have last dimension of size 3")
        delta = world - self.ipp

        u_coord = np.tensordot(delta, self.u, axes=([-1], [0]))
        v_coord = np.tensordot(delta, self.v, axes=([-1], [0]))
        w_coord = np.tensordot(delta, self.w, axes=([-1], [0]))

        j = u_coord / self.ps_col
        i = v_coord / self.ps_row
        kf = self._invert_gfo(w_coord)

        return np.stack([i, j, kf], axis=-1)
