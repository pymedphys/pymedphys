---
myst:
  heading_anchors: 2
---

# Check the text detector against HaN-Seg

Under the Clean Pixel Data Option, the de-identification engine gives each frame of the pixel data to a text detector, blacks out every region that it finds, and holds the instance for review (D-037 in the [de-identification design](deidentification-design.md)). The `Text Detector Check` workflow gives the same detector the slices of the HaN-Seg data set's 42 head and neck planning CTs and 42 T1-weighted MRs, and publishes only counts of the slices and regions that it finds.

HaN-Seg's images hold no burned-in text, as far as the project knows, so each region counted is one that a run would black out in error, over anatomy unless the region is all air, and that a reviewer would have to clear. That is an inference, not something the check measures; the counts are the option's only evidence on real images of the anatomy in scope.

The check counts false positives alone, on two IODs of one body site. Measuring missed text and false positives together, on images with and without burned-in text across the IODs in scope, and tuning the detector against criteria set beforehand, is designed in D-056; its library is described under [Measuring missed text as well](#measuring-missed-text-as-well), and its tuning runs and the adoption of a tuned detector are not yet made, so this check's counts remain the detector's evidence on these images until then.

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
| Regions | Each region's area as a share of its slice's, its shorter side in pixels, its longer side over its shorter, and, for CT, the share of its pixels above -900 HU, where the region would black out more than air; then each region's score margin and the renderings that gave it. |
| By the larger side of a slice | For each bin of the larger side of a slice, in pixels: the volumes, the slices searched, the slices with a region, and the regions; and, for the bins that hold a volume, the regions by score margin and by the renderings that gave them. |
| By the larger spacing within a slice | The same, for each bin of the larger spacing within a slice, in millimetres. |

A region's score margin is the highest mean probability that any of the detector's three renderings (its full range and its white and black top-hats) gave the region's box, less the detector's box threshold, 0.5 by default. A box is kept while any rendering gives it, so the regions with a margin of at least some amount are those that the same detector would keep with its box threshold raised by that amount, every other parameter unchanged. Raising the box threshold could also lose text that the detector now finds, which this check cannot show, since HaN-Seg holds none.

The summary is labelled `pymedphys-deid-pixel-text-validation/2`. It also gives the detector's method as the method digest of a run takes it: the finder's class, the model's SHA-256, the ONNX Runtime version and distributions, the NumPy and SciPy versions, the detection parameters, and the renderings. Each measure is counted in fixed bins, and no case is named, so the summary gives no value of any case.

## Results on main

The check ran on main at commit `d3c67ee1e56e9d161a131061484f7ceec364cf26` on 26 October 2026, in run [40286977414](https://github.com/pymedphys/pymedphys/actions/runs/40286977414), whose two jobs both succeeded. Their artefacts expire on 24 January 2027, so their counts are recorded here, as the job summaries give them. The run predates the `/2` summary: its summaries are labelled `/1`, and have no score margins, no renderings, and no counts by the larger side of a slice or the larger spacing within one.

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
- 35 of the 42 CTs have slices of 1024 pixels or more on their larger side, and every MR has slices of 512 to under 640. These `/1` summaries do not count regions by slice size, so they do not show whether size explains the difference between CT and MR; the `/2` summary counts them so, and its [rerun](#results-by-slice-size-and-score-margin) is recorded below.
- The counts are evidence, not a verdict: whether the detector's false positives on CT and MR are acceptable is decided by the evaluation that D-056 designs, which measures them with missed text on the same images against acceptance criteria set before tuning, and the validation table of the design doc waits on its held-out confirmation.

## Results by slice size and score margin

The check ran again at commit `904b15d6fcec766a73f0d7532aee94d54873c3b0`, the change that added the `/2` summary, now on main, in run [41145832882](https://github.com/pymedphys/pymedphys/actions/runs/41145832882) on 31 October 2026, whose two jobs both succeeded. An earlier run at the same commit, [41145744256](https://github.com/pymedphys/pymedphys/actions/runs/41145744256), gave the same summaries, value for value. Their artefacts expire on 28 January 2027, so their counts are recorded here, as the summaries give them. Every count that the `/1` summary also gives is the same as in the [run on main](#results-on-main) above, so only the counts that `/2` adds are shown.

| About | |
| --- | --- |
| Summary | `pymedphys-deid-pixel-text-validation/2` |
| Data set | HaN-Seg 1.0, doi:10.5281/zenodo.7442914, the same file as above |
| Software | Python 3.14.9, pymedphys 0.42.0.dev1, NumPy 2.5.4, SciPy 1.18.1, ONNX Runtime 1.31.0 |
| Finder | `pymedphys._dicom.deidentify.text_detection.TextDetector`, with its default parameters, box threshold 0.5 |
| Model SHA-256 | `090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f` |
| Artefact `pixel-text-validation-results-CT` | 5564 bytes as uploaded, SHA-256 `e5b39d9b7489b944e1b63eb5b291b7db817b5966d06ca3a4c598f24d97dc977c` |
| Artefact `pixel-text-validation-results-MR_T1` | 4911 bytes as uploaded, SHA-256 `04bd1ce00bd56037d7f184690efb76b794330aaf869c6fbafe3e372774e8f204` |

### Regions by score margin and rendering

| Score margin (mean probability above the box threshold) | CT regions | MR_T1 regions |
| --- | ---: | ---: |
| 0 to under 0.025 | 1822 | 106 |
| 0.025 to under 0.05 | 1862 | 73 |
| 0.05 to under 0.1 | 3906 | 210 |
| 0.1 to under 0.15 | 4482 | 132 |
| 0.15 to under 0.2 | 5155 | 128 |
| 0.2 to under 0.25 | 5932 | 152 |
| 0.25 to under 0.3 | 4996 | 98 |
| 0.3 to under 0.35 | 3932 | 41 |
| 0.35 to under 0.4 | 962 | 13 |
| 0.4 to under 0.45 | 134 | 0 |
| 0.45 or more | 0 | 0 |

| Renderings that gave the region | CT regions | MR_T1 regions |
| --- | ---: | ---: |
| `black-top-hat` | 18516 | 401 |
| `full-range` | 4715 | 29 |
| `full-range+white-top-hat` | 114 | 0 |
| `white-top-hat` | 9838 | 523 |

### By the larger side of a slice

Every other bin of the larger side of a slice holds no volume of either image.

| Image and larger side of a slice (pixels) | Volumes | Slices searched | Slices with a region | Regions |
| --- | ---: | ---: | ---: | ---: |
| CT, 512 to under 640 | 7 | 1132 | 841 | 1646 |
| CT, 1024 or more | 35 | 6449 | 6321 | 31537 |
| MR_T1, 512 to under 640 | 42 | 3613 | 719 | 953 |

| Score margin | CT, 512 to under 640 pixels | CT, 1024 or more pixels | MR_T1, 512 to under 640 pixels |
| --- | ---: | ---: | ---: |
| 0 to under 0.025 | 101 | 1721 | 106 |
| 0.025 to under 0.05 | 117 | 1745 | 73 |
| 0.05 to under 0.1 | 188 | 3718 | 210 |
| 0.1 to under 0.15 | 220 | 4262 | 132 |
| 0.15 to under 0.2 | 237 | 4918 | 128 |
| 0.2 to under 0.25 | 382 | 5550 | 152 |
| 0.25 to under 0.3 | 253 | 4743 | 98 |
| 0.3 to under 0.35 | 104 | 3828 | 41 |
| 0.35 to under 0.4 | 43 | 919 | 13 |
| 0.4 to under 0.45 | 1 | 133 | 0 |
| 0.45 or more | 0 | 0 | 0 |

| Renderings | CT, 512 to under 640 pixels | CT, 1024 or more pixels | MR_T1, 512 to under 640 pixels |
| --- | ---: | ---: | ---: |
| `black-top-hat` | 678 | 17838 | 401 |
| `full-range` | 497 | 4218 | 29 |
| `full-range+white-top-hat` | 6 | 108 | 0 |
| `white-top-hat` | 465 | 9373 | 523 |

### By the larger spacing within a slice

Every other bin of the larger spacing within a slice holds no volume of either image.

| Image and larger spacing within a slice (mm) | Volumes | Slices searched | Slices with a region | Regions |
| --- | ---: | ---: | ---: | ---: |
| CT, 0.5 to under 0.75 | 35 | 6449 | 6321 | 31537 |
| CT, 0.75 to under 1 | 5 | 869 | 650 | 1274 |
| CT, 1 to under 1.25 | 1 | 122 | 107 | 211 |
| CT, 1.5 to under 2 | 1 | 141 | 84 | 161 |
| MR_T1, 0 to under 0.5 | 27 | 1866 | 388 | 503 |
| MR_T1, 0.5 to under 0.75 | 14 | 1707 | 323 | 441 |
| MR_T1, 0.75 to under 1 | 1 | 40 | 8 | 9 |

| Score margin | CT, 0.5 to under 0.75 mm | CT, 0.75 to under 1 mm | CT, 1 to under 1.25 mm | CT, 1.5 to under 2 mm | MR_T1, 0 to under 0.5 mm | MR_T1, 0.5 to under 0.75 mm | MR_T1, 0.75 to under 1 mm |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 to under 0.025 | 1721 | 70 | 16 | 15 | 54 | 50 | 2 |
| 0.025 to under 0.05 | 1745 | 82 | 12 | 23 | 38 | 35 | 0 |
| 0.05 to under 0.1 | 3718 | 139 | 29 | 20 | 110 | 98 | 2 |
| 0.1 to under 0.15 | 4262 | 150 | 43 | 27 | 78 | 54 | 0 |
| 0.15 to under 0.2 | 4918 | 156 | 50 | 31 | 64 | 64 | 0 |
| 0.2 to under 0.25 | 5550 | 328 | 35 | 19 | 85 | 65 | 2 |
| 0.25 to under 0.3 | 4743 | 222 | 13 | 18 | 52 | 45 | 1 |
| 0.3 to under 0.35 | 3828 | 88 | 9 | 7 | 15 | 25 | 1 |
| 0.35 to under 0.4 | 919 | 39 | 3 | 1 | 7 | 5 | 1 |
| 0.4 to under 0.45 | 133 | 0 | 1 | 0 | 0 | 0 | 0 |
| 0.45 or more | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

| Renderings | CT, 0.5 to under 0.75 mm | CT, 0.75 to under 1 mm | CT, 1 to under 1.25 mm | CT, 1.5 to under 2 mm | MR_T1, 0 to under 0.5 mm | MR_T1, 0.5 to under 0.75 mm | MR_T1, 0.75 to under 1 mm |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `black-top-hat` | 17838 | 544 | 70 | 64 | 230 | 163 | 8 |
| `full-range` | 4218 | 353 | 79 | 65 | 10 | 19 | 0 |
| `full-range+white-top-hat` | 108 | 3 | 2 | 1 | 0 | 0 | 0 |
| `white-top-hat` | 9373 | 374 | 60 | 31 | 263 | 259 | 1 |

### What the new counts show

- The 35 CTs whose slices are 1024 pixels or more on their larger side gave 31,537 of the 33,183 CT regions (95.0%): a region in 98.0% of their 6,449 slices, and 4.89 regions for each slice searched. The other 7 CTs, of 512 to under 640 pixels, gave a region in 74.3% of their 1,132 slices, 1.45 regions for each, and the MRs, all of 512 to under 640 pixels, gave a region in 19.9% of theirs, 0.26 for each.
- Inference, not measured: at the same slice size, CT still gives a region in far more slices than MR, so slice size alone does not explain the difference between them, though among the CTs the larger slices give 3.4 times as many regions for each slice. The smaller bin holds only 7 CTs, so that comparison rests on few patients.
- On CT, the bin of 1024 pixels or more and the bin of 0.5 to under 0.75 mm give the same counts in every column, so as far as the counts show they hold the same 35 volumes, and these data cannot separate slice size from spacing. On MR, slices under 0.5 mm and of 0.5 to under 0.75 mm gave a region at nearly the same rate, 20.8% and 18.9%.
- A box threshold raised from 0.5 to 0.6, 0.7, 0.8, or 0.9, every other parameter unchanged, would keep 77.1%, 48.1%, 15.2%, or 0.4% of the CT regions, and 59.2%, 31.9%, 5.7%, or none of the MR regions. On CT the share kept at 0.7 is nearly the same for both slice sizes, 47.6% and 48.1%. These counts give the regions kept only at the edges of the bins, and cannot show what text a raised threshold would miss, since HaN-Seg holds none.
- Almost every region was given by one rendering alone. On CT, the black top-hat gave 55.8% of the regions, the white top-hat 29.6%, the full range 14.2%, and the full range and white top-hat together 0.3%; on MR, the white top-hat gave 54.9%, the black top-hat 42.1%, and the full range 3.0%. For each slice searched, the CTs of 1024 pixels or more gave 4.6 times as many black top-hat regions as the CTs of 512 to under 640, 3.5 times as many white top-hat regions, and 1.5 times as many full-range regions, so most of the increase with slice size is in the top-hat renderings.
- These counts show where the false positives arise, not how to remove them: whether a change to the renderings or to the box threshold would remove them without losing text needs images with known text, which HaN-Seg lacks.

## Measuring missed text as well

This check counts only regions on images without text. The text detector's evaluation library (D-056), in the modules `pymedphys._dicom.deidentify.text_evaluation` and `text_evaluation_*`, measures both sides of the trade-off on the same images: it burns synthetic text of known ink, in fonts, heights, contrasts, styles, orientations, and positions that a plan lists, into synthetic phantoms and, on a runner, into real images without text, and counts the text fully covered beside the regions on frames without text and away from the text. A text is fully covered when the boxes cover every pixel of its core ink, the pixels more than half ink (or all its ink, where no pixel is), and missed when they cover none of that core; whether every pixel with any ink is covered is counted beside, since a covered core does not prove that the fringe left over cannot be read. Its text is drawn in bitmap fonts, its own and Pillow's, and in fonts under the SIL Open Font License, version 1.1 (Source Sans Pro, Source Serif Pro, Lato, Noto Sans, FiraGO, Fira Mono, and Space Mono), which PyMedPhys does not ship: each is fetched from a wheel on the Python Package Index when first drawn, and used only if the wheel and the font have the SHA-256 digests pinned in `text_evaluation_font_files`, which also records each font's copyright and licence. It evaluates a grid of post-processing settings from one pass of the network, and detector variants that only a check can select, never a run. Cases are split by a fixed rule into a tuning part and a held-out part, by the patient where a source knows one, so that one patient's series all fall in the same part, and the bootstrap resamples patients, not cases, so that a patient's series are not treated as independent. Every point of the grid is counted in every stratum, so the criteria can compare each with today's settings, and its summary, labelled `pymedphys-deid-text-detector-evaluation/1`, gives only counts, shares, and their intervals, never a value or a case.

The acceptance criteria, chosen before any tuning run and held in `text_evaluation_criteria`, require, for texts at least 7 frame pixels high, whether drawn in pixels or in millimetres, at least 99% fully covered in every cell of IOD, contrast, and height where the text stands 16 or more times the noise above its background, and at least 95% from 4 to under 16 times; on frames without text, a region on at most 2% of CT, MR, and PET frames, Legacy Converted Enhanced ones included, and 5% of RT Image, CR, DX, and XA frames, in each IOD and in each bin of slice size, with every other image IOD held to the stricter 2% until it is given a group, and at most 0.01% of tissue blacked out in any; an IOD without 300 frames known to be free of text fails; no text of MIDI-B's answer key missed entirely, read from the frames of its tier of the corpus, which each case names; and no single stratum more than 2 percentage points worse than today's settings. Each limit must hold at the unfavourable end of both the Wilson interval and the bootstrap interval over subjects (patients where known, cases otherwise), and a cell of fewer than 400 texts or 300 frames fails, as does a cell of contrast and height that the criteria judge but in which an IOD has no text at all, so that an IOD is never passed on the cells it happens to have, such as one whose colour frames took no injected text. Cells below those contrasts and heights are reported, not judged. A stratum counted at one point and not at today's settings fails the loss rule, rather than being left out of it. The assessment also gives, for each IOD measured, the review that its frames need: only the frames that the detector flags, where the detector is adoptable and no criterion fails for the IOD's own cells, and every frame otherwise. A failure that no single IOD's cells hold, such as a missed answer-key text or a loss in a collection's or modality's stratum, counts against every IOD, and an IOD that the evaluation did not measure needs every frame reviewed. Failing the criteria does not bar the Clean Pixel Data Option from an IOD; it only takes away flagged-only review, as the maintainer decided on 1 November 2026.

It also reads a folder of DICOM files on the machine of someone allowed to use them, such as a department's own RT Images, grouped into cases by patient and named only by a digest, which also serves as the patient for the split and the bootstrap. Their text as read is unknown, unless someone drew boxes around it in a CSV file of annotations, so regions on them are counted apart from false positives, as regions where text is unknown, and text injected into them is counted as on any other image: each injected text is fully covered, partly covered, or missed, with none of its core ink covered, and counted in fixed bins of the share of its core ink covered. The text is drawn into copies of the images held in memory, so nothing is written to that machine's disk. Only the summary leaves that machine, and only if its owner chooses.

Real patients' scans in openly licensed collections of NCI's Imaging Data Commons are read on CI's runners alone, through the module `text_evaluation_idc`. It takes a series from IDC's index only where its collection is one of those vetted, by IDC's `collection_id`, IDC gives it the same licence as was vetted (CC BY 3.0 or 4.0, CC BY-NC 3.0 or 4.0, CC0, or PDDL), it carries a DOI, its modality is one of an image that may hold burned-in text, and, in the fourteen collections taken only for their screen captures, Nuclear Medicine, and ultrasound images, its SOP Class is one of those; where IDC's licence and the vetted one differ, the series is refused, and every refusal is counted by its reason. MIDI-B's source collection is taken only less the series that MIDI-B's answer key marks. Each collection's series are taken in an order fixed by a digest, up to a number and a size, and written as an `s5cmd` manifest; each downloaded series is read as one case, of tier T3, whose patient, for the split and the bootstrap, is a salted digest of its collection and IDC's PatientID, which stays on the runner and is never written to a summary or report, whose frames are taken to hold no text, as these collections were curated for public release: a region on one of them counts as a false positive, so the criteria's limits on regions in frames without text apply to them, and the zones of the summary show where curation may have left text. The frames of those fourteen collections, whose screen captures and ultrasound commonly carry text, are the exception: their text is taken as unknown, so a region found on one as received is counted apart from the false positives, and the text burned into them measures missed text. Beside them, the same workflow reads folders of openly licensed archives, through the module `text_evaluation_archives`: five Zenodo records, of head CT angiography, bone scintigraphy with multi-frame Nuclear Medicine, dental cone-beam CT, and volunteers' Enhanced MR, and the RT Images of the BRAVEHeart breast radiotherapy trial, from the University of Sydney's research data store, whose text is taken as unknown. Each archive is pinned by its size, the SHA-256 of its central directory, and either the MD5 that its Zenodo record gives it or its path in the Sydney store, and read in place over HTTP ranges; whole leaf folders are taken in an order fixed by a digest, up to a number and a size, and, in BRAVEHeart's archives, only the folders that held RT Images when they were pinned; each member is written under a digest of its name, and, from BRAVEHeart, only RT Images are written. These are counted only: the per-case report withholds them. For these series alone, the module `text_evaluation_cases` gives a per-case report beside the counts-only summary, which it leaves as it is: each series by its `collection_id` and Series Instance UID, with its licence and DOI, and for each setting its counts of texts fully covered, partly covered, and missed, and of frames with a region, never a pixel value or a crop. The seven collections taken from The Cancer Imaging Archive under CC BY or CC BY-NC are read from the Imaging Data Commons' copy of them, which held the same image series as TCIA's public listing under the same licences when it was checked on 7 November 2026, and are reported in the same way, by TCIA collection name and Series Instance UID, as the maintainer confirmed on 1 November 2026, and only under one of those licences; so Pediatric-CT-SEG, which the split holds out whole, is held out by that name. Every other case is counted as withheld.

The `Text Detector Evaluation` workflow (`.github/workflows/text-detector-evaluation.yml`), started by hand with the model, its settings, the part of the split, and the budgets as inputs, runs these in one job and, in a second job on a runner of its own, the phantoms: it selects series of IDC's three allow-listed phantom collections alone (`idc-select --phantoms`), CC-Radiomics-Phantom-3, RIDER PHANTOM PET-CT, and VICTRE, whose files carry TCIA's project block naming them, and reports them and the synthetic phantoms in full (`phantom-report`), with the counts-only summary, each case's report, PNG crops of its regions and of the texts not fully covered, and the collections' attribution. The command refuses a selection that holds any other collection, and, unless the whole corpus is evaluated, reports only the cases in the part of the split evaluated, so that no case held out is previewed while the detector is tuned.

To measure Legacy Converted Enhanced CT, MR, and PET images, and the multi-frame path that reads them, on real scans, the evaluation makes its own from the classic CT, MR, and PET series it downloads, in memory on the runner, through the module `text_evaluation_lce`, and measures them again as a stratum of their own (`idc-measure --converted`, through `text_evaluation_converted`). The conversion is built on pydicom and follows PS3.3's rules for these IODs (A.70 to A.72 and C.7.6.16.2.25): attributes that every image shares and that the IOD defines at the top level stay there, as the shipped tables of PS3.3 decide; attributes of a Functional Group Macro move into it, shared where its item is the same for every frame; every other attribute, standard or private, goes into the Unassigned Shared or Per-Frame Converted Attributes Sequence; Frame Anatomy codes Body Part Examined by the code that PS3.16 Annex L gives it, generated with the other standard tables into `anatomic_regions.json`; and each frame's Conversion Source names its image. It never changes a pixel: each frame holds the stored values that a run gives the text detector for its classic image, in the same layout, and an image that the IOD cannot hold unchanged, such as one in MONOCHROME1, with a Modality LUT, or with bits the IOD does not allow, is counted as skipped by a code instead. The tests convert synthetic series of each modality and check that every frame reads back identically, and dciodvfy, in the DICOM validators job, finds no error in the converted instances.

Images of phantoms are not patient data, so for them alone the module `text_evaluation_phantom_report` also gives each case's full results and previews: every frame's boxes for each setting, and PNG crops of each region away from text and of each injected text not fully covered, with an `ATTRIBUTION.md` that credits each collection under its licence. It takes only phantom sources, by their type, and reads only files of an allow-listed phantom collection that name that collection as their archive's project. The allow-listed collections are CC-Radiomics-Phantom-3, RIDER PHANTOM PET-CT, and VICTRE's in-silico breast phantoms, each a collection whose every subject is a phantom. MRI-DIR is not listed: its physical phantom is porcine, which the evaluation does not use, and its other subjects are synthetic images derived from patients, which are only counted. It refuses any frame not of the synthetic tier or the allow-listed phantoms' tier, so that no frame of a patient is drawn, even with synthetic text burned into it.

Before any detection, the module `text_evaluation_inventory` counts what each approved collection's files are, so that sampling can be planned from the counts: by SOP Class, Modality, a fixed list of manufacturers, Rows and Columns, pixel spacing, Number of Frames, Image Type values such as `LOCALIZER`, Burned In Annotation, Recognizable Visual Features, Photometric Interpretation, Bits Stored, and Transfer Syntax, singly and in fixed crosses, with the distinct patients, studies, and series. Each label is a defined term or standard value, a fixed bin, or one of the codes `absent`, `malformed`, and `other`, so the inventory, labelled `pymedphys-deid-dicom-inventory/1`, quotes no value, identifier, or path.

Today's model and each further text detection model that passes vetting are measured through the same harness, each through an adapter in the module `text_evaluation_models` that only the evaluation can select. An adapter pins the model's weights by URL and SHA-256 and refuses any others, records the licences of its code and its weights, each the Apache License 2.0 or one at least as permissive, and says how a rendering becomes the model's input and what its output is. A model whose output is a map of the probability of text, as today's is, takes the grid of post-processing settings from one pass of the network; a model that gives boxes is measured at each of its own post-processing settings, and the network runs again only for a setting that changes its input. The summary's method names the model, its digest, its licences, and its training data as its publishers describe it. Beside today's model, the module adapts RapidOCR's conversions of PaddleOCR's PP-OCRv6 medium and tiny and PP-OCRv5 server and mobile detection models, which RapidOCR runs with today's input and output, and adapts PaddlePaddle's own ONNX files of the same models and of PP-OCRv6 small on Hugging Face, each pinned at a commit, with the normalisation that each one's `inference.yml` gives at that commit. Each of these records how its publishers run it, from that file and PaddleX's defaults: the longer side scaled down to at most 960 pixels and the model's own thresholds. A model so recorded is measured both at those settings (`published_variant` and `published_point`) and at today's, rather than at one chosen beforehand. At its publishers' settings, a rendering is sized exactly as PaddleX sizes it, each side truncated and then rounded to a multiple of 32, and resized by OpenCV's `cv2.resize`, as their pipeline does, with their normalisation's arithmetic; OpenCV is installed only for the evaluation's own CI runs, never as a dependency. Since text strokes one to three pixels wide can cross a threshold under a sub-pixel shift, the module `text_evaluation_parity` measures what the resize alone changes: each frame through the same model at the same points with each resize, counting the regions that only one gives and the texts that only one covers fully. The `Text Detection Model Pins` workflow, started by hand, checks that a GitHub-hosted runner can download each pinned model and that each has its pinned SHA-256, printing only each pin's URL, host, size, and hash result.

Beside the models, the module `text_evaluation_rules` holds a rule that needs no model, measured through the same harness at each of its own settings: it finds connected components of a glyph's size at a frame's least or greatest value, where devices often draw their overlays, joins glyphs that lie close together along a line into one box, and grows each box by a margin. It serves as a comparator, and, joined with a model's boxes so that a region is boxed where either boxes it, as a candidate to combine with a model. Like the adapters, only the evaluation can select it.

Models are measured in two tiers. The adoptable tier is the adapters above, any of which could become the detector. The benchmark-only tier, in the module `text_evaluation_benchmarks`, measures other detectors through the same harness for comparison, such as those with runners of their own in PyTorch, OpenCV, or Tesseract: each may be under any licence that permits its use on CI, read first-hand and recorded with its evidence and its training data, and is still pinned, its runner's packages by version and the SHA-256 of each file and its weights by URL and SHA-256. Their packages are installed on CI alone, into an environment of their own, never among PyMedPhys's dependencies or in its lock file, and their runners run on the runner itself, never as a service, since some frames are real patients'. Their summaries, pages, and assessments are marked benchmark-only, and none can be adopted.

## Run the evaluation on your own images

The evaluation can also be run on DICOM files that you may use, such as your department's RT Images, on your own machine (T6 of D-056). It measures them as the `Text Detector Evaluation` workflow measures its patients' series, and burns synthetic text into copies of their frames held in memory. It renders nothing and writes only counts.

1. Put the files to measure in one folder, under the rules that apply to the data. Subfolders are searched, and files that are not DICOM, or not of a SOP Class read, are counted and left alone.
2. In a development environment of this repository, run:

   ```bash
   uv run -- python -m pymedphys._dicom.deidentify.text_evaluation_local_command <folder> --out <results>
   ```

   `<results>` must not exist and must lie outside `<folder>`. The command reads each file where it lies and writes nothing beside it, creates `<results>` with `summary.json`, labelled `pymedphys-deid-text-detector-evaluation/1`, `summary.md`, and `assessment.json`, and prints the page. On first use it fetches the detector's model and the pinned fonts from the Python Package Index into PyMedPhys's data directory, each used only with its pinned SHA-256.
3. The run succeeds when the command exits with status 0. It refuses a folder that holds no file of the SOP Classes read, annotations that cannot be read or are not of their form, a pinned font that cannot be fetched or checked, and published settings without OpenCV, and reports anything else that stops it, a failure to create or write `<results>` among it, by the exception's type and place in the code alone. pydicom's warnings and log records are redacted in every process that reads the files.
4. Read `summary.md` before you share it. It holds counts, bins, intervals, settings, and the detector's method alone: no UID, name, date, path, or value. Never commit, cache, or attach the files or a value read from them.

| Option | Default | What it does |
| --- | --- | --- |
| `--sop-class <UID>` | RT Image Storage | Reads the files of this SOP Class; repeat it for several. |
| `--all-sop-classes` | off | Reads the files of every SOP Class, such as CT localisers, cone-beam CTs, and screen captures of dose. |
| `--group-by` | `patient` | Groups the files into cases by `patient`, `study`, `series`, or `file`; a case grouped more finely than by patient still keeps its patient whole in the split and the bootstrap. |
| `--known-text` | `unknown` | What is known of the text of frames that no annotation covers. With `unknown`, their regions are counted as regions where text is unknown, apart from false positives; give `none` only where the folder is known to hold no burned-in text, so that each region is a false positive. |
| `--annotations <CSV>` | none | Boxes drawn around the text of some instances, with the columns `sop_instance_uid`, `frame` (from 1, or empty for 1), `top`, `left`, `bottom`, and `right` (pixels from 0, the bottom and right excluded); a row with an empty box marks an instance as holding no text. |
| `--fonts` | `all` | The fonts of the synthetic text: `bitmaps`, the two bitmap fonts that the `Text Detector Evaluation` workflow's patients' job draws in, or `all`, which adds Pillow's bitmap font, crisp and smooth, and the twelve pinned fonts. |
| `--model`, `--settings` | PP-OCRv6 small, `today` | The model and its settings, as for `idc-measure`. `published`, for a model whose publishers give settings, resizes with OpenCV as their pipeline does, and OpenCV is not in the development environment: on Linux x86-64 with Python 3.14, the platform whose wheels that file pins, install the pinned evaluation tools first, as the `Text Detector Evaluation` workflow does, with `uv pip install --require-hashes --no-deps -r .github/text-evaluation/requirements.txt`; on any other platform, those hashes match no wheel, so install the same version, unchecked by hash, with `uv pip install --no-deps opencv-python-headless==5.0.0.93`. Without OpenCV, the command refuses `published`. |
| `--evaluated` | `tuning` | The part of the split measured: `tuning`, `held-out`, or `all`. Measure the held-out part only to confirm a chosen detector. |
| `--workers` | 1 | Processes that measure the cases. |
| `--collection` | `local RT Images` | What the summary calls these files. |

Reading the results:

- The sensitivity counts are of the synthetic text alone, unless you annotated the files: each piece is fully covered, partly covered, or missed, and counted in bins of the share of its core ink covered, by font, height, contrast, style, orientation, position, and content.
- With `--known-text unknown`, a region on a frame as read may be real text, so the counts give where regions lie, by the zones at the frame's corners, edges, and centre, without counting them as false positives.
- A projection's tissue is found from its luminance, so on an RT Image whose open field is brighter than the body, `air`, `tissue`, and `edge` positions and the tissue blacked out may refer to the open field rather than the body.
