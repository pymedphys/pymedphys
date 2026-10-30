---
myst:
  heading_anchors: 2
---

# Check the text detector against HaN-Seg

Under the Clean Pixel Data Option, the de-identification engine gives each frame of the pixel data to a text detector, blacks out every region that it finds, and holds the instance for review (D-037 in the [de-identification design](deidentification-design.md)). The `Text Detector Check` workflow gives the same detector the slices of the HaN-Seg data set's 42 head and neck planning CTs and 42 T1-weighted MRs, and publishes only counts of the slices and regions that it finds.

HaN-Seg's images hold no burned-in text, as far as the project knows, so each region counted is one that a run would black out in error, over anatomy unless the region is all air, and that a reviewer would have to clear. That is an inference, not something the check measures; the counts are the option's only evidence on real images of the anatomy in scope.

## The data set

The check uses HaN-Seg version 1.0, as the face block check does, under the same rules (D-054): only the workflow's runner downloads it, from Zenodo, and checks it against the size and MD5 that the record gives; the runner reads it from its ZIP file without extracting it; and only counts, codes, digests, versions, and the detector's method leave the runner. Its images are of real patients, so the project treats them as real patient data: never commit, cache, or attach any part of the data set, or a value read from it. See [Check the face block against HaN-Seg](deidentification-face-validation.md) for the record, its licence, and its citation.

## Run the check

1. In the repository's **Actions** tab, choose **Text Detector Check**, then **Run workflow**, and pick the branch whose detector to check.
2. Two jobs run side by side, one for the CTs (`CT`) and one for the MRs (`MR_T1`). Each downloads `HaN-Seg.zip` from Zenodo, checks its size and MD5 against the record's, and runs the check with a process for each of the runner's CPUs.
3. Each job's summary shows its results, and its artefact `pixel-text-validation-results-CT` or `pixel-text-validation-results-MR_T1`, kept for 90 days, holds `pixel-text-validation.json`, `pixel-text-validation.md`, and `commit.txt`, the commit checked.

Each job runs `python -m pymedphys._dicom.deidentify.pixel_text_validation_command hanseg <HaN-Seg.zip> --image <CT or MR_T1> --workers <CPUs> --out <directory>` through `.github/scripts/run_redacted.py`, which reports a crash by its type and code locations alone, and keeps the command's standard output and standard error, where libraries log, in files on the runner. The command makes the detector as a run under the option makes it, with the pinned model, which it downloads from PyPI on first use, and its default parameters. Each worker process has its own detector of one thread, so the regions do not depend on how many workers run. The detector takes seconds a slice, so a job takes hours; each has almost the six hours that a hosted runner allows.

## What the counts show

Each volume is given to the detector as a run gives it a series of its slices: one frame for each slice along the volume's third axis, its values, rounded where they are not integers, as stored values. The detector's renderings depend only on the stored values' minimum, maximum, and differences, so HaN-Seg's CTs, stored in Hounsfield units, give the regions that the same CTs would with a rescale intercept.

| Section | What it counts |
| --- | --- |
| Volumes | The volumes of the image in the ZIP file, those measured, those not measured by why, such as `not-read/data-length`, and crashes by the exception's type and place in the code; how each was stored; the plane of its slices, named by the patient's axis within 10 degrees of their normal, or `oblique`; the larger side of a slice, in pixels; and the larger spacing within a slice. |
| Slices | The slices searched, those with a region, the regions, and the slices by how many regions each gives. |
| Volumes by their regions | The volumes with a region, the volumes by how many regions each gives, and by the share of their slices with a region. |
| Regions | Each region's area as a share of its slice's, its shorter side in pixels, its longer side over its shorter, and, for CT, the share of its pixels above -900 HU, where the region would black out more than air. |

The summary is labelled `pymedphys-deid-pixel-text-validation/1`. It also gives the detector's method as the method digest of a run takes it: the finder's class, the model's SHA-256, the ONNX Runtime version and distributions, the NumPy and SciPy versions, the detection parameters, and the renderings. Each measure is counted in fixed bins, and no case is named, so the summary gives no value of any case.

## Results on main

