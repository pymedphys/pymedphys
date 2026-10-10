---
myst:
  heading_anchors: 2
---

# Run the MIDI-B de-identification benchmark

The de-identification engine's MIDI benchmark (D-018 in the [de-identification design](deidentification-design.md)) scores a run of the engine against the NCI MIDI-B synthetic test data and its answer key. This page runs it on your own machine, from installing the tools to the two result files, `benchmark.md` and `benchmark.json`. The harness is the development module `pymedphys._dicom.deidentify.midi_benchmark_command`. It is not part of the `pymedphys` command line, because nothing de-identification related joins the public command line before the first supported release.

MIDI-B's images carry synthetic PHI, not real patients' data, but the harness treats them as real: the QC pack and the mapping files it writes hold the test data's identifiers, so they stay on your machine.

Commands are given for bash (macOS, Linux, Git Bash) and PowerShell (Windows). The paths are examples; use your own.

## 1. Install Git and uv

- Git: <https://git-scm.com/downloads>.
- uv, bash: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- uv, PowerShell: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

Open a new terminal so that `uv` is on your path, and check with `uv --version`.

## 2. Get PyMedPhys with its DICOM dependencies and decoders

bash:

```bash
git clone https://github.com/pymedphys/pymedphys.git
cd pymedphys
uv sync --no-dev --extra user
uv run --no-dev --extra user python -m pymedphys._dicom.deidentify.midi_benchmark_command --help
uv run --no-dev --extra user python -c "import gdcm, openjpeg, pylibjpeg"
```

PowerShell:

```powershell
git clone https://github.com/pymedphys/pymedphys.git
Set-Location pymedphys
uv sync --no-dev --extra user
uv run --no-dev --extra user python -m pymedphys._dicom.deidentify.midi_benchmark_command --help
uv run --no-dev --extra user python -c "import gdcm, openjpeg, pylibjpeg"
```

The `--help` command should list two subcommands, `run` and `script-results`, and the last command should print nothing.

The `user` extra installs the decoders that the engine pins for compressed Pixel Data: python-gdcm for JPEG and JPEG-LS, and pylibjpeg with pylibjpeg-openjpeg for JPEG 2000 and HTJ2K. The `dicom` extra installs none of them, so a run with it alone would sequester every instance in one of those syntaxes as `no-decoder`, withholding its patient's files from the score. Either way, an instance in a compressed transfer syntax that the release does not support, such as JPEG 2000 Part 2 or a video syntax, is outside the release's coverage whatever is installed, and its checks are counted apart as outside coverage. python-gdcm publishes wheels for 64-bit Windows, macOS, and Linux with glibc 2.27 or later; elsewhere uv tries to build it from source.

To benchmark a later engine, run `git pull` and `uv sync --no-dev --extra user` again.

## 3. Download MIDI-B

The collection's DOI is <https://doi.org/10.7937/cf2p-aw56>, which leads to TCIA's MIDI-B-Test / MIDI-B-Validation page. TCIA publishes it under the Creative Commons Attribution 4.0 licence. It has a Validation subset (216 patients, 280 series, 23,921 instances, 7.6 GB) and a Test subset (322 patients, 428 series, 29,660 instances, 11.1 GB). Start with Validation, which is smaller. The benchmark uses the collections carrying synthetic PHI (MIDI-B-Synthetic-Validation and MIDI-B-Synthetic-Test), not the TCIA-curated ones.

PyMedPhys's development downloader fetches a subset for you. It reads TCIA's dated manifest for the subset, fetches each series it lists from TCIA's public NBIA API, and checks the manifest and the images against the SHA-256 digests pinned in `lib/pymedphys/_dicom/deidentify/midi_data.toml`, so every run benchmarks the same files. It refuses a destination that already exists.

bash:

```bash
mkdir -p /data/midi-b
uv run --no-dev --extra user python -m pymedphys._dicom.deidentify.midi_download \
  --subset validation --dest /data/midi-b/validation
```

PowerShell:

```powershell
New-Item -ItemType Directory -Force D:\midi-b | Out-Null
uv run --no-dev --extra user python -m pymedphys._dicom.deidentify.midi_download `
  --subset validation --dest D:\midi-b\validation
