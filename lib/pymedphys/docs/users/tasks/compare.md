# Compare dose and delivery

For delivery comparison, first check the two sources, monitor units, and MLC
geometry in [Work with delivery data](delivery.md). The
[MetersetMap app](apps.md) brings those steps and gamma reports together.
Dose and MetersetMap values need different physical interpretations even when
the same gamma interface is used.

For a repeatable gamma comparison:

1. Establish common physical coordinates and dose units.
2. Choose reference/evaluation roles and all gamma parameters.
3. Calculate gamma, then count analysed and excluded points separately.
4. Inspect spatial failures as well as the pass rate.
5. Retain input provenance, parameters, and the PyMedPhys version with the result.

Start with [Your first result](first-result.md) if you have not yet run gamma.
The [gamma reference](../ref/lib/gamma.rst) defines arguments and defaults.

## Choose a worked example

| Input or question | Worked example |
| --- | --- |
| One-dimensional measured and calculated profiles | [Gamma from CSV](../howto/gamma/1D-from-csv.ipynb) |
| Two RT Dose files, including slice plots | [Gamma from DICOM](../howto/gamma/from-dicom.ipynb) |
| How noise changes gamma | [Effects of noise](../howto/gamma/effect-of-noise.ipynb) |
| Speed and sampling trade-offs | [Speeding up gamma](../howto/gamma/speed-up.ipynb) |
| Planned/recorded delivery comparisons | [Delivery data](delivery.md) and [Use the apps](apps.md) |

The notebooks include data loading and plots. Keep reference/evaluation roles
consistent: swapping inputs changes the sampling grid, normalisation, and
question answered. Gamma output belongs to the reference grid.

## Establish coordinate and dose conventions

For each array dimension, pass its coordinate vector in the same order.
A 3D `dose[k, j, i]` with axes `(z, y, x)` is at `(z[k], y[j], x[i])`.
Distances supplied to gamma are in mm. Convert other position units first.
Dose units must match; percentages are relative to the chosen normalisation,
rather than a conversion between Gy and cGy.

Gamma does not require coincident grids. Direct array subtraction does:
use [interpolation](interpolation.md) onto a common physical grid before making
a difference image for non-coincident inputs. Array shape equality alone does
not establish physical alignment. For DICOM, use the paired coordinates and
dose from `pymedphys.dicom.zyx_and_dose_from_dataset`, and check that both datasets
describe the same physical frame. See [Work with DICOM](dicom.md).

## Interpret the result

For one threshold pair, `pymedphys.gamma` returns an array. A point passes at
gamma **less than or equal to 1**. `pymedphys.gamma_pass_rate` returns a percentage,
not a fraction. NaN values mark excluded points and leave its denominator.
Analysed points with no successful search can have infinite gamma and remain
failures.

```python
import numpy as np
import pymedphys

example_gamma = np.array([0.0, 1.0, 1.2, np.inf, np.nan])
print(f"Analysed: {np.count_nonzero(~np.isnan(example_gamma))}")
print(f"Excluded: {np.count_nonzero(np.isnan(example_gamma))}")
print(f"Pass rate: {pymedphys.gamma_pass_rate(example_gamma):.1f}%")
assert pymedphys.gamma_pass_rate(example_gamma) == 50.0
```

The example has four analysed points, one excluded point, and a 50% pass rate.
Do not use `np.isfinite` for the denominator: it would discard infinite failures.
An entirely excluded array has no pass rate and raises `ValueError`. For gamma
from other software or older PyMedPhys versions, establish what NaN means before
using this helper; see its reference notes.

With several thresholds, gamma returns a dictionary of arrays. Calculate a pass
rate for each array, retaining its threshold key.

## State analysis choices

Record dose/distance thresholds, local/global gamma, any explicit global
normalisation, dose cutoff, interpolation fraction, gamma cap, selected subset,
and NaN handling. The cutoff determines which reference points enter the
analysis. Global and local normalisation answer different questions. These
examples demonstrate algorithms; use justified criteria for your comparison.

For speed, use a gamma cap above the pass threshold when you only need pass/fail
information, and inspect the sampling effect before using `random_subset`.
Sampling reduces the analysed population; report its size and uncertainty rather
than treating the sample as every voxel. First-call timings can include Numba
compilation. See the [speed example](../howto/gamma/speed-up.ipynb) and
[recorded benchmark](../../contrib/info/gamma-benchmark.md).

When results surprise you, first check units, roles, geometry, normalisation,
cutoff, and analysed count. Plot dose and gamma at matching physical positions.
A high aggregate pass rate can coexist with a local region of disagreement.

```{toctree}
:hidden:

../howto/gamma/index
```
