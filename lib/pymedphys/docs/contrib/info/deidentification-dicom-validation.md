---
myst:
  heading_anchors: 2
---

# Validate de-identified DICOM with independent validators

De-identification must not break the files it releases: MIDI-BP-03 in the [requirements register](deidentification-requirements.md) asks that each output still conform to its original IOD. The engine checks its own output against its IOD before release, but that check shares the engine's reading of the standard. This page describes a second check that shares nothing with the engine: three validators written by others check each released instance and its input, and the comparison reports only what the de-identification changed.

Continuous integration runs it on every pull request, over the synthetic corpus, under each preset. This page also shows how to run it yourself, on the corpus or on a release of your own, such as the [MIDI-B benchmark's](deidentification-midi-benchmark.md).

The code is in `pymedphys._dicom.deidentify`: `dicom_validators.py` runs the validators, `dicom_validation.py` compares inputs with outputs, and `dicom_validation_known.toml` lists the explained differences. The command is the development module `pymedphys._dicom.deidentify.dicom_validation_command`. It is not part of the `pymedphys` command line, because nothing de-identification related joins the public command line before the first supported release.

## The validators

| Validator | From | Licence | Version in CI | What it checks |
| --- | --- | --- | --- | --- |
| `dciodvfy` | [dicom3tools](https://www.dclunie.com/dicom3tools/workinprogress/index.html), by David Clunie | BSD-3-Clause | Ubuntu 24.04's package, snapshot 20240118131615 | Each instance against the modules and attributes of its IOD, each value against its VR and VM, defined terms and enumerated values, and the file's encoding. |
| `dcentvfy` | dicom3tools | BSD-3-Clause | as `dciodvfy` | That the instances of one patient give the same values for the attributes of each information entity: patient, study, series, frame of reference, and equipment. |
| [dicom-validator](https://github.com/pydicom/dicom-validator) | the pydicom project | MIT | 0.9.0, pinned in the `tests` extra | Each instance against its IOD, as read from the DocBook source of PS3.3, PS3.4, and PS3.6 of the edition that the engine's tables are generated from, which it downloads from NEMA. |

None of them is installed for users of PyMedPhys: dicom-validator is in the `tests` extra, and dicom3tools is a separate program.

The dicom3tools snapshot that Ubuntu packages is from January 2024, so its dictionary lacks attributes that the standard has added since, such as Coding Scheme Resources Sequence (0008,001D). The CI job lists the newest snapshot on the dicom3tools site in its summary, so the gap stays visible. dicom-validator reads the current edition, so it covers what that snapshot cannot.

## How the comparison works

Each validator checks each released instance's input and its output; `dcentvfy` checks each patient's inputs together, and then their outputs. A finding is **introduced** where an output gives it more often than its input. A finding that the input already had is not charged to the de-identification, and one that the output no longer gives is counted as **resolved**.

Each introduced finding is then:

- **explained**, by an entry in `dicom_validation_known.toml`, whose category says why: `profile`, where the action that PS3.15 Table E.1-1 gives the attribute causes it; `validator`, where it is a limitation or heuristic of the validator and the output conforms; or `engine`, a defect of the engine's output, recorded until it is fixed;
- **not comparable**, where it lies below an attribute whose contents the validator could not read in the input, because its dictionary lacks the attribute and the input is in Implicit VR or gives it the VR UN, while it could read them in the output; or
- **unexplained**.

The comparison passes when nothing introduced is unexplained, and a validator that checked an input but could not check its output gives an unexplained finding too.

The results hold no value and no path. Every validator quotes values, and dicom3tools also prints file names, so each message is reduced to the validator, the severity, the attribute as tags without item numbers or private creators, the message's text before the first value it quotes, and the module or information entity it names. A reason that follows a value is kept only where it is text compiled into the validator itself, and a line in any other form is counted without its text.

### Known differences

At present the synthetic corpus needs six known differences, each listed with its reason in every report:

- `profile`: Study Date, Study Time, and Study ID, which the Basic Profile empties (action Z), are needed to build a DICOMDIR, so `dciodvfy` warns.
- `validator`: `dciodvfy` warns about every Person Name without a component delimiter, such as the dummy value `DEIDENTIFIED`, as a retired form; and its dictionary predates RT Assertions Sequence (0044,0110).
- `engine`: three Type 1C attributes are kept after the Basic Profile removed what met their conditions, which PS3.5 Section 7.4.2 does not allow. Clinical Trial Protocol Ethics Committee Name (0012,0081) is kept with a dummy value once Clinical Trial Protocol Ethics Committee Approval Number (0012,0082) is removed; and the Common Instance Reference Module's Referenced Series Sequence (0008,1115) and Studies Containing Other Referenced Instances Sequence (0008,1200) are kept once the references they describe are removed from the functional groups of enhanced images. Their entries go when the engine is fixed.

## Run it on the synthetic corpus

The corpus tests build the synthetic corpus, run the engine over it under `basic`, under `basic-clean-descriptors`, and under `basic` with its images compressed, and compare each run. They need Linux or macOS with dicom3tools on the `PATH`.

1. Install Git and uv, as in the [MIDI-B benchmark guide](deidentification-midi-benchmark.md).
2. Install dicom3tools. On Debian or Ubuntu, `sudo apt-get install dicom3tools`. Elsewhere, build it from a source snapshot on the [dicom3tools site](https://www.dclunie.com/dicom3tools/workinprogress/index.html), following its instructions, and put `dciodvfy` and `dcentvfy` on the `PATH`. A newer snapshot than CI's can give fewer findings, since its dictionary knows more attributes.
3. Get PyMedPhys with the `tests` extra, and run the tests:

   ```bash
   git clone https://github.com/pymedphys/pymedphys.git
   cd pymedphys
   uv sync --no-dev --extra tests
   export PYMEDPHYS_DICOM_VALIDATORS=required
   export PYMEDPHYS_DICOM_VALIDATION_REPORT="$PWD/dicom-validation"
   uv run --no-dev --extra tests pymedphys dev tests --dicom-validators \
     lib/pymedphys/tests/dicom/test_deidentify_dicom_validation_corpus.py
   ```

The tests are marked `dicom_validators`, so the ordinary test run leaves them out. Without `PYMEDPHYS_DICOM_VALIDATORS=required` they skip when a validator is missing, rather than fail. The first run downloads the DocBook source into `~/.pymedphys/dicom-validator`, or into the directory that `PYMEDPHYS_DICOM_VALIDATOR_STANDARD` names. Each preset's report is written into a directory of `dicom-validation` named after it.

In CI the job is `DICOM validation of de-identified output`, in the Unit Tests workflow. Its summary shows each preset's report, and its `dicom-validation` artefact holds the reports as Markdown and JSON.

## Run it on a release of your own

The command compares a release with its inputs. It pairs them by SOP Instance UID, through a CSV file with the columns `id_old` and `id_new`, and finds each output by its file name, the replacement SOP Instance UID with the suffix `.dcm`, as a run names it.

After a [MIDI-B benchmark run](deidentification-midi-benchmark.md), whose work directory holds the release and the UID mapping:

```bash
uv sync --no-dev --extra tests
uv run --no-dev --extra tests python -m pymedphys._dicom.deidentify.dicom_validation_command midi \
  --source /data/midi-b/validation/synthetic \
  --work /data/midi-b/runs/validation-basic-1 \
  --out /data/midi-b/runs/validation-basic-1-dicom-validation
```

For another release, give the release and the mapping instead:

```bash
uv run --no-dev --extra tests python -m pymedphys._dicom.deidentify.dicom_validation_command compare \
  --source /data/inputs \
  --release /data/runs/release-1/release \
  --uid-mapping /data/runs/uid-mapping.csv \
  --out /data/runs/release-1-dicom-validation
```

- `--out` must not exist; its parent must. The command writes `dicom-validation.md` and `dicom-validation.json` there, and prints the Markdown.
- It exits with status 0 when the comparison passed, 1 when it found unexplained findings, and 2 when it could not compare, for example because a validator is missing.
- `--workers` sets how many processes run the per-file validators; it defaults to the number of CPUs.
- Both result files hold no value or path, so they are safe to share. The inputs, the release, and the mapping file are not.

## Read a report

`dicom-validation.md` gives, in order:

1. The verdict, passed or failed.
2. The versions: the dicom3tools snapshot, dicom-validator's version, the edition it read, and the SHA-256 of each DocBook file, so that another run can be shown to have used the same standard.
3. The released instances compared, by SOP Class, and the inputs without an output of their own, such as withheld instances.
4. For each validator, how many pairs it checked, and failed on, in inputs and outputs; the findings by severity in each; and how many input findings were resolved. A validator that cannot read a file is counted as failed, not as finding nothing: `dciodvfy` aborts on the corpus's 32-bit RT Dose in Implicit VR, for example, so that pair is also left out of `dcentvfy`'s comparison, which stops at a file it cannot read, and counts only for dicom-validator.
5. The introduced findings: unexplained first, then explained, each with the number of the known difference that explains it, then not comparable.
6. The known differences, the `engine` ones first, with how many kinds of finding each explained and in how many files.

Read the unexplained findings first: each is a change that the de-identification made and that nothing accounts for. An `engine` entry is a known defect to fix, not an accepted behaviour.
