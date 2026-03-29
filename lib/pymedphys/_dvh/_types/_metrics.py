"""Metric request types (RFC section 6.5).

Grammar design note
-------------------
``MetricSpec.parse()`` currently has **no syntax for attaching a
``dose_ref_id`` inline** (e.g. ``D95%[%Rx:ptv60]``). In a SIB plan a
single ROI may need different metrics bound to different dose refs —
the current grammar cannot express this. The ``dose_ref_id`` must be
set at the ``ROIMetricRequest`` or ``MetricRequestSet`` level.

This is a known Phase 0 limitation. As the grammar expands in later
phases, an inline ``@ref_id`` suffix (e.g. ``D95%[%Rx]@ptv60``) is
the intended design direction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from pymedphys._dvh._types._dose_ref import DoseReference, DoseReferenceSet
from pymedphys._dvh._types._roi_ref import ROIRef


class MetricFamily(str, Enum):
    """The family of metric being requested."""

    DVH_DOSE = "dvh_dose"
    DVH_VOLUME = "dvh_volume"
    SCALAR = "scalar"
    INDEX = "index"


class IndexMetric(str, Enum):
    """Specific index metric identifiers.

    These carry clinical definitions so that results are reproducible
    and auditable.

    Definitions
    -----------
    HI : Homogeneity Index
        ICRU 83 definition: ``(D2% − D98%) / D50%``.
        Does **not** require a dose reference.
    CI : Conformity Index
        Paddick conformity index:
        ``CI = (TV_PIV)² / (TV × PIV)``
        where TV = target volume, PIV = prescription isodose volume,
        TV_PIV = target volume within PIV.
        Requires a dose reference.
    PCI : Paddick Conformity Index
        Alias for CI using the Paddick formulation. Requires a dose
        reference.
    GI : Gradient Index
        Paddick gradient index:
        ``GI = PIV_half / PIV``
        where PIV_half = volume of half-prescription isodose,
        PIV = prescription isodose volume.
        Requires a dose reference.
    """

    HI = "HI"
    CI = "CI"
    PCI = "PCI"
    GI = "GI"

    @property
    def requires_dose_ref(self) -> bool:
        """Whether this index metric requires a dose reference."""
        return self in {IndexMetric.CI, IndexMetric.PCI, IndexMetric.GI}


class ThresholdUnit(str, Enum):
    """Unit of the threshold/input axis."""

    PERCENT = "percent"
    CC = "cc"
    GY = "Gy"
    NONE = "none"


class OutputUnit(str, Enum):
    """Unit of the metric output."""

    GY = "Gy"
    PERCENT_DOSE = "percent_dose"
    CC = "cc"
    PERCENT_VOLUME = "percent_vol"
    DIMENSIONLESS = "dimensionless"


@dataclass(frozen=True, slots=True)
class MetricSpec:
    """A fully parsed, unambiguous metric specification.

    This is the metric AST — a structured representation that is
    unambiguous about what is being computed, in what unit, and
    against which dose reference.

    Parameters
    ----------
    family : MetricFamily
        The metric family.
    threshold : float, optional
        The threshold value (e.g. 95 for D95%).
    threshold_unit : ThresholdUnit
        Unit of the threshold.
    output_unit : OutputUnit
        Unit of the metric output.
    dose_ref_id : str, optional
        Binds to a DoseReferenceSet entry.
    index_metric : IndexMetric, optional
        For INDEX family metrics, specifies which index. Required when
        ``family == MetricFamily.INDEX``.
    raw : str
        Original string, preserved for display/provenance.
    """

    family: MetricFamily
    threshold: float | None = None
    threshold_unit: ThresholdUnit = ThresholdUnit.NONE
    output_unit: OutputUnit = OutputUnit.GY
    dose_ref_id: str | None = None
    index_metric: IndexMetric | None = None
    raw: str = ""

    def __post_init__(self) -> None:
        if self.threshold is not None and self.threshold < 0:
            raise ValueError(
                f"Metric threshold must be non-negative, got {self.threshold}"
            )
        if self.family == MetricFamily.INDEX and self.index_metric is None:
            # Auto-derive from raw for backward compatibility
            if self.raw in {m.value for m in IndexMetric}:
                object.__setattr__(self, "index_metric", IndexMetric(self.raw))
            else:
                raise ValueError(
                    f"MetricSpec with family=INDEX requires a valid "
                    f"index_metric, but raw='{self.raw}' is not a "
                    f"recognised IndexMetric value. "
                    f"Valid values: {[m.value for m in IndexMetric]}"
                )

    @property
    def requires_dose_ref(self) -> bool:
        """Whether this metric needs a DoseReference to be evaluated."""
        if (
            self.threshold_unit == ThresholdUnit.PERCENT
            and self.family == MetricFamily.DVH_VOLUME
        ):
            return True
        if self.output_unit == OutputUnit.PERCENT_DOSE:
            return True
        if self.index_metric is not None and self.index_metric.requires_dose_ref:
            return True
        return False

    @property
    def canonical_key(self) -> str:
        """A canonical string key for deduplication."""
        parts = [self.family.value]
        if self.threshold is not None:
            parts.append(f"{self.threshold:.10g}")
        parts.append(self.threshold_unit.value)
        parts.append(self.output_unit.value)
        if self.index_metric is not None:
            parts.append(f"idx={self.index_metric.value}")
        if self.dose_ref_id:
            parts.append(f"ref={self.dose_ref_id}")
        return "|".join(parts)

    def to_dict(self) -> dict:
        """Serialise to a plain dict."""
        d: dict = {
            "family": self.family.value,
            "threshold_unit": self.threshold_unit.value,
            "output_unit": self.output_unit.value,
            "raw": self.raw,
        }
        if self.threshold is not None:
            d["threshold"] = self.threshold
        if self.dose_ref_id is not None:
            d["dose_ref_id"] = self.dose_ref_id
        if self.index_metric is not None:
            d["index_metric"] = self.index_metric.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> MetricSpec:
        """Deserialise from a plain dict."""
        idx_str = d.get("index_metric")
        return cls(
            family=MetricFamily(d["family"]),
            threshold=d.get("threshold"),
            threshold_unit=ThresholdUnit(d["threshold_unit"]),
            output_unit=OutputUnit(d["output_unit"]),
            dose_ref_id=d.get("dose_ref_id"),
            index_metric=IndexMetric(idx_str) if idx_str else None,
            raw=d.get("raw", ""),
        )

    @classmethod
    def parse(cls, raw: str) -> MetricSpec:
        """Parse a metric string into a typed MetricSpec.

        Grammar
        -------
        ::

            D{x}%              -> DVH_DOSE, threshold=x, unit=PERCENT, out=GY
            D{x}%[%Rx]         -> DVH_DOSE, threshold=x, unit=PERCENT, out=PERCENT_DOSE
            D{x}cc             -> DVH_DOSE, threshold=x, unit=CC, out=GY
            V{x}Gy             -> DVH_VOLUME, threshold=x, unit=GY, out=CC
            V{x}Gy[%]          -> DVH_VOLUME, threshold=x, unit=GY, out=PERCENT_VOLUME
            V{x}%              -> DVH_VOLUME, threshold=x, unit=PERCENT, out=CC
            mean               -> SCALAR, out=GY
            mean[%Rx]          -> SCALAR, out=PERCENT_DOSE (requires dose ref)
            median|min|max     -> SCALAR
            HI|CI|PCI|GI       -> INDEX

        Note: ``dose_ref_id`` cannot be attached inline. Use
        ``ROIMetricRequest.dose_ref_id`` or ``MetricRequestSet``-level
        dose refs to bind a specific reference. See module docstring.

        Raises
        ------
        ValueError
            On unparseable input.
        """
        if not raw or not raw.strip():
            raise ValueError("Empty metric string")

        s = raw.strip()

        # Index metrics — use IndexMetric enum for unambiguous identification
        _INDEX_METRICS: dict[str, IndexMetric] = {m.value: m for m in IndexMetric}
        if s in _INDEX_METRICS:
            return cls(
                family=MetricFamily.INDEX,
                output_unit=OutputUnit.DIMENSIONLESS,
                index_metric=_INDEX_METRICS[s],
                raw=raw,
            )

        # Named scalar metrics
        _SCALAR_NAMED: dict[str, tuple[MetricFamily, OutputUnit]] = {
            "mean": (MetricFamily.SCALAR, OutputUnit.GY),
            "median": (MetricFamily.SCALAR, OutputUnit.GY),
            "min": (MetricFamily.SCALAR, OutputUnit.GY),
            "max": (MetricFamily.SCALAR, OutputUnit.GY),
        }
        if s in _SCALAR_NAMED:
            family, output_unit = _SCALAR_NAMED[s]
            return cls(family=family, output_unit=output_unit, raw=raw)

        # mean[%Rx] — mean dose as percentage of prescription (E3)
        if s == "mean[%Rx]":
            return cls(
                family=MetricFamily.SCALAR,
                output_unit=OutputUnit.PERCENT_DOSE,
                raw=raw,
            )

        # Pattern-based (threshold) metrics
        _PATTERNS: list[tuple[str, MetricFamily, ThresholdUnit, OutputUnit]] = [
            (
                r"^D(\d+(?:\.\d+)?)%\[%Rx\]$",
                MetricFamily.DVH_DOSE,
                ThresholdUnit.PERCENT,
                OutputUnit.PERCENT_DOSE,
            ),
            (
                r"^D(\d+(?:\.\d+)?)%$",
                MetricFamily.DVH_DOSE,
                ThresholdUnit.PERCENT,
                OutputUnit.GY,
            ),
            (
                r"^D(\d+(?:\.\d+)?)cc$",
                MetricFamily.DVH_DOSE,
                ThresholdUnit.CC,
                OutputUnit.GY,
            ),
            (
                r"^V(\d+(?:\.\d+)?)Gy\[%\]$",
                MetricFamily.DVH_VOLUME,
                ThresholdUnit.GY,
                OutputUnit.PERCENT_VOLUME,
            ),
            (
                r"^V(\d+(?:\.\d+)?)Gy$",
                MetricFamily.DVH_VOLUME,
                ThresholdUnit.GY,
                OutputUnit.CC,
            ),
            (
                r"^V(\d+(?:\.\d+)?)%$",
                MetricFamily.DVH_VOLUME,
                ThresholdUnit.PERCENT,
                OutputUnit.CC,
            ),
        ]
        for pattern, family, threshold_unit, output_unit in _PATTERNS:
            m = re.match(pattern, s)
            if m:
                return cls(
                    family=family,
                    threshold=float(m.group(1)),
                    threshold_unit=threshold_unit,
                    output_unit=output_unit,
                    raw=raw,
                )

        raise ValueError(f"Cannot parse metric string: '{raw}'")


@dataclass(frozen=True, slots=True)
class ROIMetricRequest:
    """Metrics requested for a single ROI.

    Parameters
    ----------
    roi : ROIRef
        The ROI to compute metrics for.
    metrics : tuple[MetricSpec, ...]
        At least one metric. No duplicates by canonical_key.
    dose_ref_id : str, optional
        Per-ROI dose reference override.
    """

    roi: ROIRef
    metrics: tuple[MetricSpec, ...]
    dose_ref_id: str | None = None

    def __post_init__(self) -> None:
        # Coerce list to tuple for true immutability
        if isinstance(self.metrics, list):
            object.__setattr__(self, "metrics", tuple(self.metrics))
        if not self.metrics:
            raise ValueError(f"ROI '{self.roi}' must have at least one metric")
        keys = [m.canonical_key for m in self.metrics]
        if len(keys) != len(set(keys)):
            raise ValueError(f"Duplicate metrics for ROI '{self.roi}'")

    @classmethod
    def from_strings(
        cls,
        name: str,
        metric_strings: list[str],
        roi_number: int | None = None,
        dose_ref_id: str | None = None,
    ) -> ROIMetricRequest:
        """Convenience constructor from raw metric strings."""
        return cls(
            roi=ROIRef(name=name, roi_number=roi_number),
            metrics=tuple(MetricSpec.parse(s) for s in metric_strings),
            dose_ref_id=dose_ref_id,
        )

    def to_dict(self) -> dict:
        """Serialise to a plain dict."""
        d: dict = {
            "roi": self.roi.to_dict(),
            "metrics": [m.to_dict() for m in self.metrics],
        }
        if self.dose_ref_id is not None:
            d["dose_ref_id"] = self.dose_ref_id
        return d

    @classmethod
    def from_dict(cls, d: dict) -> ROIMetricRequest:
        """Deserialise from a plain dict."""
        return cls(
            roi=ROIRef.from_dict(d["roi"]),
            metrics=tuple(MetricSpec.from_dict(m) for m in d["metrics"]),
            dose_ref_id=d.get("dose_ref_id"),
        )


@dataclass(frozen=True, slots=True)
class MetricRequestSet:
    """Complete specification of what to compute.

    Parameters
    ----------
    roi_requests : tuple[ROIMetricRequest, ...]
        Per-ROI metric requests.
    dose_refs : DoseReferenceSet, optional
        Dose references for percentage-dose metrics.
    """

    roi_requests: tuple[ROIMetricRequest, ...]
    dose_refs: DoseReferenceSet | None = None

    def __post_init__(self) -> None:
        # Coerce list to tuple for true immutability
        if isinstance(self.roi_requests, list):
            object.__setattr__(self, "roi_requests", tuple(self.roi_requests))
        # Duplicate ROI detection using ROIRef.matches() semantics:
        # match by roi_number if both have one, otherwise by name.
        #
        # Set-based O(n) approach with three buckets:
        #   seen_numbers: numbered ROIs keyed by roi_number
        #   seen_unnumbered_names: unnumbered ROIs keyed by name
        #   seen_numbered_names: names claimed by numbered ROIs
        #
        # matches() logic:
        #   Both numbered → compare numbers (same name, different number = OK)
        #   One or both unnumbered → compare names
        seen_numbers: dict[int, ROIRef] = {}
        seen_unnumbered_names: dict[str, ROIRef] = {}
        seen_numbered_names: dict[str, ROIRef] = {}
        for rr in self.roi_requests:
            ref = rr.roi
            if ref.roi_number is not None:
                # Check against other numbered ROIs by number
                if ref.roi_number in seen_numbers:
                    raise ValueError(
                        f"Duplicate ROI in request: '{ref}' and "
                        f"'{seen_numbers[ref.roi_number]}'"
                    )
                # Check against unnumbered ROIs by name (mixed case)
                if ref.name in seen_unnumbered_names:
                    raise ValueError(
                        f"Duplicate ROI in request: '{ref}' and "
                        f"'{seen_unnumbered_names[ref.name]}'"
                    )
                seen_numbers[ref.roi_number] = ref
                seen_numbered_names[ref.name] = ref
            else:
                # Check against other unnumbered ROIs by name
                if ref.name in seen_unnumbered_names:
                    raise ValueError(
                        f"Duplicate ROI in request: '{ref}' and "
                        f"'{seen_unnumbered_names[ref.name]}'"
                    )
                # Check against numbered ROIs by name (mixed case)
                if ref.name in seen_numbered_names:
                    raise ValueError(
                        f"Duplicate ROI in request: '{ref}' and "
                        f"'{seen_numbered_names[ref.name]}'"
                    )
                seen_unnumbered_names[ref.name] = ref
        for rr in self.roi_requests:
            for m in rr.metrics:
                if m.requires_dose_ref:
                    ref_id = m.dose_ref_id or rr.dose_ref_id
                    if self.dose_refs is None:
                        raise ValueError(
                            f"Metric '{m.raw}' for ROI '{rr.roi}' requires a "
                            f"dose reference, but no DoseReferenceSet was "
                            f"provided"
                        )
                    try:
                        self.dose_refs.get(ref_id)
                    except ValueError as e:
                        raise ValueError(
                            f"Metric '{m.raw}' for ROI '{rr.roi}': {e}"
                        ) from e

    @property
    def default_dose_ref(self) -> str | None:
        """Default dose reference id, if any."""
        if self.dose_refs is None:
            return None
        return self.dose_refs.default_id

    def to_dict(self) -> dict:
        """Serialise to a lossless canonical dict.

        The canonical format uses ``roi_requests`` — a list of explicit
        ``ROIMetricRequest.to_dict()`` entries — so that duplicate ROI
        names, per-metric metadata, and per-ROI dose_ref_ids are all
        preserved without loss.

        The legacy ``metrics`` name-keyed format is accepted only as an
        input convenience in ``from_dict()``.
        """
        d: dict = {
            "roi_requests": [rr.to_dict() for rr in self.roi_requests],
        }
        if self.dose_refs is not None:
            d["dose_refs"] = self.dose_refs.to_dict()
        if self.default_dose_ref is not None:
            d["default_dose_ref"] = self.default_dose_ref
        return d

    @property
    def roi_refs(self) -> frozenset[ROIRef]:
        """All ROIRefs in the request."""
        return frozenset(rr.roi for rr in self.roi_requests)

    @classmethod
    def from_dict(cls, d: dict) -> MetricRequestSet:
        """Construct from a dict representation.

        Accepts two formats:

        **Canonical** (lossless, emitted by ``to_dict()``):
            ``{"dose_refs": ..., "default_dose_ref": ..., "roi_requests": [...]}``

        **Legacy/compact** (for hand-authored TOML or backwards compat):
            ``{"metrics": {roi_name: [metric_strings] | {metrics: [...], ...}}, ...}``
            with optional ``dose_refs``, ``dose_ref_gy``, ``dose_ref_source``.
        """
        # --- Dose references ---
        dose_refs = None
        dose_refs_raw = d.get("dose_refs")
        if dose_refs_raw is not None:
            # Canonical format: dose_refs is a DoseReferenceSet.to_dict()
            if "refs" in dose_refs_raw:
                dose_refs = DoseReferenceSet.from_dict(dose_refs_raw)
            else:
                # Legacy format: dose_refs is {id: {dose_gy, source}}
                refs = {
                    k: DoseReference(dose_gy=v["dose_gy"], source=v["source"])
                    for k, v in dose_refs_raw.items()
                }
                dose_refs = DoseReferenceSet(
                    refs=refs, default_id=d.get("default_dose_ref")
                )
        elif "dose_ref_gy" in d:
            source = d.get("dose_ref_source")
            if not source or not source.strip():
                raise ValueError(
                    "dose_ref_source must be non-empty when dose_ref_gy is specified."
                )
            dose_refs = DoseReferenceSet.single(dose_gy=d["dose_ref_gy"], source=source)

        # --- ROI requests ---
        if "roi_requests" in d:
            # Canonical format
            roi_requests = tuple(
                ROIMetricRequest.from_dict(rr) for rr in d["roi_requests"]
            )
        elif "metrics" in d:
            # Legacy compact format
            roi_list: list[ROIMetricRequest] = []
            for roi_key, spec in d["metrics"].items():
                if isinstance(spec, list):
                    roi_list.append(ROIMetricRequest.from_strings(roi_key, spec))
                elif isinstance(spec, dict):
                    roi_list.append(
                        ROIMetricRequest.from_strings(
                            roi_key,
                            spec["metrics"],
                            roi_number=spec.get("roi_number"),
                            dose_ref_id=spec.get("dose_ref"),
                        )
                    )
            roi_requests = tuple(roi_list)
        else:
            raise ValueError(
                "MetricRequestSet.from_dict() requires either 'roi_requests' "
                "(canonical) or 'metrics' (legacy) key"
            )

        return cls(
            roi_requests=roi_requests,
            dose_refs=dose_refs,
        )

    @classmethod
    def from_toml(cls, path: str) -> MetricRequestSet:
        """Load from a TOML file.

        Parameters
        ----------
        path : str
            Path to the TOML file.
        """
        try:
            import tomllib
        except ModuleNotFoundError:
            import tomli as tomllib  # type: ignore[no-redef]

        with open(path, "rb") as f:
            d = tomllib.load(f)
        return cls.from_dict(d)
