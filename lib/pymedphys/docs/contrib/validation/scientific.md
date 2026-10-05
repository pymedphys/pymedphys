# Build scientific evidence for a change

This guide is for contributors changing numerical results, geometry, format
interpretation, or standards-based behaviour in the current source. Start with
the intended use, relevant design decisions, and the
[testing guide](testing.md). The outcome is a defensible claim with independent,
reproducible evidence and a stated domain of support.

Verification checks whether the implementation follows its intended definition.
Validation considers whether that definition and implementation are suitable
for the stated task. Passing tests or reproducing a result does not by itself
establish clinical suitability.

## Plan the evidence before implementation

Write a compact claim-to-evidence table in the PR or programme's design document:

| Claim | Acceptance criterion | Independent evidence | Relevant input characteristics | Remaining limit |
| --- | --- | --- | --- | --- |
| Example: coordinate conversion preserves dose positions | Each asymmetric dose value retains its independently calculated patient position | Hand-worked voxel positions and a separately derived matrix calculation | Nonzero origin, unequal spacing, descending offsets, supported orientations | Only the stated separable-grid domain is covered |

Choose claims that matter to callers. Identify units, normalisation, array
dimensions, coordinate frames, supported ranges, failure modes, and standard
editions where applicable. Distinguish planned, implemented, and released
behaviour. Test and document each shipped claim when it is implemented rather
than deferring all evidence to a later milestone.

## Establish expected results independently

Use an analytic case, a calculation derived from the governing definition,
or justified reference data. Explain why the reference does not reuse the same
code or assumption that could be wrong in production.

For geometry, use off-centre coordinates, non-square spacing, different grid
extents, and every supported orientation. Uniform arrays and symmetric inputs
can hide transpositions or reversals. Keep coordinate values paired with their
corresponding array elements: positions `[20, 10, 0]` mm with values `[1, 2, 3]`
must become `[0, 10, 20]` mm with values `[3, 2, 1]` if reordered.

For DICOM coordinates, the
[coordinate validation record](../info/dicom-coordinate-validation.md) shows
how references were derived independently from PS3.3 and how asymmetric inputs
exposed order errors. Its [illustrated notebook](../info/dicom-coordinates-illustrated.ipynb)
explains the coordinates and physical grid-equality tolerances for callers.
Read those definitions before changing geometry.

Agreement with the previous version can establish preservation of a known
behaviour, but it cannot prove that behaviour was correct. A round trip through
one implementation or a snapshot regenerated from it has the same limitation.
Explain intentional differences from an established baseline using independent
worked examples, and retain its useful coverage.

## Seek cases that could falsify the claim

Check the boundaries relevant to the changed calculation: zero or small values,
NaN/inf handling, singleton dimensions, interpolation boundaries, differing
storage order, malformed metadata, and unsupported inputs as applicable.
Use transformations whose expected effect follows from the definition, such
as physically equivalent data encoded in different supported orientations.
Do not assume an invariant, symmetry, or monotonicity the method does not promise.

Include a negative control when useful: demonstrate that the independent check
detects an intentionally wrong axis pairing or the pre-fix result. Matching
coordinate sets without checking coordinate-to-value correspondence cannot
establish safe grid combination. Keep validation at public boundaries even if
fixed geometry is checked once before repeated inner-loop calculations.

## Choose and explain tolerances

State tolerances in the result's units and justify them from the intended
accuracy, reference/input uncertainty, discretisation, or floating-point effects.
Use an absolute tolerance near zero when a relative difference has no useful
denominator; use a relative tolerance only when its scaling matches the claim.
Do not loosen a tolerance solely to make a test pass.

Keep numerical round-off, allowed physical discrepancies, and clinical
significance distinct. For example, a grid-equality acceptance limit does not
resample either grid or decide whether a dose difference matters clinically.
When comparing direction cosines, use the original encoded directions for the
physical comparison; rounding them beforehand can hide an error that grows
with distance across the grid. The illustrated coordinate notebook owns the
current grid limits and their explanation.

Document which array each coordinate sequence belongs to, particularly after
an ordering change. Provide indexing/plotting migration advice when callers
would otherwise associate results with the wrong positions. Describe affected
inputs and result changes in the changelog without implying an unmeasured
clinical frequency is known.

## Match fixtures to the claim

Use [the fixture guide](data.md) to identify the input characteristics that
could change the result. Synthetic data can be sufficient for a precise
mathematical property. Native-export compatibility may require approved
authentic data or a justified faithful reduction retaining the relevant
headers, encodings, names, nesting, and vendor/exporter behaviour.

One authentic example covers that variant, not every site or exporter. A mock
downstream component covers the boundary actually exercised. State whether the
available fixtures support the whole claim or a narrower one, and propose the
smallest useful check for a material gap.

## Support performance and statistical claims

For performance, compare equivalent work and accuracy on representative inputs.
Account for JIT warm-up, caches, repeated timings, memory, and the parameters
controlling numerical accuracy. Reducing accuracy or coverage is a trade-off
to describe, not a speed improvement at the same task. Use the existing
[gamma evidence](../evidence/index.md) as examples of recorded methods and inputs.

For statistical results, identify the independent observation, sample selection,
denominator, exclusions, missingness, and uncertainty. Correlated pixels or
repeated measurements are not automatically independent samples. A fixed seed
or many generated examples does not establish representativeness or clinical
incidence.

## Make the evidence reproducible and scoped

Record the tested revision, commands, environment, inputs and provenance/hashes,
parameters, seeds, and whether agreement was exact or within a justified
tolerance. Preserve enough to repeat the check without publishing identifiers,
original clinical paths, or credentials.

For standards claims, cite the applicable edition, profile/options, and clause
or equation. Follow the [de-identification design](../info/deidentification-design.md)
for its conformance and privacy boundaries, and generate standard-derived
tables rather than editing them by hand. A requirements-to-tests matrix without
test outcomes establishes traceability, not successful execution or conformance.

Report ongoing regression tests separately from one-off studies and historical
results. Tie a validation record to its named revisions; it does not silently
validate later changes. Review the affected public API, CLI, GUI, examples,
and changelog so their claims match the evidence actually available.
