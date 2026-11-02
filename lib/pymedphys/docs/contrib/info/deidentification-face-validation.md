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
| What the finder saw | By each case's outcome: the finder's voxel size and the balls of soft tissue that it considered and kept as possible globes; at each eye, the nearest ball considered and why it was or was not kept, the nearest kept ball, and the depth of soft tissue there; the tests of the pair of kept balls at the eyes, including the head's fills behind and in front and the cranium's test; the other pairs that passed the tests of a pair and where they lie; whether each ball of the pair at the eyes, and of each other pair that passes the other tests, lies just under the skin, with air in front of it; and the tissue about each kept ball. |
| Settings | The engine's settings that the counts depend on. |

Each measure is counted in fixed bins, and no case is named, so the summary gives no value of any case.

## Reading the results

- A globe-centre error of more than a few millimetres warrants checking the finder and the reference masks. A run given those eyes as ROIs holds the series for `eyes-disagree-with-rois` when an eye point lies more than 25 mm from both found globe centres.
- A height above the inferior limit below 0 means that part of an eye lies below the block's axial plane, which the block keeps.
- The front of each eye, `Eye_AR` and `Eye_AL`, should be written as air in every defaced series, and the back, `Eye_PR` and `Eye_PL`, only in part, since the block keeps what lies behind its plane 5 mm behind the globes' centres. Organs behind that plane, or below the block, such as the brainstem, the parotid glands, and the lips, should have none written.
- For a series not defaced, what the finder saw names the test that refused it. `no-eyes` with no kept ball at an eye points to that eye's ball: not considered, where the depth of soft tissue there is outside the window in which balls are looked for, or not kept, where its surround test's shares fall short. With a kept ball at each eye, it points to the pair's tests: side by side, bone lateral or superior to a ball, or air just in front of each. `ambiguous-eyes` comes with other pairs, whose places show what else the finder took for globes. `head-not-behind-eyes` means the one pair that passed failed the head test, and that pair need not be the eyes': the head's fills describe the eyes' pair only where each eye has its own kept ball within 5 mm, and otherwise the nearest kept ball at each eye and the other pairs' places show which pair the finder took. The other pairs that pass every test but the one of air in front show what that test refuses, and the depths in front of the eyes' balls how near its 20 mm they come.
- The margin, the 30 mm above the higher globe's centre from which the brain is kept, and the 25 mm for an eye ROI are placeholders (D-050). The counts bear on the margin and the 25 mm, without validating either; changing a setting is a decision of its own.

## Limits

- Nothing here renders a surface or tests whether a defaced face can be recognised. The check on the Visible Human's CT renders each cadaver's head (below).
- HaN-Seg's masks include no targets, so the hold for a target in the block is not tested.
- They include no brain either, so neither the brain that defacing keeps within the cranial cavity nor the 30 mm floor below which it keeps none is tested; the brainstem, chiasm, and pituitary are no reference for them.
- Each CT volume is written as the CT Image instances of one series in memory, so the check tests the finder and the defacer, not the reading of a scanner's DICOM files, which the engine's own tests cover.
- The masks are the reference: an error in a mask counts against the finder.
- The finder's settings for globes that soft tissue borders on every half, and for the air in front of each globe, were set with these counts in view (D-050), so for those settings HaN-Seg is tuning data, not an independent test.

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

## Check on the Visible Human's CT

The `Face Block Check on Visible Human` workflow checks the finder and the defacer on the CT of the U.S. National Library of Medicine's Visible Human Project, two cadavers scanned from head to toe, as NCI Imaging Data Commons converted them to DICOM (collection `nlm_visible_human_project`, IDC data release v19, [doi:10.5281/zenodo.16114440](https://doi.org/10.5281/zenodo.16114440)) (D-057). Courtesy of the U.S. National Library of Medicine. The data are used under [NLM's Terms and Conditions](https://www.nlm.nih.gov/databases/download/terms_and_conditions.html); NLM has not endorsed PyMedPhys or these results, which may not reflect the most current or accurate data available from NLM.

The scans are held-out evidence: the finder's settings were not set from them, and none is to be changed from what they show. They are real people, so the maintainer allowed these two cadavers alone, with renders of both their faces. Never commit, cache, or attach the series themselves.

1. In the repository's **Actions** tab, choose **Face Block Check on Visible Human**, then **Run workflow**, and pick the branch whose engine to check.
2. The job downloads the collection's 11 CT series, about 2.1 GB, from IDC's public bucket with `.github/scripts/fetch_idc_series.py`, and runs `python -m pymedphys._dicom.deidentify.face_validation_command visible-human <directory> --out <results>`, which refuses the set unless each series' file count and digest are those that `face_validation_vhp.SERIES` pins.
3. The job's summary shows `face-validation-vhp.md`, and its artefact `face-validation-vhp-results`, kept for 90 days, holds it with `face-validation-vhp.json`, labelled `pymedphys-deid-face-validation-vhp/1`, `commit.txt`, and `renders/`: for each of the three heads, the skin surface as received and as each block would deface it, and slices through each globe, with `NOTICE.txt`.

To run it on your own machine, download the series with `python .github/scripts/fetch_idc_series.py --out <directory> <uuid> ...`, taking each UUID from `SERIES`, and run the same command in a development environment of this repository.

| Part | What it shows |
| --- | --- |
| Outcomes | For each series: a run's outcome, as `find_face_blocks` gives it for the series' files; each stack's, where the slices that share a geometry are given as a series of their own; and the outcome on the slices within the head reach resampled onto one grid. IDC keeps each scan as one series whose field of view changes along the body, so a run refuses each series of several stacks as `not-one-stack`. |
| Stacks | For each series that holds a head, each stack's slices, pixel spacing, extent along z, and slice gaps. |
| What the finder saw | For each way: the voxel, the balls kept, the pairs passing, each found globe's distance from the reference centre on its side, and the ball nearest each reference centre, with its radius, surround test's shares, and whether it was kept. |
| Tissue about the reference globes | The median Hounsfield units, and the share in the finder's soft tissue window, within 6 mm of each reference centre and from 13.2 mm to 18 mm, where a living globe's orbital fat lies. |
| Defacing | For each block found and the reference block placed from the reference centres: the slices and volume written as air, the tissue written and the tissue in the block kept, any pixel written outside the block, each reference globe's share written and whether its anterior pole is, and how a found block lies against the reference block. |

The reference centres were placed by hand on the native slices, within 3 mm, before any measure against them was taken; the renders of each head's globes show them, so that a reader can judge them. The scans are post-mortem, from an early 1990s scanner, and one of the male's was made frozen, when water reads as ice, below the finder's soft tissue window, so they bear on the finder's tests of real anatomy, not on its yield on clinical CT.
