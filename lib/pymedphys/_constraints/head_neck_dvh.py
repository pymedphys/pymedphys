# pymedphys contribution: Head & Neck DVH constraint library
# To be placed at: lib/pymedphys/_constraints/head_neck_dvh.py
#
# Based on: QUANTEC (2010), AAPM TG-101, UK SABR 2022 (PMID:35272913)
# Clinical source: Shanghai Ninth People's Hospital Head & Neck RT Series
# GitHub: https://github.com/antica1

from typing import Dict, List, Optional, Tuple
from enum import Enum
import math


# ── Constants ─────────────────────────────────────────────

ALPHA_BETA_TUMOR = 10   # Gy (HNSCC)
ALPHA_BETA_LATE = 3     # Gy (CNS, bone, soft tissue late effects)


class ViolationLevel(Enum):
    PASS = "pass"                # within limit
    NEAR_LIMIT = "near_limit"   # <10% over
    SOFT_FAIL = "soft_fail"     # 10-30% over, negotiable 
    HARD_FAIL = "hard_fail"     # >30% over or hard constraint


class Modality(Enum):
    CONVENTIONAL = "conventional"  # 30-33 fx, 1.8-2.0 Gy/fx
    SBRT_1FX = "sbrt_1fx"
    SBRT_3FX = "sbrt_3fx"
    SBRT_5FX = "sbrt_5fx"


# ── OAR Constraint Database ───────────────────────────────

