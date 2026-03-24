"""Core data types for the PyMedPhys DVH engine.

This module defines the foundational data model for DVH computation:

- ``PlanarContour``: a single closed polygon on one axial slice.
- ``Structure``: a named DICOM ROI composed of planar contours.
- ``DoseGrid``: a rectilinear 3-D dose distribution on DICOM patient axes.
- ``DVHResult``: a cumulative DVH curve with metadata and diagnostics.
- Strategy protocols for point-in-polygon, inter-slice interpolation,
  and end-cap logic, enabling clean strategy-swapping without inheritance.

Design notes
------------
All frozen dataclasses use ``eq=False`` to suppress the default ``__eq__``
that ``@dataclass`` would generate.  This is deliberate: the dataclasses
contain NumPy arrays, and the default equality would delegate to
``ndarray.__eq__``, returning a boolean *array* instead of a scalar.
That breaks container semantics (sets, dicts, ``if obj == other``)
in confusing ways.  With ``eq=False`` every instance compares by identity,
which is safe and predictable.  When element-wise comparison is needed,
callers should use ``numpy.array_equal`` or ``numpy.allclose`` explicitly.

Coordinate contract (§4.2 of the project plan)
-----------------------------------------------
``DoseGrid.values_gy[ix, iy, iz]`` corresponds to
``(axes_mm[0][ix], axes_mm[1][iy], axes_mm[2][iz])``.
This is an axis-indexing contract only; in NumPy C-order the last index
is contiguous in memory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from numbers import Real
from typing import ClassVar, NamedTuple, Protocol, cast, runtime_checkable

import numpy as np
import numpy.typing as npt

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

FloatArray1D = npt.NDArray[np.float64]
FloatArray2D = npt.NDArray[np.float64]
FloatArray3D = npt.NDArray[np.float64]
BoolArray1D = npt.NDArray[np.bool_]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ALLOWED_COMBINATION_MODES = frozenset(
    {
        "auto",
        "xor",
        "slice_union",
        "vendor_compat_xor",
    }
)

_ALLOWED_GEOMETRIC_TYPES = frozenset(
    {
        "CLOSED_PLANAR",
        "CLOSED_PLANAR_XOR",
    }
)

_UNIFORM_SPACING_RTOL: float = 1e-5
_UNIFORM_SPACING_ATOL: float = 1e-8


# ---------------------------------------------------------------------------
# Named tuples
# ---------------------------------------------------------------------------


class ZExtent(NamedTuple):
    """A z-axis extent expressed as ``(z_lower_mm, z_upper_mm)``.

    Interpretation (open vs closed) depends on context:

    - ``EndCapStrategy`` returns a half-open extent ``[z_lower, z_upper)``
      consistent with the slab-ownership convention (§5.3 of the plan).
    - ``Structure.z_extent_mm`` returns a closed extent
      ``[z_first, z_last]`` spanning the first and last contour slices.
    """

    z_lower_mm: float
    z_upper_mm: float


# ---------------------------------------------------------------------------
# PlanarContour
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False, slots=True)
class PlanarContour:
    """A single planar contour in DICOM patient coordinates.

    ``points_xy_mm`` stores XY vertices on one axial slice at ``z_mm``.
    The contour is normalised to a closed polygon by appending the first
    point when needed.  A minimum of three non-closing vertices is required.

    The resulting ``points_xy_mm`` array is made read-only after construction
    to preserve the frozen-dataclass contract.

    Parameters
    ----------
    z_mm : float
        Axial slice position in mm (DICOM patient z).
    points_xy_mm : array-like, shape (N, 2)
        XY vertex coordinates.  Must contain at least 3 non-closing vertices.
    geometric_type : str
        DICOM-derived contour geometric type.  Must be one of
        ``CLOSED_PLANAR`` or ``CLOSED_PLANAR_XOR``.
    """

    z_mm: float
    points_xy_mm: FloatArray2D
    geometric_type: str = "CLOSED_PLANAR"

    def __post_init__(self) -> None:
        geometric_type = str(self.geometric_type)
        if geometric_type not in _ALLOWED_GEOMETRIC_TYPES:
            allowed = ", ".join(sorted(_ALLOWED_GEOMETRIC_TYPES))
            raise ValueError(
                f"PlanarContour.geometric_type must be one of "
                f"{{{allowed}}}; got {geometric_type!r}"
            )

        points_xy_mm = _normalise_planar_points(self.points_xy_mm)

        object.__setattr__(self, "z_mm", float(self.z_mm))
        object.__setattr__(self, "points_xy_mm", points_xy_mm)
        object.__setattr__(self, "geometric_type", geometric_type)


# ---------------------------------------------------------------------------
# Strategy protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class PIPStrategy(Protocol):
    """Return an inclusion mask for query points against one planar contour.

    Parameters
    ----------
    query_points_xy_mm : FloatArray2D
        Shape ``(M, 2)`` array of query-point XY coordinates.
    contour_xy_mm : FloatArray2D
        Shape ``(N, 2)`` array of closed-polygon XY vertices.

    Returns
    -------
    BoolArray1D
        Length-``M`` boolean mask; ``True`` means inside or on boundary.
    """

    def __call__(
        self,
        query_points_xy_mm: FloatArray2D,
        contour_xy_mm: FloatArray2D,
        /,
    ) -> BoolArray1D: ...


@runtime_checkable
class InterSliceStrategy(Protocol):
    """Return an interpolated contour for a requested z position.

    The returned ``PlanarContour`` is constructed at ``z_mm`` with
    interpolated XY vertices derived from the bounding contours.

    Parameters
    ----------
    lower_contour : PlanarContour
        The contour on the slice immediately below ``z_mm``.
    upper_contour : PlanarContour
        The contour on the slice immediately above ``z_mm``.
    z_mm : float
        The target axial position for interpolation.

    Returns
    -------
    PlanarContour
        A new contour at ``z_mm`` with interpolated vertex positions.
    """

    def __call__(
        self,
        lower_contour: PlanarContour,
        upper_contour: PlanarContour,
        z_mm: float,
        /,
    ) -> PlanarContour: ...


@runtime_checkable
class EndCapStrategy(Protocol):
    """Return the z extent owned by an end contour for the chosen rule.

    The returned ``ZExtent`` expresses a half-open interval
    ``[z_lower_mm, z_upper_mm)`` consistent with the project's
    slab-ownership convention (§5.3).

    Parameters
    ----------
    contour : PlanarContour
        The terminal (inferior or superior) contour.
    neighbour_spacing_mm : float
        The axial spacing to the nearest neighbouring contour slice.
    is_superior : bool
        ``True`` if this is the most-superior (highest-z) end contour.

    Returns
    -------
    ZExtent
        The half-open z extent owned by this end contour.
    """

    def __call__(
        self,
        contour: PlanarContour,
        neighbour_spacing_mm: float,
        is_superior: bool,
        /,
    ) -> ZExtent: ...


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False, slots=True)
class Structure:
    """A named DICOM structure (ROI), preserving contour ordering semantics.

    Contours are sorted by ``z_mm`` during initialisation so downstream code
    can rely on monotonic slice order.
    """

    name: str
    number: int
    contours: tuple[PlanarContour, ...]
    colour_rgb: tuple[int, int, int] | None = None
    combination_mode: str = "auto"
    coordinate_frame: str = "DICOM_PATIENT"

    def __post_init__(self) -> None:
        contours = tuple(self.contours)
        for contour in contours:
            if not isinstance(contour, PlanarContour):
                raise TypeError(
                    "Structure.contours must contain only PlanarContour instances"
                )

        sorted_contours = tuple(sorted(contours, key=lambda c: c.z_mm))

        if self.colour_rgb is not None:
            colour_rgb = _normalise_colour_rgb(self.colour_rgb)
            object.__setattr__(self, "colour_rgb", colour_rgb)

        combination_mode = str(self.combination_mode)
        if combination_mode not in _ALLOWED_COMBINATION_MODES:
            allowed = ", ".join(sorted(_ALLOWED_COMBINATION_MODES))
            raise ValueError(
                f"Structure.combination_mode must be one of "
                f"{{{allowed}}}; got {combination_mode!r}"
            )

        coordinate_frame = str(self.coordinate_frame)
        if not coordinate_frame:
            raise ValueError("Structure.coordinate_frame must be a non-empty string")

        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(self, "number", int(self.number))
        object.__setattr__(self, "contours", sorted_contours)
        object.__setattr__(self, "combination_mode", combination_mode)
        object.__setattr__(self, "coordinate_frame", coordinate_frame)

    @property
    def z_extent_mm(self) -> ZExtent:
        """Closed z-extent ``[z_first, z_last]`` spanning the contour slices.

        Returns the z positions of the most-inferior and most-superior
        contours.  Requires at least one contour.

        Raises
        ------
        ValueError
            If the structure has no contours.
        """
        if not self.contours:
            raise ValueError("Structure has no contours; z_extent_mm is undefined")
        return ZExtent(
            z_lower_mm=self.contours[0].z_mm,
            z_upper_mm=self.contours[-1].z_mm,
        )


# ---------------------------------------------------------------------------
# DoseGrid
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False, slots=True)
class DoseGrid:
    """A rectilinear dose grid sampled on DICOM patient axes.

    Axis contract
    -------------
    ``axes_mm`` is ``(x_mm, y_mm, z_mm)`` and
    ``values_gy[ix, iy, iz]`` corresponds to
    ``(x_mm[ix], y_mm[iy], z_mm[iz])``.

    This is an axis-indexing contract only.  In NumPy C-order the last index
    is contiguous in memory, so this class makes no claim that "x varies
    fastest".

    Validation
    ----------
    On construction, every axis is checked for:

    - monotonically increasing coordinates;
    - uniform spacing (the MVP requires uniformly spaced rectilinear axes);
    - non-negative dose values throughout the grid.

    All arrays are defensively copied and made read-only.
    """

    axis_indexing_contract: ClassVar[str] = (
        "values_gy[ix, iy, iz] corresponds to "
        "(axes_mm[0][ix], axes_mm[1][iy], axes_mm[2][iz]). "
        "This is an axis-indexing contract only; in NumPy C-order the last "
        "index is contiguous in memory."
    )

    axes_mm: tuple[FloatArray1D, FloatArray1D, FloatArray1D]
    values_gy: FloatArray3D

    def __post_init__(self) -> None:
        if len(self.axes_mm) != 3:
            raise ValueError(
                "DoseGrid.axes_mm must contain exactly three axes: "
                "(x_mm, y_mm, z_mm)"
            )

        x_mm = _normalise_dose_axis(self.axes_mm[0], name="x_mm")
        y_mm = _normalise_dose_axis(self.axes_mm[1], name="y_mm")
        z_mm = _normalise_dose_axis(self.axes_mm[2], name="z_mm")
        values_gy = _normalise_values_3d(self.values_gy, name="values_gy")

        expected_shape = (x_mm.size, y_mm.size, z_mm.size)
        if values_gy.shape != expected_shape:
            raise ValueError(
                f"DoseGrid.values_gy shape mismatch: expected "
                f"{expected_shape} from axes lengths, got {values_gy.shape}"
            )

        if np.any(values_gy < 0.0):
            raise ValueError(
                "DoseGrid.values_gy must contain only non-negative dose values"
            )

        object.__setattr__(self, "axes_mm", (x_mm, y_mm, z_mm))
        object.__setattr__(self, "values_gy", values_gy)

    @property
    def shape(self) -> tuple[int, int, int]:
        """Grid dimensions ``(nx, ny, nz)``."""
        s = self.values_gy.shape
        return (int(s[0]), int(s[1]), int(s[2]))

    @property
    def spacing_mm(self) -> tuple[float, float, float]:
        """Voxel spacing ``(dx, dy, dz)`` in mm.

        Returns ``0.0`` for any single-point axis where spacing is undefined.
        """
        return (
            _axis_spacing(self.axes_mm[0]),
            _axis_spacing(self.axes_mm[1]),
            _axis_spacing(self.axes_mm[2]),
        )

    @property
    def extent_mm(
        self,
    ) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
        """Per-axis ``(min, max)`` extent in mm."""
        return (
            (float(self.axes_mm[0][0]), float(self.axes_mm[0][-1])),
            (float(self.axes_mm[1][0]), float(self.axes_mm[1][-1])),
            (float(self.axes_mm[2][0]), float(self.axes_mm[2][-1])),
        )

    @property
    def origin_mm(self) -> tuple[float, float, float]:
        """Grid origin (first voxel centre) in mm."""
        return (
            float(self.axes_mm[0][0]),
            float(self.axes_mm[1][0]),
            float(self.axes_mm[2][0]),
        )


# ---------------------------------------------------------------------------
# DVHResult
# ---------------------------------------------------------------------------


@dataclass(eq=False, slots=True)
class DVHResult:
    """A cumulative DVH result with computation metadata.

    Cumulative-bin semantics
    ------------------------
    - ``dose_bins_gy[i]`` is a dose threshold.
    - ``cumulative_volume_cm3[i]`` is the structure volume receiving
      **at least** ``dose_bins_gy[i]``.

    Both arrays describe sampled points on a cumulative curve rather than
    histogram bin edges.

    Mutability contract
    -------------------
    ``DVHResult`` is a *mutable* dataclass.  However, the NumPy arrays
    (``dose_bins_gy`` and ``cumulative_volume_cm3``) are made read-only
    after construction to prevent accidental corruption of computed results.
    The ``warnings`` list is intentionally left mutable so that downstream
    code can append diagnostics after initial construction.
    """

    cumulative_bin_semantics: ClassVar[str] = (
        "dose_bins_gy[i] is a dose threshold; cumulative_volume_cm3[i] is the "
        "structure volume receiving at least that dose."
    )

    # --- Required fields (no defaults) ---

    structure_name: str
    dose_bins_gy: FloatArray1D
    cumulative_volume_cm3: FloatArray1D
    total_volume_cm3: float
    voxel_count: int
    bin_width_gy: float
    supersampling_factor: tuple[int, int, int]
    pip_method: str
    interslice_method: str
    endcap_method: str

    # --- Optional fields ---

    preset_name: str | None = None
    warnings: list[str] = field(default_factory=list)
    surface_min_dose_gy: float | None = None
    surface_max_dose_gy: float | None = None
    computation_time_s: float | None = None

    def __post_init__(self) -> None:
        dose_bins_gy = _normalise_1d_array(self.dose_bins_gy, name="dose_bins_gy")
        cumulative_volume_cm3 = _normalise_1d_array(
            self.cumulative_volume_cm3,
            name="cumulative_volume_cm3",
        )
        if dose_bins_gy.shape != cumulative_volume_cm3.shape:
            raise ValueError(
                "DVHResult.dose_bins_gy and DVHResult.cumulative_volume_cm3 "
                "must have the same shape; got "
                f"{dose_bins_gy.shape} and {cumulative_volume_cm3.shape}"
            )

        total_volume_cm3 = float(self.total_volume_cm3)
        if total_volume_cm3 < 0:
            raise ValueError("DVHResult.total_volume_cm3 must be non-negative")

        voxel_count = int(self.voxel_count)
        if voxel_count < 0:
            raise ValueError("DVHResult.voxel_count must be non-negative")

        bin_width_gy = float(self.bin_width_gy)
        if bin_width_gy < 0:
            raise ValueError("DVHResult.bin_width_gy must be non-negative")

        supersampling_factor = self.supersampling_factor
        if len(supersampling_factor) != 3 or any(
            int(v) <= 0 for v in supersampling_factor
        ):
            raise ValueError(
                "DVHResult.supersampling_factor must contain three " "positive integers"
            )
        supersampling_factor = (
            int(supersampling_factor[0]),
            int(supersampling_factor[1]),
            int(supersampling_factor[2]),
        )

        pip_method = str(self.pip_method)
        if not pip_method:
            raise ValueError("DVHResult.pip_method must be a non-empty string")

        interslice_method = str(self.interslice_method)
        if not interslice_method:
            raise ValueError("DVHResult.interslice_method must be a non-empty string")

        endcap_method = str(self.endcap_method)
        if not endcap_method:
            raise ValueError("DVHResult.endcap_method must be a non-empty string")

        self.structure_name = str(self.structure_name)
        self.dose_bins_gy = dose_bins_gy
        self.cumulative_volume_cm3 = cumulative_volume_cm3
        self.total_volume_cm3 = total_volume_cm3
        self.voxel_count = voxel_count
        self.bin_width_gy = bin_width_gy
        self.supersampling_factor = supersampling_factor
        self.pip_method = pip_method
        self.interslice_method = interslice_method
        self.endcap_method = endcap_method
        self.preset_name = _normalise_optional_string(self.preset_name)
        self.warnings = [str(w) for w in self.warnings]
        self.surface_min_dose_gy = _normalise_optional_float(self.surface_min_dose_gy)
        self.surface_max_dose_gy = _normalise_optional_float(self.surface_max_dose_gy)
        self.computation_time_s = _normalise_optional_float(self.computation_time_s)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _normalise_planar_points(
    points_xy_mm: FloatArray2D | npt.ArrayLike,
) -> FloatArray2D:
    """Validate and normalise contour vertex array to a closed (N, 2) polygon.

    Returns a read-only float64 copy.
    """
    points_array = np.array(points_xy_mm, dtype=np.float64, copy=True)
    points_array = cast(FloatArray2D, points_array)

    if points_array.ndim != 2 or points_array.shape[1] != 2:
        raise ValueError(
            "PlanarContour.points_xy_mm must have shape (N, 2); "
            f"got {points_array.shape}"
        )

    is_closed = points_array.shape[0] >= 2 and bool(
        np.allclose(points_array[0], points_array[-1])
    )
    non_closing_count = (
        points_array.shape[0] - 1 if is_closed else points_array.shape[0]
    )
    if non_closing_count < 3:
        raise ValueError(
            "PlanarContour.points_xy_mm must contain at least 3 " "non-closing vertices"
        )

    if not is_closed:
        points_array = np.vstack((points_array, points_array[0]))

    points_array.setflags(write=False)
    return points_array


def _normalise_1d_array(
    values: FloatArray1D | npt.ArrayLike, *, name: str
) -> FloatArray1D:
    """Validate and normalise a 1-D array.  Returns a read-only float64 copy."""
    axis = np.array(values, dtype=np.float64, copy=True)
    axis = cast(FloatArray1D, axis)

    if axis.ndim != 1:
        raise ValueError(
            f"{name} must be a one-dimensional array; got shape {axis.shape}"
        )
    if axis.size == 0:
        raise ValueError(f"{name} must not be empty")

    axis.setflags(write=False)
    return axis


def _normalise_dose_axis(
    values: FloatArray1D | npt.ArrayLike, *, name: str
) -> FloatArray1D:
    """Validate and normalise a DoseGrid axis: 1-D, monotonic, uniform.

    Returns a read-only float64 copy.
    """
    axis = _normalise_1d_array(values, name=name)

    if axis.size >= 2:
        diffs = np.diff(axis)
        if not np.all(diffs > 0):
            raise ValueError(f"DoseGrid axis {name} must be monotonically increasing")
        if not np.allclose(
            diffs,
            diffs[0],
            rtol=_UNIFORM_SPACING_RTOL,
            atol=_UNIFORM_SPACING_ATOL,
        ):
            raise ValueError(
                f"DoseGrid axis {name} is not uniformly spaced; "
                "the MVP requires uniformly spaced rectilinear axes"
            )

    return axis


def _normalise_values_3d(
    values: FloatArray3D | npt.ArrayLike, *, name: str
) -> FloatArray3D:
    """Validate and normalise a 3-D array.  Returns a read-only float64 copy."""
    values_array = np.array(values, dtype=np.float64, copy=True)
    values_array = cast(FloatArray3D, values_array)

    if values_array.ndim != 3:
        raise ValueError(
            f"{name} must be a three-dimensional array; "
            f"got shape {values_array.shape}"
        )

    values_array.setflags(write=False)
    return values_array


def _normalise_colour_rgb(
    colour_rgb: tuple[int, int, int],
) -> tuple[int, int, int]:
    """Validate and normalise an RGB colour tuple to ``(int, int, int)``."""
    if len(colour_rgb) != 3:
        raise ValueError("Structure.colour_rgb must contain exactly three channels")

    channels = (int(colour_rgb[0]), int(colour_rgb[1]), int(colour_rgb[2]))
    if any(c < 0 or c > 255 for c in channels):
        raise ValueError(
            "Structure.colour_rgb channels must each be in the range 0..255"
        )

    return channels


def _normalise_optional_string(value: str | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _normalise_optional_float(value: float | None) -> float | None:
    if value is None:
        return None
    if not isinstance(value, Real):
        raise TypeError(f"Expected a real number or None, got {type(value)!r}")
    return float(value)


def _axis_spacing(axis: FloatArray1D) -> float:
    """Return the uniform spacing of an axis, or 0.0 for single-point axes."""
    if axis.size < 2:
        return 0.0
    return float(axis[1] - axis[0])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "BoolArray1D",
    "DVHResult",
    "DoseGrid",
    "EndCapStrategy",
    "FloatArray1D",
    "FloatArray2D",
    "FloatArray3D",
    "InterSliceStrategy",
    "PIPStrategy",
    "PlanarContour",
    "Structure",
    "ZExtent",
]
