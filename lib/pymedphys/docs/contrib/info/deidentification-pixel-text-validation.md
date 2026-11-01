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
- The counts are evidence, not a verdict: whether the option's false positives on CT and MR are acceptable is for the maintainer to decide, and the validation table of the design doc records that decision as not yet made.

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
