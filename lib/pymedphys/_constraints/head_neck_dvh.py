# pymedphys contribution: Head & Neck DVH constraint library
# To be placed at: lib/pymedphys/_constraints/head_neck_dvh.py
#
# Unless an entry states otherwise, values are departmental planning targets
# (Shanghai Ninth People's Hospital Head & Neck RT Series) informed by
# QUANTEC (IJROBP 2010;76(3 Suppl)), AAPM TG-101 and UK SABR 2022. QUANTEC /
# TG-101 are named as the source only where the number is taken from them.
# Clinical source: Shanghai Ninth People's Hospital Head & Neck RT Series
# GitHub: https://github.com/antica1

import math
from enum import Enum

# ── Constants ─────────────────────────────────────────────

ALPHA_BETA_TUMOR = 10  # Gy (HNSCC)
ALPHA_BETA_LATE = 3  # Gy (CNS, bone, soft tissue late effects)


class ViolationLevel(Enum):
    PASS = "pass"  # within limit
    NEAR_LIMIT = "near_limit"  # soft-level limit exceeded by <10%
    SOFT_FAIL = "soft_fail"  # soft-level limit exceeded by 10-30%, negotiable
    HARD_FAIL = "hard_fail"  # soft-level limit exceeded by >30%, or ANY exceedance of a hard-level constraint


class Modality(Enum):
    CONVENTIONAL = "conventional"  # 30-33 fx, 1.8-2.0 Gy/fx
    SBRT_1FX = "sbrt_1fx"
    SBRT_3FX = "sbrt_3fx"
    SBRT_5FX = "sbrt_5fx"


# ── OAR Constraint Database ───────────────────────────────

HEAD_NECK_CONSTRAINTS: dict[str, dict] = {
    # --- Hard constraints (one-strike: any exceedance is a hard fail) ---
    "spinal_cord": {
        "level": "hard",
        "conventional": {"dmax": 45.0, "unit": "Gy"},
        "sbrt_1fx": {"dmax": 14.0},
        "sbrt_3fx": {"dmax": 21.0},
        "sbrt_5fx": {"dmax": 25.0},
        "source": "Institutional hard limit (45 Gy); dose-risk data: QUANTEC 2010, AAPM TG-101, UK SABR 2022",
        "note": "Animal model extrapolation: Dmax 50 Gy at 2 Gy/fx = 0.2% myelopathy risk (QUANTEC 2010). 45 Gy is the departmental conservative limit.",
    },
    "brainstem": {
        "level": "hard",
        "conventional": {"dmax": 54.0, "unit": "Gy"},
        "sbrt_1fx": {"dmax": 14.0},
        "sbrt_3fx": {"dmax": 21.0},
        "sbrt_5fx": {"dmax": 25.0},
        "source": "QUANTEC 2010 (conventional); AAPM TG-101, UK SABR 2022 (SBRT)",
    },
    "optic_chiasm": {
        "level": "hard",
        "conventional": {"dmax": 54.0, "unit": "Gy"},
        "sbrt_1fx": {"dmax": 10.0},
        "sbrt_3fx": {"d0_03cc": 17.0},
        "sbrt_5fx": {"d0_03cc": 23.0},
        "source": "QUANTEC 2010 (Dmax <55 Gy; institutional limit 54 Gy); AAPM TG-101 (SBRT)",
    },
    "optic_nerve": {
        "level": "hard",
        "conventional": {"dmax": 54.0, "unit": "Gy"},
        "sbrt_1fx": {"dmax": 10.0},
        "sbrt_3fx": {"d0_03cc": 17.0},
        "sbrt_5fx": {"d0_03cc": 23.0},
        "source": "QUANTEC 2010 (Dmax <55 Gy; institutional limit 54 Gy); AAPM TG-101 (SBRT)",
    },
    "lens": {
        "level": "hard",
        "conventional": {"dmax": 10.0, "unit": "Gy"},
        "source": "Institutional H&N protocol (lens tolerance literature; QUANTEC has no lens recommendation)",
    },
    # --- Soft constraints ---
    "parotid_contralateral": {
        "level": "soft",
        "conventional": {"dmean": 26.0, "unit": "Gy"},
        "source": "Institutional H&N IMRT protocol planning target (not a QUANTEC value)",
        "note": "Outcome targeted: long-term xerostomia. QUANTEC 2010 (Deasy et al., PMID 20171519) instead gives a paired-gland rule - at least one parotid mean <20 Gy, or both glands <25 Gy - which check_plan() applies when both parotids are supplied.",
    },
    "parotid_ipsilateral": {
        "level": "soft",
        "conventional": {"dmean": 30.0, "unit": "Gy"},
        "source": "Institutional H&N IMRT protocol planning target (not a QUANTEC value)",
        "note": "Outcome targeted: long-term xerostomia. See parotid_contralateral for the QUANTEC paired-gland rule applied in check_plan().",
    },
    "cochlea": {
        "level": "soft",
        "conventional": {"dmean": 45.0, "unit": "Gy"},
        "source": "QUANTEC 2010 (Dmean <=45 Gy)",
    },
    "mandible": {
        "level": "soft",
        "conventional": {"dmax": 70.0, "v60": 30.0, "unit": "Gy"},
        "source": "Institutional H&N protocol (ORN literature; QUANTEC has no mandible recommendation)",
    },
    "pharyngeal_constrictors": {
        "level": "soft",
        "conventional": {"dmean": 50.0, "unit": "Gy"},
        "source": "Institutional H&N IMRT target; cf. QUANTEC larynx/pharynx 2010 (Rancati et al.)",
    },
    "lacrimal_gland": {
        "level": "soft",
        "conventional": {"dmean": 25.0, "unit": "Gy"},
        "source": "Shanghai Ninth People's Hospital",
    },
    "brachial_plexus": {
        "level": "soft",
        "conventional": {"dmax": 66.0, "unit": "Gy"},
        "sbrt_1fx": {"dmax": 17.5},
        "sbrt_3fx": {"dmax": 24.0},
        "sbrt_5fx": {"dmax": 30.5},
        "source": "Conventional: RTOG H&N protocols (60-66 Gy). SBRT: AAPM TG-101 Table III, max point dose <3 cc",
    },
    "oral_cavity": {
        "level": "soft",
        "conventional": {"dmean": 40.0, "unit": "Gy"},
        "source": "Institutional H&N IMRT protocol (not a QUANTEC value)",
    },
    "larynx": {
        "level": "soft",
        "conventional": {"dmean": 45.0, "unit": "Gy"},
        "source": "Institutional target 45 Gy; QUANTEC 2010 (Rancati et al.) recommends Dmean <=44 Gy for uninvolved larynx",
    },
}


