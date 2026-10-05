# Model electron insert factors

The library models an insert factor from equivalent ellipse width and
perimeter-to-area ratio. Keep measurements for each energy, applicator, and
source-to-surface distance (SSD) separate. Record whether a supplied factor is
cutout/open dose or its reciprocal; the library fits the values you give it.
This is a modelling workflow that needs local measurement verification.

## Check a synthetic model

This artificial surface is linear in both inputs. It checks the fitting
interface against a known result, without providing a clinical model:

```python
import numpy as np
import pymedphys

width_grid, ratio_grid = np.meshgrid(
    np.linspace(1, 5, 5), np.linspace(0.4, 1.2, 5), indexing="ij"
)
width_data = width_grid.ravel()
ratio_data = ratio_grid.ravel()
factor_data = 0.9 + 0.01 * width_data + 0.02 * ratio_data
prediction = pymedphys.electronfactors.spline_model(
    np.array([3.0]), np.array([0.8]),
    width_data, ratio_data, factor_data,
)
np.testing.assert_allclose(prediction, [0.946], atol=1e-8)
print(f"Synthetic prediction: {prediction[0]:.3f}")
```

The expected output is `Synthetic prediction: 0.946`. The function currently
emits a warning about deviations observed with SciPy 1.11 and later; retain it
and compare an established local baseline after dependency changes. See
[the reported algorithm deviations](https://github.com/pymedphys/pymedphys/issues/1858).
Passing this simple surface check does not verify a measured model.

For a real dataset, use arrays with the same length, consistent units, finite
values, and sufficiently varied points in both input dimensions. Duplicate or
nearly collinear measurements can make the spline ill-conditioned. Read fitting
warnings and investigate them rather than treating a returned number as success.

## Parameterise a measured outline

Provide the perimeter vertices in order, in one length unit. Width is the
diameter of the largest circle bounded by the outline. Length is chosen to
give the equivalent ellipse the same area. It is not the bounding box length.

This 4 cm square has width 4 cm and equivalent ellipse length `16 / pi` cm:

```python
outline_x = np.array([-2, 2, 2, -2])
outline_y = np.array([-2, -2, 2, 2])
width, length, centre = pymedphys.electronfactors.parameterise_insert(
    outline_x, outline_y
)
np.testing.assert_allclose([width, length], [4, 16 / np.pi], atol=1e-3)
ratio = pymedphys.electronfactors.convert2_ratio_perim_area(width, length)
assert ratio > 0
print(f"Width: {width:.3f} cm; equivalent length: {length:.3f} cm")
```

The optimisation uses a stochastic search; small numerical differences are
expected. Inspect the outline, largest circle, and equivalent ellipse,
particularly for concave shapes. The ellipse perimeter-to-area approximation
has inverse length units; centimetre data produce per centimetre, and
millimetre data produce per millimetre. Convert outlines and measurements
together before predicting.

## Verify a measured model and its usable region

1. Confirm energy, applicator, SSD, output-factor definition, and units.
2. Compare predictions with independent measurements, including small and
   irregular inserts and points near the proposed model boundary.
3. Calculate leave-one-out prediction differences and report the missing
   predictions as well as the finite errors.
4. Retain the measurement dataset, dependency versions, plots, and agreed
   limits with the model.

`spline_model` permits extrapolation by extending the fitting bounding box.
It does not reject a query outside the measured range.
`spline_model_with_deformability` additionally calculates how much the model
changes when a test point is perturbed and returns `NaN` where deformability
exceeds 0.5. That filter is a model diagnostic, not an independent uncertainty
estimate or a guarantee of accurate extrapolation.

For arrays `width_data`, `ratio_data`, and `factor_data` from one measured
group:

```python
differences = pymedphys.electronfactors.calculate_percent_prediction_differences(
    width_data, ratio_data, factor_data
)
usable = np.isfinite(differences)
print(f"Finite leave-one-out predictions: {usable.sum()} / {differences.size}")
if usable.any():
    print(f"Largest absolute difference: {np.max(np.abs(differences[usable])):.3f}%")
```

The sign convention is
`100 * (measured_factor - predicted_factor) / measured_factor`.
Do not discard `NaN` results without recording why those points were excluded.
A separate hold-out set is needed to assess the completed model independently
of the fitting data.

`create_transformed_mesh` and `plot_model` display predictions against width
and equivalent length; they apply the deformability filter and remove
width-greater-than-length points. Check the supported region rather than
reading across blank areas. The scientific method is described in the
[original research paper](https://doi.org/10.1016/j.ejmp.2015.11.002).

## Use the experimental app

**Electron Insert Factor Modelling** is labelled Alpha in the
[app catalogue](apps.md). It can use demo data or configured measurements.
The configuration requires a CSV path and two regular expressions for the
Monaco beam model and applicator. Each expression must expose the intended
value in capture group 1.

The CSV columns are exactly:

- `Energy (MeV)`
- `Applicator (cm)`
- `SSD (cm)`
- `Width (cm @ 100SSD)`
- `Length (cm @ 100SSD)`
- `RCCC Inverse factor (dose open / dose cutout)`

The app currently selects SSD 100 cm and requires at least eight measurements
for a selected energy/applicator group. It converts the Monaco outline from
millimetres to centimetres. Check that the imported outline, selected group,
and factor convention agree with your measurements before interpreting its
plots or prediction. The [configuration reference](../ref/configuration.md)
describes the keys, and the [library reference](../ref/lib/electronfactors.rst)
lists the functions.
