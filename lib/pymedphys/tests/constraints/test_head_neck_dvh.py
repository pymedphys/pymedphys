# Tests for pymedphys._constraints.head_neck_dvh
# Shanghai Ninth People's Hospital Head & Neck RT Series
#
# Tests cover the behaviours requested in the PR review:
# - P1: hard-limit exceedance blocks pass; missing/invalid metrics never pass;
#       re-irradiation totals computed from the listed dose and fractions.
# - P2: SBRT modalities do not borrow conventional limits; parotid sources
#       separated from QUANTEC and paired-gland rule applied; SER documented
#       as a caller-supplied research assumption (no clinical advice).

import pytest

from pymedphys._constraints.head_neck_dvh import (
    HEAD_NECK_CONSTRAINTS,
    Modality,
    ViolationLevel,
    bed,
    check_constraint,
    check_plan,
    cumulative_bed,
    eqd2,
    screen_reirradiation,
    ser_adjusted_dose,
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

    def test_brachial_plexus_sbrt_limits_present(self):
        """TG-101 Table III max point dose (brachial plexus <3 cc)."""
        bp = HEAD_NECK_CONSTRAINTS["brachial_plexus"]
        assert bp["sbrt_1fx"]["dmax"] == 17.5
        assert bp["sbrt_3fx"]["dmax"] == 24.0
        assert bp["sbrt_5fx"]["dmax"] == 30.5
        assert "TG-101" in bp["source"]

    def test_parotid_source_not_claimed_as_quantec(self):
        """Per-gland 26/30 Gy are institutional targets, not QUANTEC numbers."""
        for name in ("parotid_contralateral", "parotid_ipsilateral"):
            c = HEAD_NECK_CONSTRAINTS[name]
            assert "not a QUANTEC value" in c["source"]
        note = HEAD_NECK_CONSTRAINTS["parotid_contralateral"]["note"]
        assert "20 Gy" in note and "25 Gy" in note

    def test_soft_constraint_levels(self):
        """Non-hard OARs must be marked as 'soft' to prevent severity misclassification."""
        soft_structures = [
            "parotid_contralateral",
            "parotid_ipsilateral",
            "mandible",
            "cochlea",
            "pharyngeal_constrictors",
            "lacrimal_gland",
            "brachial_plexus",
            "oral_cavity",
            "larynx",
        ]
        for name in soft_structures:
            assert name in HEAD_NECK_CONSTRAINTS, f"{name} missing"
            assert HEAD_NECK_CONSTRAINTS[name]["level"] == "soft", (
                f"{name} level={HEAD_NECK_CONSTRAINTS[name]['level']}, expected 'soft'"
            )


class TestSBRTModalityLimits:
    """SBRT checks must use SBRT limits, never borrowed conventional ones (P2)."""

    def test_missing_sbrt_limit_not_evaluated(self):
        """Lens has no SBRT entry → 'not_evaluated', not a pass against 10 Gy."""
        lens = HEAD_NECK_CONSTRAINTS["lens"]
        assert "sbrt_5fx" not in lens
        r = check_constraint("lens", Modality.SBRT_5FX, {"dmax": 5.0})
        assert r["overall"] == "not_evaluated"

    def test_brachial_plexus_sbrt_1fx_checked_against_tg101(self):
        """20 Gy in 1 fx exceeds TG-101's 17.5 Gy max point dose."""
        r = check_constraint("brachial_plexus", Modality.SBRT_1FX, {"dmax": 20.0})
        assert r["overall"] == "soft_fail"
        assert r["violations"][0]["limit"] == 17.5

        r_ok = check_constraint("brachial_plexus", Modality.SBRT_1FX, {"dmax": 16.0})
        assert r_ok["overall"] == "pass"

    def test_not_evaluated_blocks_plan_pass(self):
        r = check_plan(Modality.SBRT_5FX, {"lens": {"dmax": 5.0}})
        assert r["plan_pass"] is False
        assert r["plan_status"] == "incomplete"


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
        assert r["plan_status"] == "pass"
        assert len(r["hard_fails"]) == 0

    def test_hard_fail_spinal_cord(self):
        metrics = {"spinal_cord": {"dmax": 60.0}}  # >30% over
        r = check_plan(Modality.CONVENTIONAL, metrics)
        assert r["plan_pass"] is False
        assert len(r["hard_fails"]) == 1

    def test_hard_limit_exceedance_blocks_pass(self):
        """P1: 47 Gy spinal cord (hard limit 45) must not pass; 58 Gy neither."""
        for dose in (47.0, 58.0):
            r = check_plan(Modality.CONVENTIONAL, {"spinal_cord": {"dmax": dose}})
            assert r["plan_pass"] is False, f"dmax {dose} passed"
            assert r["plan_status"] == "fail"
            assert r["hard_fails"][0]["violations"][0]["level"] == "hard_fail"

    def test_docstring_example_matches_behaviour(self):
        metrics = {
            "spinal_cord": {"dmax": 47.0},
            "brainstem": {"dmax": 53.0},
            "parotid_contralateral": {"dmean": 24.0},
        }
        assert check_plan(Modality.CONVENTIONAL, metrics)["plan_pass"] is False

    def test_missing_required_metric_cannot_pass(self):
        """P1: dmax missing (only dmean supplied) → incomplete, never pass."""
        r = check_constraint("spinal_cord", Modality.CONVENTIONAL, {"dmean": 100.0})
        assert r["overall"] == "incomplete"
        assert "dmax" in r["missing"]

        p = check_plan(Modality.CONVENTIONAL, {"spinal_cord": {"dmean": 100.0}})
        assert p["plan_pass"] is False
        assert p["plan_status"] == "incomplete"

    def test_nan_metric_cannot_pass(self):
        r = check_plan(Modality.CONVENTIONAL, {"spinal_cord": {"dmax": float("nan")}})
        assert r["plan_pass"] is False
        assert r["plan_status"] == "incomplete"

    def test_unknown_oar_cannot_pass(self):
        r = check_plan(Modality.CONVENTIONAL, {"not_an_oar": {"dmax": 999.0}})
        assert r["plan_pass"] is False
        assert r["plan_status"] == "incomplete"
        assert r["incomplete"][0]["overall"] == "error"

    def test_corrections_argument_rejected(self):
        """Previously accepted and silently ignored."""
        with pytest.raises(ValueError):
            check_plan(
                Modality.CONVENTIONAL,
                {"spinal_cord": {"dmax": 40.0}},
                corrections={"partial_volume": True},
            )
        # None (the default) remains accepted
        check_plan(
            Modality.CONVENTIONAL, {"spinal_cord": {"dmax": 40.0}}, corrections=None
        )

    def test_parotid_pair_quantec_rule(self):
        """QUANTEC paired rule: one gland <20 Gy, or both <25 Gy."""
        # 25.5 / 29: meets institutional 26/30 targets but NOT the QUANTEC rule
        r = check_plan(
            Modality.CONVENTIONAL,
            {
                "parotid_contralateral": {"dmean": 25.5},
                "parotid_ipsilateral": {"dmean": 29.0},
            },
        )
        pair = r["parotid_pair_quantec"]
        assert pair is not None and pair["pass"] is False
        # per-gland institutional targets still pass; the two systems are separate
        assert r["plan_pass"] is True

        # one gland <20 → QUANTEC rule met
        r2 = check_plan(
            Modality.CONVENTIONAL,
            {
                "parotid_contralateral": {"dmean": 19.0},
                "parotid_ipsilateral": {"dmean": 30.0},
            },
        )
        assert r2["parotid_pair_quantec"]["pass"] is True

        # both <25 → QUANTEC rule met
        r3 = check_plan(
            Modality.CONVENTIONAL,
            {
                "parotid_contralateral": {"dmean": 24.0},
                "parotid_ipsilateral": {"dmean": 23.0},
            },
        )
        assert r3["parotid_pair_quantec"]["pass"] is True

    def test_parotid_pair_none_when_single_gland(self):
        r = check_plan(
            Modality.CONVENTIONAL,
            {
                "parotid_contralateral": {"dmean": 24.0},
            },
        )
        assert r["parotid_pair_quantec"] is None


class TestReirradiation:
    """Re-irradiation dose estimation verification."""

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
        assert "SBRT" not in " ".join(names)  # gap < 2 yr

    def test_conventional_option_uses_listed_dose(self):
        """P1: 60 Gy/30 fx prior at 1 yr → residual 30 EQD2 + listed 30 Gy
        course (15 fx × 2 Gy = 30 EQD2) = 60 EQD2, which is NOT below the
        60 Gy screening threshold."""
        results = {r["regimen"]: r for r in screen_reirradiation(60, 30, 1.0)}
        conv = results["Conventional 2 Gy/fx"]
        assert conv["new_course_total_dose_gy"] == 30.0
        assert abs(conv["new_course_eqd2"] - 30.0) < 0.2
        assert abs(conv["prior_residual_eqd2"] - 30.0) < 0.2
        assert abs(conv["cumulative_eqd2"] - 60.0) < 0.2
        assert conv["below_screening_threshold"] is False

    def test_q3w_option_uses_listed_six_cycles(self):
        """P1: Q3w lists 6 cycles (6 fx × 3.5 Gy = 21 Gy), not 3."""
        results = {r["regimen"]: r for r in screen_reirradiation(60, 30, 1.0)}
        q3w = results["Q3w 3.5 Gy + IO/ADC"]
        assert q3w["new_course_total_dose_gy"] == 21.0
        expected_eqd2 = eqd2(bed(3.5, 6, 3), 3)  # ≈27.3
        assert abs(q3w["new_course_eqd2"] - expected_eqd2) < 0.2

    def test_sbrt_course_bed_not_scaled_per_cycle(self):
        """P1: SBRT entry is one 5-fx course; its BED must not be multiplied."""
        results = {r["regimen"]: r for r in screen_reirradiation(60, 30, 2.0)}
        sbrt = results["SBRT 5-6 Gy x 5 + IO"]
        assert sbrt["new_course_total_dose_gy"] == 27.5
        expected_eqd2 = eqd2(bed(5.5, 5, 3), 3)  # ≈46.7
        assert abs(sbrt["new_course_eqd2"] - expected_eqd2) < 0.2

    def test_quad_shot_full_three_cycle_course(self):
        results = {r["regimen"]: r for r in screen_reirradiation(60, 30, 3.0)}
        quad = results["Quad-Shot + Pembrolizumab"]
        assert quad["new_course_total_dose_gy"] == 44.4
        expected_eqd2 = eqd2(bed(3.7, 12, 3), 3)  # ≈59.5
        assert abs(quad["new_course_eqd2"] - expected_eqd2) < 0.2

    def test_no_safety_label_in_output(self):
        """P1: prescription-level estimation must not claim 'safe'."""
        for r in screen_reirradiation(60, 30, 3.0):
            assert "safe" not in r
            assert "below_screening_threshold" in r
            assert "screening_threshold_eqd2" in r


class TestViolationLevels:
    """Violation severity grading."""

    def test_pass(self):
        r = check_constraint("spinal_cord", Modality.CONVENTIONAL, {"dmax": 40.0})
        assert r["overall"] == "pass"

    def test_hard_oar_any_exceedance_is_hard_fail(self):
        """P1: hard-level OAR exceeded by any margin is a hard fail."""
        r = check_constraint("spinal_cord", Modality.CONVENTIONAL, {"dmax": 47.0})
        assert r["overall"] == "hard_fail"
        assert r["violations"][0]["excess_pct"] == pytest.approx(4.4, abs=0.1)

        r2 = check_constraint("brainstem", Modality.CONVENTIONAL, {"dmax": 56.0})
        assert r2["overall"] == "hard_fail"

    def test_soft_oar_near_limit(self):
        r = check_constraint(
            "parotid_contralateral", Modality.CONVENTIONAL, {"dmean": 27.0}
        )
        assert r["overall"] == "near_limit"

    def test_soft_fail(self):
        r = check_constraint(
            "parotid_contralateral", Modality.CONVENTIONAL, {"dmean": 30.0}
        )
        assert r["overall"] == "soft_fail"

    def test_soft_fail_boundary_at_10_percent(self):
        """Exactly 10% over a soft limit is a soft fail, per the enum docs."""
        r = check_constraint(
            "parotid_contralateral", Modality.CONVENTIONAL, {"dmean": 28.6}
        )
        assert r["overall"] == "soft_fail"

    def test_soft_over_30_percent_is_hard_fail(self):
        r = check_constraint(
            "parotid_contralateral", Modality.CONVENTIONAL, {"dmean": 34.0}
        )
        assert r["overall"] == "hard_fail"
