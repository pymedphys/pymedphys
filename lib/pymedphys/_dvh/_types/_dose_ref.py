"""Dose reference types (RFC section 6.3)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class DoseReference:
    """An explicit dose reference for percentage-dose metric computation.

    The tool never guesses the reference dose. Any metric containing '%'
    on the dose axis must have a DoseReference supplied.

    Parameters
    ----------
    dose_gy : float
        Reference dose in Gy. Must be strictly positive.
    source : str
        Human-readable provenance string (>= 5 characters). Forces the
        user to document where the reference dose came from.
    """

    dose_gy: float
    source: str

    _SOURCE_RE = re.compile(r"[a-zA-Z]{3,}")

    def __post_init__(self) -> None:
        if self.dose_gy <= 0:
            raise ValueError(f"Reference dose must be positive, got {self.dose_gy}")
        stripped = self.source.strip()
        if not stripped:
            raise ValueError(
                "DoseReference.source must be non-empty. Document where "
                "this value came from (e.g. 'prescription: 3 fx x 14 Gy')."
            )
        if not self._SOURCE_RE.search(stripped):
            raise ValueError(
                f"DoseReference.source must contain at least one word "
                f"with 3+ alphabetic characters (got '{stripped}'). "
                f"Provide a meaningful description of where this dose "
                f"reference comes from."
            )

    def to_dict(self) -> dict:
        """Serialise to a plain dict."""
        return {"dose_gy": self.dose_gy, "source": self.source}

    @classmethod
    def from_dict(cls, d: dict) -> DoseReference:
        """Deserialise from a plain dict."""
        return cls(dose_gy=d["dose_gy"], source=d["source"])


@dataclass(frozen=True, slots=True)
class DoseReferenceSet:
    """A named registry of dose references with an optional default.

    Supports SIB and multi-target plans where different ROIs reference
    different prescription doses.

    Parameters
    ----------
    refs : Mapping[str, DoseReference]
        Named dose references. Must be non-empty.
    default_id : str, optional
        Key into ``refs`` for the default reference.
    """

    refs: Mapping[str, DoseReference]
    default_id: str | None = None

    def __post_init__(self) -> None:
        # Defensive copy to preserve immutability
        object.__setattr__(self, "refs", dict(self.refs))
        if not self.refs:
            raise ValueError("DoseReferenceSet must contain at least one reference")
        if self.default_id is not None and self.default_id not in self.refs:
            raise ValueError(
                f"default_id '{self.default_id}' not found in refs: "
                f"{list(self.refs.keys())}"
            )

    @property
    def default(self) -> DoseReference | None:
        """The default DoseReference, or None if no default is set."""
        if self.default_id is None:
            return None
        return self.refs[self.default_id]

    def get(self, ref_id: str | None = None) -> DoseReference:
        """Resolve a reference by id, falling back to the default.

        Raises
        ------
        ValueError
            If neither ``ref_id`` nor ``default_id`` resolves.
        """
        if ref_id is not None:
            if ref_id not in self.refs:
                raise ValueError(
                    f"Dose reference '{ref_id}' not found. "
                    f"Available: {list(self.refs.keys())}"
                )
            return self.refs[ref_id]
        if self.default_id is not None:
            return self.refs[self.default_id]
        raise ValueError(
            "No ref_id specified and no default_id set in DoseReferenceSet"
        )

    @classmethod
    def single(cls, dose_gy: float, source: str) -> DoseReferenceSet:
        """Convenience for the common single-prescription case."""
        ref = DoseReference(dose_gy=dose_gy, source=source)
        return cls(refs={"default": ref}, default_id="default")

    def to_dict(self) -> dict:
        """Serialise to a plain dict."""
        d: dict = {
            "refs": {k: v.to_dict() for k, v in self.refs.items()},
        }
        if self.default_id is not None:
            d["default_id"] = self.default_id
        return d

    @classmethod
    def from_dict(cls, d: dict) -> DoseReferenceSet:
        """Deserialise from a plain dict."""
        refs = {k: DoseReference.from_dict(v) for k, v in d["refs"].items()}
        return cls(refs=refs, default_id=d.get("default_id"))
