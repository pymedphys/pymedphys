# Head & Neck DVH Constraint Checking

`pymedphys._constraints.head_neck_dvh` checks head and neck
radiotherapy DVH summary measurements against a table of organ-at-risk
constraints. The caller supplies the measurements; only the organs the
caller supplies are checked. It also provides BED/EQD2 helpers and a
prescription-level re-irradiation dose estimator.

```{note}
The constraint table is the single source of truth and lives in the
module itself as `HEAD_NECK_CONSTRAINTS`. This page explains how to call
the tool and how to read its output; it does not duplicate the numbers.
```

## What each measurement means

* Dose values are in **Gy**.
* `dmax` is the maximum point dose to the structure.
* `dmean` is the mean dose to the structure.
* `v60` is a **percentage** of the structure volume (for example `30.0`
  means 30% of the volume receives at least 60 Gy).
* `d0_035cc` is the near-maximum dose to the hottest **0.035 cc** of the
  structure. This is the metric used by the UK SABR 2022 rows (Tables 5
  and 6); it is a different measurement from D0.03 cc and the two must
  not be interchanged.
* For spinal cord under SBRT, the cited UK consensus applies the limit to
  the **cord planning organ-at-risk volume (PRV)** for spinal targets, or
  the **bony canal** for non-spinal targets. Under conventional
  fractionation the limit applies to the anatomical cord. Each check
  reports which structure it expects in the result's `structure` field;
  supply the measurement for that structure.
* Fractionation is selected with `Modality`: `CONVENTIONAL` (1.8-2.0
  Gy/fx), `SBRT_1FX`, `SBRT_3FX` or `SBRT_5FX`. A modality without a
  defined limit returns `not_evaluated` rather than borrowing another
  modality's limit.

## Example

```python
from pymedphys._constraints.head_neck_dvh import Modality, check_plan

metrics = {
    "spinal_cord": {"dmax": 43.0},
    "brainstem": {"dmax": 53.0},
    "parotid_contralateral": {"dmean": 24.0},
}
result = check_plan(Modality.CONVENTIONAL, metrics)
print(result["plan_pass"], result["plan_status"])
# True pass
```

An exceeded hard limit fails the plan:

```python
hard = check_plan(Modality.CONVENTIONAL, {"spinal_cord": {"dmax": 47.0}})
print(hard["plan_pass"], hard["plan_status"])
# False fail
```

A missing required measurement is not a pass — it is incomplete:

```python
missing = check_plan(Modality.CONVENTIONAL, {"spinal_cord": {"dmean": 100.0}})
print(missing["plan_pass"], missing["plan_status"])
# False incomplete
```

## Reading the report

* `plan_pass` is `True` only when every requested check completed and no
  hard constraint was exceeded. `plan_status` is `pass`, `fail` or
  `incomplete`.
* `hard_fails` holds exceeded hard-level constraints; `soft_fails` and
  `near_limits` are reported but do not by themselves block a pass. A
  plan-level pass therefore does **not** mean every soft target was met
  — read the individual lists.
* `incomplete` collects organs whose required measurement was missing or
  not a finite number, unknown organ names, and modalities with no
  defined limit (`not_evaluated`).
* `parotid_pair_quantec` is an informational QUANTEC paired-gland
  assessment (at least one gland mean < 20 Gy, or both < 25 Gy). It is
  reported only for `Modality.CONVENTIONAL` — the QUANTEC physical-dose
  rule was derived at about 1.8-2 Gy/fx — and is `None` for SBRT. It
  does not change `plan_pass`.

## Sources and assumptions

Each entry in `HEAD_NECK_CONSTRAINTS` carries a `source` string.
Published recommendations (QUANTEC 2010, AAPM TG-101, UK SABR 2022,
PMID:35272913) are named with their table where available; departmental
planning targets from Shanghai Ninth People's Hospital are explicitly
labelled as institutional rather than published values.

The re-irradiation estimator (`screen_reirradiation`) is a
prescription-level dose estimate, not a safety determination. Its
documented assumptions include: the prior course is assumed to deliver
its prescription dose to the organs at risk (actual organ doses and
old/new overlap are unknown to the function); gap repair for the prior
course is a departmental heuristic (<6 months 0%, 6 to <12 months 30%,
1 to <2 years 50%, >=2 years 70%); no intra-course recovery is credited
for the new course; and `screening_threshold_eqd2` values are
institutional screening references rather than organ-specific tolerance
limits. Cumulative EQD2 uses alpha/beta = 3 Gy by default; see the
function docstring for the discussion of alternative values (QUANTEC
cord fitted about 0.87 Gy, Nieder 2006 used 2 Gy) and how to override
it. `ser_adjusted_dose` applies a caller-supplied SER that is a
research assumption, not clinical guidance.
