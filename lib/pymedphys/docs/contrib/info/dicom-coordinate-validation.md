# DICOM coordinate validation

This note records the geometry and impact review for
[#2066](https://github.com/pymedphys/pymedphys/pull/2066). The review compared
the original implementation on `main` at `400b61fe8` with the PR at `658c4b6f0`,
then added the regression tests described below. It does not establish that
every DICOM helper or every gamma search case is correct.

[DICOM coordinates and gamma, illustrated](dicom-coordinates-illustrated.ipynb) demonstrates these checks with executable examples and figures, including gamma plotting and a speed comparison.

## Independent definition

The governing definitions are DICOM PS3.3
[C.7.6.2.1.1](https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.7.6.2.html#sect_C.7.6.2.1.1)
and
[C.8.8.3.2](https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.8.8.3.2.html).
For raw dose element `pixel_array[k, row, column]`, the patient position is

```text
P = S + column * dc * r + row * dr * c + g[k] * (r x c)
```

Here `S` is Image Position (Patient), `r` and `c` are the first and second
triples of Image Orientation (Patient), `dr, dc` are Pixel Spacing, and `g`
contains relative slice offsets. In the permitted absolute-offset form,
subtract `S[z]` to obtain `g`; that form requires IOP `(1,0,0,0,1,0)` and its first value must equal `S[z]`.

The first transmitted voxel is at `S` for relative offsets starting at zero.
An orientation change does not negate `S`: the direction cosines determine
the displacement from it.

For the eight supported transverse cardinal orientations the basis is a signed permutation.
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

## Physical tolerances and accepted orientation rounding

For conversion to three patient axes, direction cosines within `1e-4` of a
supported transverse cardinal orientation are snapped to it. This is an
approximation, whose displacement grows with grid extent. The exact-placement
checks above concern exact cardinal directions. Other cardinal orientations
can also be separable but are outside the current implementation's support.

Grid equality instead retains the original encoded cosines. It combines the
origin, spacing and orientation into the maximum Euclidean displacement of
corresponding voxel centres, across every pair of datasets:

- up to **0.01 mm**: accept silently;
- above **0.01 mm through 0.1 mm**: warn and still treat as coincident;
- above **0.1 mm**: reject.

A separate `1e-9` mm allowance handles arithmetic round-off at those limits.
These absolute limits do not grow with the coordinate origin, do not resample
dose, and do not assess clinical significance. Absolute-offset metadata
consistency retains its separate 0.01 mm rule.

The difference between two corresponding voxel positions is affine in row
and column within each slice. Its norm is convex, so the maximum occurs at
an in-plane corner. Checking four corners of **every** slice therefore gives
the maximum without allocating a volume; an uneven-offset error can peak on
an interior slice. Regression checks compare this calculation with an
independent exhaustive voxel calculation, including slightly rotated cosines.

For example, a `0.00009` rad in-plane rotation over 400 mm in each direction
produces a maximum displacement of about 0.0509 mm. This now warns and accepts,
rather than hiding the displacement by rounding both orientations first.

The historical cancellation argument also needs a physical bound: for
feet-first offsets `g[k]`, the old slice error was
`-2 * S_z + g[k] + g[N - 1 - k]`. With `S_z = 55` and offsets `[0, 2.5, 6]`,
the errors are `[-104, -105, -104]` mm, not a constant translation. The notebook
demonstrates different gamma values even with identical reference/evaluation
grid headers. Correct HFS placement also does not rule out the former default
interpolator's separate error on unevenly spaced evaluation axes.

## Evidence and its limits

Validation combines ongoing local tests with recorded historical checks:

1. A homogeneous 4x4 matrix implementation in
   [the synthetic fixture](https://github.com/pymedphys/pymedphys/blob/e50f96951ddc5ee4ecdf89b9de4f3d72d5504355/lib/pymedphys/tests/dicom/_synthetic_rtdose.py), checked
   against manually worked HFP and FFDL voxels.
2. A manually tabulated storage encoding in
   [the orientation invariance tests](https://github.com/pymedphys/pymedphys/blob/e50f96951ddc5ee4ecdf89b9de4f3d72d5504355/lib/pymedphys/tests/dicom/test_orientation_invariance.py).
   This starts with known patient axes and dose values and does not call the
   production geometry code or the matrix oracle to encode them.
3. The historical real-file orientation metadata and
   `expected_fixed_xyz.json` baseline, verified before retiring the
   download-backed tests as recorded below.

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
| 800 seeded perturbed grid pairs | Original 0.01 mm equality decision agrees with exhaustive 3D voxel displacement for exact cardinal directions; the revised regression also checks rounded cosines and both physical limits |
| IEC FIXED on those 800 grids | Exactly equal to the original implementation |
| Negative control using the original dose conversion | New physical-grid tests detect all 15 changed encoding cases; ordinary HFS with increasing offsets passes |

The randomised probes used seed 2066, 100 grids per orientation, dimensions
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

## Retirement of downloaded test fixtures

On 26 September 2026 the original tests were rerun before removing their
download dependency. The replay used Python 3.12.14, NumPy 1.26.4, pydicom
3.0.2 and pytest 9.1.1, with the existing cached downloads. These are results
from the named revisions, not a claim that the old DICOM expectations pass
against the corrected implementation.

| Revision and test selection | Result |
| --- | --- |
| Original code at `400b61fe8`, `test_coords.py` and `test_dose.py` | **7 passed, 1 skipped** |
| PR at `97b086739`, the same two files before retiring downloads | **14 passed** |

The original IEC PATIENT test was already unconditionally skipped because
its assertions failed; it was not a passing validation. The original DICOM
coordinate JSON matched the original implementation in all eight
orientations. On the PR, that JSON agrees only for HFS: the other orientations
were deliberately checked against the independent DICOM matrix instead.
The IEC FIXED JSON, wedge dose baseline, non-square-pixel contour test and
patient-position checks passed without changing their expectations.

The precise original tests remain available in Git history:
[original coordinate tests](https://github.com/pymedphys/pymedphys/blob/400b61fe8bc2b836e3af543630a34addee3aaabd/lib/pymedphys/tests/dicom/test_coords.py),
[original dose tests](https://github.com/pymedphys/pymedphys/blob/400b61fe8bc2b836e3af543630a34addee3aaabd/lib/pymedphys/tests/dicom/test_dose.py),
and [PR coordinate tests before removal](https://github.com/pymedphys/pymedphys/blob/97b086739468c16880951a3cbd2cfb448d2b0609/lib/pymedphys/tests/dicom/test_coords.py).
To replay either historical run in a checkout of that revision, use:

```bash
uv run -- python -m pytest -q \
  lib/pymedphys/tests/dicom/test_coords.py \
  lib/pymedphys/tests/dicom/test_dose.py -ra
```

Fixture provenance is retained for that optional replay:

| Fixture | Source | Repository SHA-1 |
| --- | --- | --- |
| `dicom_dose_test_data.zip` | [Zenodo record 3870436](https://zenodo.org/record/3870436/files/dicom_dose_test_data.zip?download=1) | `e09f71ebf4d98a58bc3c00e7dd9f59e91e9f8bb6` |
| `rtdose_non_square_pixels.dcm` | [Pinned data-repository file](https://github.com/pymedphys/data/blob/a9f530bcf9ceeb73fe6e1583ac060252b3ef9c96/rtdose_non_square_pixels.dcm) | `9d59aafe2f2f2d3b706c092e62ff90bc33430e14` |
| `example_structures.dcm` | [Zenodo record 3576026](https://zenodo.org/record/3576026/files/example_structures.dcm?download=1) | `3600a63d8f29f2b6b42dff37f280f3d45aff2a32` |

The roughly 75 MiB dose archive and separate DICOM files are no longer
downloaded by these coordinate and dose tests. Their useful coverage is
retained locally:

| Retired downloaded check | Ongoing local coverage |
| --- | --- |
| DICOM axes for eight orientations | Analytic matrix tests, manually encoded physical grids, and seeded voxel checks |
| IEC FIXED historical JSON | Independent image-axis projection tests for all eight orientations, with the exact historical agreement recorded above |
| Non-square-pixel dose/contour example | Unequal row/column spacing in voxel-placement and interpolation tests, plus the local structure-mask regression |
| Wedge dose values, units and coordinates | A generated asymmetric HFS dose written and read locally in implicit and explicit VR little endian; expected dose values and coordinates are defined independently |
| Patient-position checks using orientation and structure files | Generated datasets covering all eight orientations, with and without Patient Position, missing Image Orientation (Patient), and a conflicting Patient Position |

This removes recurring vendor-file regression coverage from this test group;
the recorded historical pass is evidence for those revisions, not a substitute
for future testing. Local DICOM serialisation retains file-reading coverage,
but it cannot represent every vendor-specific encoding. Other repository
test groups may still download their own data. The fixture URL/hash registry
is retained so historical tests can be replayed.

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

### Effect on gamma calculations

The original DICOM gamma workflow used the affected coordinate code.
`zyx_and_dose_from_dataset` obtained axes from `xyz_axes_from_dataset` and
returned them with the dose array. Both the internal `gamma_dicom` wrapper and
the public [Gamma from DICOM example](../../users/howto/gamma/from-dicom.ipynb)
passed that pair into gamma. Incorrect coordinates could therefore change
gamma values and pass rates, not just the position of a displayed heatmap.

`pymedphys.gamma` itself takes coordinate arrays and dose arrays, not DICOM
datasets. A call supplied with independently correct coordinates does not use
this DICOM conversion and is not affected by this particular geometry defect.
The separate interpolation and search limitations above still apply.

Matching coordinate errors can cancel when they amount to the same translation
of both grids. That explains why a self-comparison can pass despite incorrect
absolute positions. It does not protect comparisons with differing origins,
extents or orientations. In the HFP example above, the full grid and its crop
acquire an artificial 2 mm relative displacement even though both are HFP.
The original custom interpolator also mishandled descending evaluation axes;
shared coordinate errors do not resolve that separate problem.

### Array order and plotting

Two operations must be distinguished:

- **DICOM conversion** returns ascending patient `(z, y, x)` axes and a dose
  array reordered to match. Reversing or transposing the array is an exact
  rearrangement: it does not resample dose or change voxel positions.
- **Gamma** normalises evaluation axes and dose together internally. It leaves
  the supplied reference order unchanged, including descending reference axes.
  Each returned gamma array has the reference dose's shape and index order.

For example, sorting an x axis must retain its pairing with dose:

| Representation | x coordinates (mm) | Corresponding dose values (Gy) |
| --- | --- | --- |
| Original descending storage | `[100, 99, 98]` | `[10, 20, 30]` |
| Ascending representation | `[98, 99, 100]` | `[30, 20, 10]` |

The dose at x = 100 mm is still 10 Gy. Likewise, with reference axes `(z, y, x)`,
`gamma[i_z, i_y, i_x]` and `dose_reference[i_z, i_y, i_x]` belong to the same position
`(z[i_z], y[i_y], x[i_x])`. Plot a transverse gamma slice with the reference x and y
coordinates, and identify its plane using the reference z coordinate. The
[DICOM tutorial](../../users/howto/gamma/from-dicom.ipynb) demonstrates this
after calculating gamma for the full volume.

The compatibility change is in array storage order. A gamma array calculated
from the converted reference must not be overlaid on raw `pixel_array` by
index without accounting for the reordering. Use the converted reference dose
and its axes together, or apply the inverse reversals and dimension permutation
to restore raw order. Decubitus conversion can swap the row/column lengths;
equal shapes in other orientations do not prove equal index order.

The evaluation dose has its own coordinates. A matching slice index does not
necessarily select the same physical z position in both datasets. Dose
subtraction requires coincident sample positions, or interpolation onto a
common grid; gamma itself does not require matching grids. Reversing the
display axes to choose a viewing convention does not change these physical
correspondences.

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

This command uses local fixtures and includes the explicitly recorded
limitations. Expected failures are strict: an unexpected pass must be
investigated and the corresponding limitation updated.

At the assurance test commit `e50f96951`, this targeted command completed with
420 passed and 20 expected failures: four existing gamma-search cases and
16 cases covering the two private decubitus helper defects above. Pre-commit,
Pyright and MyPy passed, and Pylint using the repository configuration scored
10.00/10 for the changed Python files.

After replacing the downloaded fixtures, the same selection completed with
**428 passed and the same 20 expected failures**. This run used an empty data
cache and a temporary pytest guard that rejected network access and calls to
the PyMedPhys data-download helpers; the cache remained empty. The generated
DICOM files were written only to pytest's temporary directories. Ruff,
Pyright and MyPy passed for the changed Python files, and Pylint with the
repository configuration again scored 10.00/10.

The follow-up review on 26 September 2026 revised the equality limits and
retained encoded direction cosines in the physical comparison. Its targeted
selection completed with **453 passed and the same 20 strict expected
failures**, on Windows with Python 3.12.14, NumPy 1.26.4, SciPy 1.16.2,
pydicom 3.0.1 and Numba 0.61.2. The existing environment lacked pytest-timeout,
so plugin autoload was disabled and a 180-second subprocess timeout covered
the whole selection; per-test timeout behaviour was not exercised. Ruff,
Pyright and the repository pre-commit checks passed.

The notebook's ordinary cells were executed in a fresh Jupyter kernel and
its figures inspected. The optional two-checkout performance comparison was
not rerun: its worker was smoke-tested with both 2D interpolators, and guards
for missing paths, invalid revisions and incorrect import origins were
exercised. The notebook no longer presents historical hard-coded timings as
verified measurements or claims full-array agreement from checksums alone.
