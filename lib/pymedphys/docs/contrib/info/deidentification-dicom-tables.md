# Regenerate the DICOM tables for a new edition

The de-identification engine reads its rules from tables generated from one edition of the DICOM Standard, the pinned edition (D-001 in the [de-identification design](deidentification-design.md)). Each table, each rule file curated by hand for that edition, the tables' notice file, the README, and the user guide name the edition in their attribution, such as "DICOM PS3.15 2026d, © NEMA". So the tables are regenerated for every new edition of the Standard, even one that changes no row.

The DICOM Edition Check workflow, `deid-edition-check.yml`, which the [workflow guide](workflows.md) describes, runs each month and opens or updates the issue titled "DICOM edition check: the de-identification tables need attention" when the current edition differs from the pinned one or would change a table. Regenerate the tables when that issue opens, or whenever NEMA publishes a new edition.

## Checklist

1. Move the pin in `lib/pymedphys/_dev/deid_tables/generate.py` to the new edition and its digests.
2. Run `uv run -- pymedphys dev deid-tables` until it succeeds, updating the pin's corrections and lists where it fails.
3. Move the hand-written rule files, the README, and the user guide to the new edition.
4. Bring the requirements register's PS3.15 entries into line with the regenerated Annex E paragraphs.
5. Review every changed row, then run the checks below.

## Steps

1. In `PIN`, set `edition` to the new edition, such as `"2027a"`, and set each `PinnedSource` digest to the SHA-256 of that page of the new edition. NEMA serves the current edition under `https://dicom.nema.org/medical/dicom/current/output/`, followed by the page's path, such as `chtml/part15/chapter_E.html`. Add every page of Annex E that the edition adds, as the check's report names it; generation fails if it reaches a page that the pin does not list.
2. Run `uv run -- pymedphys dev deid-tables`. It downloads each page, checks its digest, and writes the tables and `_standard/NOTICE-DICOM.txt`, or writes nothing and says why. Where it fails because a named correction no longer applies, an IOD it names can now be generated, or a coding scheme, repeated row, or shared Functional Group Macros table has changed, update the pin's `corrections`, `left_out_iods`, `structured_content_schemes`, `left_out_structured_content_schemes`, `repeated_snomed_ids`, or `shared_functional_groups`, and check each change against the new edition's text.
3. In each rule file that carries an acknowledgement, set `edition` and `acknowledgement` to the new edition: `requirements.toml`, `safe_private.toml`, `supplementary_actions.toml`, `supplementary_concepts.toml`, `temporal_roles.toml`, `uid_roles.toml`, and `head_and_neck_regions.toml` in `lib/pymedphys/_dicom/deidentify/`. Review each file's rules against the new edition, as each file's header describes. Keep each file's `link` and `notice` as they are.
4. In `README.rst`, under "Third-party content", and in the user guide's [DICOM de-identification](../../users/background/dicom-deidentification.md) page, under "DICOM Standard attribution", replace the old edition with the new one wherever it appears.
5. Update the PS3.15 entries of `requirements.toml` so that they are exactly the regenerated Annex E paragraphs, with the same sections, links, and text, in the same order. A paragraph that the edition adds takes a new identifier.
6. Review the diff of every generated table, and follow each changed row into the engine's rules and tests.

## Success criteria

- `uv run -- pymedphys dev deid-tables --check` exits with status 0.
- `uv run -- pymedphys dev deid-tables --check-current` reports `Result: unchanged` and names the new edition as the edition of the current pages.
- `_standard/NOTICE-DICOM.txt` and every table in `_standard/` name the new edition.
- The de-identification tests pass, including `tests/dicom/test_deidentify_attribution.py`, which checks that every table, rule file, the notice file, the package's description, and the user guide carry the attribution of the pinned edition, and `tests/dicom/test_deidentify_requirements.py`, which checks the register against the regenerated paragraphs.
- Once the change merges, close the edition-check issue.