```

It writes:

- `images/`, the subset's DICOM files, named `<series>/<instance>.dcm` by their position in the manifest, so no path carries a UID;
- `answer-key.db`, the subset's answer key, when a copy of it is pinned or given (see below);
- `download.json`, what it fetched: counts, digests, and whether each digest matched its pin. It prints the same record at the end.

TCIA publishes each subset's answer key only through IBM Aspera, as a package (`MIDI-B-Answer-Key-Validation` or `MIDI-B-Answer-Key-Test`) holding a ZIP file of the same name, which holds the SQLite database. `midi_data.toml` pins that ZIP file's SHA-256 (`answer_key_sha256`) and, once one is published, the HTTPS address of a byte-identical copy (`answer_key_url`), which the downloader then fetches for you. Otherwise, download the package with its link on TCIA's page, in a browser or with IBM's `ascli` command, and give the downloader the ZIP file:

```bash
uv run --no-dev --extra user python -m pymedphys._dicom.deidentify.midi_download \
  --subset validation --dest /data/midi-b/validation \
  --answer-key-file ~/Downloads/MIDI-B-Answer-Key-Validation.zip
```

It checks the file against the pinned digest before it downloads the images, extracts the database as `answer-key.db`, and records both digests in `download.json`. An answer key at another HTTPS address can be given with `--answer-key-url` and `--answer-key-sha256`, in place of the pinned one.

If you prefer TCIA's own tool, open the subset's `.tcia` manifest from the page in NBIA Data Retriever and point it at an empty `images` folder. The Retriever's folder layout inside it does not matter: the harness reads every file below the folder you give it.

To check that a copy holds exactly the pinned files, however you downloaded it, run the downloader with `--verify` and the folder in place of `--dest`, adding `--answer-key-file` with the answer key's ZIP file to check that too. It counts and fingerprints every DICOM file below the folder, whatever its name, and exits with status 1 when the count or a fingerprint differs from its pin. The images' fingerprint (`content_sha256` in `midi_data.toml`) is the SHA-256 of the sorted, newline-joined SHA-256 digests of the files, so it depends only on the files' bytes. [Section 10](#10-where-the-data-come-from-and-how-to-check-them) explains what the pins establish.

```bash
uv run --no-dev --extra user python -m pymedphys._dicom.deidentify.midi_download \
  --subset validation --verify /data/midi-b/validation/images \
  --answer-key-file ~/Downloads/MIDI-B-Answer-Key-Validation.zip
```

## 4. Run the benchmark

The work directory must not exist yet, but its parent must. The command creates the work directory, readable by you alone.

bash:

```bash
mkdir -p /data/midi-b/runs
uv run --no-dev --extra user python -m pymedphys._dicom.deidentify.midi_benchmark_command run \
  --source /data/midi-b/validation/images \
  --answer-key /data/midi-b/validation/answer-key.db \
  --work /data/midi-b/runs/validation-basic-1 \
  --collection "MIDI-B Validation (TCIA 10.7937/cf2p-aw56)"
```

PowerShell:

```powershell
New-Item -ItemType Directory -Force D:\midi-b\runs | Out-Null
uv run --no-dev --extra user python -m pymedphys._dicom.deidentify.midi_benchmark_command run `
  --source D:\midi-b\validation\images `
  --answer-key D:\midi-b\validation\answer-key.db `
  --work D:\midi-b\runs\validation-basic-1 `
  --collection "MIDI-B Validation (TCIA 10.7937/cf2p-aw56)"
