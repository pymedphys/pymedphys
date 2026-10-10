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
- `answer-key.db`, the subset's answer key, when one is pinned for it;
- `download.json`, what it fetched: counts, digests, and whether each digest matched its pin. It prints the same record at the end.

When no answer key is pinned for the subset, download it from TCIA's page (an SQLite `.db` file) and save it as `answer-key.db` beside `images/`. If you have an answer key at an HTTPS address, `--answer-key-url` and `--answer-key-sha256` fetch and check it in place of the pinned one.

If you prefer TCIA's own tool, open the subset's `.tcia` manifest from the page in NBIA Data Retriever and point it at an empty `images` folder. The Retriever's folder layout inside it does not matter: the harness reads every file below the folder you give it.

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
- It refuses `basic-clean-descriptors`, which needs a reviewed ROI-names list that the harness does not take yet.
- It refuses a work directory that already exists. For another run, use a new name such as `validation-basic-2`.
- At the end it prints the results as Markdown, the same text as `benchmark.md`.
- If it stops with an error, the message quotes no value from the files, so it is safe to share in an issue.

## 5. What it writes

Inside the work directory:

| Path | What it is | Safe to share? |
| --- | --- | --- |
| `benchmark.md` | The results to read: counts by answer-key category, coverage, deliberate differences (by category, tag, and the action the engine selected), and findings. | Yes |
| `benchmark.json` | The same results as JSON, with versions and digests. | Yes |
| `release/` | The de-identified release, with its release report. | No |
| `qc/` | The confidential QC pack. | No |
| `validation-script/` | `uid_mapping.csv` and `patid_mapping.csv`, mapping the test data's UIDs and Patient IDs to their replacements, for the NCI script. | No |

In `benchmark.md`, read the findings first. The deliberate differences are where TCIA's curation differs from the Basic Profile. Checks of instances outside the release's coverage (a nuclear medicine image, say) and of instances the run withheld are counted apart and not scored. A withheld instance withholds all of its patient's files.

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

The repository's **MIDI-B Benchmark** workflow (`.github/workflows/midi-b-benchmark.yml`) does steps 2 to 6 on a GitHub-hosted runner, so you need neither the disk space nor the download time. It runs only when started by hand. A maintainer starts it on `pymedphys/pymedphys`; anyone can start it on their own fork, where it uses the fork's free runner minutes.

1. On GitHub, open the repository's (or your fork's) **Actions** tab, choose **MIDI-B Benchmark**, and choose **Run workflow**.
2. Pick the branch, the subset (`validation`, `test`, or `both`, which runs each in a job of its own), and, only when no answer key is pinned for the subset, an HTTPS address for one and its SHA-256.
3. When the run finishes, its summary page shows `download.json` and `benchmark.md`, and the `midi-b-<subset>-results` artefact holds `download.json`, `benchmark.md`, and `benchmark.json`.

Workflow logs and artefacts on a public repository can be read by anyone, so the workflow keeps everything else on the runner, which is deleted when the job ends: the downloaded files, the release, the QC pack, and the mapping files. The benchmark's standard error, where libraries log, goes to a file on the runner, and a crash is reported by `.github/scripts/run_redacted.py` as its exception type and code locations, never its message.
