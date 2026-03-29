"""ROI identity type (RFC section 6.4, enriched with colour_rgb)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ROIRef:
    """Identifies an ROI across the entire pipeline.

    Provides a single source of truth for ROI identity, carried from
    DICOM import through request, internal compute, and result output.

    The ``roi_number``, when present, comes from the DICOM ROI Number
    (3006,0022). The ``colour_rgb``, when present, comes from DICOM
    ROI Display Color (3006,002A) and is preserved for plotting.

    Identity semantics: two ROIRefs match if their ``roi_number`` matches
    (when both have one), otherwise by name.

    Parameters
    ----------
    name : str
        ROI name. Must be non-empty.
    roi_number : int, optional
        DICOM ROI Number for unambiguous identification.
    colour_rgb : tuple[int, int, int], optional
        Display colour as (R, G, B) with each component in [0, 255].
    """

    name: str
    roi_number: int | None = None
    colour_rgb: tuple[int, int, int] | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("ROI name must be non-empty")
        if self.colour_rgb is not None:
            if len(self.colour_rgb) != 3:
                raise ValueError(
                    f"colour_rgb must have exactly 3 elements, "
                    f"got {len(self.colour_rgb)}"
                )
            for i, c in enumerate(self.colour_rgb):
                if not (0 <= c <= 255):
                    raise ValueError(
                        f"colour_rgb values must be in 0..255, got {c} at index {i}"
                    )

    def __str__(self) -> str:
        if self.roi_number is not None:
            return f"{self.name} (#{self.roi_number})"
        return self.name

    def matches(self, other: ROIRef) -> bool:
        """Match by roi_number if both have one, else by name."""
        if self.roi_number is not None and other.roi_number is not None:
            return self.roi_number == other.roi_number
        return self.name == other.name

    def to_dict(self) -> dict:
        """Serialise to a plain dict."""
        d: dict = {"name": self.name}
        if self.roi_number is not None:
            d["roi_number"] = self.roi_number
        if self.colour_rgb is not None:
            d["colour_rgb"] = list(self.colour_rgb)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> ROIRef:
        """Deserialise from a plain dict."""
        colour = d.get("colour_rgb")
        return cls(
            name=d["name"],
            roi_number=d.get("roi_number"),
            colour_rgb=tuple(colour) if colour is not None else None,
        )