```

- `--preset` defaults to `basic`, the run to do first. The preset need not be enabled, since this is a validation run.
- `--preset basic-clean-descriptors` runs the Clean Descriptors Option too. The harness cleans ROI Names with the pinned TG-263 edition, which it downloads to PyMedPhys's data directory on first use, or reads from a copy of the spreadsheet given with `--tg263`. No one reviews the names in a benchmark, so a name that would be held for review is emptied, as `--empty-held-roi-names` empties it, and its structure set is released and scored.
- It refuses a work directory that already exists. For another run, use a new name such as `validation-basic-2`.
- At the end it prints the results as Markdown, the same text as `benchmark.md`.
- If it stops with an error, the message quotes no value from the files, so it is safe to share in an issue.

## 5. What it writes

Inside the work directory:

| Path | What it is | Safe to share? |
| --- | --- | --- |
| `benchmark.md` | The results to read: a headline over every check, counts by answer-key category, coverage (with the unreleased instances by SOP Class and transfer syntax), deliberate differences (by category, tag, and the action the engine selected), source gaps, findings, and the failed checks at their source. | Yes |
| `benchmark.json` | The same results as JSON, with versions and digests. | Yes |
| `release/` | The de-identified release, with its release report. | No |
| `qc/` | The confidential QC pack. | No |
| `validation-script/` | `uid_mapping.csv` and `patid_mapping.csv`, mapping the test data's UIDs and Patient IDs to their replacements, for the NCI script. | No |

In `benchmark.md`, the headline counts every check of the answer key. Checks of instances that the run did not release (withheld, or outside the release's coverage) and of instances the input lacked are outcomes of their own, so nothing drops out of the total, and the coverage section lists the unreleased instances by the run's reasons, SOP Class, and transfer syntax, and counts each reason that has a place, such as residual text, by the tags of the source attribute and of where it was found, never the value. An instance withheld for an internal error is also counted by the exception's type, the code that raised it, and the instance's SOP Class and transfer syntax, never the exception's message, so that the error can be reproduced on synthetic data. Then read the findings. The deliberate differences are where TCIA's curation differs from the Basic Profile: an attribute that the profile removes but the answer key keeps, and Patient Identity Removed and Longitudinal Temporal Information Modified, whose values the PS3.15 markers replace (`marker`). A text that the answer key says to remove is never a deliberate difference, even where the profile keeps it, since a kept value can still carry an identifier. A source gap is a check that asks for an attribute, or a value, that the source instance does not have either, so no de-identifier could keep it. The last section describes the failed checks at their source, without a value: whether the source holds each attribute that a check asked to be present, empty or with a value, and, for each text that a check asked to be removed, its VR, its number of digits where it is an Integer String, and whether the answer key's text is the whole value. Checks of instances outside the release's coverage (a nuclear medicine image, say) and of instances the run withheld are neither passed nor failed. A withheld instance withholds all of its patient's files.

## 6. Share the results

`benchmark.md` and `benchmark.json` hold counts, codes, versions, and digests, and no value from the files, so they can be attached to an issue or pull request. Keep `release/`, `qc/`, and `validation-script/` on your machine.

## 7. Optional: score the same release with the NCI script

The NCI validation script (<https://github.com/CBIIT/midi_validation_script>) pins `pydicom==2.2.1` and other old versions in its `requirements.txt`, so clone it outside the PyMedPhys checkout and give it a virtual environment of its own. Its manual, `manual/midi_validation_manual.docx` in the clone, describes the script in full.

bash:

```bash
git clone https://github.com/CBIIT/midi_validation_script.git
cd midi_validation_script
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

PowerShell:

```powershell
git clone https://github.com/CBIIT/midi_validation_script.git
Set-Location midi_validation_script
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Write its config, for example `midi-validation-basic-1.json`, naming the release and the mapping files from step 5:

```json
{
  "run_name": "validation-basic-1",
  "input_data_path": "/data/midi-b/runs/validation-basic-1/release",
  "output_data_path": "/data/midi-b/nci-results",
  "answer_db_file": "/data/midi-b/validation/answer-key.db",
  "uid_mapping_file": "/data/midi-b/runs/validation-basic-1/validation-script/uid_mapping.csv",
  "patid_mapping_file": "/data/midi-b/runs/validation-basic-1/validation-script/patid_mapping.csv",
  "multiprocessing": "True",
  "multiprocessing_cpus": "4",
  "log_path": "/data/midi-b/nci-logs",
  "log_level": "info",
  "report_series": "False"
}
```

On Windows, write the JSON paths with forward slashes (`D:/midi-b/...`), since a single backslash is not valid in JSON.

In the script's clone and environment:

```bash
python run_validation.py midi-validation-basic-1.json
python run_reports.py midi-validation-basic-1.json
```

Then count its results by the harness's categories, back in the PyMedPhys checkout:

```bash
uv run --no-dev --extra user python -m pymedphys._dicom.deidentify.midi_benchmark_command script-results \
  /data/midi-b/nci-results/validation-basic-1/validation_results.db
