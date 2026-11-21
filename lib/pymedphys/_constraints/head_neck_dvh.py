# Copyright (C) 2026 Guopei Zhu
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Head & Neck DVH constraint library.

Each limit carries its own source in HEAD_NECK_CONSTRAINTS: published
values name the publication and table where available; values without a
published source are labelled as departmental planning targets.
Clinical source: Shanghai Ninth People's Hospital Head & Neck RT Series
GitHub: https://github.com/antica1
"""

import math
from enum import Enum

# ── Constants ─────────────────────────────────────────────

ALPHA_BETA_TUMOR = 10  # Gy (HNSCC)
ALPHA_BETA_LATE = 3  # Gy (default for late endpoints in this module; see
# screen_reirradiation for the α/β discussion)


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
        "sbrt_1fx": {"d0_035cc": 14.0},
        "sbrt_3fx": {"d0_035cc": 20.3},
        "sbrt_5fx": {"d0_035cc": 25.3},
        "source": "conventional 45 Gy: departmental hard limit (risk data: QUANTEC 2010, Kirkpatrick - Dmax 50 Gy at 2 Gy/fx ~0.2% myelopathy); SBRT 14/20.3/25.3 Gy: UK SABR 2022 (PMID:35272913) Table 5, D0.035 cc",
        "note": "Animal model extrapolation for the conventional limit; the SBRT numbers are consensus tolerance doses for D0.035 cc.",
        "required_structure": {
            "conventional": "spinal cord (anatomical cord, full cross-section)",
            "sbrt_1fx": "cord PRV (spinal targets) or bony canal (non-spinal targets)",
            "sbrt_3fx": "cord PRV (spinal targets) or bony canal (non-spinal targets)",
            "sbrt_5fx": "cord PRV (spinal targets) or bony canal (non-spinal targets)",
        },
    },
    "brainstem": {
        "level": "hard",
        "conventional": {"dmax": 54.0, "unit": "Gy"},
        "sbrt_1fx": {"d0_035cc": 15.0},
        "sbrt_3fx": {"d0_035cc": 23.1},
        "sbrt_5fx": {"d0_035cc": 31.0},
        "source": "conventional 54 Gy: QUANTEC 2010 (Dmax <54 Gy); SBRT 15/23.1/31 Gy: UK SABR 2022 (PMID:35272913) Table 6, D0.035 cc",
    },
    "optic_chiasm": {
        "level": "hard",
        "conventional": {"dmax": 54.0, "unit": "Gy"},
        "sbrt_1fx": {"d0_035cc": 10.0},
        "sbrt_3fx": {"d0_035cc": 20.0},
        "sbrt_5fx": {"d0_035cc": 25.0},
        "source": "conventional 54 Gy: departmental limit (QUANTEC 2010 gives Dmax <55 Gy); SBRT 10/20/25 Gy: UK SABR 2022 (PMID:35272913) Table 6, D0.035 cc",
    },
    "optic_nerve": {
        "level": "hard",
        "conventional": {"dmax": 54.0, "unit": "Gy"},
        "sbrt_1fx": {"d0_035cc": 10.0},
        "sbrt_3fx": {"d0_035cc": 20.0},
        "sbrt_5fx": {"d0_035cc": 25.0},
        "source": "conventional 54 Gy: departmental limit (QUANTEC 2010 gives Dmax <55 Gy); SBRT 10/20/25 Gy: UK SABR 2022 (PMID:35272913) Table 6, D0.035 cc",
    },
    "lens": {
        "level": "hard",
        "conventional": {"dmax": 10.0, "unit": "Gy"},
        "sbrt_1fx": {"d0_035cc": 1.5},
        "source": "conventional 10 Gy: institutional H&N protocol (lens tolerance literature; the QUANTEC 2010 supplement has no lens review). SBRT 1 fx 1.5 Gy: UK SABR 2022 (PMID:35272913) Table 6, D0.035 cc",
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
        "source": "QUANTEC 2010 (mean dose <=45 Gy, Dmean for hearing loss)",
    },
    "mandible": {
        "level": "soft",
        "conventional": {"dmax": 70.0, "v60": 30.0, "unit": "Gy"},
        "source": "Institutional H&N protocol (ORN literature; the QUANTEC 2010 supplement has no mandible review)",
    },
    "pharyngeal_constrictors": {
        "level": "soft",
        "conventional": {"dmean": 50.0, "unit": "Gy"},
        "source": "Institutional H&N IMRT target; cf. QUANTEC larynx/pharynx 2010 (Rancati et al.)",
    },
    "lacrimal_gland": {
        "level": "soft",
        "conventional": {"dmean": 25.0, "unit": "Gy"},
        "source": "Shanghai Ninth People's Hospital departmental target",
    },
    "brachial_plexus": {
        "level": "soft",
        "conventional": {"dmax": 66.0, "unit": "Gy"},
        "sbrt_1fx": {"dmax": 17.5},
        "sbrt_3fx": {"dmax": 24.0},
        "sbrt_5fx": {"dmax": 30.5},
        "source": "conventional 66 Gy: RTOG H&N protocols (60-66 Gy); SBRT 17.5/24/30.5 Gy: AAPM TG-101 2010 Table III, maximum point dose (defined as 0.035 cc or less; Table III lists a separate 3 cc criterion)",
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
    """Biological Effective Dose: BED = n * d * (1 + d / (alpha/beta)).

    Parameters
    ----------
    dose_per_fx : float
        Dose per fraction in Gy.
    n_fractions : int
        Number of fractions.
    alpha_beta : float
        Tissue alpha/beta ratio in Gy.

    Returns
    -------
    float
        BED in Gy.
    """
    return n_fractions * dose_per_fx * (1 + dose_per_fx / alpha_beta)


def eqd2(bed_value: float, alpha_beta: float) -> float:
    """Equivalent dose in 2 Gy fractions: EQD2 = BED / (1 + 2 / (alpha/beta)).

    Parameters
    ----------
    bed_value : float
        Biological effective dose in Gy.
    alpha_beta : float
        Tissue alpha/beta ratio in Gy.

    Returns
    -------
    float
        Equivalent dose in Gy.
    """
    return bed_value / (1 + 2 / alpha_beta)


def ser_adjusted_dose(physical_dose: float, ser: float = 1.0) -> float:
    """Apply a caller-supplied Sensitizer Enhancement Ratio (SER).

    SER here is a research assumption, not clinical guidance. The default of
    1.0 applies no enhancement.

    Parameters
    ----------
    physical_dose : float
        Physical dose in Gy.
    ser : float, optional
        Enhancement ratio supplied by the caller. Published ranges are
        model-specific: 1.1-1.3 for cisplatin/cetuximab (phase III tumour
        data); 1.2-1.5 for ADC/IO (preclinical only, e.g. PMID:34074654, a
        single anti-TIP1 ADC in NSCLC cell lines and xenografts).

    Returns
    -------
    float
        SER-adjusted dose in Gy.

    Notes
    -----
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
    """Cumulative BED of prior courses with a gap-repair correction.

    Parameters
    ----------
    regimens : list of (dose_per_fx, n_fractions, ser) tuples
        The courses to sum. Every regimen passed here is treated as a PRIOR
        course; the gap repair is applied to their combined total. Deliver
        any new course outside this function (see screen_reirradiation).
        SER defaults to 1.0; see ser_adjusted_dose for why a non-unit SER is
        a caller-supplied research assumption.
    gap_years : float, optional
        Time elapsed since the prior course(s).
    alpha_beta : float, optional
        Tissue alpha/beta ratio in Gy.
    gap_repair : bool, optional
        Apply the gap-repair fraction to the total.

    Returns
    -------
    float
        Cumulative BED in Gy.

    Notes
    -----
    Gap-repair estimates for late-responding tissue (departmental heuristic):
    <6 months 0%; 6 to <12 months 30%; 1 to <2 years 50%; >=2 years 70%.
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
    """Check a single OAR against the limits for the requested modality.

    Parameters
    ----------
    oar_name : str
        Key from HEAD_NECK_CONSTRAINTS.
    modality : Modality
        Fractionation scheme whose limits are to be applied. Conventional
        limits are never borrowed for SBRT.
    metrics : dict of str to float
        Measured values, e.g. {"dmax": 47.2}. Every metric defined for this
        OAR under this modality must be present and finite, otherwise the
        check is incomplete.

    Returns
    -------
    dict
        With keys ``oar``, ``level``, ``violations``, ``overall`` and
        ``source``; ``structure`` is added when the cited source prescribes
        which anatomical structure must be measured (e.g. cord PRV vs
        bony canal); ``missing`` is added when a required metric was absent
        or invalid, and ``reason``/``error`` for not-evaluated/unknown OARs.
        ``overall`` is one of:

        - ``hard_fail``: ANY exceedance of a hard-level constraint, or >30%
          over a soft-level limit.
        - ``soft_fail``: 10-30% over a soft-level limit.
        - ``near_limit``: <10% over a soft-level limit.
        - ``incomplete``: a required metric was missing or not a finite
          number (e.g. NaN). An incomplete check is never a pass.
        - ``not_evaluated``: no limit is defined for this modality.
        - ``error``: unknown OAR name.
        - ``pass``: all supplied values within limits.
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
                # Any exceedance of a hard constraint is a hard fail; the
                # percentage over the limit is still reported as info.
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
    structure = constraint.get("required_structure", {}).get(modality.value)
    if structure is not None:
        result["structure"] = structure
    if missing:
        result["missing"] = missing
    return result


