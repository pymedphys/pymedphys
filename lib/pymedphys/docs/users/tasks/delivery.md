# Work with delivery data

`pymedphys.Delivery` represents planned or recorded control points using
cumulative MU, gantry/collimator angles, and MLC/jaw positions. Use its source
adapters to obtain that common representation, then inspect the arrays or
calculate a MetersetMap.

## Choose the input adapter

| Source | Call | Input and restrictions |
| --- | --- | --- |
| DICOM RT Plan | `Delivery.from_dicom(plan, fraction_group_number=1)` | Dataset or path. Choose the actual fraction-group number when there are several. Supported beam-limiting devices are `MLCX` plus `ASYMY`. |
| Elekta Agility TRF | `Delivery.from_trf(path)` | Native TRF file; reads the decoded delivery columns. |
| Elekta iCOM | `Delivery.from_icom(stream)` | Decompressed bytes, rather than the path of an `.xz` archive. |
| Monaco | `Delivery.from_monaco(path)` | Supported Monaco `tel.1` format with its Agility-oriented layout. |
| Mosaiq | `Delivery.from_mosaiq(connection, field_id)` | Open connection and internal `TxField.FLD_ID`, not a patient ID or displayed field label. |

`fraction_group_number="all"` returns a dictionary indexed by fraction group.
Do not treat it as a single Delivery. Adapters have format and machine
assumptions; importing one vendor's dataset does not establish support for
another device. See the [Delivery reference](../ref/lib/delivery.rst),
[logfile guide](logfiles.md), and [Mosaiq guide](mosaiq.md).

## Make and inspect a synthetic delivery

This static aperture has three 5 mm leaf pairs, a 4 mm total MLC opening,
a 15 mm total jaw opening, and 10 MU. Each side uses a positive opening distance
from the central axis; a negative value means that side crosses the axis.

```python
import numpy as np
import pymedphys

delivery = pymedphys.Delivery(
    monitor_units=[0.0, 10.0],
    gantry=[0.0, 0.0],
    collimator=[0.0, 0.0],
    mlc=np.full((2, 3, 2), 2.0),
    jaw=np.full((2, 2), 7.5),
)
metersetmap = delivery.metersetmap(
    leaf_pair_widths=(5, 5, 5), max_leaf_gap=10, grid_resolution=1
)
grid = pymedphys.metersetmap.grid(
    leaf_pair_widths=(5, 5, 5), max_leaf_gap=10, grid_resolution=1
)
assert metersetmap.shape == (len(grid["jaw"]), len(grid["mlc"]))
assert np.isclose(metersetmap.max(), 10.0)
print(f"Total MU: {delivery.mu[-1]:.1f}")
print(f"Peak MetersetMap: {metersetmap.max():.1f} MU")
```

Both values are `10.0`. Interior pixels see full open-field MU; aperture-boundary
pixels can have partial exposure. To display the map, call
`pymedphys.metersetmap.display(grid, metersetmap)` with matplotlib installed.
Use the same geometry arguments for `grid` and `metersetmap`.

The constructor stores nested tuples. For inspection,
`np.asarray(delivery.mlc)` has shape `(control_points, leaf_pairs, 2)` and
`np.asarray(delivery.jaw)` has shape `(control_points, 2)`. Cumulative MU and
angles have one value per control point. Positions are mm at the isocentre
projection; angles are degrees in the representation returned by the adapter.
Preserve the adapter's conversions when comparing sources, rather than copying
raw vendor leaf-bank columns into a Delivery.

## Combine deliveries and keep geometry explicit

`first.merge(second)` returns a combined Delivery, and
`pymedphys.Delivery.combine(first, second)` provides the corresponding class
method. Merging concatenates control points and accumulates non-negative MU
increments; check the resulting MU against the intended fields or fractions.
It does not establish that records belong to the same delivery.

Default library MetersetMap geometry is 80 leaf pairs of 5 mm width, a
400 mm maximum leaf gap, and 1 mm resolution. Supply actual geometry when
those defaults do not match. The app has its own fixed geometry; see
[Use the apps](apps.md). A Delivery does not carry leaf widths, timestamps,
patient identity, or a dose model as fields.

For angle-resolved maps, pass a sequence such as `gantry_angles=[0, 90]` and a
justified `gantry_tolerance`. Grouping assumes each requested angle selects one
contiguous block; separated beams at the same angle are not supported by that
grouping. The result is an array for one map and otherwise a list;
`output_always_list=True` makes its container consistent.

## Interpret a MetersetMap and export deliberately

A MetersetMap integrates the open fraction of each grid pixel over MU. It is
not absorbed dose: it does not model anatomy, scatter, transmission, or a
planning system's beam model. Compare identical grids, retain source roles and
geometry, and interpret alongside independent delivery checks. The
[MetersetMap reference](../ref/lib/metersetmap.rst) includes the usage warning.

`delivery.to_dicom(template, fraction_group_number=...)` returns an RT Plan
using a compatible template. It does not reconstruct a complete plan from the
five Delivery fields. Beam grouping and template geometry must match; save to
a new file and verify metersets, control points, angles, collimation, and DICOM
references before using the export in another workflow.