# ── BED Calculation ───────────────────────────────────────


def bed(dose_per_fx: float, n_fractions: int, alpha_beta: float) -> float:
    """Biological Effective Dose.

    BED = n × d × (1 + d / (α/β))
    """
    return n_fractions * dose_per_fx * (1 + dose_per_fx / alpha_beta)


def eqd2(bed_value: float, alpha_beta: float) -> float:
    """Equivalent dose in 2 Gy fractions.

    EQD2 = BED / (1 + 2 / (α/β))
    """
    return bed_value / (1 + 2 / alpha_beta)


def ser_adjusted_dose(physical_dose: float, ser: float = 1.0) -> float:
    """Apply a Sensitizer Enhancement Ratio (SER) supplied by the caller.

    SER is a research assumption, not clinical guidance. The default of 1.0
    applies no enhancement.

    Published SER ranges are model-specific:
      1.1-1.3 = cisplatin/cetuximab (phase III tumour data)
      1.2-1.5 = ADC/IO (preclinical only, e.g. PMID:34074654 - a single
                anti-TIP1 ADC in NSCLC cell lines and xenografts)

    No prospective clinical data establish a general SER for ADCs or
    immunotherapy in head-and-neck normal tissues, and tumour-derived SERs
    must not be applied to normal-tissue BED without tissue-specific
    evidence. Callers should state which assumption they are using.
    """
    return physical_dose * ser


def cumulative_bed(
    regimens: list[tuple[float, int, float]],
    gap_years: float = 0,
    alpha_beta: float = ALPHA_BETA_LATE,
    gap_repair: bool = True,
) -> float:
    """Cumulative BED from multiple RT courses with gap repair correction.

    Args:
        regimens: list of (dose_per_fx, n_fractions, ser) tuples. SER defaults
            to 1.0 in this library; see ser_adjusted_dose() for why a
            non-unit SER is a caller-supplied research assumption and should
            not be used for normal-tissue BED without tissue-specific
            evidence.
        gap_years: time since last course
        alpha_beta: tissue α/β ratio
        gap_repair: apply gap repair correction for late effects

    Returns:
        Cumulative BED (Gy)

    Gap repair estimates (late-responding tissue only; departmental
    heuristic, applied to the PRIOR course):
      <6 months  → 0% repair
      6-12 months → 30% repair
      1-2 years   → 50% repair
      >2 years    → 70% repair
    """
    total_bed = sum(
        bed(ser_adjusted_dose(d, ser), n, alpha_beta) for d, n, ser in regimens
    )

    if gap_repair and gap_years > 0:
        if gap_years < 0.5:
            repair = 0.0
        elif gap_years < 1.0:
            repair = 0.30
        elif gap_years < 2.0:
            repair = 0.50
        else:
            repair = 0.70
        total_bed *= 1 - repair

    return total_bed


