"""Configuration types (RFC section 6.6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class InterpolationMethod(str, Enum):
    """Between-slice contour interpolation method."""

    RIGHT_PRISM = "right_prism"
    SHAPE_BASED = "shape_based"


class EndCapPolicy(str, Enum):
    """Terminal contour slice z-extension policy."""

    NONE = "none"
    HALF_SLICE = "half_slice"
    HALF_SLICE_CAPPED = "half_slice_capped"
    ROUNDED = "rounded"


class OccupancyMethod(str, Enum):
    """Voxel occupancy computation method."""

    BINARY_CENTRE = "binary_centre"
    FRACTIONAL_SUPERSAMPLED = "fractional_supersampled"
    ADAPTIVE_SUPERSAMPLED = "adaptive_supersampled"


class PointInPolygonRule(str, Enum):
    """Point-in-polygon algorithm."""

    SCANLINE_EVEN_ODD = "scanline_even_odd"
    WINDING_NUMBER = "winding_number"


class DoseInterpolationMethod(str, Enum):
    """Dose interpolation method."""

    TRILINEAR = "trilinear"
    TRICUBIC_CATMULL_ROM = "tricubic_catmull_rom"
    TRICUBIC_BSPLINE = "tricubic_bspline"


class DVHType(str, Enum):
    """Which DVH representations to compute."""

    CUMULATIVE = "cumulative"
    DIFFERENTIAL = "differential"
    BOTH = "both"


class InvalidROIPolicy(str, Enum):
    """How to handle invalid ROI geometry."""

    STRICT = "strict"
    REPAIR_IF_SAFE = "repair_if_safe"
    SKIP_INVALID = "skip_invalid"


class FloatingPointPrecision(str, Enum):
    """Internal floating-point precision."""

    FLOAT32 = "float32"
    FLOAT64 = "float64"


@dataclass(frozen=True, slots=True)
class SupersamplingConfig:
    """Controls supersampling behaviour.

    Parameters
    ----------
    factor : int, optional
        Fixed supersampling factor. None means adaptive.
    adaptive_min_voxels : int
        Minimum voxel count for adaptive convergence checks.
    adaptive_convergence_tol : float
        Convergence tolerance for adaptive supersampling.
    adaptive_edge_refinement : bool
        Whether to refine edge voxels adaptively.
    """

    factor: Optional[int] = None
    adaptive_min_voxels: int = 10000
    adaptive_convergence_tol: float = 0.002
    adaptive_edge_refinement: bool = True

    @property
    def is_adaptive(self) -> bool:
        """True if using adaptive supersampling (factor is None)."""
        return self.factor is None

    def __post_init__(self) -> None:
        if self.factor is not None and self.factor < 1:
            raise ValueError(f"Supersampling factor must be >= 1, got {self.factor}")
        if self.adaptive_min_voxels < 1:
            raise ValueError("adaptive_min_voxels must be >= 1")
        if self.adaptive_convergence_tol <= 0:
            raise ValueError("adaptive_convergence_tol must be positive")

    @classmethod
    def adaptive(
        cls,
        min_voxels: int = 10000,
        convergence_tol: float = 0.002,
        edge_refinement: bool = True,
    ) -> SupersamplingConfig:
        """Create an adaptive supersampling config."""
        return cls(
            factor=None,
            adaptive_min_voxels=min_voxels,
            adaptive_convergence_tol=convergence_tol,
            adaptive_edge_refinement=edge_refinement,
        )

    @classmethod
    def fixed(cls, factor: int) -> SupersamplingConfig:
        """Create a fixed-factor supersampling config."""
        return cls(factor=factor)


@dataclass(frozen=True, slots=True)
class AlgorithmConfig:
    """Settings that affect computed results.

    Any change here can produce different outputs from the same inputs.
    """

    interpolation_method: InterpolationMethod = InterpolationMethod.SHAPE_BASED
    endcap_policy: EndCapPolicy = EndCapPolicy.HALF_SLICE
    endcap_max_mm: Optional[float] = None
    occupancy_method: OccupancyMethod = OccupancyMethod.ADAPTIVE_SUPERSAMPLED
    point_in_polygon: PointInPolygonRule = PointInPolygonRule.SCANLINE_EVEN_ODD
    supersampling: SupersamplingConfig = field(
        default_factory=SupersamplingConfig.adaptive
    )
    surface_sampling: bool = True
    dose_interpolation: DoseInterpolationMethod = DoseInterpolationMethod.TRILINEAR
    dvh_bin_width_gy: float = 0.01
    dvh_type: DVHType = DVHType.BOTH
    floating_point_precision: FloatingPointPrecision = FloatingPointPrecision.FLOAT64

    def __post_init__(self) -> None:
        if self.dvh_bin_width_gy <= 0:
            raise ValueError(
                f"dvh_bin_width_gy must be positive, got {self.dvh_bin_width_gy}"
            )
        if (
            self.endcap_policy == EndCapPolicy.HALF_SLICE_CAPPED
            and self.endcap_max_mm is None
        ):
            raise ValueError(
                "endcap_max_mm is required when endcap_policy is 'half_slice_capped'"
            )


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """Settings that affect performance but not results.

    When ``deterministic=True``, changes here should produce
    bit-identical outputs.
    """

    deterministic: bool = True
    max_threads: Optional[int] = None
    batch_size_gb: float = 12.0

    def __post_init__(self) -> None:
        if self.batch_size_gb <= 0:
            raise ValueError(
                f"batch_size_gb must be positive, got {self.batch_size_gb}"
            )
        if self.max_threads is not None and self.max_threads < 1:
            raise ValueError(f"max_threads must be >= 1, got {self.max_threads}")


@dataclass(frozen=True, slots=True)
class PipelinePolicy:
    """Settings controlling import behaviour and error handling."""

    invalid_roi_policy: InvalidROIPolicy = InvalidROIPolicy.REPAIR_IF_SAFE
    anonymise_provenance: bool = False
    z_tolerance_mm: float = 0.01


@dataclass(frozen=True, slots=True)
class DVHConfig:
    """Complete configuration, composed from three orthogonal sub-configs.

    Named profiles (``reference``, ``fast``) are factory methods.
    """

    algorithm: AlgorithmConfig = field(default_factory=AlgorithmConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    policy: PipelinePolicy = field(default_factory=PipelinePolicy)

    @classmethod
    def reference(cls) -> DVHConfig:
        """High-accuracy reference mode.

        TENTATIVE — pending benchmark calibration.
        """
        return cls(
            algorithm=AlgorithmConfig(
                interpolation_method=InterpolationMethod.SHAPE_BASED,
                endcap_policy=EndCapPolicy.ROUNDED,
                occupancy_method=OccupancyMethod.ADAPTIVE_SUPERSAMPLED,
                point_in_polygon=PointInPolygonRule.WINDING_NUMBER,
                supersampling=SupersamplingConfig.adaptive(
                    min_voxels=40000,
                    convergence_tol=0.001,
                    edge_refinement=True,
                ),
                surface_sampling=True,
                dvh_bin_width_gy=0.005,
                dvh_type=DVHType.BOTH,
            ),
            runtime=RuntimeConfig(
                deterministic=True,
                max_threads=1,
            ),
        )

    @classmethod
    def fast(cls) -> DVHConfig:
        """Speed-optimised practical mode.

        TENTATIVE — pending benchmark calibration.
        """
        return cls(
            algorithm=AlgorithmConfig(
                interpolation_method=InterpolationMethod.RIGHT_PRISM,
                endcap_policy=EndCapPolicy.HALF_SLICE,
                occupancy_method=OccupancyMethod.FRACTIONAL_SUPERSAMPLED,
                point_in_polygon=PointInPolygonRule.SCANLINE_EVEN_ODD,
                supersampling=SupersamplingConfig.fixed(3),
                surface_sampling=False,
                dvh_bin_width_gy=0.01,
                dvh_type=DVHType.CUMULATIVE,
            ),
            runtime=RuntimeConfig(deterministic=True),
        )
