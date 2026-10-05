# Work with DICOM

Use the [library reference](../ref/lib/dicom.rst) for arrays and in-memory
operations, and the [DICOM CLI reference](../ref/cli/dicom.rst) for file editing
and transfer. Start with the [synthetic header example](first-result.md#change-a-synthetic-dicom-header-with-the-cli)
to check the CLI without clinic data. Work on output copies and check the
resulting attributes and references.

## Extract dose with matching physical coordinates

Read an RT Dose with pydicom, then pass the dataset to
`pymedphys.dicom.zyx_and_dose_from_dataset`. It returns matching ascending axes
and dose in patient `(z, y, x)` order. Dose values include `DoseGridScaling`;
check `DoseUnits` before assigning units or comparing datasets.

This entirely synthetic grid has unequal spacings and an off-centre origin,
so the checks establish which coordinates belong to each array dimension:

```python
import numpy as np
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian
import pymedphys

rt_dose = Dataset()
rt_dose.file_meta = FileMetaDataset()
rt_dose.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
rt_dose.Modality = "RTDOSE"
rt_dose.DoseUnits = "GY"
rt_dose.DoseGridScaling = 0.01
rt_dose.Rows = 2
rt_dose.Columns = 3
rt_dose.NumberOfFrames = 2
rt_dose.ImagePositionPatient = [-10, -20, 30]
rt_dose.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
rt_dose.PixelSpacing = [2, 3]
rt_dose.GridFrameOffsetVector = [0, 4]
rt_dose.SamplesPerPixel = 1
rt_dose.PhotometricInterpretation = "MONOCHROME2"
rt_dose.BitsAllocated = 16
rt_dose.BitsStored = 16
rt_dose.HighBit = 15
rt_dose.PixelRepresentation = 0
rt_dose.PixelData = np.arange(12, dtype="<u2").reshape(2, 2, 3).tobytes()
(z, y, x), dose = pymedphys.dicom.zyx_and_dose_from_dataset(rt_dose)
np.testing.assert_allclose(z, [30, 34])
np.testing.assert_allclose(y, [-20, -18])
np.testing.assert_allclose(x, [-10, -7, -4])
assert dose.shape == (2, 2, 3)
assert np.isclose(dose[1, 1, 2], 0.11)
print("Dose at (z, y, x) = (34, -18, -4) mm: 0.11 Gy")
```

The helper supports eight transverse cardinal patient orientations. It may
reverse axes and transpose pixel dimensions for other supported orientations;
keep its returned axes and dose together. Oblique grids are outside this
interface's supported geometry. The rearrangement does not resample dose.
For overlays, use the returned dose rather than indexing raw `pixel_array`
as though its order always agrees. The [illustrated coordinate guide](../../contrib/info/dicom-coordinates-illustrated.ipynb)
and [validation record](../../contrib/info/dicom-coordinate-validation.md)
explain the supported geometry and limits.

For a dose value at new physical locations, use
`pymedphys.dicom.dicom_dose_interpolate((z_positions, y_positions, x_positions), dataset)`.
The positions form a Cartesian grid and must fall within the dose grid.
`depth_dose` and `profile` have narrower phantom/beam assumptions: consult
those functions before using patient data. See [Compare dose](compare.md)
for the complete RT Dose gamma workflow.

## Merge overlapping planar contours

The library accepts **one ROIContourSequence item**, not a whole RT Structure
Set. `inplace=True` modifies that item and returns `None`. The default returns
a shallow copy whose element mapping can remain shared with the input;
deep-copy the input first when preserving it matters. This example combines
two overlapping 2 mm squares in the
same axial plane, with a known union area of 7 square mm:

```python
import copy
import numpy as np
from pydicom.dataset import Dataset
from pydicom.uid import CTImageStorage, generate_uid
import pymedphys

image_uid = generate_uid()
roi = Dataset()
roi.ReferencedROINumber = 1
roi.ContourSequence = []
for vertices in (
    [(0, 0), (2, 0), (2, 2), (0, 2)],
    [(1, 1), (3, 1), (3, 3), (1, 3)],
):
    image = Dataset()
    image.ReferencedSOPClassUID = CTImageStorage
    image.ReferencedSOPInstanceUID = image_uid
    contour = Dataset()
    contour.ContourGeometricType = "CLOSED_PLANAR"
    contour.NumberOfContourPoints = len(vertices)
    contour.ContourImageSequence = [image]
    contour.ContourData = [v for px, py in vertices for v in (px, py, 0)]
    roi.ContourSequence.append(contour)
merged = pymedphys.dicom.merge_contours(copy.deepcopy(roi))
assert len(roi.ContourSequence) == 2
assert len(merged.ContourSequence) == 1
vertices = np.asarray(merged.ContourSequence[0].ContourData).reshape(-1, 3)
px, py = vertices[:, 0], vertices[:, 1]
area = abs(np.dot(px, np.roll(py, 1)) - np.dot(py, np.roll(px, 1))) / 2
assert np.isclose(area, 7.0)
print(f"Merged area: {area:.1f} square mm")
```

For a file containing supported contours:

```bash
pymedphys dicom merge-contours structures.dcm merged-structures.dcm --structures DOCUMENTATION
```

Omitting `--structures` processes every ROI contour item. The implementation
requires `CLOSED_PLANAR` contours with constant z, the expected contour fields,
and one common referenced image per plane. It writes exterior polygon
boundaries rounded to 0.1 mm; inspect output topology and do not use it to
preserve holes. Unsupported geometry or extra contour fields can raise
`ValueError`. Verify contour locations and image references in the output.

## Edit machine names and electron-density overrides

The [first-result command](first-result.md) changes every beam's
`TreatmentMachineName`. It changes metadata, not the machine model or calculated
dose. For relative electron density (RED) overrides in an RT Structure Set,
supply alternating **exact ROI name and density** pairs:

```bash
pymedphys dicom adjust-RED structures.dcm changed-structures.dcm "DOCUMENTATION" 1.15 "ANOTHER_ROI" 0.20
```

Each selected ROI must have an associated observation. A missing ROI raises
unless `--ignore_missing_structure` is used. Check each
`ROIPhysicalPropertiesSequence` for the intended `REL_ELEC_DENSITY` value.
`adjust-RED-by-structure-name` reads density from names ending in forms such as
`DOCUMENTATION RED=1.15`. These edits require downstream verification; the
commands do not recalculate dose.

## Send and receive a local synthetic file

Create `synthetic-plan.dcm` from [Your first result](first-result.md) first.
In one activated terminal, start a receiver bound to this computer:

```bash
pymedphys dicom listen 11112 --host 127.0.0.1 --storage_directory received --aetitle DOCS
```

In a second terminal in the practice directory, send the file:

```bash
pymedphys dicom send 127.0.0.1 11112 synthetic-plan.dcm --aetitle DOCS
```

The receiver stores objects below
`received/PatientID/StudyUID/SeriesUID/<modality-prefix>.SOPUID.dcm`.
Check the received file rather than relying only on the sender's process exit
status. Save and run this check from the practice directory:

```python
from pathlib import Path
import pydicom

source = pydicom.dcmread("synthetic-plan.dcm")
received = list(Path("received").rglob(f"*.{source.SOPInstanceUID}.dcm"))
assert len(received) == 1
received_plan = pydicom.dcmread(received[0])
assert received_plan.SOPInstanceUID == source.SOPInstanceUID
assert received_plan.BeamSequence[0].TreatmentMachineName == "SYNTHETIC_A"
print("Synthetic file received and checked.")
```

Stop the receiver with Ctrl+C. For a real endpoint, obtain its address, port,
called AE title, and supported storage/transfer syntaxes. The sender negotiates
Implicit VR Little Endian; an endpoint or source requiring other encodings may
fail. Connection errors require checking the listener, AE title, route, and
firewall. Without `--host`, the listener binds all interfaces. Received paths
and local logs can contain identifiers; choose appropriately protected storage.
On Windows, long practice-directory paths plus the UID hierarchy can exceed
the filesystem path limit. Use a short practice path if the receiver cannot
write the file despite having permissions.

## Share data only after reviewing identification risks

The current anonymisation and experimental pseudonymisation tools have known
limitations. Read [DICOM de-identification](../background/dicom-deidentification.md)
before applying them or sharing output. The [replacement design](../../contrib/info/deidentification-design.md)
describes planned functionality, rather than an available public API.

```{toctree}
:hidden:

../background/dicom-deidentification
```