# ── Constraint Checking ───────────────────────────────────


def _is_valid_number(value) -> bool:
    """True only for finite, real measurements (not bool/NaN/inf/str)."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def check_constraint(
    oar_name: str, modality: Modality, metrics: dict[str, float]
) -> dict:
    """Check a single OAR against constraints.

    Args:
        oar_name: key from HEAD_NECK_CONSTRAINTS
        modality: fractionation scheme
        metrics: dict of measured values (e.g. {"dmax": 47.2, "dmean": 12.5})

    Returns:
        {
            "oar": str,
            "violations": [{"metric": "dmax", "limit": 45.0, "value": 47.2,
                           "excess_pct": 4.9, "level": "hard_fail"}],
            "overall": "pass" | "near_limit" | "soft_fail" | "hard_fail"
                       | "incomplete" | "not_evaluated" | "error"
        }

    Overall levels:
      - "hard_fail": ANY exceedance of a hard-level constraint (level
        "hard"), or >30% over a soft-level limit.
      - "soft_fail": 10-30% over a soft-level limit.
      - "near_limit": <10% over a soft-level limit.
      - "incomplete": one or more metrics required by this modality were not
        supplied, or were not finite numbers (e.g. NaN). An incomplete check
        is never a pass.
      - "not_evaluated": no limit is defined for the requested modality.
        Conventional limits are deliberately NOT borrowed for SBRT.
      - "error": unknown OAR name.
    """
    if oar_name not in HEAD_NECK_CONSTRAINTS:
        return {"oar": oar_name, "error": "unknown OAR", "overall": "error"}

    constraint = HEAD_NECK_CONSTRAINTS[oar_name]

    if modality.value not in constraint:
        return {
            "oar": oar_name,
            "level": constraint["level"],
            "violations": [],
            "overall": "not_evaluated",
            "reason": (
                f"no '{modality.value}' limit defined for {oar_name}; "
                "conventional limits are not applied to SBRT"
            ),
            "source": constraint["source"],
        }

    limits = constraint[modality.value]
    is_hard_oar = constraint["level"] == "hard"

    violations = []
    missing = []

    for metric_key, limit_value in limits.items():
        if metric_key == "unit":
            continue
        if metric_key not in metrics:
            missing.append(metric_key)
            continue
        measured = metrics[metric_key]
        if not _is_valid_number(measured):
            missing.append(f"{metric_key} (invalid value: {measured!r})")
            continue
        if measured > limit_value:
            excess_pct = (measured - limit_value) / limit_value * 100
            if is_hard_oar:
                # Any exceedance of a hard constraint is a hard fail.
                # The percentage over the limit is still reported as info.
                level = ViolationLevel.HARD_FAIL
            elif excess_pct > 30:
                level = ViolationLevel.HARD_FAIL
            elif excess_pct >= 10:
                level = ViolationLevel.SOFT_FAIL
            elif excess_pct > 0:
                level = ViolationLevel.NEAR_LIMIT
            else:
                level = ViolationLevel.PASS
            violations.append(
                {
                    "metric": metric_key,
                    "limit": limit_value,
                    "value": measured,
                    "excess_pct": round(excess_pct, 1),
                    "level": level.value,
                }
            )

    if missing:
        # A check that was not performed cannot be reported as a pass.
        overall = "incomplete"
    elif not violations:
        overall = ViolationLevel.PASS.value
    else:
        levels = [ViolationLevel(v["level"]) for v in violations]
        if ViolationLevel.HARD_FAIL in levels:
            overall = ViolationLevel.HARD_FAIL.value
        elif ViolationLevel.SOFT_FAIL in levels:
            overall = ViolationLevel.SOFT_FAIL.value
        else:
            overall = ViolationLevel.NEAR_LIMIT.value

    result = {
        "oar": oar_name,
        "level": constraint["level"],
        "violations": violations,
        "overall": overall,
        "source": constraint["source"],
    }
    if missing:
        result["missing"] = missing
    return result


def _check_parotid_pair_quantec(metrics: dict[str, dict[str, float]]) -> dict | None:
    """QUANTEC paired-gland parotid rule (Deasy et al., IJROBP 2010;76(3 Suppl):S58-63, PMID 20171519).

    At least one parotid gland spared to mean <20 Gy, OR both glands spared
    to mean <25 Gy, usually avoids severe long-term xerostomia. Applied
    jointly to both glands; the per-gland institutional targets in
    HEAD_NECK_CONSTRAINTS are separate planning targets.

    Returns None unless both glands carry a finite dmean.
    """
    try:
        contra = metrics["parotid_contralateral"]["dmean"]
        ipsi = metrics["parotid_ipsilateral"]["dmean"]
    except (KeyError, TypeError):
        return None
    if not (_is_valid_number(contra) and _is_valid_number(ipsi)):
        return None
    pair_pass = min(contra, ipsi) < 20.0 or max(contra, ipsi) < 25.0
    return {
        "rule": "QUANTEC: at least one parotid gland mean < 20 Gy, or both glands mean < 25 Gy",
        "outcome": "severe long-term xerostomia usually avoided",
        "contralateral_dmean": contra,
        "ipsilateral_dmean": ipsi,
        "pass": pair_pass,
        "source": "QUANTEC 2010 (Deasy et al., IJROBP 76(3 Suppl):S58-63, PMID 20171519)",
    }


def check_plan(
    modality: Modality,
    metrics: dict[str, dict[str, float]],
    corrections: dict | None = None,
) -> dict:
    """Full plan check against head & neck constraints.

    Args:
        modality: fractionation scheme
        metrics: {"spinal_cord": {"dmax": 43.0}, "brainstem": {"dmax": 52.0}, ...}
        corrections: NOT SUPPORTED - passing any value raises ValueError.
            (The argument used to be accepted and silently ignored.) BED or
            partial-volume adjustments must be applied by the caller before
            comparing against these limits.

    Returns:
        {
            "plan_pass": bool,      # True only if every requested check was
                                    # completed AND no hard constraint was
                                    # exceeded
            "plan_status": "pass" | "fail" | "incomplete",
            "hard_fails": [...],
            "soft_fails": [...],    # reported; do not by themselves block pass
            "near_limits": [...],
            "incomplete": [...],    # missing/invalid metrics, unknown OARs,
                                    # or modalities with no defined limit
            "all_results": [...],
            "parotid_pair_quantec": {...} | None,  # reported when both
                                    # parotids supplied; informational
        }

    Example:
        >>> metrics = {"spinal_cord": {"dmax": 47.0}, "brainstem": {"dmax": 53.0},
        ...            "parotid_contralateral": {"dmean": 24.0}}
        >>> result = check_plan(Modality.CONVENTIONAL, metrics)
        >>> result["plan_pass"]
        False  # spinal cord hard constraint exceeded
    """
    if corrections is not None:
        raise ValueError(
            "check_plan() does not support 'corrections'; apply BED or "
            "partial-volume adjustments to the measured values before "
            "calling, or compare against adjusted limits explicitly."
        )

    results = []
    hard_fails, soft_fails, near_limits, incomplete = [], [], [], []

    for oar_name, oar_metrics in metrics.items():
        r = check_constraint(oar_name, modality, oar_metrics)
        results.append(r)

        if r["overall"] == "hard_fail":
            hard_fails.append(r)
        elif r["overall"] == "soft_fail":
            soft_fails.append(r)
        elif r["overall"] == "near_limit":
            near_limits.append(r)
        elif r["overall"] != "pass":
            # incomplete / not_evaluated / error: cannot certify a pass
            incomplete.append(r)

    if hard_fails:
        plan_status = "fail"
    elif incomplete:
        plan_status = "incomplete"
    else:
        plan_status = "pass"

    return {
        "plan_pass": plan_status == "pass",
        "plan_status": plan_status,
        "hard_fails": hard_fails,
        "soft_fails": soft_fails,
        "near_limits": near_limits,
        "incomplete": incomplete,
        "all_results": results,
        "parotid_pair_quantec": _check_parotid_pair_quantec(metrics),
        "modality": modality.value,
    }


# ── Re-Irradiation Dose Estimation ─────────────────────────

REIRRADIATION_REGIMENS = {
    "quad_shot_io": {
        "name": "Quad-Shot + Pembrolizumab",
        "prescription": "3.7 Gy/fx x 4 per cycle BID, Q4w x 3 cycles",
        "dose_per_fx": 3.7,
        "fractions_per_cycle": 4,
        "cycles": 3,  # 12 fx, 44.4 Gy total
        "evidence": "JAMA Otolaryngol 2026 (PMID:42313403)",
        "min_gap_years": 3.0,
        "screening_threshold_eqd2": 50.0,
    },
    "q3w_io": {
        "name": "Q3w 3.5 Gy + IO/ADC",
        "prescription": "3.5 Gy x 1 fx Q3w x 6 cycles",
        "dose_per_fx": 3.5,
        "fractions_per_cycle": 1,
        "cycles": 6,  # 6 fx, 21.0 Gy total
        "evidence": "Shanghai Ninth People's Hospital institutional regimen",
        "min_gap_years": 0.5,
        "screening_threshold_eqd2": 50.0,
    },
    "conventional": {
        "name": "Conventional 2 Gy/fx",
        "prescription": "2 Gy x 15 fx (typical starting course)",
        "dose_per_fx": 2.0,
        "fractions_per_cycle": 15,
        "cycles": 1,  # 15 fx, 30.0 Gy total
        "evidence": "Standard clinical practice",
        "min_gap_years": 0.0,
        "screening_threshold_eqd2": 60.0,  # cumulative BED3 = 100 Gy
    },
    "sbrt_continuous": {
        "name": "SBRT 5-6 Gy x 5 + IO",
        "prescription": "5.5 Gy x 5 fx (midpoint of 5-6 Gy range)",
        "dose_per_fx": 5.5,
        "fractions_per_cycle": 5,
        "cycles": 1,  # 5 fx, 27.5 Gy total
        "evidence": "Phase I/II (PMID:37105404, PMID:38892731)",
        "min_gap_years": 2.0,
        "screening_threshold_eqd2": 50.0,
    },
}


def screen_reirradiation(
    prior_dose: float, prior_fractions: int, gap_years: float
) -> list[dict]:
    """Prescription-level re-irradiation dose ESTIMATION (not a safety tool).

    Computes cumulative EQD2 (alpha/beta = 3 Gy) = prior course (gap-repair
    adjusted) + each option at the dose and fraction count it actually lists.

    Scope and documented assumptions - the output is an estimate, not a
    clinical safety determination:
      - The prior course is assumed to deliver its prescription dose to the
        organs at risk. Actual organ doses and old/new field overlap are NOT
        known to this function and must be judged separately per organ.
      - Prior-course gap repair (late tissue) uses cumulative_bed():
        <6 mo 0%, 6-12 mo 30%, 1-2 yr 50%, >2 yr 70% - a departmental
        heuristic.
      - No intra-course recovery is credited for the new course
        (conservative).
      - "screening_threshold_eqd2" values are institutional screening
        references (departmental practice), NOT organ-specific tolerance
        limits - e.g. spinal cord and bowel re-irradiation tolerances differ
        and must be checked separately.

    Returns:
        List of dicts, sorted by cumulative_eqd2:
        {
            "regimen", "prescription",
            "new_course_total_dose_gy", "new_course_eqd2",
            "prior_residual_eqd2", "cumulative_eqd2",
            "screening_threshold_eqd2", "below_screening_threshold": bool,
            "evidence",
        }
    """
    residual_bed = cumulative_bed(
        [(prior_dose / prior_fractions, prior_fractions, 1.0)],
        gap_years,
        ALPHA_BETA_LATE,
        True,
    )
    residual_eqd2 = eqd2(residual_bed, ALPHA_BETA_LATE)

    results = []
    for regimen in REIRRADIATION_REGIMENS.values():
        if gap_years < regimen["min_gap_years"]:
            continue

        n_fx = regimen["fractions_per_cycle"] * regimen["cycles"]
        new_bed = bed(regimen["dose_per_fx"], n_fx, ALPHA_BETA_LATE)
        new_eqd2 = eqd2(new_bed, ALPHA_BETA_LATE)
        cumulative_eqd2 = eqd2(residual_bed + new_bed, ALPHA_BETA_LATE)
        threshold = regimen["screening_threshold_eqd2"]

        results.append(
            {
                "regimen": regimen["name"],
                "prescription": regimen["prescription"],
                "new_course_total_dose_gy": round(regimen["dose_per_fx"] * n_fx, 1),
                "new_course_eqd2": round(new_eqd2, 1),
                "prior_residual_eqd2": round(residual_eqd2, 1),
                "cumulative_eqd2": round(cumulative_eqd2, 1),
                "screening_threshold_eqd2": threshold,
                "below_screening_threshold": cumulative_eqd2 < threshold,
                "evidence": regimen["evidence"],
            }
        )

    return sorted(results, key=lambda x: x["cumulative_eqd2"])
