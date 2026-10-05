# Your first result

Complete one of these routes after the [Quick Start Guide](../get-started/quick-start.rst).
The Python and CLI examples use synthetic data, need no clinic connection, and
do not download anything. The app route downloads public demonstration data.

## Calculate gamma in Python

Save this as `first_gamma.py` and run `python first_gamma.py` in your activated
environment. It compares a simple dose profile with an identical copy. Positions
are in mm, and both dose arrays use the same units.

```python
import numpy as np
import pymedphys

x = np.linspace(-10.0, 10.0, 21)
dose = np.exp(-(x / 5.0) ** 2)
gamma = pymedphys.gamma(
    x, dose, x, dose.copy(),
    dose_percent_threshold=3,
    distance_mm_threshold=2,
    lower_percent_dose_cutoff=20,
    interp_fraction=10,
)
analysed = ~np.isnan(gamma)
assert gamma.shape == dose.shape
assert analysed.any()
assert np.allclose(gamma[analysed], 0)
print(f"Analysed points: {analysed.sum()}")
print(f"Pass rate: {pymedphys.gamma_pass_rate(gamma):.1f}%")
```

The output is `Analysed points: 13` and `Pass rate: 100.0%`. Points below
the cutoff are excluded and have NaN gamma. This checks installation and the
array interface; an identical-input calculation does not validate a clinical
comparison. Continue to [Compare dose](compare.md) for different inputs and
interpretation.

If a required package is missing, follow the installation command in the
exception, in this same environment. If `python` uses another install,
reactivate the environment from the Quick Start Guide.

## Change a synthetic DICOM header with the CLI

Work in an empty practice directory. Save this as `make_synthetic_plan.py` and
run `python make_synthetic_plan.py`. The file contains only fields needed for
this example; it is a plumbing fixture, not a complete treatment plan.

```python
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.uid import ImplicitVRLittleEndian, RTPlanStorage, generate_uid

meta = FileMetaDataset()
meta.TransferSyntaxUID = ImplicitVRLittleEndian
meta.MediaStorageSOPClassUID = RTPlanStorage
meta.MediaStorageSOPInstanceUID = generate_uid(prefix=None)
plan = FileDataset("synthetic-plan.dcm", {}, file_meta=meta, preamble=b"\0" * 128)
plan.SOPClassUID = meta.MediaStorageSOPClassUID
plan.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
plan.StudyInstanceUID = generate_uid(prefix=None)
plan.SeriesInstanceUID = generate_uid(prefix=None)
plan.PatientID = "SYNTHETIC"
plan.PatientName = "PHANTOM^Documentation"
plan.Modality = "RTPLAN"
beam = Dataset()
beam.TreatmentMachineName = "SYNTHETIC_A"
plan.BeamSequence = [beam]
plan.save_as("synthetic-plan.dcm", enforce_file_format=True)
```

Run the command to create a separate output:

```bash
pymedphys dicom adjust-machine-name synthetic-plan.dcm changed-plan.dcm SYNTHETIC_B
```

Save and run this as `check_changed_plan.py`:

```python
import pydicom

original = pydicom.dcmread("synthetic-plan.dcm")
changed = pydicom.dcmread("changed-plan.dcm")
assert original.BeamSequence[0].TreatmentMachineName == "SYNTHETIC_A"
assert changed.BeamSequence[0].TreatmentMachineName == "SYNTHETIC_B"
print("Output machine name changed; original preserved.")
```

If the command is unavailable, reactivate the environment. An error about
`BeamSequence` means the input was not the synthetic RT Plan created above.
Continue to [Work with DICOM](dicom.md) for transfer and editing tasks.

## Compare delivery using the app demonstration

From a practice directory, run `pymedphys gui` and select **MetersetMap
Comparison**. Choose **Demo Data** under **Config Mode**. The app downloads
and extracts its example configuration and inputs into the current directory.

1. Enter `989898` as the **Patient ID**.
2. Choose the Monaco plan whose name contains `3ABUT`.
3. Select the iCOM timestamp `2020-04-29 07:47:29`.
4. Check that both overviews show `PHYSICS, Mock` and `150.0` MU.
5. Select **Run Calculation** and inspect the result panels and saved PNG report.

These selections are demonstration records. The calculation produces reference
and evaluation MetersetMaps, their difference, a gamma image, and a histogram.
PDF generation additionally needs ImageMagick; the PNG report remains available
if conversion fails. Without ImageMagick, the app displays a conversion error
after saving the PNGs. Read [Use the apps](apps.md) for interpretation, output
locations, file uploads, and configuration.

If the demo cannot download, check the installation guide's network guidance.
If a previous extraction has been edited, start from a new practice directory:
explicit extraction directories preserve existing files.