HEAD_NECK_CONSTRAINTS: Dict[str, Dict] = {
    # --- Hard constraints (one-strike) ---
    "spinal_cord": {
        "level": "hard",
        "conventional": {"dmax": 45.0, "unit": "Gy"},
        "sbrt_1fx": {"dmax": 14.0},
        "sbrt_3fx": {"dmax": 21.0},
        "sbrt_5fx": {"dmax": 25.0},
        "source": "QUANTEC 2010, TG-101, UK SABR 2022",
        "note": "Animal model extrapolation: Dmax 50 Gy at 2 Gy/fx = 0.2% myelopathy risk (QUANTEC)"
    },
    "brainstem": {
        "level": "hard",
        "conventional": {"dmax": 54.0, "unit": "Gy"},
        "sbrt_1fx": {"dmax": 14.0},
        "sbrt_3fx": {"dmax": 21.0},
        "sbrt_5fx": {"dmax": 25.0},
        "source": "QUANTEC 2010, TG-101",
    },
    "optic_chiasm": {
        "level": "hard",
        "conventional": {"dmax": 54.0, "unit": "Gy"},
        "sbrt_1fx": {"dmax": 10.0},
        "sbrt_3fx": {"d0_03cc": 17.0},
        "sbrt_5fx": {"d0_03cc": 23.0},
        "source": "QUANTEC 2010, TG-101",
    },
    "optic_nerve": {
        "level": "hard",
        "conventional": {"dmax": 54.0, "unit": "Gy"},
        "sbrt_1fx": {"dmax": 10.0},
        "sbrt_3fx": {"d0_03cc": 17.0},
        "sbrt_5fx": {"d0_03cc": 23.0},
        "source": "QUANTEC 2010, TG-101",
    },
    "lens": {
        "level": "hard",
        "conventional": {"dmax": 10.0, "unit": "Gy"},
        "source": "QUANTEC 2010",
    },
    # --- Soft constraints ---
    "parotid_contralateral": {
        "level": "soft",
        "conventional": {"dmean": 26.0, "unit": "Gy"},
        "source": "QUANTEC 2010",
    },
    "parotid_ipsilateral": {
        "level": "soft",
        "conventional": {"dmean": 30.0, "unit": "Gy"},
        "source": "QUANTEC 2010",
    },
    "cochlea": {
        "level": "soft",
        "conventional": {"dmean": 45.0, "unit": "Gy"},
        "source": "QUANTEC 2010",
    },
    "mandible": {
        "level": "soft",
        "conventional": {"dmax": 70.0, "v60": 30.0, "unit": "Gy"},
        "source": "QUANTEC 2010",
    },
    "pharyngeal_constrictors": {
        "level": "soft",
        "conventional": {"dmean": 50.0, "unit": "Gy"},
        "source": "QUANTEC 2010",
    },
    "lacrimal_gland": {
        "level": "soft",
        "conventional": {"dmean": 25.0, "unit": "Gy"},
        "source": "Shanghai Ninth People's Hospital",
    },
    "brachial_plexus": {
        "level": "soft",
        "conventional": {"dmax": 66.0, "unit": "Gy"},
        "source": "QUANTEC 2010",
    },
    "oral_cavity": {
        "level": "soft",
        "conventional": {"dmean": 40.0, "unit": "Gy"},
        "source": "QUANTEC 2010",
    },
    "larynx": {
        "level": "soft",
        "conventional": {"dmean": 45.0, "unit": "Gy"},
        "source": "QUANTEC 2010",
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
    """Apply Sensitizer Enhancement Ratio.

    SER:
      1.0 = no sensitization
      1.1-1.3 = cisplatin/cetuximab (phase III evidence)
      1.2-1.5 = ADC/IO (preclinical estimate, PMID:34074654)
    
    Note: ADC radiosensitization SER lacks prospective clinical data.
    Clinical use: SER=1.0 as conservative floor; SER=1.2 as midpoint estimate.
    """
    return physical_dose * ser


def cumulative_bed(regimens: List[Tuple[float, int, float]], 
                   gap_years: float = 0,
                   alpha_beta: float = ALPHA_BETA_LATE,
                   gap_repair: bool = True) -> float:
    """Cumulative BED from multiple RT courses with gap repair correction.
    
    Args:
        regimens: list of (dose_per_fx, n_fractions, ser) tuples
        gap_years: time since last course
        alpha_beta: tissue α/β ratio
        gap_repair: apply gap repair correction for late effects
    
    Returns:
        Cumulative BED (Gy)
    
    Gap repair estimates (late-responding tissue only):
      <6 months  → 0% repair
      6-12 months → 30% repair
      1-2 years   → 50% repair
      >2 years    → 70% repair
    """
    total_bed = sum(
        bed(ser_adjusted_dose(d, ser), n, alpha_beta)
        for d, n, ser in regimens
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
        total_bed *= (1 - repair)
    
    return total_bed


# ── Constraint Checking ───────────────────────────────────

def check_constraint(oar_name: str, 
                     modality: Modality,
                     metrics: Dict[str, float]) -> Dict:
    """Check a single OAR against constraints.
    
    Args:
        oar_name: key from HEAD_NECK_CONSTRAINTS
        modality: fractionation scheme
        metrics: dict of measured values (e.g. {"dmax": 47.2, "dmean": 12.5})
    
    Returns:
        {
            "oar": str,
            "violations": [{"metric": "dmax", "limit": 45.0, "value": 47.2, 
                           "excess_pct": 4.9, "level": "near_limit"}],
            "overall": "pass" | "near_limit" | "soft_fail" | "hard_fail"
        }
    """
    if oar_name not in HEAD_NECK_CONSTRAINTS:
        return {"oar": oar_name, "error": "unknown OAR", "overall": "error"}
    
    constraint = HEAD_NECK_CONSTRAINTS[oar_name]
    limits = constraint.get(modality.value, constraint.get("conventional", {}))
    
    violations = []
    for metric_key, limit_value in limits.items():
        if metric_key in ("unit",):
            continue
        if metric_key in metrics:
            measured = metrics[metric_key]
            if measured > limit_value:
                excess_pct = (measured - limit_value) / limit_value * 100
                if excess_pct > 30:
                    level = ViolationLevel.HARD_FAIL
                elif excess_pct > 10:
                    level = ViolationLevel.SOFT_FAIL
                elif excess_pct > 0:
                    level = ViolationLevel.NEAR_LIMIT
                else:
                    level = ViolationLevel.PASS
                violations.append({
                    "metric": metric_key,
                    "limit": limit_value,
                    "value": measured,
                    "excess_pct": round(excess_pct, 1),
                    "level": level.value,
                })
    
    if not violations:
        overall = ViolationLevel.PASS.value
    else:
        levels = [ViolationLevel(v["level"]) for v in violations]
        if ViolationLevel.HARD_FAIL in levels:
            overall = ViolationLevel.HARD_FAIL.value
        elif ViolationLevel.SOFT_FAIL in levels:
            overall = ViolationLevel.SOFT_FAIL.value
        else:
            overall = ViolationLevel.NEAR_LIMIT.value
    
    return {
        "oar": oar_name,
        "level": constraint["level"],
        "violations": violations,
        "overall": overall,
        "source": constraint["source"],
    }


def check_plan(modality: Modality,
               metrics: Dict[str, Dict[str, float]],
               corrections: Optional[Dict] = None) -> Dict:
    """Full plan check against head & neck constraints.
    
    Args:
        modality: fractionation scheme
        metrics: {"spinal_cord": {"dmax": 43.0}, "brainstem": {"dmax": 52.0}, ...}
        corrections: optional override dict for BED/partial-volume adjustment
    
    Returns:
        {
            "plan_pass": bool,
            "hard_fails": [...],
            "soft_fails": [...],
            "near_limits": [...],
            "all_results": [...],
        }
    
    Example:
        >>> metrics = {"spinal_cord": {"dmax": 47.0}, "brainstem": {"dmax": 53.0},
        ...            "parotid_contralateral": {"dmean": 24.0}}
        >>> result = check_plan(Modality.CONVENTIONAL, metrics)
        >>> result["plan_pass"]
        False  # spinal cord near limit
    """
    results = []
    hard_fails, soft_fails, near_limits = [], [], []
    
    for oar_name, oar_metrics in metrics.items():
        r = check_constraint(oar_name, modality, oar_metrics)
        results.append(r)
        
        if r["overall"] == "hard_fail":
            hard_fails.append(r)
        elif r["overall"] == "soft_fail":
            soft_fails.append(r)
        elif r["overall"] == "near_limit":
            near_limits.append(r)
    
    return {
        "plan_pass": len(hard_fails) == 0,
        "hard_fails": hard_fails,
        "soft_fails": soft_fails,
        "near_limits": near_limits,
        "all_results": results,
        "modality": modality.value,
    }


# ── Re-Irradiation Screening ──────────────────────────────

REIRRADIATION_REGIMENS = {
    "quad_shot_io": {
        "name": "Quad-Shot + Pembrolizumab",
        "prescription": "3.7 Gy × 4 BID Q4w × 3 cycles",
        "total_dose": 44.4,
        "bed_late_per_cycle": 33.1,  # Gy₃
        "evidence": "JAMA Otolaryngol 2026 (PMID:42313403)",
        "min_gap_years": 3.0,
    },
    "q3w_io": {
        "name": "Q3w 3.5 Gy + IO/ADC",
        "prescription": "3.5 Gy × 1 Q3w × 6 cycles",
        "total_dose": 21.0,
        "bed_late_per_cycle": 7.58,
        "evidence": "Shanghai Ninth People's Hospital",
        "min_gap_years": 0.5,
    },
    "conventional": {
        "name": "Conventional 2 Gy/fx",
        "prescription": "2 Gy × 15-25 fx",
        "total_dose": 30.0,  # typical starting point
        "bed_late_per_cycle": float("inf"),  # always safe
        "evidence": "Standard clinical practice",
        "min_gap_years": 0.0,
    },
    "sbrt_continuous": {
        "name": "SBRT 5-6 Gy × 5 + IO",
        "prescription": "5-6 Gy × 5 fx",
        "total_dose": 27.5,
        "bed_late_per_cycle": 66.7,  # Gy₃ for 5 Gy × 5
        "evidence": "Phase I/II (PMID:37105404, PMID:38892731)",
        "min_gap_years": 2.0,
    },
}


def screen_reirradiation(prior_dose: float, 
                         prior_fractions: int,
                         gap_years: float) -> List[Dict]:
    """Screen re-irradiation options based on cumulative late tissue risk.
    
    Returns:
        List of feasible regimens with cumulative EQD2 estimates.
    """
    prior_bed = bed(prior_dose / prior_fractions, prior_fractions, ALPHA_BETA_LATE)
    residual_bed = cumulative_bed(
        [(prior_dose / prior_fractions, prior_fractions, 1.0)],
        gap_years, ALPHA_BETA_LATE, True
    )
    residual_eqd2 = eqd2(residual_bed, ALPHA_BETA_LATE)
    
    results = []
    for key, regimen in REIRRADIATION_REGIMENS.items():
        if gap_years < regimen["min_gap_years"]:
            continue
        
        if regimen["bed_late_per_cycle"] == float("inf"):
            cumulative_eqd2 = residual_eqd2 + 20  # approximate
            safe = cumulative_eqd2 < 60
        else:
            # 3 cycles, 4-week repair correction
            cumulative_bed_rt = residual_bed + regimen["bed_late_per_cycle"] * 3 * 0.65
            cumulative_eqd2 = eqd2(cumulative_bed_rt, ALPHA_BETA_LATE)
            safe = cumulative_eqd2 < 50
        
        results.append({
            "regimen": regimen["name"],
            "prescription": regimen["prescription"],
            "cumulative_eqd2": round(cumulative_eqd2, 1),
            "safe": safe,
            "evidence": regimen["evidence"],
        })
    
    return sorted(results, key=lambda x: x["cumulative_eqd2"])
