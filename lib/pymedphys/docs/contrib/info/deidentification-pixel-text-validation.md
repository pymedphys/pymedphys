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

## Measuring missed text as well

This check counts only regions on images without text. The text detector's evaluation library (D-056), in the modules `pymedphys._dicom.deidentify.text_evaluation` and `text_evaluation_*`, measures both sides of the trade-off on the same images: it burns synthetic text of known ink, in fonts, heights, contrasts, styles, orientations, and positions that a plan lists, into synthetic phantoms and, on a runner, into real images without text, and counts the text fully covered beside the regions on frames without text and away from the text. It evaluates a grid of post-processing settings from one pass of the network, and detector variants that only a check can select, never a run. Cases are split by a fixed rule into a tuning part and a held-out part, and its summary, labelled `pymedphys-deid-text-detector-evaluation/1`, gives only counts, shares, and their intervals, never a value or a case.
