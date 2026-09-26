# DICOM coordinate validation

This note records the geometry and impact review for
[#2066](https://github.com/pymedphys/pymedphys/pull/2066). The review compared
the original implementation on `main` at `400b61fe8` with the PR at `658c4b6f0`,
then added the regression tests described below. It does not establish that
every DICOM helper or every gamma search case is correct.

## Independent definition

The governing definitions are DICOM PS3.3
[C.7.6.2.1.1](https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.7.6.2.html#sect_C.7.6.2.1.1)
and
[C.8.8.3.2](https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.8.8.3.2.html).
For raw dose element `pixel_array[k, i, j]`, the patient position is

```text
P = S + j * dc * r + i * dr * c + g[k] * (r x c)
```

Here `S` is Image Position (Patient), `r` and `c` are the first and second
triples of Image Orientation (Patient), `dr, dc` are Pixel Spacing, and `g`
contains relative slice offsets. In the permitted absolute-offset form,
subtract `S[z]` to obtain `g`; that form requires IOP `(1,0,0,0,1,0)`.

The first transmitted voxel is at `S` for relative offsets starting at zero.
An orientation change does not negate `S`: the direction cosines determine
the displacement from it.

For the eight supported orientations the basis is a signed permutation.
Each patient coordinate therefore depends on exactly one raw array index.
Extracting its one-dimensional axis is algebraically the same transformation
as applying the full matrix to every voxel, without allocating a coordinate
volume. Dose conversion must then transpose the raw dimensions and reverse
both coordinates and dose wherever an axis decreases.

| Orientation | Increasing raw column | Increasing raw row | Positive slice offset |
| --- | --- | --- | --- |
| HFS | +x | +y | +z |
| HFP | -x | -y | +z |
| FFS | -x | +y | -z |
| FFP | +x | -y | -z |
| HFDL | -y | +x | +z |
| HFDR | +y | -x | +z |
| FFDL | +y | +x | -z |
| FFDR | -y | -x | -z |

## A worked difference from the original implementation

Consider HFP, an x origin of 100 mm, five columns and 1 mm column spacing.
The raw columns must lie at:

```text
100, 99, 98, 97, 96 mm
```

The original DICOM branch returned:

```text
-96, -97, -98, -99, -100 mm
```

It first formed the image-aligned axis `-100 + j`, which is appropriate to
the retained image-aligned convention, then reversed the array to obtain
the DICOM result. Reversing array order does not undo the origin sign.
The PR's raw-order DICOM axis is the first sequence above. Its public dose
conversion returns ascending `96, 97, 98, 99, 100` and reverses the dose with it.

The old and correct raw-order axes in this example differ by a constant
-196 mm. If both grids have that same error, their relative geometry is
unchanged. But removing the last two columns changes the old error to
-198 mm. The full grid and its crop now disagree by 2 mm even though **both
are HFP**. This is why different orientations are not a prerequisite for
affected comparisons.

For a uniformly spaced descending axis, the old displacement is
`(n - 1) * spacing - 2 * origin`. Equal shifts cancel only when shared by the
two grids. This argument does not cover decubitus row/column permutations,
uneven reversed slice offsets, or the old interpolator's inability to handle
descending evaluation axes. A passing self-comparison alone is insufficient.

## Evidence and its limits

The persistent tests use three independent anchors:

1. A homogeneous 4x4 matrix implementation in
   [the synthetic fixture](https://github.com/pymedphys/pymedphys/blob/e50f96951ddc5ee4ecdf89b9de4f3d72d5504355/lib/pymedphys/tests/dicom/_synthetic_rtdose.py), checked
   against manually worked HFP and FFDL voxels.
2. A manually tabulated storage encoding in
   [the orientation invariance tests](https://github.com/pymedphys/pymedphys/blob/e50f96951ddc5ee4ecdf89b9de4f3d72d5504355/lib/pymedphys/tests/dicom/test_orientation_invariance.py).
   This starts with known patient axes and dose values and does not call the
   production geometry code or the matrix oracle to encode them.
3. The historical real-file orientation metadata and the retained
   `expected_fixed_xyz.json` baseline.

Checks completed during this review:

| Check | Result |
| --- | --- |
| Eight orientations, increasing and decreasing relative slice offsets | All 16 encodings recover exactly the original physical axes and dose |
| All 64 reference/evaluation orientation pairs, both interpolators | Same results as gamma on the known physical grid, within `1e-12` |
| Identical and discrepant dose fields for every pair | Identical fields give zero; the discrepancy includes failing points and remains orientation invariant |
| First/last crop on each of three patient axes in all eight orientations | All 48 cropped-reference comparisons give zero gamma against their full grid |
| Off-grid dose interpolation in all eight orientations | Agrees with independently averaged voxel corners within `1e-12` Gy |
| Historical metadata files for all eight orientations | Zero difference from the independent DICOM matrix calculation |
| Historical IEC FIXED baseline and pre-PR implementation | Exactly equal in all eight orientations |
| 800 additional seeded random grids, including unequal spacing and uneven/decreasing slice offsets | Zero coordinate difference from the matrix calculation; every dose value retains its physical voxel |
| 800 seeded perturbed grid pairs | Compact 0.01 mm equality decision agrees with exhaustive 3D voxel displacement |
| IEC FIXED on those 800 grids | Exactly equal to the original implementation |
| Negative control using the original dose conversion | New physical-grid tests detect all 15 changed encoding cases; ordinary HFS with increasing offsets passes |

The randomized probes used seed 2066, 100 grids per orientation, dimensions
between 2 and 8, origins within +/-1500 mm, and spacings between 0.2 and 5 mm.
The committed seeded matrix regression also checks 100 grids per orientation.
These checks are not a statistical estimate of clinical error frequency.

The historical orientation DICOM files have empty pixel data. They verify
real metadata and the IEC convention, not nonzero real dose registration.
The dose-order and gamma checks deliberately use asymmetric, nonzero
synthetic dose data. The downloaded archive matched the repository's SHA-1
`e09f71ebf4d98a58bc3c00e7dd9f59e91e9f8bb6`.

Before the added assurance tests, the reviewed head's CI passed on Windows,
Linux and macOS with Python 3.10, 3.11 and 3.12. The Linux 3.12 job explicitly
ran the historical coordinate and dose tests. Fresh CI on the final commit
remains the merge gate; an earlier green run does not validate later edits.

## Remaining limitations

- Oblique geometry is outside the three-independent-patient-axes contract.
  The private IEC PATIENT option is disabled pending separate validation.
- The existing singleton-plane gamma search defect remains tracked in
  [#2070](https://github.com/pymedphys/pymedphys/issues/2070). Narrow evaluation
  grids can also be missed by discrete shells. The four existing strict
  expected-failure tests remain; geometry invariance does not solve these.
- Two **pre-existing private decubitus helpers remain incorrect**:
  `get_dose_grid_structure_mask` returns patient `(z, y, x)` dimensions while
  `find_dose_within_structure` applies the mask to raw `(slice, row, column)`
  dose, and `DicomDose.coords` similarly assumes raw rows are y and columns
  are x. A raw shape `(3, 5, 4)` can receive a mask shaped `(3, 4, 5)`; square
  grids can conceal the shape mismatch while selecting the wrong values.
  Both were reproduced with the original implementation as well as the PR.
  Sixteen additional strict expected-failure cases cover the four decubitus
  orientations on square and rectangular grids for these two helpers.
  They require a separate fix or an explicit restriction before claiming
  general decubitus support for those helpers. The public
  `zyx_and_dose_from_dataset` and `dicom_dose_interpolate` paths do not call them.

## Impact statement

Ordinary HFS dose conversion with increasing relative slice offsets is
unchanged. Expected affected usage may therefore be low in workflows
dominated by those grids, but no usage survey establishes its frequency.
This is distinct from severity: affected non-HFS grids can be substantially
misregistered. Same-orientation crops, absolute coordinate queries, and
comparison with external contours also matter. Absolute slice offsets and
decreasing HFS slice offsets have their own corrected behaviour.

The public dose conversion and DICOM gamma output now use ascending patient
axes, so callers must not assume their returned array order matches raw
`pixel_array`. Existing code that overlays or indexes these outputs needs
to use the returned axes and matching array order.

## Reproducing the committed checks

After the usual locked development installation, run from the repository root:

```bash
uv run -- python -m pytest -q \
  lib/pymedphys/tests/dicom/test_coords.py \
  lib/pymedphys/tests/dicom/test_coords_analytic.py \
  lib/pymedphys/tests/dicom/test_orientation_invariance.py \
  lib/pymedphys/tests/dicom/test_dose.py \
  lib/pymedphys/tests/dicom/structure/test_masking.py \
  lib/pymedphys/tests/gamma/test_gamma_axes.py \
  lib/pymedphys/tests/gamma/test_gamma_shell.py \
  lib/pymedphys/tests/interp/test_interp.py
```

This command includes the download-backed historical tests and the explicitly
recorded limitations. Expected failures are strict: an unexpected pass must
be investigated and the corresponding limitation updated.

At the assurance test commit `e50f96951`, this targeted command completed with
420 passed and 20 expected failures: four existing gamma-search cases and
16 cases covering the two private decubitus helper defects above. Pre-commit,
Pyright and MyPy passed, and Pylint using the repository configuration scored
10.00/10 for the changed Python files.
