"""Metric request types (RFC section 6.5)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet, Optional

from pymedphys._dvh._types._dose_ref import DoseReference, DoseReferenceSet
from pymedphys._dvh._types._roi_ref import ROIRef


class MetricFamily(str, Enum):
    """The family of metric being requested."""

    DVH_DOSE = "dvh_dose"
    DVH_VOLUME = "dvh_volume"
    SCALAR = "scalar"
    INDEX = "index"


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
    raw : str
        Original string, preserved for display/provenance.
    """

    family: MetricFamily
    threshold: Optional[float] = None
    threshold_unit: ThresholdUnit = ThresholdUnit.NONE
    output_unit: OutputUnit = OutputUnit.GY
    dose_ref_id: Optional[str] = None
    raw: str = ""

    def __post_init__(self) -> None:
        if self.threshold is not None and self.threshold < 0:
            raise ValueError(
                f"Metric threshold must be non-negative, got {self.threshold}"
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
        if self.family == MetricFamily.INDEX and self.raw in {
            "CI",
            "PCI",
            "GI",
        }:
            return True
        return False

    @property
    def canonical_key(self) -> str:
        """A canonical string key for deduplication."""
        parts = [self.family.value]
        if self.threshold is not None:
            parts.append(f"{self.threshold}")
        parts.append(self.threshold_unit.value)
        parts.append(self.output_unit.value)
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
        return d

    @classmethod
    def from_dict(cls, d: dict) -> MetricSpec:
        """Deserialise from a plain dict."""
        return cls(
            family=MetricFamily(d["family"]),
            threshold=d.get("threshold"),
            threshold_unit=ThresholdUnit(d["threshold_unit"]),
            output_unit=OutputUnit(d["output_unit"]),
            dose_ref_id=d.get("dose_ref_id"),
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
            mean|median|min|max -> SCALAR
            HI|CI|PCI|GI       -> INDEX

        Raises
        ------
        ValueError
            On unparseable input.
        """
        if not raw or not raw.strip():
            raise ValueError("Empty metric string")

        s = raw.strip()

        # Scalar metrics
        if s in {"mean", "median", "min", "max"}:
            return cls(
                family=MetricFamily.SCALAR,
                output_unit=OutputUnit.GY,
                raw=raw,
            )

        # Index metrics
        if s in {"HI", "CI", "PCI", "GI"}:
            return cls(
                family=MetricFamily.INDEX,
                output_unit=OutputUnit.DIMENSIONLESS,
                raw=raw,
            )

        # D{x}%[%Rx]
        m = re.match(r"^D(\d+(?:\.\d+)?)%\[%Rx\]$", s)
        if m:
            return cls(
                family=MetricFamily.DVH_DOSE,
                threshold=float(m.group(1)),
                threshold_unit=ThresholdUnit.PERCENT,
                output_unit=OutputUnit.PERCENT_DOSE,
                raw=raw,
            )

        # D{x}%
        m = re.match(r"^D(\d+(?:\.\d+)?)%$", s)
        if m:
            return cls(
                family=MetricFamily.DVH_DOSE,
                threshold=float(m.group(1)),
                threshold_unit=ThresholdUnit.PERCENT,
                output_unit=OutputUnit.GY,
                raw=raw,
            )

        # D{x}cc
        m = re.match(r"^D(\d+(?:\.\d+)?)cc$", s)
        if m:
            return cls(
                family=MetricFamily.DVH_DOSE,
                threshold=float(m.group(1)),
                threshold_unit=ThresholdUnit.CC,
                output_unit=OutputUnit.GY,
                raw=raw,
            )

        # V{x}Gy[%]
        m = re.match(r"^V(\d+(?:\.\d+)?)Gy\[%\]$", s)
        if m:
            return cls(
                family=MetricFamily.DVH_VOLUME,
                threshold=float(m.group(1)),
                threshold_unit=ThresholdUnit.GY,
                output_unit=OutputUnit.PERCENT_VOLUME,
                raw=raw,
            )

        # V{x}Gy
        m = re.match(r"^V(\d+(?:\.\d+)?)Gy$", s)
        if m:
            return cls(
                family=MetricFamily.DVH_VOLUME,
                threshold=float(m.group(1)),
                threshold_unit=ThresholdUnit.GY,
                output_unit=OutputUnit.CC,
                raw=raw,
            )

        # V{x}%
        m = re.match(r"^V(\d+(?:\.\d+)?)%$", s)
        if m:
            return cls(
                family=MetricFamily.DVH_VOLUME,
                threshold=float(m.group(1)),
                threshold_unit=ThresholdUnit.PERCENT,
                output_unit=OutputUnit.CC,
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
    dose_ref_id: Optional[str] = None

    def __post_init__(self) -> None:
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
        roi_number: Optional[int] = None,
        dose_ref_id: Optional[str] = None,
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
    dose_refs: Optional[DoseReferenceSet] = None

    def __post_init__(self) -> None:
        for i, a in enumerate(self.roi_requests):
            for b in self.roi_requests[i + 1 :]:
                if a.roi.matches(b.roi):
                    raise ValueError(
                        f"Duplicate ROI in request: '{a.roi}' and '{b.roi}'"
                    )
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

    def to_dict(self) -> dict:
        """Serialise to a dict compatible with ``from_dict()``.

        Uses the rich format with explicit dose_refs and per-ROI
        metric dicts.
        """
        d: dict = {}
        if self.dose_refs is not None:
            d["dose_refs"] = {
                k: {"dose_gy": v.dose_gy, "source": v.source}
                for k, v in self.dose_refs.refs.items()
            }
            if self.dose_refs.default_id is not None:
                d["default_dose_ref"] = self.dose_refs.default_id
        metrics: dict = {}
        for rr in self.roi_requests:
            entry: dict = {
                "metrics": [m.raw for m in rr.metrics],
            }
            if rr.dose_ref_id is not None:
                entry["dose_ref"] = rr.dose_ref_id
            metrics[rr.roi.name] = entry
        d["metrics"] = metrics
        return d

    @property
    def roi_refs(self) -> FrozenSet[ROIRef]:
        """All ROIRefs in the request."""
        return frozenset(rr.roi for rr in self.roi_requests)

    @classmethod
    def from_dict(cls, d: dict) -> MetricRequestSet:
        """Construct from a compact dict representation.

        Supports both simple (single dose ref) and rich (SIB) formats.
        See RFC section 6.5 for full schema.
        """
        dose_refs = None
        if "dose_refs" in d:
            refs = {
                k: DoseReference(dose_gy=v["dose_gy"], source=v["source"])
                for k, v in d["dose_refs"].items()
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

        roi_requests = []
        for roi_key, spec in d["metrics"].items():
            if isinstance(spec, list):
                roi_requests.append(ROIMetricRequest.from_strings(roi_key, spec))
            elif isinstance(spec, dict):
                roi_requests.append(
                    ROIMetricRequest.from_strings(
                        roi_key,
                        spec["metrics"],
                        dose_ref_id=spec.get("dose_ref"),
                    )
                )
        return cls(
            roi_requests=tuple(roi_requests),
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
