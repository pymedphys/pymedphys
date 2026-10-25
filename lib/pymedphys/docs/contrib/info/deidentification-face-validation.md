---
myst:
  heading_anchors: 2
---

# Check the face block against HaN-Seg

Under the Clean Recognizable Visual Features Option, the de-identification engine finds a face block in each head CT series and writes air into it (D-046 and D-050 in the [de-identification design](deidentification-design.md)). The `Face Block Check` workflow checks the block that the engine finds, and the air that it writes, against the eye and organ masks of the HaN-Seg data set's 42 head and neck planning CTs, and publishes only counts (D-054).

## The data set

HaN-Seg version 1.0 is on Zenodo as record 7442914 ([doi:10.5281/zenodo.7442914](https://doi.org/10.5281/zenodo.7442914)), one ZIP file of 4,938,848,306 bytes. It holds the CT and T1-weighted MR images of 42 head and neck patients imaged for radiotherapy planning, with binary masks of 30 organs at risk on each CT, among them each eye's anterior and posterior parts (`Eye_AR`, `Eye_PR`, `Eye_AL`, and `Eye_PL`), as NRRD files. Its Zenodo record and the licence in the ZIP file give CC BY-NC-ND 4.0, and its README CC BY-ND 4.0; the project follows the stricter. Cite it as:

> G. Podobnik, P. Strojan, P. Peterlin, B. Ibragimov, T. Vrtovec, "HaN-Seg: The head and neck organ-at-risk CT & MR segmentation dataset", Medical Physics, 2023, [doi:10.1002/mp.16197](https://doi.org/10.1002/mp.16197).

Its images are of real patients, published de-identified, so the project treats them as real patient data. As the maintainer chose on 24 October 2026, only the workflow's runner downloads the data set, and only counts, codes, digests, versions, and the engine's settings leave it. Never commit, cache, or attach any part of the data set, or a value read from it.

## Run the check

1. In the repository's **Actions** tab, choose **Face Block Check**, then **Run workflow**, and pick the branch whose engine to check.
2. The job downloads `HaN-Seg.zip` from Zenodo, checks its size and MD5 against the record's, and runs the check, which reads the ZIP file without extracting it.
3. The job's summary shows the results, and its artefact `face-validation-results`, kept for 90 days, holds `face-validation.json`, `face-validation.md`, and `commit.txt`, the commit checked.

The job runs `python -m pymedphys._dicom.deidentify.face_validation_command hanseg <HaN-Seg.zip> --out <directory>` through `.github/scripts/run_redacted.py`, which reports a crash by its type and code locations alone, and keeps the command's standard output and standard error, where libraries log, in files on the runner. The command takes the ZIP file unchanged, and writes both result files into a directory that it creates.

## What the counts show

| Section | What it counts |
| --- | --- |
| Cases | The cases in the ZIP file, those measured, those not measured by why, such as `ct-missing` or `ct-not-read/data-length`, and crashes by the exception's type and place in the code. |
| CT volumes | How each CT was stored, whether at least 1% of its voxels are at -900 HU or below, as a head CT's are where its values are in Hounsfield units, and its spacings. |
| Masks | How each mask was stored, those not read by why, such as `several-segments`, and those with voxels outside the CT, which are left out. |
| Series | The series defaced, and those not defaced, by the reason that a release report gives, such as `no-eyes`. |
| Defaced series against the reference eyes | Whether every eye voxel lies within 25 mm of the nearer globe found, as a run requires of an eye ROI (`agree`), or not (`eyes-disagree-with-rois`); the distance from each globe found to its eye's centroid; the series whose globes were taken for the other side's; the distance from the farthest eye voxel to the nearer globe found; and the height of the eyes' lowest voxel above the block's inferior limit. |
| Reference eyes | The eyes' own diameters, as those of spheres of their volumes, their separation across the axial plane, and the turn of the line between them, whatever the finder found. |
| Organs written as air | For each organ, the defaced series in which none, under 10%, and so on up to all of its voxels were written as air. |
| Settings | The engine's settings that the counts depend on. |

Each measure is counted in fixed bins, and no case is named, so the summary gives no value of any case.

## Reading the results

- A globe-centre error of more than a few millimetres warrants checking the finder and the reference masks. A run given those eyes as ROIs holds the series for `eyes-disagree-with-rois` when an eye point lies more than 25 mm from both found globe centres.
- A height above the inferior limit below 0 means that part of an eye lies below the block's axial plane, which the block keeps.
- The front of each eye, `Eye_AR` and `Eye_AL`, should be written as air in every defaced series, and the back, `Eye_PR` and `Eye_PL`, only in part, since the block keeps what lies behind its plane 5 mm behind the globes' centres. Organs behind that plane, or below the block, such as the brainstem, the parotid glands, and the lips, should have none written.
- The margin, the 30 mm above the higher globe's centre from which the brain is kept, and the 25 mm for an eye ROI are placeholders (D-050). The counts bear on the margin and the 25 mm, without validating either; changing a setting is a decision of its own.

## Limits

- Nothing here renders a surface or tests whether a defaced face can be recognised.
- HaN-Seg's masks include no targets, so the hold for a target in the block is not tested.
- They include no brain either, so neither the brain that defacing keeps within the cranial cavity nor the 30 mm floor below which it keeps none is tested; the brainstem, chiasm, and pituitary are no reference for them.
- Each CT volume is written as the CT Image instances of one series in memory, so the check tests the finder and the defacer, not the reading of a scanner's DICOM files, which the engine's own tests cover.
- The masks are the reference: an error in a mask counts against the finder.

## Check DICOM exports on your own machine

The same engine code can be checked on DICOM files that you may process, such as your planning system's exports of head and neck cases, on your own machine (D-054). The check renders nothing and writes only counts. Unlike HaN-Seg, planning exports hold targets, eye ROIs as planners draw and name them, RT Doses, and RT Plans, so it also checks the hold for a target in the block, the hold for an eye ROI away from the globes found, RT Dose defacing, and contour cutting.

1. Export the CT Image series, RT Structure Sets, RT Plans, and RT Doses to check into one directory, under the rules that apply to the data. Subdirectories are searched; links and files named `DICOMDIR` are skipped, and files that are not DICOM are counted and left alone.
2. In a development environment of this repository, run:

   ```bash
   uv run -- python -m pymedphys._dicom.deidentify.face_validation_command dicom <exports> --out <results>
   ```

   `<results>` must not exist. The command reads each file where it lies and writes nothing beside it, creates `<results>` with `face-validation.json`, labelled `pymedphys-deid-face-validation-dicom/1`, and `face-validation.md`, and prints the page.
3. The check succeeds when the command exits with status 0. It refuses a directory that cannot be listed or that holds no CT Image series, and reports anything else that stops it by the exception's type and place in the code alone.
4. Read `face-validation.md` before you share it. It holds counts, codes, bin edges, versions, and settings alone: no UID, name, date, path, ROI name, or value. Never commit, cache, or attach the exports or a value read from them.

| Section | What it counts |
| --- | --- |
| Files | The files found, read, not read, and refused, by why, and the files read by IOD. |
| CT series | How each series' first slice is stored, whether at least 1% of its voxels are at -900 HU or below (not measured for compressed slices), and its spacings. |
| Outcomes | The series defaced, those not defaced by the reason that a release report gives, such as `target-in-block` or `eyes-disagree-with-rois`, and, by outcome, the series whose searched structure sets hold an eye ROI. |
| Eye ROIs against the globes found | For each series with a block, defaced or held: whether its eye ROIs agree with the globes found; for each eye ROI, the side that its name gives, the distance from the globe found to the centroid of its contours, weighted by their areas (for a name that gives no side, from each globe to its own contours), whether it is nearer the other side's globe, the distance from its farthest point to the nearer globe, which a run compares with 25 mm, and the height of its lowest point above the block's inferior limit. |
| Targets | For each series with a block, its targets (PTV, CTV, and GTV) by whether they hold the series and why, and the clearance from the block of each that does not. |
| RT Doses in a defaced frame | Each RT Dose with pixel data set to zero in the block or held, by why, and the greatest dose that a run would set to zero as a fraction of the grid's greatest, which a run compares with 5%; each grid goes through the run's own cleaner, so one whose Pixel Data a run refuses is counted as held; a compressed RT Dose is not measured. |
| RT Structure Sets in a defaced frame | Each structure set cut, unchanged, or held, and the ROIs that a run would cut, by RT ROI Interpreted Type. |
| RT Plans | The RT Plans, and those in a defaced series' frame. |
| Settings | The engine's settings that the counts depend on. |

Reading the results:

- A run holds a series for `eyes-disagree-with-rois` when a point of an eye ROI lies more than 25 mm from both globes found, or cannot be placed: the finder took something else for a globe, or the eye ROI is not where the image shows the eye. A globe error of more than a few millimetres warrants checking the finder and the eye ROI, but does not itself hold the series.
- A refused series, such as `no-eyes`, that holds an eye ROI is a series that a planner could find the eyes in and the finder could not: a cost in yield, since a run leaves it undefaced for the face review.
- Targets that reach the block, and their clearances, show how often a run would hold a head and neck series for its targets.
- Dose fractions near 5%, and RT Doses held as `dose-in-face-block`, bear on the dose fraction, a placeholder (D-051), as eye ROIs' reach does on the 25 mm (D-050), without validating either; changing a setting is a decision of its own.
- Nothing here measures the brain that defacing keeps or the 30 mm floor below which it keeps none. The dose set to zero and the contours cut are those in the block less the brain kept, so they depend on the floor without testing it.
- Eye ROIs are those whose names a run reads as an eye's, such as `Eye_L` or `Globe_R`, not lenses; an eye named otherwise is not checked, as in a run.