def _check_parotid_pair_quantec(metrics: dict[str, dict[str, float]]) -> dict | None:
    """QUANTEC paired-gland parotid rule (Deasy et al., IJROBP 2010;76(3 Suppl):S58-63, PMID 20171519).

    Meaningful only for conventional fractionation (QUANTEC derived the
    physical-dose rule at ~1.8-2 Gy/fx); check_plan calls this for
    Modality.CONVENTIONAL only and returns None for SBRT modalities.

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

    Parameters
    ----------
    modality : Modality
        Fractionation scheme of the plan being checked.
    metrics : dict of str to dict of str to float
        Measured values per OAR, e.g.
        {"spinal_cord": {"dmax": 43.0}, "brainstem": {"dmax": 52.0}}. Only
        the organs supplied by the caller are checked.
    corrections : dict, optional
        NOT SUPPORTED: passing any value raises ValueError. (The argument
        used to be accepted and silently ignored.) BED or partial-volume
        adjustments must be applied to the measured values by the caller
        before calling.

    Returns
    -------
    dict
        ``plan_pass`` is True only when every requested check completed and
        no hard constraint was exceeded. ``plan_status`` is ``pass``,
        ``fail`` or ``incomplete``. ``hard_fails``, ``soft_fails``,
        ``near_limits``, ``incomplete`` and ``all_results`` hold the
        per-OAR results; ``incomplete`` collects missing/invalid metrics,
        unknown OARs and modalities with no defined limit.
        ``parotid_pair_quantec`` reports the QUANTEC paired-gland rule when
        both parotids are supplied under CONVENTIONAL fractionation
        (informational; it does not change ``plan_pass``). It is None for
        SBRT modalities - the QUANTEC physical-dose rule is derived from
        conventional ~1.8-2 Gy/fx - and when both glands are not supplied.

    Raises
    ------
    ValueError
        If ``corrections`` is not None.

    Example
    -------
    >>> metrics = {"spinal_cord": {"dmax": 47.0}, "brainstem": {"dmax": 53.0},
    ...            "parotid_contralateral": {"dmean": 24.0}}
    >>> result = check_plan(Modality.CONVENTIONAL, metrics)
    >>> # the spinal cord hard constraint (45 Gy) is exceeded
    >>> result["plan_pass"]
    False
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
        "parotid_pair_quantec": (
            _check_parotid_pair_quantec(metrics)
            if modality == Modality.CONVENTIONAL
            else None
        ),
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
        "evidence": "Institutional regimen, unpublished (Shanghai Ninth People's Hospital)",
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
        "name": "SBRT 5.5 Gy x 5 (institutional)",
        "prescription": "5.5 Gy x 5 fx (midpoint of a departmental 5-6 Gy range)",
        "dose_per_fx": 5.5,
        "fractions_per_cycle": 5,
        "cycles": 1,  # 5 fx, 27.5 Gy total
        "evidence": (
            "Dose: institutional protocol, unpublished. Gap: Tham et al. 2024 "
            "review (PMID:38892731, section 5.1 prefers >2 yr). Echevarria "
            "et al. 2023 phase 1 (PMID:37105404) tested 6-8 Gy x 5 with "
            "cisplatin, a different schedule"
        ),
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

    Parameters
    ----------
    prior_dose : float
        Total prescription dose of the prior course in Gy.
    prior_fractions : int
        Number of fractions of the prior course.
    gap_years : float
        Years since the prior course.

    Returns
    -------
    list of dict
        One entry per eligible regimen, sorted by ``cumulative_eqd2``:
        ``regimen``, ``prescription``, ``new_course_total_dose_gy``,
        ``new_course_eqd2``, ``prior_residual_eqd2``, ``cumulative_eqd2``,
        ``screening_threshold_eqd2``, ``below_screening_threshold`` and
        ``evidence``.

    Raises
    ------
    ValueError
        If the prior dose or time gap is not finite, the prior dose is not
        positive, the gap is negative, or the fraction count is not a
        positive whole number.

    Notes
    -----
    Scope and documented assumptions - the output is an estimate, not a
    clinical safety determination:

    - The prior course is assumed to deliver its prescription dose to the
      organs at risk. Actual organ doses and old/new field overlap are NOT
      known to this function and must be judged separately per organ.
    - Prior-course gap repair (late tissue) uses cumulative_bed():
      <6 mo 0%, 6 to <12 mo 30%, 1 to <2 yr 50%, >=2 yr 70% - a
      departmental heuristic.
    - No intra-course recovery is credited for the new course
      (conservative).
    - ``screening_threshold_eqd2`` values are institutional screening
      references (departmental practice), NOT organ-specific tolerance
      limits - e.g. spinal cord and bowel re-irradiation tolerances differ
      and must be checked separately.
    - alpha/beta = 3 Gy is the default late-tissue value and matches the
      re-irradiation constraints in the cited Tham review (section 5.3).
      The choice is debatable: QUANTEC's spinal cord review (Kirkpatrick
      2010) fitted alpha/beta ~0.87 Gy and Nieder et al. 2006 used 2 Gy for
      cervical/thoracic cord, and it materially moves cumulative EQD2.
      Callers computing their own totals can override via
      cumulative_bed(alpha_beta=...).
    """
    if not _is_valid_number(prior_dose) or prior_dose <= 0:
        raise ValueError(
            f"prior_dose must be a finite positive number of Gy, got {prior_dose!r}"
        )
    if not _is_valid_number(gap_years) or gap_years < 0:
        raise ValueError(
            f"gap_years must be a finite non-negative number of years, got {gap_years!r}"
        )
    if (
        isinstance(prior_fractions, bool)
        or not _is_valid_number(prior_fractions)
        or prior_fractions <= 0
        or prior_fractions != int(prior_fractions)
    ):
        raise ValueError(
            f"prior_fractions must be a positive whole number, got {prior_fractions!r}"
        )
    prior_fractions = int(prior_fractions)

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
