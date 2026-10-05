# Export Pinnacle data for research

The Pinnacle exporter converts raw Pinnacle patient data to DICOM CT, RT
Structure Set, RT Plan, and RT Dose objects. Its public API moved out of the
experimental namespace in PyMedPhys 0.40.0, but the exporter remains a research
tool with known limitations. Use [the documented warning](../ref/lib/pinnacle.rst)
and inspect the exported objects before relying on any result.

## Select the intended plan and trial

Use an authorised copy of a raw patient directory containing the `Patient`
file and its related image and plan files. A TAR archive is also accepted by
the CLI, provided it contains exactly one patient. Replace the path and the
plan/trial names below with values from your approved research dataset.

First list the available plans, trials, and image series:

```bash
pymedphys pinnacle export approved-patient --list
```

Then explicitly select the plan and trial, and a new output directory:

```bash
pymedphys pinnacle export approved-patient -o research-output --plan "PLAN_NAME" --trial "TRIAL_NAME"
```

With no `--modality`, the command attempts CT, RTSTRUCT, RTPLAN, and RTDOSE.
For a restricted export, repeat the modality option:

```bash
pymedphys pinnacle export approved-patient -o images-and-structures --plan "PLAN_NAME" --trial "TRIAL_NAME" --modality CT --modality RTSTRUCT
```

Without `--plan`, the first plan is selected with a warning. Trial selection
also has a default; use the listed trial name explicitly for reproducible
exports. `--image` selects an image-series UID, or `all`; this is separate
from the plan's primary CT export. `--roiskip` is a regular expression for
excluding structures. Check the [CLI reference](../ref/cli/pinnacle.rst) for the
exact options, including UID-prefix validation.

The command logs some missing-plan, missing-trial, missing-output, and
archive-selection failures and then exits without a non-zero status.
A successful process exit therefore does not establish that the expected
objects were produced. Read the log and inspect the output directory.

## Check the resulting objects

1. Confirm the selected patient, plan, trial, and image series against the source.
2. Check the expected object counts and each object's modality and SOP class.
3. Check structure alignment with the images and all cross-object UID references.
4. Check dose grid geometry, units, scaling, and values against an independent
   source result.
5. For exported plans, inspect beams, control points, angles, monitor units,
   and machine-specific details against the raw data.

Conversion can encounter unsupported modalities, source variants, missing
primary images, or trial content that does not produce all requested objects.
Keep logs and validation evidence with the exported dataset. An RT Dose file
existing on disk is insufficient to establish that its coordinates and values
are correct. The [DICOM task guide](dicom.md) shows how to inspect dose arrays
and their physical coordinates.

## Handle archives and identifiers

TAR extraction refuses links, special files, and paths that would escape its
temporary extraction directory. Members whose names contain `:` are skipped
for Windows compatibility. Extraction relies on a Python build containing
CPython's June 2025 TAR fixes; the implementation documents the relevant patch
versions. It creates a temporary directory, so include temporary storage in
your handling and cleanup procedure.

The exporter preserves identifying source information, and its logs may
include it. `--mrn` appends the medical record number to the output-directory
name. Keep research copies, extracted files, output, and logs in authorised
storage. Exporting does not anonymise the data; review
[DICOM de-identification](../background/dicom-deidentification.md) separately
before sharing.

## Use the Python interface

`pymedphys.pinnacle.PinnacleExport(path)` exposes `patient_info`, `plans`,
and `images`, with export methods for individual object types.
A plan's `plan_info["PlanName"]` identifies it; set `plan.active_trial` to
the intended trial name before exporting. The
[library reference](../ref/lib/pinnacle.rst) describes `PinnacleExport`,
`PinnaclePlan`, and `PinnacleImage`. Preserve the same explicit selection
and independent checks when scripting repeated research exports.
