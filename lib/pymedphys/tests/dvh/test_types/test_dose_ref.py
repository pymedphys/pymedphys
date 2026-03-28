"""Tests for DoseReference and DoseReferenceSet (RFC section 6.3)."""

from __future__ import annotations

import pytest

from pymedphys._dvh._types._dose_ref import DoseReference, DoseReferenceSet


class TestDoseReference:
    """Tests for DoseReference construction and validation."""

    def test_accepts_valid_input(self) -> None:
        ref = DoseReference(dose_gy=60.0, source="prescription: 30 fx x 2 Gy")
        assert ref.dose_gy == 60.0
        assert ref.source == "prescription: 30 fx x 2 Gy"

    def test_rejects_zero_dose(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            DoseReference(dose_gy=0.0, source="some valid source text")

    def test_rejects_negative_dose(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            DoseReference(dose_gy=-1.0, source="some valid source text")

    def test_rejects_empty_source(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            DoseReference(dose_gy=42.0, source="")

    def test_rejects_whitespace_only_source(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            DoseReference(dose_gy=42.0, source="   ")

    def test_rejects_source_without_alphabetic_word(self) -> None:
        with pytest.raises(ValueError, match="3\\+ alphabetic"):
            DoseReference(dose_gy=42.0, source="12345")


class TestDoseReferenceSet:
    """Tests for DoseReferenceSet construction and lookup."""

    def _make_ref(self, dose: float = 60.0) -> DoseReference:
        return DoseReference(dose_gy=dose, source="test prescription source")

    def test_single_creates_default_keyed_set(self) -> None:
        drs = DoseReferenceSet.single(42.0, "prescription: 3 fx x 14 Gy")
        assert "default" in drs.refs
        assert drs.default_id == "default"
        assert drs.refs["default"].dose_gy == 42.0

    def test_rejects_empty_refs(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            DoseReferenceSet(refs={})

    def test_rejects_invalid_default_id(self) -> None:
        with pytest.raises(ValueError, match="not found"):
            DoseReferenceSet(
                refs={"ptv60": self._make_ref(60.0)},
                default_id="nonexistent",
            )

    def test_get_resolves_by_ref_id(self) -> None:
        drs = DoseReferenceSet(
            refs={
                "ptv60": self._make_ref(60.0),
                "ptv42": self._make_ref(42.0),
            },
        )
        result = drs.get("ptv42")
        assert result.dose_gy == 42.0

    def test_get_falls_back_to_default(self) -> None:
        drs = DoseReferenceSet(
            refs={
                "ptv60": self._make_ref(60.0),
                "ptv42": self._make_ref(42.0),
            },
            default_id="ptv60",
        )
        result = drs.get()
        assert result.dose_gy == 60.0

    def test_get_raises_when_no_ref_id_and_no_default(self) -> None:
        drs = DoseReferenceSet(refs={"ptv60": self._make_ref(60.0)})
        with pytest.raises(ValueError, match="No ref_id"):
            drs.get()

    def test_get_raises_for_unknown_ref_id(self) -> None:
        drs = DoseReferenceSet(refs={"ptv60": self._make_ref(60.0)})
        with pytest.raises(ValueError, match="not found"):
            drs.get("unknown")

    def test_default_property_returns_ref(self) -> None:
        drs = DoseReferenceSet(
            refs={"ptv60": self._make_ref(60.0)},
            default_id="ptv60",
        )
        assert drs.default is not None
        assert drs.default.dose_gy == 60.0

    def test_default_property_returns_none_when_no_default(self) -> None:
        drs = DoseReferenceSet(refs={"ptv60": self._make_ref(60.0)})
        assert drs.default is None

    def test_refs_is_defensively_copied(self) -> None:
        """A4: External mutation of the refs dict must not affect the set."""
        refs_dict: dict[str, DoseReference] = {
            "ptv60": self._make_ref(60.0),
        }
        drs = DoseReferenceSet(refs=refs_dict)
        refs_dict["sneaky"] = self._make_ref(99.0)
        assert "sneaky" not in drs.refs
