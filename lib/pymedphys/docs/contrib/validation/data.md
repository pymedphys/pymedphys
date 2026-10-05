# Fixtures and external data

This guide is for contributors adding, using, or replacing data in the current
tests and documentation. You need an identified behaviour to check and a
[development checkout](../start/setup.md). The outcome is a reproducible input
whose provenance, licence, privacy, and expected result are clear.

## Choose the smallest suitable fixture

1. State which property the fixture must exercise: numerical geometry,
   parser semantics, archive layout, exporter compatibility, or an app workflow.
2. Prefer a small, deterministic local generator or checked-in synthetic input
   when it represents that property faithfully.
3. Identify the characteristics a generated input may omit. For proprietary
   exporters, a specification alone may not establish actual exporter behaviour.
4. Use approved authentic data or a justified reduction when those omitted
   characteristics materially affect the claim. Retain synthetic boundary
   cases as well.
5. Establish expected results independently and record the fixture's scope.

Useful characteristics include structure, semantic relationships, units,
encodings, ranges, scale, rare cases, vendor/version variation, and archive
headers, member types, names, and nesting. Choose those relevant to the claim;
a fixture need not resemble a complete clinical dataset for every test.

Keep tests independent of live clinical systems. Mock data lives in `_mocks/`
and feature test directories; inspect existing generators before adapting them.
[Scientific evidence](scientific.md) explains why appearance, round trips, and
implementation-generated snapshots do not establish correctness.

## Keep patient data out of shared evidence

Follow the [patient-data policy](https://github.com/pymedphys/pymedphys/blob/main/CONTRIBUTING.md#keep-patient-data-out-of-public-posts)
before committing or uploading a fixture, notebook, log, screenshot, or archive.
Review filenames, paths, metadata, free text, pixels, and reports as well as
obvious patient attributes. The legacy anonymisation interfaces have documented
limitations; do not assume their output is suitable for public sharing.

For DICOM, read the
[de-identification background](../../users/background/dicom-deidentification.md)
and the [replacement design](../info/deidentification-design.md). Claims about
de-identification must name the validated edition, profile, and options.
Use opaque identifiers in published evidence and record provenance without
identifying a patient or exposing original paths. Report accidental disclosure
privately using the security policy linked from CONTRIBUTING.

## Register a downloaded dataset

PyMedPhys uses `_data` registries and a verified cache for approved external
datasets, including Zenodo records. A new downloaded fixture needs a deliberate
publication/approval process; ask the relevant maintainer to arrange the
dataset's destination and licence before linking it from tests.

1. Record where the data came from, exporter/version where relevant, applicable
   licence, approval to share, and transformations applied. Bundled data and
   vocabularies need compatible terms and any required attribution.
2. Use the immutable version/record and exact file being reviewed. Add its URL
   under its unique filename in `_data/urls.json`. Named Zenodo collections also
   use `_data/zenodo.json` to map the name to the reviewed record ID.
3. Calculate and independently inspect the file fingerprint. The current
   `_utilities.filehash.hash_file` uses SHA-1 as a cache content fingerprint,
   not as a security primitive:

   ```shell
   uv run python -c "from pymedphys._utilities.filehash import hash_file; print(hash_file('fixture.zip'))"
   ```

4. Add the matching filename/fingerprint to `_data/hashes.json`. Record a hash
   for every registered file; downloads require one by default and never
   populate the registry automatically.
5. Add the test or notebook using that approved fixture, and verify its expected
   behaviour. Check download/cache reuse and the relevant extracted members.
6. Include the registry edits, provenance, and test evidence in the same PR.
   Data changes can select additional CI; consult
   [PR checks](../maintainers/pr-checks.md).

For example, an existing approved archive can be read with
`pymedphys.zip_data_paths("metersetmap-gui-e2e-data.zip")`. The public
`data_path`, `zip_data_paths`, and `zenodo_data_paths` functions are exported
from the package root; their current implementation is in
[`_data/download.py`](https://github.com/pymedphys/pymedphys/blob/main/lib/pymedphys/_data/download.py).

Passing `check_hash=False` explicitly accepts unverified bytes. It is not a
repair for a mismatched registered fixture. Verify the source and reviewed
bytes before intentionally updating the registry or expected results.

## Use the cache without changing shared inputs

The cache defaults to `~/.pymedphys/data`; `PYMEDPHYS_DATA_DIR` overrides its
location. Tests isolate the normal home directories but keep this data cache
shared so they do not repeatedly download the same files.

`data_path` locks each file while checking/downloading it. `zip_data_paths`
locks an archive from checking or repair through extraction, so parallel workers
do not replace an open archive or read a partly refreshed extraction. Let the
public helpers manage those resources rather than extracting over the shared
cache yourself.

Cache-managed extraction is refreshed when the archive changes, extraction
metadata is missing/invalid, a member is missing, or a file's size no longer
matches. A caller-chosen `extract_directory` behaves differently: only missing
files are added, preserving the caller's edits. The GUI demo uses that behaviour.

Write test outputs to `tmp_path` or a separate working directory, never beside
cached inputs. If a test needs to modify an input, copy it into its own directory
first. For GUI tests, use the shared temporary-working-directory fixtures in
[the testing guide](testing.md#test-a-streamlit-app).

## Replace or retire a fixture

Before removing download-backed coverage, record the tested revisions,
fixture provenance, and results. Preserve the meaningful properties in local
fixtures or an approved reduced dataset. Distinguish intentionally changed
expectations, unchanged baselines, and previously skipped cases.

Anonymising, simplifying, or repacking a native export can remove the precise
header, filename, relationship, or layout that exposed a defect. Check that a
transformed fixture retains the behaviour it is intended to cover and meets
privacy requirements. One real export supports only the covered variant.

The [DICOM coordinate validation record](../info/dicom-coordinate-validation.md)
shows a documented retirement of downloaded fixtures with independent geometry
checks and preserved baseline coverage. Keep the equivalent reasoning and
reproduction evidence in the replacement PR or validation record.

Success means the relevant behaviour remains checked, ordinary test runs use
only approved reproducible data, and the PR states any remaining compatibility
limit. Removing a network dependency by dropping the covered scenario does not
complete that replacement.
