# Tests for pymedphys._constraints.head_neck_dvh
# Shanghai Ninth People's Hospital Head & Neck RT Series

import pytest
from pymedphys._constraints.head_neck_dvh import (
    bed, eqd2, ser_adjusted_dose, cumulative_bed,
    HEAD_NECK_CONSTRAINTS, check_constraint, check_plan,
    screen_reirradiation, Modality, ViolationLevel
)


class TestBED:
    """BED calculation verification against known reference values."""

    def test_bed_conventional(self):
        # 60 Gy / 30 fx @2 Gy, α/β=3 → BED₃ = 100
        assert abs(bed(2.0, 30, 3) - 100.0) < 0.1

    def test_bed_sbrt(self):
        # 3.5 Gy × 6, α/β=10 (tumor) → BED₁₀ = 28.35
        b = bed(3.5, 6, 10)
        assert 28.0 < b < 29.0

    def test_eqd2_conversion(self):
        # BED₃=100 → EQD2 = 60 Gy
        eq = eqd2(100.0, 3)
        assert 59.5 < eq < 60.5

    def test_eqd2_tumor(self):
        # 3.5 Gy × 6 for tumor → EQD2 ~23.6 Gy
        b = bed(3.5, 6, 10)
        eq = eqd2(b, 10)
        assert 23.0 < eq < 24.5

    def test_ser_default(self):
        assert ser_adjusted_dose(3.5) == 3.5

    def test_ser_enhancement(self):
        assert 4.0 < ser_adjusted_dose(3.5, 1.2) < 4.5
        assert 5.0 < ser_adjusted_dose(3.5, 1.5) < 5.5

    def test_cumulative_bed_no_gap(self):
        regimens = [(2.0, 30, 1.0)]
        cb = cumulative_bed(regimens, 0, 3, True)
        assert 95 < cb < 105

    def test_cumulative_bed_2yr_gap(self):
        regimens = [(2.0, 30, 1.0)]
        cb = cumulative_bed(regimens, 2.0, 3, True)
        assert 25 < cb < 35  # ~50% repair


class TestConstraints:
    """Verify constraint database integrity."""

    def test_all_hard_constraints_present(self):
        hard = ["spinal_cord", "brainstem", "optic_chiasm", "optic_nerve", "lens"]
        for name in hard:
            assert name in HEAD_NECK_CONSTRAINTS
            assert HEAD_NECK_CONSTRAINTS[name]["level"] == "hard"

    def test_spinal_cord_conventional(self):
        c = HEAD_NECK_CONSTRAINTS["spinal_cord"]
        assert c["conventional"]["dmax"] == 45.0

    def test_brainstem_sbrt_5fx(self):
        c = HEAD_NECK_CONSTRAINTS["brainstem"]
        assert c["sbrt_5fx"]["dmax"] == 25.0

    def test_parotid_mean(self):
        c = HEAD_NECK_CONSTRAINTS["parotid_contralateral"]
        assert c["conventional"]["dmean"] == 26.0

    def test_all_have_source(self):
        for name, c in HEAD_NECK_CONSTRAINTS.items():
            assert "source" in c, f"{name} missing source"


class TestCheckPlan:
    """Plan evaluation tests."""

    def test_pass_plan(self):
        metrics = {
            "spinal_cord": {"dmax": 43.0},
            "brainstem": {"dmax": 52.0},
            "parotid_contralateral": {"dmean": 24.0},
        }
        r = check_plan(Modality.CONVENTIONAL, metrics)
        assert r["plan_pass"] is True
        assert len(r["hard_fails"]) == 0

    def test_hard_fail_spinal_cord(self):
        metrics = {"spinal_cord": {"dmax": 60.0}}  # >30% over
        r = check_plan(Modality.CONVENTIONAL, metrics)
        assert r["plan_pass"] is False
        assert len(r["hard_fails"]) == 1

    def test_near_limit_brainstem(self):
        metrics = {"brainstem": {"dmax": 56.0}}  # ~4% over
        r = check_plan(Modality.CONVENTIONAL, metrics)
        assert len(r["near_limits"]) > 0

    def test_unknown_oar(self):
        r = check_constraint("nonexistent_oar", Modality.CONVENTIONAL, {"dmax": 10})
        assert r["overall"] == "error"


class TestReirradiation:
    """Re-irradiation screening verification."""

    def test_2yr_gap_60gy(self):
        regimens = screen_reirradiation(60, 30, 2.0)
        names = [r["regimen"] for r in regimens]
        assert "Conventional 2 Gy/fx" in names
        assert len(regimens) >= 2

    def test_recent_rt_limited(self):
        regimens = screen_reirradiation(60, 30, 0.3)  # only 3 months
        names = [r["regimen"] for r in regimens]
        assert "Conventional 2 Gy/fx" in names  # always available
        assert "Quad-Shot" not in " ".join(names)  # too recent for Quad-Shot

    def test_sbrt_screened_out(self):
        regimens = screen_reirradiation(60, 30, 1.0)
        names = [r["regimen"] for r in regimens]
        assert "SBRT" not in " ".join(names)  # not safe with 60 Gy prior


class TestViolationLevels:
    """Violation severity grading."""

    def test_pass(self):
        r = check_constraint("spinal_cord", Modality.CONVENTIONAL, {"dmax": 40.0})
        assert r["overall"] == "pass"

    def test_near_limit(self):
        r = check_constraint("spinal_cord", Modality.CONVENTIONAL, {"dmax": 47.0})
        assert r["overall"] == "near_limit"

    def test_soft_fail(self):
        r = check_constraint("parotid_contralateral", Modality.CONVENTIONAL, {"dmean": 30.0})
        assert r["overall"] in ("soft_fail", "near_limit")
