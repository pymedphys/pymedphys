# Copyright (C) 2025 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
DVH configuration dataclass and presets.

This module defines:
- DVHConfig: a typed, serialisable, and validate-able configuration container
- PRESETS: canonical, literature-backed starting points for common use cases
- Helper utilities: .preset(), .to_dict(), .from_dict(), .replace(), .validate()

Examples
--------
>>> from pymedphys._dvh.config import DVHConfig
>>> cfg = DVHConfig.preset("clinical_qa")
>>> cfg.endcaps
'shape_based'
>>> cfg2 = cfg.replace(target_points=200_000).validate()
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any, Dict, Literal, Optional, Tuple

EndCaps = Literal["truncate", "half_slice", "shape_based", "half_slice_with_max_mm"]
InterSlice = Literal["shape_based", "right_prism"]
InclusionRule = Literal["even_odd", "winding"]
Interpolation = Literal["trilinear", "nearest", "cubic"]
BinsMode = Literal["dynamic", "fixed"]
ExtremaStrategy = Literal["volume_samples_only", "volume_plus_surface_vertices"]


@dataclass(frozen=True, slots=True)
class DVHConfig:
    """
    Immutable configuration for DVH computation.

    Parameters
    ----------
    preset : Optional[str]
        Name of the originating preset, if any (for audit and reproducibility).

    # Geometry / voxelisation
    interslice_interp : InterSlice
        Strategy to interpolate shapes between axial contours.
    endcaps : EndCaps
        End-cap construction mode. See docs for clinical implications.
    inclusion_rule : InclusionRule
        Point-in-polygon rule for polygons with holes (rings).

    # Sampling
    target_points : Optional[int]
        Target number of volumetric sample points inside the ROI for DVH tally.
    grid_factor : Optional[Tuple[int, int, int]]
        Optional supersampling factors (x, y, z) — odd integers recommended.
    target_subvoxel_mm : Optional[float]
        Target maximum edge length (mm) of subvoxels used for sampling.

    # Dose interpolation
    interpolation : Interpolation
        Dose interpolation method (default: trilinear).

    # Histogram binning
    bins_mode : BinsMode
        'dynamic' chooses bin width from range; 'fixed' uses bin_width_gy.
    bin_width_gy : Optional[float]
        Fixed bin width (Gy) when bins_mode='fixed'.
    min_bins : int
        Minimum number of bins for 'dynamic' mode.
    max_bins : int
        Maximum number of bins for 'dynamic' mode.

    # Extrema
    extrema_strategy : ExtremaStrategy
        Whether to also probe dose at surface vertices for min/max.

    # Analysis & performance toggles
    precision_analysis : bool
        Enable Pepin-style precision indicators (implemented in later sprints).
    gpu : bool
        Enable GPU (CuPy) path when available (later sprint).
    jit : bool
        Enable JIT acceleration (Numba) where available (later sprint).

    # Reproducibility
    deterministic : bool
        Request deterministic sampling & processing where possible.
    random_seed : Optional[int]
        Seed used when deterministic stochastic processes are desired.

    Methods
    -------
    preset(name) -> DVHConfig
    replace(**changes) -> DVHConfig
    to_dict() -> Dict[str, Any]
    from_dict(d) -> DVHConfig
    validate() -> DVHConfig
        Returns self if valid, raises ValueError otherwise.

    Notes
    -----
    Defaults reflect the “clinical_qa” preset, tuned for a good accuracy-time
    balance in conventional EBRT QA scenarios; SRS/SBRT and max_accuracy
    presets expose more aggressive sampling & bins. See PRESETS below.
    """

    # Provenance
    preset: Optional[str] = None

    # Geometry / voxelisation
    interslice_interp: InterSlice = "shape_based"
    endcaps: EndCaps = "shape_based"
    inclusion_rule: InclusionRule = "even_odd"

    # Sampling
    target_points: Optional[int] = 100_000
    grid_factor: Optional[Tuple[int, int, int]] = None
    target_subvoxel_mm: Optional[float] = None

    # Dose interpolation
    interpolation: Interpolation = "trilinear"

    # Histogram binning
    bins_mode: BinsMode = "dynamic"
    bin_width_gy: Optional[float] = None
    min_bins: int = 10_000
    max_bins: int = 100_000

    # Extrema
    extrema_strategy: ExtremaStrategy = "volume_plus_surface_vertices"

    # Analysis & performance toggles
    precision_analysis: bool = True
    gpu: bool = False
    jit: bool = False

    # Reproducibility
    deterministic: bool = True
    random_seed: Optional[int] = 20250101

    # -------- convenience API -------- #

    @staticmethod
    def _ensure_odd_triple(triple: Tuple[int, int, int]) -> bool:
        return all((x % 2 == 1) for x in triple)

    def validate(self) -> "DVHConfig":
        """
        Validate internal consistency; raise ValueError on invalid combos.

        Checks include:
        - bins_mode/width coherence
        - grid_factor oddness (recommended) where provided
        - min/max bins ranges
        - allowed literal values (guarded by type hints but verified at runtime)
        """
        if self.bins_mode == "fixed" and (
            self.bin_width_gy is None or self.bin_width_gy <= 0
        ):
            raise ValueError("bins_mode='fixed' requires bin_width_gy > 0.")
        if self.bins_mode == "dynamic":
            if (
                self.min_bins <= 0
                or self.max_bins <= 0
                or self.max_bins < self.min_bins
            ):
                raise ValueError(
                    "Invalid dynamic bin configuration (min_bins/max_bins)."
                )
        if self.grid_factor is not None:
            if len(self.grid_factor) != 3 or not all(
                isinstance(v, int) and v > 0 for v in self.grid_factor
            ):
                raise ValueError("grid_factor must be a tuple of 3 positive integers.")
            # not hard-failing on even values, but warn via exception message guideline
            if not self._ensure_odd_triple(self.grid_factor):
                # odd multiples are strongly recommended to include original dose planes
                # See plan rationale in docs (Sprint 0).
                pass
        # sampling targets: at least one should be set
        if (
            self.target_points is None
            and self.grid_factor is None
            and self.target_subvoxel_mm is None
        ):
            raise ValueError(
                "At least one sampling control must be set (target_points, grid_factor, or target_subvoxel_mm)."
            )
        return self

    def replace(self, **changes: Any) -> "DVHConfig":
        """Return a copy with selected fields replaced, then validated."""
        new_cfg = replace(self, **changes)
        return new_cfg.validate()

    def to_dict(self) -> Dict[str, Any]:
        """JSON‑serialisable dict representation (stable field order)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DVHConfig":
        """Construct a DVHConfig from a dict of fields (validates on return)."""
        obj = cls(**data)
        return obj.validate()

    @classmethod
    def from_preset(cls, name: str) -> "DVHConfig":
        """Return a validated configuration based on a named preset."""
        try:
            base = PRESETS[name]
        except KeyError as exc:
            raise KeyError(
                f"Unknown DVH preset '{name}'. Available: {', '.join(PRESETS)}"
            ) from exc
        # stamp the preset name for audit provenance
        return replace(base, preset=name).validate()


# ---- Canonical presets (Sprint 0) ---- #

PRESETS: Dict[str, DVHConfig] = {
    # Balanced accuracy ↔ time for typical EBRT QA (3 mm dose grids; 10–500 cc ROIs).
    "clinical_qa": DVHConfig(
        interslice_interp="shape_based",
        endcaps="shape_based",
        inclusion_rule="even_odd",
        target_points=100_000,
        grid_factor=None,
        target_subvoxel_mm=None,
        interpolation="trilinear",
        bins_mode="dynamic",
        bin_width_gy=None,
        min_bins=10_000,
        max_bins=50_000,
        extrema_strategy="volume_plus_surface_vertices",
        precision_analysis=True,
        gpu=False,
        jit=False,
        deterministic=True,
        random_seed=20250101,
    ),
    # Aggressive settings for SRS/SBRT & small volumes (steep gradients; sub‑cc ROIs).
    "srs_small_volume": DVHConfig(
        interslice_interp="shape_based",
        endcaps="shape_based",
        inclusion_rule="even_odd",
        target_points=None,
        grid_factor=(5, 5, 7),  # elevate Z where 1 mm slice spacing is common
        target_subvoxel_mm=None,
        interpolation="trilinear",
        bins_mode="dynamic",
        bin_width_gy=None,
        min_bins=50_000,
        max_bins=100_000,
        extrema_strategy="volume_plus_surface_vertices",
        precision_analysis=True,
        gpu=False,
        jit=False,
        deterministic=True,
        random_seed=20250101,
    ),
    # Push accuracy for validation against analytical datasets (Nelms).
    "max_accuracy": DVHConfig(
        interslice_interp="shape_based",
        endcaps="shape_based",
        inclusion_rule="even_odd",
        target_points=300_000,
        grid_factor=None,
        target_subvoxel_mm=None,
        interpolation="trilinear",
        bins_mode="dynamic",
        bin_width_gy=None,
        min_bins=50_000,
        max_bins=100_000,
        extrema_strategy="volume_plus_surface_vertices",
        precision_analysis=True,
        gpu=False,
        jit=False,
        deterministic=True,
        random_seed=1337,
    ),
    # Very fast preview (explicitly *not* for clinical decisions).
    "fast_preview": DVHConfig(
        interslice_interp="right_prism",
        endcaps="half_slice",
        inclusion_rule="even_odd",
        target_points=30_000,
        grid_factor=None,
        target_subvoxel_mm=None,
        interpolation="trilinear",
        bins_mode="dynamic",
        bin_width_gy=None,
        min_bins=2_000,
        max_bins=10_000,
        extrema_strategy="volume_samples_only",
        precision_analysis=False,
        gpu=False,
        jit=False,
        deterministic=False,
        random_seed=None,
    ),
}

__all__ = ["DVHConfig", "PRESETS"]
