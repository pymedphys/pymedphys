"""Tests for ROIRef (RFC section 6.4, enriched with colour_rgb)."""

from __future__ import annotations

import pytest

from pymedphys._dvh._types._roi_ref import ROIRef


class TestROIRefConstruction:
    """Tests for ROIRef construction and defaults."""

    def test_accepts_valid_name(self) -> None:
        ref = ROIRef(name="PTV")
        assert ref.name == "PTV"

    def test_roi_number_defaults_to_none(self) -> None:
        ref = ROIRef(name="PTV")
        assert ref.roi_number is None

    def test_colour_rgb_defaults_to_none(self) -> None:
        ref = ROIRef(name="PTV")
        assert ref.colour_rgb is None

    def test_preserves_colour_rgb(self) -> None:
        ref = ROIRef(name="PTV", colour_rgb=(255, 0, 0))
        assert ref.colour_rgb == (255, 0, 0)

    def test_preserves_roi_number(self) -> None:
        ref = ROIRef(name="PTV", roi_number=3)
        assert ref.roi_number == 3


class TestROIRefValidation:
    """Tests for ROIRef validation."""

    def test_rejects_empty_name(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ROIRef(name="")

    def test_rejects_whitespace_only_name(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ROIRef(name="   ")

    def test_rejects_colour_value_above_255(self) -> None:
        with pytest.raises(ValueError, match="0.*255"):
            ROIRef(name="PTV", colour_rgb=(256, 0, 0))

    def test_rejects_colour_value_below_0(self) -> None:
        with pytest.raises(ValueError, match="0.*255"):
            ROIRef(name="PTV", colour_rgb=(-1, 0, 0))


class TestROIRefMatches:
    """Tests for the matches() identity comparison."""

    def test_matches_by_number_when_both_have_one(self) -> None:
        a = ROIRef(name="PTV", roi_number=3)
        b = ROIRef(name="DifferentName", roi_number=3)
        assert a.matches(b)

    def test_does_not_match_by_number_when_different(self) -> None:
        a = ROIRef(name="PTV", roi_number=3)
        b = ROIRef(name="PTV", roi_number=4)
        assert not a.matches(b)

    def test_matches_by_name_when_no_numbers(self) -> None:
        a = ROIRef(name="PTV")
        b = ROIRef(name="PTV")
        assert a.matches(b)

    def test_matches_by_name_when_one_has_no_number(self) -> None:
        a = ROIRef(name="PTV", roi_number=3)
        b = ROIRef(name="PTV")
        assert a.matches(b)

    def test_does_not_match_different_names_without_numbers(self) -> None:
        a = ROIRef(name="PTV")
        b = ROIRef(name="CTV")
        assert not a.matches(b)


class TestROIRefStr:
    """Tests for __str__ representation."""

    def test_str_with_number(self) -> None:
        ref = ROIRef(name="PTV", roi_number=3)
        assert str(ref) == "PTV (#3)"

    def test_str_without_number(self) -> None:
        ref = ROIRef(name="PTV")
        assert str(ref) == "PTV"