```

That prints JSON with counts and no values, which is safe to share too. The script counts per instance, and its figures will not match `benchmark.md` exactly, for the reasons given in the module docstring of `lib/pymedphys/_dicom/deidentify/midi_benchmark.py`. For example, the script fails a consistent-UID check that the mapping files do not cover, which the harness reports as not evaluated.

## 8. The Test subset

Repeat steps 3 to 7 with `--subset test` and a destination such as `/data/midi-b/test`, a new work directory such as `test-basic-1`, and `--collection "MIDI-B Test (TCIA 10.7937/cf2p-aw56)"`.

## 9. Run it on GitHub Actions instead

The repository's **MIDI-B Benchmark** workflow (`.github/workflows/midi-b-benchmark.yml`) does steps 2 to 7 on GitHub-hosted runners, so you need neither the disk space nor the download time. It runs only when started by hand. A maintainer starts it on `pymedphys/pymedphys`; anyone can start it on their own fork, where it uses the fork's free runner minutes.

1. On GitHub, open the repository's (or your fork's) **Actions** tab, choose **MIDI-B Benchmark**, and choose **Run workflow**.
2. Pick the branch, the subset (`validation`, `test`, or `both`), and where the answer key comes from. Each subset runs under `basic` and under `basic-clean-descriptors`, each in a job of its own.
   - `pinned`, the default: the copy at the address pinned in `midi_data.toml`. While no address is pinned, the run downloads and checks the images but cannot score them.
   - `tcia`: TCIA's own Aspera packages, fetched on the runner with IBM's `ascli` and checked against the pinned digest. This is the check from the source described in section 10.
   - Otherwise, give an HTTPS address for an answer key and its SHA-256, for one subset at a time.
   - Optionally, give an engine ref, a pull request's head (`refs/pull/<n>/head`) or a branch (`refs/heads/<name>`), to merge into the chosen branch on the runner before the run. This benchmarks an engine change before it merges, and `engine.txt` in the artefact records both commits.
3. Each job benchmarks its subset under its preset, then validates each released file against its input with dciodvfy, dcentvfy, and dicom-validator, as the [DICOM validation guide](deidentification-dicom-validation.md) describes, and scores the same release with NCI's validation script (step 7), at a pinned commit, in a Python 3.10 environment of its own. When the run finishes, its summary page shows each job's `download.json`, `benchmark.md`, DICOM validation results, and the script's counts, and each job's `midi-b-<subset>-<preset>-results` artefact holds:
   - `download.json`, `benchmark.md`, and `benchmark.json`;
   - `script-results.json`, the script's results counted by answer-key category as step 7's `script-results` counts them, or `script-results.txt` saying why there are none;
   - `dicom-validation.json` and `dicom-validation.md`, the validators' comparison of the release with its inputs, and `dicom-validation-status.txt`, its exit status;
   - `nci-script-environment.txt`, the script's commit and the versions of the packages it ran with;
   - with `tcia`, `tcia-answer-keys.txt`, the names, sizes, and SHA-256 digests of the files in TCIA's packages.

Workflow logs and artefacts on a public repository can be read by anyone, so the workflow keeps everything else on the runner, which is deleted when the job ends: the downloaded files, the release, the QC pack, the mapping files, and the NCI script's logs and results database, which quote values from the files. The benchmark's standard error, where libraries log, goes to a file on the runner, and a crash is reported by `.github/scripts/run_redacted.py` as its exception type and code locations, never its message.

## 10. Where the data come from, and how to check them

Anyone reading a MIDI-B result should be able to ask "were these really NCI's files?" and check the answer without trusting PyMedPhys. The benchmark is built so that they can.

### The images

The downloader fetches the images from The Cancer Imaging Archive itself, through its public NBIA API, and checks three things before it writes a result:

1. TCIA's dated manifest for the subset (`TCIA-MIDI-B-Synthetic-Validation_20250502.tcia` or `TCIA-MIDI-B-Synthetic-Test_20250502.tcia`, linked from the collection page) has the pinned SHA-256, so the list of series is the one TCIA published.
2. The counts match: 280 series and 23,921 DICOM files for Validation, and 428 series and 29,660 for Test. These are the counts on TCIA's collection page and in Table 1 of the MIDI-B challenge paper ([arXiv:2508.01889](https://arxiv.org/abs/2508.01889)).
3. The fingerprint of the files' bytes, `content_sha256`, matches its pin. It was pinned from a download on a GitHub-hosted runner and has matched on every download since, so NBIA serves the same bytes each time.

A copy fetched any other way, such as with NBIA Data Retriever, can be checked against the same pins with `--verify` (step 3), whatever its folder layout.

### The answer keys

TCIA offers the answer keys only through IBM Aspera, which a GitHub runner or a script can use only with IBM's client. So the pins name TCIA's own file:

- `answer_key_sha256` is the SHA-256 of the ZIP file in TCIA's package for the subset, as the **MIDI-B Benchmark** workflow received it from TCIA on 10 October 2026.
- Routine runs fetch a copy of that same ZIP file from Zenodo (`answer_key_url`), deposited with a citation of TCIA's DOI under the same CC BY 4.0 licence. The downloader refuses any copy whose digest differs from the pin, so a run can only ever score against a file byte-identical to TCIA's.
- Running the workflow with `answer-keys-from: tcia` fetches the packages from TCIA again, records their files' digests in `tcia-answer-keys.txt`, and scores against TCIA's file directly. If TCIA's file still matches the pin, so does the Zenodo copy. Anyone can run it on a fork.
- On your own machine, `--verify` with `--answer-key-file` checks a ZIP file you downloaded from TCIA against the same pin.

### What the pins do not establish

A matching digest shows that the files are the ones TCIA served when they were pinned. It says nothing about whether the answer key is right about a given file, which is NCI's responsibility; the benchmark reports deliberate differences from it by category for that reason. If TCIA revises the collection or the answer keys, as NCI did once in 2025, the downloader stops with a digest mismatch rather than benchmark different files quietly, and the pins are updated in a reviewed pull request.
