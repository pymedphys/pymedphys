# Interpolate data

Use `pymedphys.interpolate.interp` to obtain values at new points on a regular
one-, two-, or three-dimensional grid. Source axes must be finite, strictly
ascending, evenly spaced, and contain at least two points each. Use matching
units for known and requested coordinates.

## Interpolate at individual points

This asymmetric 2D example uses the analytic field `2*x + 3*y`. Its values
are indexed `[x_index, y_index]`; another axis order is valid if the array and
coordinates use that same order.

```python
import numpy as np
from pymedphys.interpolate import interp

x = np.array([0.0, 1.0, 2.0])
y = np.array([0.0, 2.0, 4.0])
values = 2 * x[:, None] + 3 * y[None, :]
points = np.array([[0.5, 1.0], [1.5, 3.0]])
result = interp((x, y), values, points_interp=points)
np.testing.assert_allclose(result, [4.0, 12.0])
print(result)
```

The result is `[4. 12.]`, one value for each row of `points`. In `d` dimensions,
`points_interp` has shape `(number_of_points, d)`, and `values` has shape
`tuple(len(axis) for axis in axes_known)`.

## Interpolate onto another grid

Continue the same example:

```python
new_x = np.array([0.5, 1.5])
new_y = np.array([1.0, 3.0])
new_grid = interp(
    (x, y), values, axes_interp=(new_x, new_y), keep_dims=True
)
np.testing.assert_allclose(new_grid, [[4.0, 10.0], [6.0, 12.0]])
print(new_grid.shape)
```

This prints `(2, 2)`. `axes_interp` forms the Cartesian product of its axes.
The default `keep_dims=False` flattens that grid to a one-dimensional result.
Supply exactly one of `axes_interp` and `points_interp`.

## Handle bounds and invalid inputs

The default raises for points outside the known grid. To retain their positions
with a missing value, use `bounds_error=False`:

```python
outside = interp(
    (x, y), values,
    points_interp=np.array([[0.5, 1.0], [3.0, 1.0]]),
    bounds_error=False,
)
assert outside[0] == 4.0
assert np.isnan(outside[1])
```

`extrap_fill_value` supplies a fixed fill value; it does not extrapolate the
field. Descending or irregular axes raise `ValueError`. If reversing a descending
axis, reverse the corresponding array dimension too. For genuinely irregular
sampling, choose an interpolator that supports it.

Keep public input checks enabled while establishing the workflow.
`skip_checks=True` skips shape, dtype, and bounds checks, while still validating
source-axis length, finiteness, order, and spacing. A successful interpolation
does not establish alignment between unrelated datasets.

See the [API reference](../ref/lib/interp.rst) for options and the
[implementation comparison](../howto/interp/implementation_comparison.ipynb)
for timing against SciPy. Timings depend on input size, versions, hardware,
and compilation warm-up.

```{toctree}
:hidden:

../howto/interp/index
```
