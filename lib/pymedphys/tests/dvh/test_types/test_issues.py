"""Tests for IssueLevel, IssueCode, and Issue (RFC section 6.9)."""

from __future__ import annotations

import pytest

from pymedphys._dvh._types._issues import Issue, IssueCode, IssueLevel


class TestIssueLevel:
    """Tests for the IssueLevel enum."""

    def test_has_info(self) -> None:
        assert IssueLevel.INFO == "info"

    def test_has_warning(self) -> None:
        assert IssueLevel.WARNING == "warning"

    def test_has_error(self) -> None:
        assert IssueLevel.ERROR == "error"


class TestIssueCode:
    """Tests for the IssueCode enum — all 13 codes from the RFC."""

    EXPECTED_CODES = [
        "STRUCTURE_VOLUME_SMALL",
        "DOSE_GRID_COARSE",
        "SPARSE_CONTOUR_STACK",
        "STEEP_GRADIENT_BOUNDARY",
        "CONVERGENCE_NOT_REACHED",
        "ENDCAP_LARGE_FRACTION",
        "DOSE_COVERAGE_INCOMPLETE",
        "CONTOUR_REPAIRED",
        "CONTOUR_STAGE_BYPASSED",
        "ROI_SKIPPED",
        "ROI_FAILED",
        "METRIC_UNAVAILABLE",
        "Z_TOLERANCE_APPLIED",
    ]

    def test_all_expected_codes_exist(self) -> None:
        for code_name in self.EXPECTED_CODES:
            assert hasattr(IssueCode, code_name), f"Missing IssueCode.{code_name}"

    def test_code_count_matches(self) -> None:
        assert len(IssueCode) == len(self.EXPECTED_CODES)


class TestIssue:
    """Tests for the Issue dataclass."""

    def test_stores_all_fields(self) -> None:
        issue = Issue(
            level=IssueLevel.WARNING,
            code=IssueCode.DOSE_GRID_COARSE,
            message="Dose grid spacing exceeds 3mm",
            path=("PTV60", "D95%"),
            context={"spacing_mm": 4.0},
        )
        assert issue.level == IssueLevel.WARNING
        assert issue.code == IssueCode.DOSE_GRID_COARSE
        assert issue.message == "Dose grid spacing exceeds 3mm"
        assert issue.path == ("PTV60", "D95%")
        assert issue.context == {"spacing_mm": 4.0}

    def test_empty_path_is_valid(self) -> None:
        issue = Issue(
            level=IssueLevel.INFO,
            code=IssueCode.Z_TOLERANCE_APPLIED,
            message="Z tolerance applied",
        )
        assert not issue.path

    def test_context_defaults_to_none(self) -> None:
        issue = Issue(
            level=IssueLevel.INFO,
            code=IssueCode.Z_TOLERANCE_APPLIED,
            message="test",
        )
        assert issue.context is None

    def test_is_frozen(self) -> None:
        issue = Issue(
            level=IssueLevel.INFO,
            code=IssueCode.Z_TOLERANCE_APPLIED,
            message="test",
        )
        with pytest.raises(AttributeError):
            issue.message = "changed"  # type: ignore[misc]