The check ran on main at commit `d3c67ee1e56e9d161a131061484f7ceec364cf26` on 26 October 2026, in run [40286977414](https://github.com/pymedphys/pymedphys/actions/runs/40286977414), whose two jobs both succeeded. Their artefacts expire on 24 January 2027, so their counts are recorded here, as the job summaries give them.

| About | |
| --- | --- |
| Summary | `pymedphys-deid-pixel-text-validation/1` |
| Data set | HaN-Seg 1.0, doi:10.5281/zenodo.7442914 |
| File | 4938848306 bytes, MD5 `c3d3070de3034933a63031b73b9cf0fc`, SHA-256 `20226dd717f334dc1b1afe961b3375f946fa56b64a80bf5349128f90c0bbfa5f` |
| Software | Python 3.14.8, pymedphys 0.42.0.dev1, NumPy 2.5.4, SciPy 1.18.1, ONNX Runtime 1.31.0 |
| Finder | `pymedphys._dicom.deidentify.text_detection.TextDetector`, with its default parameters |
| Model SHA-256 | `090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f` |
| Artefact `pixel-text-validation-results-CT` | 3737 bytes as uploaded, SHA-256 `09f316a2e66307ca3a0169d73afa7663c156f4534094ebcc0f573df77feac2e9` |
| Artefact `pixel-text-validation-results-MR_T1` | 3466 bytes as uploaded, SHA-256 `687fb9165b5167ad9487ef2ef8fd46977af0c371dbbe0241e406f3f7d777a0cb` |

### Volumes

| Volumes | CT | MR_T1 |
| --- | ---: | ---: |
| In the data set | 42 | 42 |
| Measured | 42 | 42 |
| Stored as `int16 gzip left-posterior-superior` | 31 | 36 |
| Stored as `int32 gzip left-posterior-superior` | 11 | 0 |
| Stored as `uint16 gzip left-posterior-superior` | 0 | 6 |
| With axial slices | 42 | 42 |

| Larger side of a slice (pixels) | CT volumes | MR_T1 volumes |
| --- | ---: | ---: |
| 0 to under 256 | 0 | 0 |
| 256 to under 384 | 0 | 0 |
| 384 to under 512 | 0 | 0 |
| 512 to under 640 | 7 | 42 |
| 640 to under 768 | 0 | 0 |
| 768 to under 1024 | 0 | 0 |
| 1024 or more | 35 | 0 |

| Larger spacing within a slice (mm) | CT volumes | MR_T1 volumes |
| --- | ---: | ---: |
| 0 to under 0.5 | 0 | 27 |
| 0.5 to under 0.75 | 35 | 14 |
| 0.75 to under 1 | 5 | 1 |
| 1 to under 1.25 | 1 | 0 |
| 1.25 to under 1.5 | 0 | 0 |
| 1.5 to under 2 | 1 | 0 |
| 2 or more | 0 | 0 |

### Slices

| Slices | CT | MR_T1 |
| --- | ---: | ---: |
| Searched | 7581 | 3613 |
| With a region | 7162 | 719 |
| Regions | 33183 | 953 |

| Regions in a slice (regions) | CT slices | MR_T1 slices |
| --- | ---: | ---: |
| 0 to under 1 | 419 | 2894 |
| 1 to under 2 | 993 | 540 |
| 2 to under 3 | 1133 | 134 |
| 3 to under 4 | 1066 | 36 |
| 4 to under 5 | 968 | 8 |
| 5 to under 10 | 2388 | 1 |
| 10 to under 20 | 611 | 0 |
| 20 or more | 3 | 0 |

### Volumes by their regions

Every volume of each image gave at least one region: 42 CTs and 42 MRs.

| Regions in a volume (regions) | CT volumes | MR_T1 volumes |
| --- | ---: | ---: |
| 0 to under 1 | 0 | 0 |
| 1 to under 2 | 0 | 0 |
| 2 to under 5 | 0 | 1 |
| 5 to under 10 | 0 | 3 |
| 10 to under 20 | 0 | 14 |
| 20 to under 50 | 0 | 24 |
| 50 to under 100 | 0 | 0 |
| 100 to under 200 | 2 | 0 |
| 200 to under 500 | 6 | 0 |
| 500 to under 1000 | 25 | 0 |
| 1000 or more | 9 | 0 |

| Share of a volume's slices with a region (share) | CT volumes | MR_T1 volumes |
| --- | ---: | ---: |
| 0 to under 0.1 | 0 | 2 |
| 0.1 to under 0.2 | 0 | 19 |
| 0.2 to under 0.3 | 0 | 17 |
| 0.3 to under 0.4 | 0 | 4 |
| 0.4 to under 0.5 | 0 | 0 |
| 0.5 to under 0.6 | 1 | 0 |
| 0.6 to under 0.7 | 2 | 0 |
| 0.7 to under 0.8 | 1 | 0 |
| 0.8 to under 0.9 | 2 | 0 |
| 0.9 to under 1 | 21 | 0 |
| 1 or more | 15 | 0 |

### Regions

| Area (share of the slice) | CT regions | MR_T1 regions |
| --- | ---: | ---: |
| 0 to under 0.0005 | 1615 | 0 |
| 0.0005 to under 0.001 | 4410 | 0 |
| 0.001 to under 0.002 | 8910 | 25 |
| 0.002 to under 0.005 | 10227 | 167 |
| 0.005 to under 0.01 | 3942 | 203 |
| 0.01 to under 0.02 | 2126 | 228 |
| 0.02 to under 0.05 | 1886 | 287 |
| 0.05 to under 0.1 | 65 | 40 |
| 0.1 or more | 2 | 3 |

| Shorter side (pixels) | CT regions | MR_T1 regions |
| --- | ---: | ---: |
| 0 to under 8 | 0 | 0 |
| 8 to under 12 | 0 | 0 |
| 12 to under 16 | 91 | 1 |
| 16 to under 24 | 3635 | 50 |
| 24 to under 32 | 5388 | 140 |
| 32 to under 48 | 9465 | 277 |
| 48 to under 64 | 5217 | 195 |
| 64 to under 96 | 6139 | 250 |
| 96 or more | 3248 | 40 |

| Longer side over shorter (ratio) | CT regions | MR_T1 regions |
| --- | ---: | ---: |
| 1 to under 1.5 | 27571 | 637 |
| 1.5 to under 2 | 3592 | 202 |
| 2 to under 3 | 1498 | 104 |
| 3 to under 5 | 485 | 10 |
| 5 to under 10 | 37 | 0 |
| 10 or more | 0 | 0 |

| Share of the region's pixels above -900 HU (share) | CT regions |
| --- | ---: |
| 0 to under 0.1 | 36 |
| 0.1 to under 0.2 | 261 |
| 0.2 to under 0.3 | 1798 |
| 0.3 to under 0.4 | 4516 |
| 0.4 to under 0.5 | 3913 |
| 0.5 to under 0.6 | 3446 |
| 0.6 to under 0.7 | 2783 |
| 0.7 to under 0.8 | 1779 |
| 0.8 to under 0.9 | 1431 |
| 0.9 to under 1 | 3142 |
| 1 or more | 10078 |

### Reading these counts

- On CT, the detector found a region in 94.5% of the slices searched and in every volume, 4.38 regions for each slice searched. Of its 33,183 regions, 22,659 (68%) have half or more of their pixels above -900 HU, and 10,078 (30%) have all of them, so most would black out tissue rather than air.
- On MR, it found a region in 19.9% of the slices and in every volume, 0.26 regions for each slice searched.
- If, as above, HaN-Seg's images hold no burned-in text, every one of these regions is a false positive. A reviewer can add a region to a cleaned instance but cannot remove one that the finder found (D-048), so a cleaned slice like these is released with every region blacked out, or rejected.
- 35 of the 42 CTs have slices of 1024 pixels or more on their larger side, and every MR has slices of 512 to under 640. The summaries do not count regions by slice size, so they do not show whether size explains the difference between CT and MR.
- The counts are evidence, not a verdict: whether the option's false positives on CT and MR are acceptable is for the maintainer to decide, and the validation table of the design doc records that decision as not yet made.
