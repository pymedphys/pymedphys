# Summaries of relevant DVH literature

Combined from the 21 markdown summaries in this project source set. Ordered chronologically by publication year.

## Contents
- [Drzymala (1991) - Dose-volume histograms](#drzymala-1991-dose-volume-histograms)
- [Kooy (1993) - Dose-volume histogram computations for small intracranial volumes](#kooy-1993-dose-volume-histogram-computations-for-small-intracranial-volumes)
- [Fraass (1998) - American Association of Physicists in Medicine Radiation Therapy Committee Task Group 53: Quality assurance for clinical radiotherapy treatment planning](#fraass-1998-american-association-of-physicists-in-medicine-radiation-therapy-committee-task-group-53-quality-assurance-for-clinical-radiotherapy-treatment-planning)
- [Panitsa (1998) - Quality control of dose volume histogram computation characteristics of 3D treatment planning systems](#panitsa-1998-quality-control-of-dose-volume-histogram-computation-characteristics-of-3d-treatment-planning-systems)
- [Corbett (2002) - The effect of voxel size on the accuracy of dose-volume histograms of prostate 125I seed implants](#corbett-2002-the-effect-of-voxel-size-on-the-accuracy-of-dose-volume-histograms-of-prostate-125i-seed-implants)
- [IAEA (2004) - Commissioning and quality assurance of computerized planning systems for radiation treatment of cancer](#iaea-2004-commissioning-and-quality-assurance-of-computerized-planning-systems-for-radiation-treatment-of-cancer)
- [Chung (2006) - Dose variations with varying calculation grid size in head and neck IMRT](#chung-2006-dose-variations-with-varying-calculation-grid-size-in-head-and-neck-imrt)
- [Kirisits (2007) - Accuracy of volume and DVH parameters determined with different brachytherapy treatment planning systems](#kirisits-2007-accuracy-of-volume-and-dvh-parameters-determined-with-different-brachytherapy-treatment-planning-systems)
- [Henríquez (2008) - A novel method for the evaluation of uncertainty in dose-volume histogram computation](#henrquez-2008-a-novel-method-for-the-evaluation-of-uncertainty-in-dosevolume-histogram-computation)
- [Ebert (2010) - Comparison of DVH data from multiple radiotherapy treatment planning systems](#ebert-2010-comparison-of-dvh-data-from-multiple-radiotherapy-treatment-planning-systems)
- [Gossman (2010) - Dose-volume histogram quality assurance for linac-based treatment planning systems](#gossman-2010-dose-volume-histogram-quality-assurance-for-linac-based-treatment-planning-systems)
- [Grimm (2011) - Dose tolerance limits and dose volume histogram evaluation for stereotactic body radiotherapy](#grimm-2011-dose-tolerance-limits-and-dose-volume-histogram-evaluation-for-stereotactic-body-radiotherapy)
- [Zhang (2011) - Motion-weighted target volume and dose-volume histogram: A practical approximation of four-dimensional planning and evaluation](#zhang-2011-motion-weighted-target-volume-and-dose-volume-histogram-a-practical-approximation-of-four-dimensional-planning-and-evaluation)
- [Rosewall (2014) - The effect of dose grid resolution on dose volume histograms for slender organs at risk during pelvic intensity-modulated radiotherapy](#rosewall-2014-the-effect-of-dose-grid-resolution-on-dose-volume-histograms-for-slender-organs-at-risk-during-pelvic-intensity-modulated-radiotherapy)
- [Nelms (2015) - Methods, software and datasets to verify DVH calculations against analytical values: twenty years late(r)](#nelms-2015-methods-software-and-datasets-to-verify-dvh-calculations-against-analytical-values-twenty-years-later)
- [Sunderland (2016) - Effects of voxelization on dose volume histogram accuracy](#sunderland-2016-effects-of-voxelization-on-dose-volume-histogram-accuracy)
- [Snyder (2017) - Investigating the dosimetric effects of grid size on dose calculation accuracy using volumetric modulated arc therapy in spine stereotactic radiosurgery](#snyder-2017-investigating-the-dosimetric-effects-of-grid-size-on-dose-calculation-accuracy-using-volumetric-modulated-arc-therapy-in-spine-stereotactic-radiosurgery)
- [Stanley (2021) - Accuracy of dose-volume metric calculation for small-volume radiosurgery targets](#stanley-2021-accuracy-of-dose-volume-metric-calculation-for-small-volume-radiosurgery-targets)
- [Pepin (2022) - Assessment of dose-volume histogram precision for five clinical systems](#pepin-2022-assessment-of-dose-volume-histogram-precision-for-five-clinical-systems)
- [Penoncello (2024) - Multicenter multivendor evaluation of dose volume histogram creation consistencies for 8 commercial radiation therapy dosimetric systems](#penoncello-2024-multicenter-multivendor-evaluation-of-dose-volume-histogram-creation-consistencies-for-8-commercial-radiation-therapy-dosimetric-systems)
- [Grammatikou (2025) - Validation of dose-volume calculation accuracy for intracranial stereotactic radiosurgery with volumetric-modulated arc therapy using analytical and clinical treatment plans](#grammatikou-2025-validation-of-dose-volume-calculation-accuracy-for-intracranial-stereotactic-radiosurgery-with-volumetric-modulated-arc-therapy-using-analytical-and-clinical-treatment-plans)
- [Walker (2025) - Clinical impact of DVH uncertainties](#walker-2025-clinical-impact-of-dvh-uncertainties)


---

## About this collection

This document is a structured databank of detailed technical summaries for 21 papers relevant to dose-volume histogram (DVH) computation, accuracy, and validation in radiotherapy. The summaries were produced to support the design, implementation, and validation of a reference-quality open-source DVH calculation engine intended for the international medical physics community.

Each summary was generated using LLM-assisted summarisation from the full text of each paper, following a structured prompt designed for maximum technical fidelity and engineering utility. Summaries were reviewed against the source papers for accuracy and completeness. All summaries follow a consistent 10-section template: executive summary, bibliographic record, paper type and scope, background and motivation, detailed methods, quantitative results, authors' conclusions, implications for reference DVH calculator design, connections to other literature, data extraction tables, and critical appraisal.

Key conventions used throughout: Australian English spelling; doses in Gy (noting where source papers used cGy); volumes in cc; percentage differences always specify the reference denominator; missing methodological details are flagged as [DETAIL NOT REPORTED]; inferences drawn only from abstracts are flagged as [INFERRED FROM ABSTRACT ONLY]; connection-section citations are limited to papers the summariser is confident exist.

---

<!-- Source: SUMMARY - Drzymala 1991 - Dose-volume histograms.md -->

## Drzymala (1991) - Dose-volume histograms

### Executive summary

This 1991 paper by Drzymala and colleagues is a foundational methodological article for dose-volume histogram (DVH) computation rather than a conventional clinical outcomes study. Its major contribution is not simply endorsing the use of DVHs, but documenting the computational choices that determine whether a DVH is trustworthy: how anatomy is rasterised from contours, how dose is interpolated from a separate grid, how Boolean structure combinations are handled, how bin widths affect interpretability, and how apparently small numerical differences can become biologically important when propagated into TCP/NTCP models.

For a reference-quality DVH calculator, the paper supports several enduring design principles. First, structure discretisation should be decoupled from dose-grid resolution. Second, contour rasterisation must explicitly handle tangencies, reversals, and overlap logic rather than relying on naïve crossing counts. Third, cumulative DVHs need finer binning than the coarse defaults historically used in some systems; the paper recommends 0.5 Gy as a useful cumulative bin width and describes 2 Gy as crude. Fourth, validation must include synthetic phantoms with known truth, especially shapes that expose boundary-classification errors such as nested cubes, notched geometries, and cylinders. Fifth, the low-volume tail of a DVH must be preserved accurately because it can reverse biological plan ranking even when conventional cumulative plots look similar.

The paper is highly relevant to modern independent DVH benchmarking because it identifies failure modes that remain current: binary voxel inclusion, incomplete dose-grid coverage, loss of spatial information, and ambiguity introduced by contouring uncertainty. Its quantitative guidance is historically important but should be interpreted cautiously because several thresholds are based on limited examples rather than systematic validation. As a databank entry for a gold-standard open DVH engine, this paper is best read as a foundational requirements document: it defines the minimum algorithmic transparency and validation philosophy that a modern implementation should exceed.

### 1. Bibliographic record

- **Authors:** R. E. Drzymala, R. Mohan, L. Brewster, J. Chu, M. Goitein, W. Harms, M. Urie.
- **Title:** *Dose-volume histograms*.
- **Journal:** *International Journal of Radiation Oncology, Biology, Physics*.
- **Year:** 1991.
- **DOI:** [10.1016/0360-3016(91)90168-4](https://doi.org/10.1016/0360-3016(91)90168-4).
- **Open access:** No.

### 2. Paper type and scope

Type: **Original research**.
Domain tags: **D1 Computation | D3 Metric innovation**.
Scope statement: This is a foundational multi-institution methodological paper from four NCI-supported 3D planning centres. It explains how cumulative DVHs were being computed from CT-defined anatomy and 3D dose matrices, gives practical recommendations on spatial and dose sampling, discusses structure-combination logic and verification phantoms, and explicitly warns about failure modes that remain highly relevant to reference-quality DVH computation.

### 3. Background and motivation

The paper addresses a very early but important problem in 3D radiotherapy planning: dose calculation systems were beginning to generate far more information than clinicians could easily interpret from stacks of axial, sagittal, coronal, or oblique isodose displays alone. The authors argue that condensing volumetric dose information into a histogram of dose versus irradiated volume offered an efficient summary of target dose uniformity, cold regions, and normal-tissue hot spots. They also note that what most clinics were calling a “DVH” was, strictly speaking, a cumulative dose-volume frequency distribution rather than a differential histogram, and that cumulative plots were generally more useful for plan review.

What was missing in the literature was not the concept of DVHs, but a transparent description of how to compute them accurately. The paper states that DVHs had already been used in the pancreas and prostate literature, and that they were being linked to tumour control probability (TCP) and normal tissue complication probability (NTCP), yet details of contour handling, voxelisation, binning, interpolation, and structure logic were not being described. That omission mattered because small changes in DVH shape could materially change TCP/NTCP calculations. The paper therefore positions itself as a practical computational-methods article: not a clinical outcomes study, but a first attempt to document how DVHs were actually being generated across four institutions and what technical caveats users needed to understand before trusting them.

### 4. Methods: detailed technical summary

This was a **multi-institution methodological and experience report** rather than a prospective clinical study. Four institutions participating in an NCI-sponsored 3D photon treatment-planning effort independently developed DVH code. The paper states that the usefulness of DVHs had been evaluated across **eight anatomic sites**, but site-specific cohorts, numbers of patients, numbers of plans, and plan techniques are **[DETAIL NOT REPORTED]** in this article; those details were said to be described elsewhere. Three of the four institutions later participated in an explicit intercomparison using a common phantom. Statistical tests were **not applicable**: no p-values, confidence intervals, or formal hypothesis tests were reported.

The anatomical basis was a contiguous CT series represented as a 3D grid of cuboid volume elements. The paper emphasises that the CT image matrix, the geometric volume grid used for structure/volume estimation, and the 3D dose grid need not coincide. In the authors’ convention, each CT slice lies at a constant `Z`, each in-slice element is referenced by the `X,Y` coordinates of its centre, and the patient volume can be divided into “slabs” associated with CT sections. They explicitly define voxel volume as `Δx × Δy × slab thickness`, with slab thickness set from neighbouring slice spacing; the article states that the nth slab thickness equals the distance between the `(n−1)`th and `(n+1)`th slices, while the first and last slabs use nearest-neighbour spacing. This slice-thickness convention is historically interesting and should be read as the authors’ implementation convention rather than a universal standard.

A key methodological point is the **decoupling of structure-resolution from dose-resolution**. Because dose calculations were slow, the authors recommend permitting a relatively coarse dose grid while using a finer geometric grid for volume estimation. Dose at each geometric voxel was estimated by **tri-linear interpolation** from the dose matrix to the voxel centre. If a voxel lay inside a structure but outside the dose-calculation window, its dose was set to zero. The authors explicitly warn that this can be problematic if the dose matrix does not cover all irradiated anatomy. Dose algorithm, beam model, heterogeneity correction, energy, calculation engine, and software version are all **[DETAIL NOT REPORTED]**.

For **volume resolution**, the paper reports experimental manipulation of voxel size and concludes that small structures are most sensitive to coarse sampling. In a spinal cord example in a relatively homogeneous dose region, they observed little DVH change when voxel dimensions were below **0.25 times** the structure dimensions. At that resolution, the estimated volume was on average within **5% of the true volume** (reference denominator: true volume), though theory predicted errors up to **16% of true volume** in extreme cases. They attribute this mainly to contour-boundary detection errors from regular rectangular voxels. The paper also notes that long, narrow appendages can require finer sampling than gross organ dimensions would suggest, and mentions dynamic adjustment of voxel size independently in `X`, `Y`, and `Z`, including possible use of **quadtrees/octrees**.

For **dose resolution**, the paper frames the problem in terms of two criteria: desired dose accuracy and maximum acceptable isodose-position error. Linear interpolation is said to be a good approximation in both the steepest and the most slowly varying regions of the beam profile, with the largest interpolation error in intermediate regions where the second derivative is large. Their practical rule-of-thumb is that dose-grid spacing should be about **2.5 ×** the allowable isodose-position error `δ`; for `δ ≥ 2 mm`, a **5 mm** grid was said to achieve either about **2% dose accuracy** or **2 mm isodose positional accuracy**, though **not necessarily both simultaneously**. The provenance of this result includes private communication, so it should be treated as expert guidance rather than a rigorously validated universal law.

Structure membership was determined using a **scanline / odd-even crossing** approach in each `X-Y` plane. If the volume grid planes were not coincident with CT slices, the contour at that plane was interpolated between adjacent sections, but the interpolation formula itself is **[DETAIL NOT REPORTED]**. For each row, the algorithm selected and sorted only true contour crossings (“transections”) and classified voxels as inside the structure when their **centres** lay between odd and even crossings. This is important: no explicit **fractional partial-volume weighting** is described; the implementation appears to be **binary voxel-centre inclusion**. The paper devotes substantial attention to tricky edge cases, including invaginations/evaginations that touch a scanline and reverse direction, and contour segments that run collinear with the scanline. These are not to be naively counted as boundary crossings.

For histogram construction, dose range was divided into equispaced bins. **Differential DVHs** retained per-bin volume directly; **cumulative DVHs** summed each bin with all higher-dose bins. The authors preferred cumulative plots for most planning tasks. They recommend **0.5 Gy** bins (about **1% of prescription dose**) for cumulative DVHs and call **2 Gy** bins crude. By contrast, one group using differential DVHs extensively found **2-5 Gy** bins useful for breast-plan evaluation. Supersampling is **[DETAIL NOT REPORTED]**. For structure combinations, the paper describes logical operations (`and`, `or`, `not`, `inside`, `outside`) and a hierarchy-based 3D **tag matrix** that resolves overlaps by priority, enabling union, subtraction, and disjoint addition of structures.

Ground-truth / verification relied on synthetic phantoms of known geometry and assigned dose. The recommended tests were: nested concentric cubes with different uniform doses in each rind, a cube with a rectangular notch sensitive to boundary-crossing logic, and a cylinder to test non-cuboid geometry. The authors also note contouring uncertainty itself as an upstream limitation, especially when contours are drawn with input devices such as a mouse, joystick, trackball, or digitiser pad. Programming languages, operating systems, and named software tools are **[DETAIL NOT REPORTED]**.

### 5. Key results: quantitative

The paper’s most important “results” are computational rather than clinical. In the explicit **three-institution phantom intercomparison**, each group used the same concentric-cube phantom with known contours and dose assignments. The resulting cumulative DVHs were reported as essentially identical to within **±1 bin**, with residual differences attributed to sampling resolution and boundary handling. Because the paper does not state the common bin width used in that comparison, the practical magnitude of **±1 bin** in Gy is **[DETAIL NOT REPORTED]**. The authors also state that the clinical importance of such small DVH differences was hard to assess directly, but potentially significant once propagated into TCP/NTCP models.

The explicit resolution findings are still notable. In the spinal cord example, once voxel dimensions fell below **25% of structure dimensions**, the authors saw little additional change in the DVH in a fairly homogeneous dose region. Even then, mean volume-estimation error remained about **5% of true volume**, and theory predicted worst-case errors up to **16% of true volume** for unfavourable alignments. For dose interpolation, they propose the rule that grid spacing should be about **2.5×** the acceptable isodose-position error, leading to the pragmatic statement that a **5 mm** dose grid can achieve either about **2% point-dose accuracy** or **2 mm isodose-position accuracy**, though not necessarily both together. For binning, they explicitly recommend **0.5 Gy** for cumulative DVHs and describe **2 Gy** as crude; for differential DVHs in breast planning, one group found **2-5 Gy** advantageous.

A particularly important result is the **rank reversal example in Figure 6** on page 6. The legend reports TCP values of **0.90**, **0.86**, **0.80**, and **0.76** for institutions **C**, **B**, **D**, and **A**, respectively. Yet by ordinary visual inspection of the standard cumulative DVHs in panel A, the authors say one would likely rank the plans **C > A > B > D** on the basis of apparent target coverage. The TCP ranking, however, is **C > B > D > A**. When the same curves are replotted with an expanded/nonlinear volume axis in panel B, the low-volume low-dose tail becomes more visible and correlates better with the TCP ordering. This is a foundational observation: a **very small percentage of total volume** in the low-dose tail can dominate a biological score and even reverse plan ranking.

The graphical examples on page 5 also codify interpretive archetypes: a near-step function indicates a structure receiving a fairly uniform high dose; a roughly **45°** cumulative slope indicates a broad heterogeneous distribution; and a concave curve indicates a structure receiving mostly low dose with one or more small hotter regions. The authors further report that superimposed cumulative DVHs were substantially more informative than separate plots, and remark that the one group not overlaying curves found DVHs less helpful. Differential histograms were judged to contain finer structure, but became visually confusing when multiple plans were overlaid. No inferential statistics, confidence intervals, or null-hypothesis tests were reported anywhere in the paper.

### 6. Authors' conclusions

The authors conclude that cumulative DVHs are a valuable way to summarise the large amount of dose information produced by 3D planning and that their greatest practical value is **rapid screening and comparison of rival plans**. However, they are equally clear that DVHs should **not** be the sole criterion for plan evaluation because they discard spatial information, do not convey field-arrangement complexity, and do not address reproducibility of patient set-up. They further conclude that accurate implementation matters: seemingly small computational differences in DVH shape can materially affect downstream TCP and NTCP estimates. Finally, they argue that methods reducing a DVH to a single number should be used cautiously, because the Figure 6 example shows that biologically relevant distinctions may reside in very small low-dose tails that are visually inconspicuous on conventional cumulative plots. These conclusions are generally well supported by the computational examples presented, although the paper extrapolates from limited phantom tests and illustrative biological calculations rather than broad systematic validation.

### 7. Implications for reference DVH calculator design

#### 7a. Algorithm and implementation recommendations

For a reference DVH calculator, this paper strongly supports **separating geometry discretisation from dose discretisation** rather than tying structure accuracy to the TPS dose grid. It also supports evaluating dose at fine geometric samples by interpolation to voxel centres, but the modern implementation should go beyond the paper by also supporting analytic or subvoxel boundary integration where possible. The scanline logic on page 3 is especially important: a reference engine must explicitly handle tangential touches, reversals, and collinear contour/scanline overlap rather than treating every intersection as a crossing. Because the paper’s inclusion rule is binary voxel-centre classification, modern software should treat that as a **baseline mode**, not the gold standard. The paper’s numeric guidance suggests that cumulative bin widths of **0.5 Gy or finer** are appropriate, and that any default **2 Gy** cumulative binning is too coarse for reference work. Structure Boolean operations and hierarchy handling should be first-class features, not ad hoc post-processing. Finally, the calculator should **not silently assign zero dose** outside the dose grid or auto-pad missing organ volume without a prominent warning and provenance trail.

#### 7b. Validation recommendations

The paper gives an unusually clear historical validation set that should absolutely be reproduced in a modern QA suite: (1) **nested concentric cubes** with known uniform doses and inclusion/exclusion logic, (2) a **notched cube** to expose boundary-crossing and tangency bugs, and (3) a **cylinder** to verify non-orthogonal boundary representation. For a true reference engine, these should be extended by grid-shift studies, anisotropic slice spacing, very small volumes, and long thin appendages, because the paper explicitly shows that alignment and minimum feature size drive error. High-gradient beam-edge tests are also essential, since the authors’ dose-grid rule-of-thumb is derived from gradient considerations. The historical inter-institution result of **±1 bin** agreement is useful as a minimal benchmark, but for a gold-standard calculator it is too weak on its own, especially because the bin width was not reported. Modern validation should therefore include absolute/relative volume error against analytical phantoms, Dv/Vd point comparisons, convergence versus spatial refinement, overlap/Boolean tests, and explicit warning behaviour for incomplete dose-matrix coverage.

#### 7c. Extensibility considerations

This paper is more extensibility-aware than its age might suggest. It explicitly proposes **Dose Area Histograms** for skin and hollow-organ surfaces and **dose-length histograms** for long linear structures such as optic nerves. It also suggests thresholded radial-extent-versus-length displays for spinal cord-type anatomy. A modern reference platform should therefore not hard-code “volume” as the only measure; instead it should implement a generic histogram framework over **weighted geometric measure** (volume, area, length, possibly mass) with pluggable region definitions and plotting back-ends. The paper’s repeated linkage to TCP/NTCP also motivates a clean interface from histogram computation to biological models, ideally with uncertainty propagation rather than simple deterministic reduction. Although the paper predates gEUD, dosiomics, and probabilistic DVHs, its Figure 6 argument strongly supports retaining access to the low-volume tail in both data structures and APIs, because those tails are biologically load-bearing.

#### 7d. Caveats and limitations

Several aspects may not generalise directly. First, the paper partly conflates **DVH computation error** with **dose-calculation/interpolation error** the underlying dose algorithm is not described, so one cannot cleanly separate histogram error from dose-field error. Second, many numeric recommendations come from limited examples, one spinal cord case, or even private communication, so they should not be over-read as universal tolerances. Third, the paper does **not** describe fractional boundary weighting, supersampling, contour interpolation method, or modern DICOM-RT geometry issues, so its algorithms are best understood as historically foundational rather than reference-grade. Fourth, the suggestion to add standard organ volume into the zero-dose bin when CT truncates the anatomy is a pragmatic clinical heuristic, but not an acceptable silent default for a benchmark calculator. Finally, the clinical examples are illustrative only; no patient-level sample sizes, no outcome validation, and no formal uncertainty analysis are provided.

### 8. Connections to other literature

**Drzymala, Harms and Purdy (1987).** This *Medical Physics* abstract appears to be the immediate precursor to the present paper; the 1991 article is essentially the fuller methodological exposition of the same DVH agenda.

**Chen et al. (1984).** Early conference use of DVHs for pancreatic treatment-plan evaluation; Drzymala et al. cite it as evidence that applications existed before robust computational methods were standardised.

**Lyman (1985).** Establishes complication probability assessment from DVHs, directly motivating the present paper’s insistence that small DVH-shape changes can have large biological consequences.

**Lyman and Wolbarst (1987).** Extends DVH-based complication modelling into treatment-optimisation thinking; this is the specific “single-number reduction” context that the Figure 6 cautionary example speaks to.

**Mohan, Brewster and Barest, 1987.** Closely linked technical companion on computing DVHs for structure combinations; the hierarchy/tag-matrix logic in the 1991 paper clearly builds on this work.

**Kessler et al. (1994).** A direct follow-on paper that tackles the major limitation identified here; loss of spatial information; by integrating DVHs with interactive 3D dose display.

**Panitsa, Rosenwald and Kappas (1998).** Later multi-system QC work that operationalises the validation and consistency concerns foreshadowed by Drzymala et al., especially in high-gradient regions and under adverse computational settings.

### 9. Data extraction table

**Table 1. Explicit quantitative guidance and benchmark values extracted from the paper.**

| Quantity | Extracted value | Context / interpretation |
|---|---:|---|
| Number of institutions | **4** | Four centres independently developed DVH code |
| Intercomparison participants | **3 of 4** | Three institutions compared cumulative DVHs on a common phantom |
| Common-phantom agreement | **±1 bin** | Concentric-cube phantom; exact bin width **[DETAIL NOT REPORTED]** |
| Suggested geometric resolution | **<0.25 × structure dimension** | In a spinal cord example, little additional DVH change below this voxel size |
| Mean volume error | **within 5% of true volume** | Reference denominator: true volume |
| Worst-case theoretical volume error | **up to 16% of true volume** | Extreme alignment/boundary cases |
| Dose-grid spacing rule | **~2.5 × allowable isodose-position error** | Practical interpolation rule-of-thumb |
| Example dose-grid spacing | **5 mm** | Said to achieve about **2% dose accuracy** or **2 mm isodose-position accuracy**, but not necessarily both simultaneously |
| Recommended cumulative bin width | **0.5 Gy** | Approx. **1% of prescription dose** authors call **2 Gy** crude |
| Suggested differential bin width | **2-5 Gy** | One group found this advantageous for breast-plan review |

**Table 2. Figure 6 TCP example illustrating biologically important low-volume tail effects.** The values below are taken from the page 6 legend and discussion.

| Institution | TCP value | Rank by TCP | Rank by ordinary visual inspection of panel A |
|---|---:|---:|---:|
| C | **0.90** | 1 | 1 |
| B | **0.86** | 2 | 3 |
| D | **0.80** | 3 | 4 |
| A | **0.76** | 4 | 2 |

Interpretive note: the visually intuitive ranking **C > A > B > D** differs from the reported TCP ranking **C > B > D > A**, implying that low-dose coverage in a very small volume fraction can dominate biological plan ranking.

### 10. Critical appraisal

**Strengths:** This is a foundational DVH computation paper that is unusually explicit, for its era, about geometry/dose-grid decoupling, contour rasterisation failure modes, Boolean structure logic, verification phantoms, and the biological sensitivity of low-volume DVH tails. The multi-institution perspective is valuable because it exposes implementation variability rather than presenting a single in-house algorithm as universal. **Weaknesses:** patient and plan sample sizes are largely absent; dose-calculation details are missing; several “tolerances” are heuristic rather than systematically validated; and no fractional partial-volume method is described, so the implied algorithm is coarser than a modern reference implementation should accept as definitive. **Confidence in findings: Medium.** The computational insights are credible and historically important, but the quantitative thresholds are based on limited examples and incomplete reporting. **Relevance to reference DVH calculator: High.** Many of the exact issues this paper raises; boundary classification, overlap logic, geometric resolution, dose-grid coverage, and tail sensitivity of downstream metrics; remain core design and validation requirements for a gold-standard DVH engine.

---

<!-- Source: SUMMARY - Kooy 1993 - DVH computations for small intracranial volumes.md -->

## Kooy (1993) - Dose-volume histogram computations for small intracranial volumes

### Executive summary

Kooy and colleagues presented an early but still highly relevant analysis of why dose-volume histogram (DVH) computation becomes numerically fragile for **small intracranial structures** embedded in **steep dose gradients**, as in stereotactic radiosurgery. Their main contribution was a **spatially nonuniform Monte Carlo sampling framework** that preferentially places dose-evaluation points near the target or structure of interest, rather than using a uniformly sampled Cartesian grid. The method was designed to generate **absolute-volume cumulative DVHs** efficiently enough for routine clinical use on early-1990s hardware.

The paper’s key technical finding is that **uniform rectilinear sampling is inefficient for small structures**, whereas targeted radial sampling substantially reduces integration variance in the high-gradient region of interest. With **7500 samples**, the proposed approach achieved approximately **4% one-standard-deviation relative error** for tested spherical volumes, and about **6-9%** error for **1-2 cm³** thin shells near the sampling centre, corresponding to shell thicknesses of **0.8-1.6 mm**. Phantom experiments showed close agreement between **sampled volumes** and **contour-derived volumes**, although both differed from the exact physical truth because of **4 mm slice thickness** and contour discretisation.

For a modern reference DVH calculator, the paper is important less because its stochastic method should be copied directly, and more because it clearly identifies the numerical edge cases that must be handled rigorously: **small structures, thin high-gradient subvolumes, contour discretisation, absolute versus relative DVH reporting, and the need to separate geometry error from dose-sampling error**. Its preferred error levels were clinically acceptable for 1993, but would be too loose for a present-day benchmark engine; nonetheless, the failure modes it characterises remain central.

### 1. Bibliographic record

**Authors:** Hanne M. Kooy, Lucien A. Nedzi, Eben Alexander III, Jay S. Loeffler, Robert J. Ledoux
**Title:** *Dose-volume histogram computations for small intracranial volumes*
**Journal:** *Medical Physics*
**Year:** 1993
**DOI:** [10.1118/1.597029](https://doi.org/10.1118/1.597029)
**Open access:** No

### 2. Paper type and scope

**Type:** Original research

**Domain tags:** D1 Computation

**Scope statement:** This paper presents a spatially nonuniform Monte Carlo sampling method for computing **absolute-volume** cumulative DVHs for the very small target and organ-at-risk volumes encountered in stereotactic radiosurgery. Its core contribution is not a new dose algorithm, but a new volume-sampling formalism that attempts to preserve clinically acceptable accuracy in steep dose gradients while using far fewer evaluation points than a uniformly sampled rectilinear grid.

### 3. Background and motivation (150-300 words)

Kooy et al. address a problem that remains highly relevant for reference DVH computation: **small structures in very steep dose gradients are numerically unforgiving**. In stereotactic radiosurgery, the target may be on the order of **10 cc**, whereas the full brain volume may be around **1000 cc** at the same time, dose gradients can be about **100 cGy/mm (1 Gy/mm)**. The authors argue that these two facts make conventional plan-evaluation strategies inadequate if they rely on coarse sampling or on DVHs normalised only to percentage volume. A **10%** involvement of a tiny target and a **10%** involvement of a critical structure do not correspond to comparable absolute tissue volumes, so percent-volume-only DVHs can be clinically misleading.

They also frame the paper as a computational-efficiency problem. A regularly spaced grid fine enough to resolve mm-scale gradients would, in their estimate, require on the order of **100,000** dose calculations for a **10 cm³** region at better than **0.25 cm** resolution, which was impractical for interactive planning on early-1990s workstations. Prior work had already discussed preferential sampling around dose gradients and Monte Carlo sampling for treatment-plan evaluation, but not a practical multi-region framework designed specifically for **small intracranial volumes**, simultaneous evaluation of multiple structures, and output in **absolute volume versus dose**. This paper therefore sits at the junction of DVH computation, sampling theory, and early stereotactic treatment-planning QA.

### 4. Methods: detailed technical summary (400-800 words)

The study is best described as a **hybrid methodological paper** combining:
(1) an analytical derivation of sampling variance,
(2) Monte Carlo simulations to compare candidate sampling distributions,
(3) a **physical phantom** verification of absolute volume estimation, and
(4) a **single-patient clinical example** showing the resulting DVHs in a stereotactic radiosurgery context. There is no cohort study, no prospective clinical design, and no multi-institutional dataset.

The computational core is a point-sampling estimator for structure volume. For a spherically symmetric probability density function \(P(r)\), the average volume represented by a sample point at radius \(r\) is written as \(\Delta v(r)=4\pi r^2/[N P(r)]\). For an arbitrary structure, any sampled point lying inside the structure contributes its weight to the estimated volume; thus, structure volume is the sum of per-point weights for all accepted points. The authors derive an analytical expression for the variance of this estimator for a sphere of radius \(R\), which allows them to compare alternative sampling distributions theoretically before implementing them. This is important: they do not merely assert that preferential sampling helps; they derive when and why it helps.

They first compare two reference distributions for integrating spherical volumes:
- a **spherical density distribution** \(P_S(r)=1/R_{\max}\), uniform in radius but spatially nonuniform in Cartesian space, and
- a **Cartesian-uniform distribution** \(P_C(r)=3r^2/R_{\max}^3\), which gives uniform point density in rectilinear coordinates.

Using the derived standard deviation, they define an efficiency ratio \(M(r)=\sigma_C(r)/\sigma_S(r)\). When \(M(r)>1\), the spherical/nonuniform strategy is more efficient. This analysis underpins the later choice to bias samples towards small radii and regions near the target/isocentre.

For clinical use, the cranial volume is partitioned into multiple sampling regions. Two classes of region are defined:
1. the region around each **target/isocentre**, where high gradients are expected;
2. a region associated with each **anatomical structure** of interest.

For the target/isocentre region, the authors use a **piecewise radial PDF** \(P_T(r)\): a constant density inside radius \(R_0\), and a lower constant density in the shell between \(R_0\) and \(R_1\). The partition parameter \(G\) assigns a fraction of points to the inner sphere; a typical value is **\(G=0.8\)**, meaning **80%** of samples fall inside \(R_0\). In clinical calculations they use **\(R_0=5\) cm** and **\(R_1=20\) cm**, justified respectively by typical maximum radiosurgery field size and negligible dose by 20 cm. For structure-specific sampling, they use \(P_V(r)=1/R_V\) for \(0<r<R_V\), where \(R_V\) is the radius of a sphere enclosing the structure, centred at the structure’s centre of mass. The target volume is therefore sampled twice: once through the target/isocentre region and once through its own anatomical region. Samples are randomly assigned to regions with probabilities proportional to **\(R_{0,i}^2\)** or **\(R_{V,i}^2\)**, via a cumulative weight \(W=\sum R_{0,i}^2+\sum R_{V,i}^2\). Angular coordinates \(\theta\) and \(\phi\) are sampled uniformly on the sphere.

The formalism is explicitly geometry-agnostic in one important sense: the authors state that **any volume representation is acceptable** as long as one can determine whether a sampled point lies inside or outside the volume. Their implementation used the XKnife treatment-planning system (RSA, Brookline, MA), in which structures were represented as semi-parallel contours on consecutive CT slices, but they stress that this particular representation is not required by the sampling method itself. This is a notable engineering point because it separates the **sampling/integration strategy** from the **structure representation**.

Phantom verification used a plastic skull phantom named **“Yorick”** in a BRW stereotactic setup. Two shapes with known dimensions were inserted: a **cube of side 1 cm** and a **cylinder of radius 1 cm and height 3 cm**. The phantom CT was imported into XKnife; structures were contoured on consecutive image sections. For the contour-derived reference volume, the authors computed the sum of contour areas times **slice thickness 4 mm**. This is a key methodological nuance: the primary comparison is **sampled volume versus contoured volume**, not sampled volume versus ideal physical ground truth alone.

DVH details are incompletely reported. The paper clearly states that it computes **integral (cumulative) DVHs** and that dose is plotted as **percentage of isocentre dose**, with volume in **cc**. However, **dose bin width** is [DETAIL NOT REPORTED], **number of bins** is [DETAIL NOT REPORTED], **dose interpolation method** is [DETAIL NOT REPORTED], **dose-calculation algorithm/version/photon energy** are [DETAIL NOT REPORTED] in this paper, and **heterogeneity handling** is [DETAIL NOT REPORTED]. The authors explicitly refer readers to their earlier treatment-planning paper for the algorithm used to compute dose at each sampling point. Boundary handling appears to be **binary point-in-volume classification** with statistical weighting, not explicit voxel partial-volume intersection. End-capping rules for contour stacks are [DETAIL NOT REPORTED].

### 5. Key results: quantitative (300-600 words)

The first main result is that **spatially nonuniform spherical sampling is markedly more efficient for small volumes** than Cartesian-uniform sampling. In Figure 1 on page 4, the error ratio \(M(r)=\sigma_C/\sigma_S\) is well above 1 for small spheres, confirming that preferential concentration of points at small radii reduces variance where small radiosurgical targets and adjacent OAR subvolumes live. The curve crosses towards parity only for larger radii, meaning the preferred sampler sacrifices some efficiency in distal, lower-interest regions to gain accuracy where it matters most clinically. Monte Carlo points track the theoretical curve closely.

The second result is the quantitative accuracy of the chosen piecewise target PDF. Using **\(R_0=4\) cm, \(R_1=15\) cm, \(G=0.8\)** in the computational-accuracy experiment (Figure 2), the authors report that the proposed sampler keeps the **one-standard-deviation relative volume error below about 4% across the full tested range of sphere radii**, whereas a spatially uniform Cartesian sampling distribution performs much worse for small radii because it over-samples the outer “uninteresting” region. They state explicitly that **\(G=0.8\)** is a good compromise; larger \(G\) would further improve inner-region accuracy at the expense of the outer shell. The Monte Carlo data in Figure 2 were averaged over **100 trials** with **7500 points/trial**.

The third result concerns thin, high-gradient subvolumes. Figure 3 shows the one-standard-deviation error in the volume of spherical shells of **1 cm³** and **2 cm³** as a function of inner shell radius. At **1 cm** from the sampling-region centre, the sampling error is **9%** for the **1 cm³** shell and **6%** for the **2 cm³** shell. At that location the corresponding shell thicknesses are **0.8 mm** and **1.6 mm**, respectively. The authors conclude that their ability to sample a volume affected by a gradient change over a **1 mm-thick shell** is about **7%**. This is a particularly important number for modern DVH benchmarking because it directly quantifies the challenge posed by thin structures or narrow gradient zones.

Phantom verification showed that the sampled volumes agreed closely with the **contoured** volumes, not necessarily the true physical volumes. For the **1.00 cm³** cube, the contoured volume was **0.74 cm³** and the sampled volume **0.73 ± 0.02 cm³**, i.e. **3%** agreement between sampled and contoured. For the **9.42 cm³** cylinder, the contoured volume was **8.13 cm³** and the sampled volume **8.18 ± 0.18 cm³**, i.e. **2%** agreement between sampled and contoured. The systematic deficit versus physical truth was attributed to contouring uncertainty and finite slice thickness. For the cylinder, which appeared on **seven slices**, each slice contributed **1.16 cm³** the implied contoured radius was **0.96 cm** versus the true **1.00 cm**, an error smaller than the pixel resolution.

The clinical illustration involved a metastatic breast tumour above the left optic nerve. The treatment used a **single 30 mm collimator** and **four treatment arcs** for a total of **310°** rotation. The tumour DVH indicated a tumour volume of **5.2 cc** with excellent coverage to the desired **80%** dose level (percentage of isocentre dose). The collimator size implied an approximate treatment volume of **14 cc**. The optic nerve volume was about **0.8 cc** and was crossed by the **10%** isodose. The authors report a ratio of tumour volume to non-tumour volume receiving tumouricidal dose (**80% of isocentre dose**) of about **0.6**, which they describe as typical in their experience. Figure 4 shows that with **20 trials** and **7500 sampling points**, the high-dose tail and fall-off region of the DVH are reproduced accurately, with uncertainty bands consistent with the expected **~4%** volume error. No p-values, confidence intervals, or formal hypothesis tests were reported anywhere in the paper.

### 6. Authors' conclusions (100-200 words)

The authors conclude that a **spatially nonuniform Monte Carlo sampling formalism** can compute absolute volumes and cumulative DVHs for small stereotactic radiosurgery structures with **clinically acceptable accuracy** while using far fewer dose evaluations than a regular rectilinear grid. They emphasise that the method is suitable for simultaneous computation of DVHs for all structures in a planning session and that it is fast enough for routine clinical use, citing **5-30 s** runtimes on then-current workstations and roughly **100-1000 points per volume** for a total of about **10,000** points, i.e. **10-100 times fewer** than a comparable grid-based approach. They further argue that **absolute-volume** DVHs are more robust and clinically meaningful than normalised percent-volume DVHs for small structures because image-acquisition and contouring limitations can make “100% of volume” a misleading denominator.

These conclusions are well supported for the specific claim that **importance-weighted sampling improves small-volume integration efficiency**. They are less well supported as a general statement about all DVH computation contexts, because the paper does not validate across diverse anatomies, dose engines, or non-spherical gradient fields.

### 7. Implications for reference DVH calculator design (300-600 words)

#### 7a. Algorithm and implementation recommendations

This paper strongly supports making **absolute-volume cumulative DVHs in cc** a first-class output of any reference calculator, not just percent-volume DVHs. For very small targets and OARs, normalising to 100% of a contour-derived structure can distort clinical interpretation; the paper’s core argument is that absolute dose-volume trade-offs are more meaningful for radiosurgery-like geometries.

Algorithmically, the paper is an early warning against naïve **uniform Cartesian sampling** for small volumes in steep gradients. A reference engine should therefore avoid any method whose effective resolution is uniform everywhere unless it can prove convergence in the relevant subvolumes. In a modern gold-standard calculator, the preferred strategy would likely be **deterministic geometric intersection** or **adaptive supersampling** rather than stochastic Monte Carlo, because the paper’s own best-case stochastic error is still about **4%** for spheres and about **7%** for a **1 mm** shell. Those errors were “clinically acceptable” in 1993, but they are too loose for a benchmark tool. If Monte Carlo is offered at all, it should be optional, uncertainty-aware, seed-controlled, and accompanied by convergence testing.

A second implementation lesson is architectural: the paper cleanly separates the integration method from the volume representation. The reference engine should likewise support arbitrary structure back-ends; contour stacks, binary masks, triangulated meshes, implicit surfaces; through a common **point-in-volume / overlap** interface. This paper’s statement that “any volume representation suffices” as long as inclusion can be tested is directly relevant to modular software design.

#### 7b. Validation recommendations

This paper suggests several high-value validation phantoms and analytical test cases. At minimum, the reference calculator should include:
(1) **spheres** of varying radius centred on a sampling origin or high-gradient centre;
(2) **thin spherical shells** of known volume, especially around **1 mm** thickness;
(3) a **1 cm cube** and **1 cm radius × 3 cm height cylinder** under CT-like slice discretisation; and
(4) a clinical-style small-target/critical-structure geometry analogous to the **5.2 cc tumour / 0.8 cc optic nerve** example.

These cases expose different failure modes. Small centred spheres test raw volumetric integration efficiency. Thin shells probe the exact pathology the paper quantifies: resolving narrow gradient zones. The cube/cylinder phantom reveals the confounding influence of contour discretisation and slice thickness. The clinical near-OAR example tests whether a DVH engine preserves both a sharp target shoulder and a low-dose OAR tail. A modern benchmark should go beyond the paper by separating **geometry error** from **dose-sampling/interpolation error** and by setting tighter tolerances than the paper’s **~4%** stochastic target; for benchmarking, uncertainty should ideally be driven well below **1%** for structure volumes and reported per DVH metric.

#### 7c. Extensibility considerations

Although the paper only reports cumulative DVHs, its weighted-point framework naturally motivates a more general data model: store **sample coordinates, structure membership, dose, and sample weight**. With that abstraction, the same engine could accumulate **differential DVHs**, absolute-volume-at-dose metrics, **gEUD/EUD**, or uncertainty-aware biological models. It could also be extended to surface- or distance-based metrics such as **DSH** or **DMH**, provided the geometry layer exposes surface and distance queries rather than only inclusion queries. The historical lesson is that once the integration kernel is generalised, DVH is just one possible weighted histogram.

#### 7d. Caveats and limitations

Several caveats limit generalisability. First, this paper mostly validates the **volume-sampling** formalism, not the underlying **dose-calculation** engine. The dose-at-point algorithm is delegated to an earlier paper, so one must not confuse agreement in sampled volume with overall dosimetric truth. Second, phantom “validation” is against the **contoured volume**, which itself underestimates the physical shape because of **4 mm** slice thickness and contouring ambiguity. Third, the sampling PDFs assume roughly **spherical symmetry** around an isocentre, which is reasonable for single-isocentre intracranial radiosurgery but not for modern IMRT/VMAT, multiple-isocentre SRS, or highly anisotropic dose clouds. Finally, several implementation details that matter greatly for a reference DVH engine; dose interpolation, histogram binning, boundary rules, partial-volume treatment, heterogeneity corrections; are simply not reported here.

### 8. Connections to other literature

- **Drzymala et al. (1991)** foundational discussion of DVHs; Kooy et al. extend that general DVH framework to the specific problem of **small-volume, absolute-volume** radiosurgery evaluation.
- **Niemierko and Goitein (1989)** provides the grid-size and preferential-sampling context that this paper develops into a practical small-volume sampling framework.
- **Lu and Chin (1993)** closely related contemporaneous sampling work; Kooy et al. differ by using **spatially nonuniform, multi-region** sampling tailored to radiosurgery structures.
- **Kooy et al. (1991)** earlier stereotactic treatment-planning paper supplying the dose-at-point calculation framework used here.
- **Flickinger (1989)** complication-prediction work helping motivate why accurate dose-volume quantification of small intracranial structures matters clinically.
- **Nedzi et al. (1991)** intracranial radiosurgery complication-analysis work for which accurate tumour-critical-structure DVH trade-off assessment is relevant.

### 9. Data extraction table

The tables below extract quantitative values explicitly reported in the text, figure captions, and Table 1.

**Table 9a. Sampling parameters and reported accuracy**

| Context | Quantity | Value | Notes |
|---|---:|---:|---|
| Clinical target-region PDF | \(R_0\) | **5 cm** | Inner sphere radius used clinically |
| Clinical target-region PDF | \(R_1\) | **20 cm** | Outer shell limit used clinically |
| Target-region PDF | \(G\) | **0.8** | **80%** of points inside \(R_0\) |
| Figure 2 test case | \(R_0\) | **4 cm** | Used for computational-accuracy comparison |
| Figure 2 test case | \(R_1\) | **15 cm** | Used for computational-accuracy comparison |
| Figure 2 test case | Trials | **100** | Monte Carlo average |
| Figure 2 test case | Points per trial | **7500** | Monte Carlo average |
| Reported performance | One-SD relative error | **~4%** | Proposed nonuniform sampler over full tested range of radii |
| Figure 3 | Error for **1 cm³** shell at **1 cm** radius | **9%** | Shell thickness **0.8 mm** |
| Figure 3 | Error for **2 cm³** shell at **1 cm** radius | **6%** | Shell thickness **1.6 mm** |
| Figure 3 | Approximate capability for **1 mm** shell | **~7%** | Authors’ interpretation |
| Discussion | Points per volume | **100-1000** | Typical clinical use |
| Discussion | Total points | **~10,000** | Across all volumes |
| Discussion | Runtime | **5-30 s** | On then-current workstations |

**Table 9b. Phantom verification**

| Shape | Exact volume (cc) | Contoured volume (cc) | Sampled volume (cc) | Reported agreement |
|---|---:|---:|---:|---|
| Cube (side **1 cm**) | **1.00** | **0.74** | **0.73 ± 0.02** | **3%** vs contoured |
| Cylinder (radius **1 cm**, height **3 cm**) | **9.42** | **8.13** | **8.18 ± 0.18** | **2%** vs contoured |

**Table 9c. Clinical example**

| Quantity | Value |
|---|---:|
| Tumour volume | **5.2 cc** |
| Optic nerve volume | **~0.8 cc** |
| Collimator size | **30 mm** |
| Number of arcs | **4** |
| Total arc rotation | **310°** |
| Desired tumour coverage level | **80%** of isocentre dose |
| Approximate treatment volume | **14 cc** |
| Tumour / non-tumour volume receiving tumouricidal dose | **~0.6** |
| Isodose transecting optic nerve | **10%** |

### 10. Critical appraisal (100-200 words)

**Strengths:** This is an early, technically serious paper that treats DVH computation as a **numerical integration problem**, not just a plotting task. It provides an analytical variance framework, demonstrates the failure of uniform sampling for small volumes, includes a physical phantom check, and makes a still-important conceptual case for **absolute-volume DVHs** in small-structure radiosurgery.

**Weaknesses:** Reporting is incomplete by modern standards. The paper omits many implementation details that matter for reproducible DVH computation, especially dose interpolation, binning, and boundary rules. Phantom validation is partly confounded by contour discretisation, and the clinical demonstration is only a single illustrative case. The stochastic accuracy achieved is clinically useful but not reference-grade.

**Confidence in findings:** **Medium.** The core sampling argument is convincing and mathematically grounded, but validation breadth is limited and some crucial computational details are absent.

**Relevance to reference DVH calculator:** **High.** The paper identifies exactly the edge cases a gold-standard DVH engine must handle: **small volumes, thin shells, steep gradients, contour discretisation, and the difference between absolute and normalised DVHs**.

---

<!-- Source: SUMMARY - Fraass 1998 - AAPM Task Group 53; QA for clinical RT planning.md -->

## Fraass (1998) - American Association of Physicists in Medicine Radiation Therapy Committee Task Group 53: Quality assurance for clinical radiotherapy treatment planning

### Executive summary

This is a deliberately **DVH-only** reworking of the earlier summary. TG-53 is not a DVH algorithm paper in the modern sense, but it is one of the earliest major QA documents to state clearly that DVH generation is a **commissioning and routine-QA problem in its own right**, not merely a passive by-product of dose calculation. Its most important contribution is **Table 3-20**, which effectively defines the early QA requirements for a clinically trustworthy DVH workflow: correct VROI creation, correct Boolean structure logic, accurate voxel-dose interpolation, accurate irregular-structure volume determination, appropriate histogram bins and limits, correct generation of direct/differential/cumulative histograms, correct plotting/output, correct relationship between plan normalisation and the DVH dose axis, explicit understanding of dose-grid/VROI-grid interactions, and caution when comparing DVHs across plans with different dose grids or bin widths.

The report is especially valuable because it refuses to collapse “DVH accuracy” into one number. Instead, it states that DVH accuracy depends on **dose calculation grid**, **volumetric ROI grid**, **accuracy of object segmentation**, **histogram bin size**, and **plan normalisation**. That is still an excellent engineering framing for a reference-grade open DVH engine. At the same time, TG-53 does **not** specify a reference DVH algorithm, numeric DVH tolerances, bin width, interpolation kernel, or partial-volume rule. It should therefore be read as a **requirements-and-failure-mode document**, not a final algorithmic specification.

For a gold-standard DVH calculator, the strongest lessons are: expose all geometry and sampling assumptions; validate irregular structures, Boolean ROIs, composite-plan accumulation, and grid-offset cases; treat histogram type and binning as configurable, provenance-bearing objects; and separate DVH-engine error from upstream dose-field error. The report also already anticipates extensibility beyond standard cumulative DVHs by explicitly linking DVH use to NTCP/TCP, fractionation corrections, and composite plans.

### 1. Bibliographic record

**Authors:** Benedick Fraass, Karen Doppke, Margie Hunt, Gerald Kutcher, George Starkschall, Robin Stern, Jake Van Dyke
**Title:** *American Association of Physicists in Medicine Radiation Therapy Committee Task Group 53: Quality assurance for clinical radiotherapy treatment planning*
**Journal:** *Medical Physics*
**Year:** 1998
**DOI:** [10.1118/1.598373](https://doi.org/10.1118/1.598373)
**Open access:** Yes

### 2. Paper type and scope

**Type:** Task group report

**Domain tags:** D1 Computation | D2 Commercial systems | D4 Outcome modelling

**Scope statement:**
TG-53 is a broad treatment-planning QA report, but this summary intentionally narrows to the paper’s DVH-relevant content only. In that narrower sense, the report functions as an early requirements document for DVH commissioning, acceptance testing, routine QA, and interpretation in image-based 3D radiotherapy planning.

### 3. Background and motivation (150-300 words)

The rapid adoption of image-based 3D planning in the 1990s changed both the usefulness and the risk profile of DVHs. Once structures were defined in 3D and dose distributions were available on full volumetric grids, clinicians increasingly depended on DVHs to compare plans, judge target coverage, assess hotspots and cold regions, and support higher-order tools such as NTCP/TCP. TG-53 recognises that this made treatment planning more powerful, but also more vulnerable to systematic software and workflow error.

The paper’s DVH motivation is therefore not “how should one display a histogram?”, but “what must be checked so that a histogram can be trusted clinically?”. The report explicitly states that DVHs are an important part of modern treatment planning, yet warns that the simple geometric and dosimetric test models that appear attractive for validation are often themselves susceptible to **grid-alignment artefacts**. This is a subtle but still highly relevant observation: a reassuring DVH QA result can be false reassurance if the test object is too regular or too well aligned to the grid.

What was missing at the time was a practical QA framework. Earlier QA literature and broader treatment-planning commissioning guidance did not spell out a DVH test matrix in enough detail. TG-53 fills that gap by identifying the actual failure modes: structure representation, voxel-region definition, Boolean operations, dose interpolation, irregular-volume determination, histogram construction, normalisation, cross-plan comparability, and hardcopy/output correctness. It does not solve those problems mathematically, but it defines them with unusual clarity.

### 4. Methods: detailed technical summary (400-800 words)

This is not an experimental patient study, phantom trial, or retrospective plan comparison. It is an expert task-group report built from prior literature, commissioning practice, and structured QA recommendations. There is therefore **no patient cohort, no measured DVH dataset, no new phantom data, and no statistical hypothesis testing**. The “methods” are the report’s internal QA framework.

From a DVH-only perspective, the relevant parts of the report are distributed across several chapters rather than concentrated in one section.

First, DVH is present already at **acceptance testing**. In Table 2-2 the report lists “Dose display, dose volume histograms” as a specific acceptance-test feature. The recommended test is to display dose results and use a **standard dose distribution provided by the vendor** to verify that the DVH code behaves as described, with optional **user-created dose distributions** for additional checks. This is important because it implies two distinct validation classes: vendor-provided regression datasets and locally designed stress tests.

Second, the report defines the geometric object on which a DVH depends. In Table 3-3, an ROI description is defined as a **voxel or surface description of each 3-D structure of interest**, used for calculation of DVHs and other statistics. This is a key conceptual point: TG-53 does not equate anatomy with contours alone. It already recognises that the actual computational object used for a DVH is some derived 3D region representation.

Third, the paper addresses DVH explicitly in **Section 3.7.2** and **Table 3-20**. The text says that DVHs are an important part of modern treatment planning and warns that apparently simple QA phantoms may be vulnerable to grid-alignment artefacts. Table 3-20 then enumerates the checks that should be performed. These cover:
- creation of the voxel VROI used for DVH generation;
- Boolean structure combinations and multi-membership voxels;
- dose interpolation into each voxel;
- structure-volume calculation with irregular objects;
- histogram bins and limits;
- core DVH calculation against known dose distributions;
- correct handling of standard/direct, differential, and cumulative histograms;
- plotting and output;
- relationship of plan normalisation to DVH results;
- dose-grid/VROI-grid interaction;
- correct comparison of DVHs from different cases with different dose grids or bin sizes.

Fourth, TG-53 extends the DVH problem to **composite plans**. In Section 3.7.4, the report notes that some systems add or subtract dose distributions from different plans to build a composite plan for course-level evaluation. DVH-relevant QA issues then include:
- prescription input for each component plan;
- availability of fractionation / bio-effect corrections;
- interpolation of individual plan dose distributions onto a common grid;
- handling of plans with different dose units;
- accuracy of addition and subtraction.

Fifth, DVH is embedded in **output QA** and **routine QA**. Table 3-21 requires DVH hardcopy output to carry a plot legend, scales and units, case/plan identification, and associated anatomical structure identifiers. Table 5-1 includes annual review of **critical software tools**, explicitly naming DVH calculations.

What the report **does not** specify is equally important. It gives **no reference DVH algorithm**, **no mandated bin width**, **no stated interpolation kernel**, **no supersampling strategy**, **no explicit partial-volume weighting method**, **no end-capping rule**, and **no quantitative DVH pass/fail tolerance**. These are all [DETAIL NOT REPORTED]. That absence is not accidental; TG-53 is a QA framework, not a numerical standard.

### 5. Key results: quantitative (300-600 words)

Because TG-53 is a task-group report rather than an empirical comparison study, its “results” are primarily **QA statements, test matrices, and illustrative tolerances** rather than measured differences between algorithms. For DVH work, the most important quantitative statement appears in Table 1-3: DVH accuracy is listed as **“Depends on many factors”** rather than assigned a single tolerance. The report then names those factors explicitly: **dose calculation grid**, **volumetric region-of-interest grid**, **accuracy of object segmentation**, **histogram bin size**, and **plan normalisation**. That is arguably the most important direct DVH result in the paper.

The second major result is the existence and content of **Table 3-20**, which is the paper’s dedicated DVH QA table. It contains **11 distinct DVH test domains**:
1. VROI identification
2. structure identification / Boolean handling
3. voxel dose interpolation
4. structure volume
5. histogram bins and limits
6. DVH calculation
7. DVH types
8. DVH plotting and output
9. plan and DVH normalisation
10. dose and VROI grid effects
11. use of DVHs from different cases

That list is not merely descriptive. It defines the minimal QA space that the report believes must be covered if DVHs are used clinically.

A third quantitative result is the paper’s acceptance-testing recommendation in Table 2-2 that the DVH code should be checked with a **standard vendor dose distribution** and optionally with **user-created dose distributions**. Although no tolerance is attached, this is effectively an early proposal for benchmark-style validation.

A fourth result, indirectly quantitative, is the inclusion of DVH checks in **annual periodic QA**. Table 5-1 explicitly places DVH calculations among “critical software tools” to be reviewed annually, alongside CT geometry, density conversions, and BEV/DRR generation. This is an operational result more than a numerical one, but it is important: DVHs are not presented as a one-time commissioning item only.

The report also identifies DVH-relevant quantitative comparability hazards in composite plans: different dose units, different dose grids, and different histogram bin sizes. That is not expressed as a tolerance, but it is a direct warning against naive cross-plan comparison.

No p-values, confidence intervals, effect sizes, or cohort statistics are reported. No numerical difference is given for “good” versus “bad” DVH calculation, because the authors intentionally decline to reduce DVH QA to a single tolerance.

### 6. Authors' conclusions (100-200 words)

Read through a DVH-only lens, the authors’ conclusion is that DVH output is clinically important enough to require **explicit QA**, but too dependent on implementation details to be validated by a single generic test or tolerance. Their strongest implied claim is that a trustworthy DVH depends on the entire computational chain: anatomy representation, ROI logic, dose interpolation, plan normalisation, output formatting, and comparison semantics.

This conclusion is well supported by the structure of the report itself. The paper never treats DVHs as isolated graphics. Instead, it embeds them in acceptance testing, nondosimetric commissioning, composite-plan QA, hardcopy verification, and annual review. The report is also careful not to overstate what can be claimed. It does **not** say that one DVH algorithm is correct or that one tolerance is sufficient. It says, in effect, that if a clinic uses DVHs clinically, then the clinic must understand and test the assumptions built into its planning system.

### 7. Implications for reference DVH calculator design (300-600 words)

#### 7a. Algorithm and implementation recommendations

A reference DVH calculator should map almost one-to-one onto Table 3-20. At minimum it should make explicit and configurable:

- the 3D ROI model used for statistics (`voxel`, `surface`, or hybrid);
- the VROI actually used for DVH accumulation;
- Boolean structure logic, including how multiply assigned voxels are handled;
- dose interpolation from dose grid to ROI support;
- structure-volume calculation, especially for irregular shapes;
- histogram bin boundaries, limits, and units;
- histogram mode (`direct`, `differential`, `cumulative`);
- plan normalisation state and its relationship to the DVH dose axis;
- dose-grid/ROI-grid alignment and mapping;
- cross-plan comparison rules.

TG-53 also strongly implies that the calculator should **not** assume the dose grid and the ROI grid are the same object. The report treats their relationship as something to be reviewed and understood, which is exactly what a benchmark tool should expose.

#### 7b. Validation recommendations

The report supports a layered validation strategy:

1. **Acceptance-test layer**
   Check the DVH engine against vendor-standard or project-standard reference dose distributions.

2. **Independent stress-test layer**
   Add user-created dose distributions and irregular structures specifically chosen to expose grid artefacts, Boolean-ROI bugs, and mis-normalisation.

3. **Composite-plan layer**
   Validate addition/subtraction of dose distributions, common-grid interpolation, mixed dose units, and fractionation-corrected accumulation.

4. **Routine regression layer**
   Re-run a core benchmark set after software changes and at least annually.

The report also cautions against overly simple regular test objects. A reference engine should therefore include deliberately awkward cases: irregular shapes, grid offsets, partial overlaps, and cross-plan comparisons with different binning or dose-grid spacing.

#### 7c. Extensibility considerations

TG-53 already points beyond a single cumulative DVH. It explicitly expects correct handling of **standard/direct**, **differential**, and **cumulative** histograms. It also places NTCP/TCP and fractionation/bio-effect corrections adjacent to DVH QA, and it treats composite plans as clinically evaluated objects. That means a modern reference engine should maintain a richer internal model than “one cumulative curve per structure”.

At minimum, the data model should support:
- multiple histogram representations from the same underlying dose-volume sample;
- Boolean ROIs;
- composite-plan accumulation;
- multiple dose-unit conventions;
- explicit normalisation provenance;
- hooks for downstream biological models.

#### 7d. Caveats and limitations

TG-53 remains foundational, but it is still only a **QA framework**. It predates `DICOM-RT` maturity, `IMRT/VMAT`, deformable accumulation, and modern sub-voxel geometry methods. It therefore cannot by itself answer questions such as “what is the correct partial-volume rule?” or “what is an acceptable D0.03cc tolerance?”. It also mixes upstream dose-calculation QA with downstream DVH QA, so a reference calculator should use it as a **requirements document**, then supplement it with later analytical-validation literature.

### 8. Connections to other literature

- **Drzymala et al. (1991)** foundational DVH methodology paper; read alongside TG-53 because Drzymala gives the early computational framing and TG-53 gives the QA framing.
- **Van Dyk et al. (1993)** direct predecessor on commissioning and acceptability criteria for treatment-planning computers; TG-53 extends the QA problem into 3D image-based planning and DVH use.
- **Kessler et al. (1994)** important companion paper on use of DVHs in 3D planning; relevant to why TG-53 treats DVH as a core plan-evaluation feature.
- **Panitsa et al. (1998)** near-contemporaneous practical DVH QC study; can be read as an operationalisation of the QA concerns listed abstractly in TG-53.
- **Ebert et al. (2010)** multicentre cross-TPS DVH comparison; effectively tests the “use of DVHs from different cases / different systems” concern flagged by TG-53.
- **Nelms et al. (2015)** analytical benchmark framework; in many ways a direct answer to TG-53’s call for known dose distributions and sound DVH calculation testing.
- **Pepin et al. (2022)** and **Penoncello et al. (2024)** modern multivendor DVH precision/consistency studies that expose the exact implementation variability TG-53 anticipated but could not yet quantify.

### 9. Data extraction table

TG-53 contains **one dedicated DVH table** and several additional DVH-specific rows embedded in broader tables. They are reproduced below.

#### Table 9A. Full reproduction of TG-53 Table 3-20: DVH tests

| Topic | Tests | Reasons |
|---|---|---|
| Volume region of interest (VROI) identification | Test creation of the voxel VROI description used to create DVHs against structure description. | Misidentification of VROI leads to incorrect DVH. |
| Structure identification | Test Boolean combinations of objects (VROI and DVH of Normal Tissue-Target), and how voxels which belong to multiple structures are handled. | Incorrect complex VROI also leads to incorrect DVH. |
| Voxel dose interpolation | Verify accuracy of dose interpolated into each voxel. | Interpolation from one 3-D grid to another could lead to grid-based artifacts or inaccuracies. |
| Structure volume | Test accuracy of volume determination with irregularly shaped objects, since regular shapes (particularly rectangular objects) can be subject to numerous grid-based artifacts. | Structure volume is basis of much NTCP modeling. Also, volume may be directly used in physician plan evaluation considerations. |
| Histogram bins and limits | Verify that appropriate histogram bins and limits are used. | Inappropriate bins and/or limits to DVH can lead to misleading DVH. |
| DVH calculation | Test DVH calculation algorithm with known dose distributions. | Basic calculation must be sound, else incorrect clinical decisions about plan evaluation may result. |
| DVH types | Verify that standard (direct), differential, and cumulative histograms are all calculated and displayed correctly. | Each type of DVH display is useful in particular situations. |
| DVH plotting and output | Test DVH plotting and output using known dose distributions. | Hardcopy output must be correct, as this may be used for physician decision making. |
| Plan and DVH normalisation | Verify relationship of plan normalisation (dose) values to DVH results. | Plan normalisation is critical to the dose axis of the DVH. |
| Dose and VROI grid effects | Review and understand relationship of dose and VROI grids. | Grid-based artifacts can cause errors in volume, dose, DVH, and the evaluation of the plan. |
| Use of DVHs from different cases | Test correct use of DVHs from different cases with different DVH bin sizes, dose grids, etc. | Comparison of DVHs from different plans depends critically on bin sizes, etc. |

#### Table 9B. Other explicit DVH-related table entries and rows

| Source table | DVH-related entry | Content |
|---|---|---|
| Table 1-3: selected performance characteristics | DVH accuracy | Traditional system: `N/A`; 3D system: “Depends on many factors.” Commentary: DVH accuracy depends on dose calculation grid, volumetric ROI grid, accuracy of object segmentation, histogram bin size, and plan normalisation. |
| Table 2-2: acceptance test features | Dose display, dose volume histograms | Display dose calculation results. Use a standard dose distribution provided by the vendor to verify that the DVH code works as described. User-created dose distributions may also be used for additional tests. |
| Table 3-3: anatomical structure definitions | Region-of-interest (ROI) description | A voxel or surface description of each 3-D structure of interest. Used for calculation of dose volume histograms and other kinds of statistics. |
| Table 3-21: hardcopy output information | DVHs | Plot legend; scales and units; case, plan, and other identifying information; associated anatomical structure(s). |
| Table 5-1: periodic RTP process QA checks | Critical software tools (annual) | Review BEV/DRR generation and plot accuracy, CT geometry, density conversions, DVH calculations, other critical tools, machine-specific conversions, data files, and other critical data. |

#### Table 9C. Composite-plan DVH-relevant checks explicitly named in Section 3.7.4

| Composite-plan issue | TG-53 concern |
|---|---|
| Prescription bookkeeping | Dose prescription input for each component plan |
| Biology-aware accumulation | Availability of fractionation (`bio-effect`) corrections |
| Spatial accumulation | Interpolation of individual plan dose distributions onto a common grid |
| Unit consistency | Handling of plans with different dose units (for example %, daily dose, total dose, dose rate) |
| Numerical integrity | Accuracy of addition and subtraction |

### 10. Critical appraisal (100-200 words)

**Strengths:**
This is one of the clearest early QA documents to treat DVH generation as a distinct computational problem. Table 3-20 remains highly usable as a failure-mode checklist for a modern benchmark engine. The report is also strong in recognising that DVH error can arise from geometry, dose sampling, normalisation, comparison semantics, and output, not only from the dose algorithm.

**Weaknesses:**
It gives no reference algorithm, no numerical DVH tolerance, no bin-width recommendation, no interpolation rule, and no partial-volume method. It is therefore not sufficient on its own for implementing or validating a contemporary gold-standard calculator.

**Confidence in findings:** **High** for the qualitative QA requirements and failure modes; **medium** for any attempt to derive concrete modern tolerances from it.

**Relevance to reference DVH calculator:** **High**. TG-53 is not where one gets the final algorithm; it is where one gets the checklist of what the final algorithm must make explicit, test, and document.


---

<!-- Source: SUMMARY - Panitsa 1998 - Quality control of DVH computation characteristics of 3D TPSs.md -->

## Panitsa (1998) - Quality control of dose volume histogram computation characteristics of 3D treatment planning systems

### Executive summary

Panitsa et al. (1998) presented an early but still highly relevant quality-control framework for testing dose-volume histogram (DVH) computation in commercial 3D treatment planning systems. Rather than validating dose calculation itself, the study focused on whether DVH-derived quantities were internally consistent with each system’s own displayed isodose distributions. Across six commercial treatment planning systems, basic low-gradient quantities such as structure volume, minimum dose, and maximum dose were generally reproduced well, with most discrepancies below 1% and the largest reported discrepancy 3.4%. In contrast, a penumbra-focused high-gradient test showed much larger disagreement, with errors ranging from 0.5% to 27% for the volume between the 80% and 20% isodose levels.

The most important engineering message is that sparse sampling can produce apparently acceptable DVHs in low-gradient situations while failing badly in high-gradient regions. Systems using larger numbers of DVH calculation points generally performed better in the penumbra test, whereas the worst result came from a system using only 1000 sampling points. The paper also showed that Boolean structure operations such as addition and subtraction should be included in DVH QA, since derived structures are part of routine planning workflows.

For a modern reference-quality DVH engine, this paper supports three concrete design principles: first, avoid coarse fixed sampling as the default and instead use exact or adaptively refined partial-volume methods; second, validate with dedicated high-gradient and structure-algebra test cases rather than only simple whole-structure dose metrics; and third, record all DVH computation settings explicitly, because hidden choices in sampling density, interpolation, and contour handling materially affect results.

### 1. Bibliographic record

**Authors:** E Panitsa, J C Rosenwald, C Kappas
**Title:** *Quality control of dose volume histogram computation characteristics of 3D treatment planning systems*
**Journal:** *Physics in Medicine and Biology*
**Year:** 1998
**DOI:** [10.1088/0031-9155/43/10/010](https://doi.org/10.1088/0031-9155/43/10/010)
**Open access:** No

### 2. Paper type and scope

**Type:** Original research.
**Domain tags:** D1 Computation | D2 Commercial systems.
**Scope statement:** This paper proposes a practical quality-control protocol for DVH computation in 3D treatment planning systems and applies it to six commercial TPS participating in the EC Dynarad programme. The key idea is not independent dosimetric validation, but internal consistency testing: DVH-derived quantities are checked against values read from the same TPS isodose distributions, with particular emphasis on basic dose and volume statistics, high-gradient behaviour, and Boolean structure operations.

### 3. Background and motivation

By the late 1990s, DVHs had already become standard for 3D plan evaluation because they compress structure-wide dose information into a single curve and support judgement of coverage, uniformity, and hot and cold spots. The paper also notes that DVHs were already being used as the basis for biological reductions such as TCP and NTCP, which raises the stakes: a computationally inaccurate DVH can propagate error into downstream biological modelling even when the displayed dose distribution itself looks plausible.

The authors’ central complaint is that existing radiotherapy QA guidance at the time addressed general TPS commissioning and broader radiotherapy process QA, but did not give concrete QC procedures for advanced 3D features such as DVH computation. That gap matters because DVH error can arise not only from the dose engine, but also from sampling choices, interpolation, voxel and structure discretisation, capping, and user-selected calculation settings. Panitsa et al. therefore aim to create a simple, clinic-usable QC protocol requiring no new measurements beyond the beam data already in the TPS library, so centres can probe whether their DVH implementation behaves consistently under clinically typical settings.

For a modern reference DVH project, this paper is important because it frames DVH accuracy as a separate QA object rather than a passive by-product of dose calculation. It is especially relevant in showing that apparently acceptable agreement for gross DVH quantities can coexist with substantial error in high-dose-gradient regions, where the histogram is most sensitive to inadequate sampling density.

### 4. Methods: detailed technical summary

This was a multi-institutional technical intercomparison performed within the EC Dynarad (Biomed I) project, described as a three-year concerted action involving 32 institutions from 14 European countries. The DVH-specific study itself examined six commercial TPS from participating centres, with one additional centre using the same Helax version and obtaining the same results as centre B. The design is best classified as a simulation or phantom-based QC study rather than clinical or prospective research. No patient datasets were used.

All tests used the same simple homogeneous geometry: a water-like 15 × 15 × 15 cm³ phantom containing a centrally placed 5 × 5 × 5 cm³ structure of the same density, so the test structure volume was 125 cc. The beam arrangement used isocentric 10 × 10 cm² beams with the isocentre at phantom centre. A clockwise coordinate system was used, with the z-axis in the feet-head direction. Importantly, the protocol did not require additional measurements beyond the user’s existing beam data library. The reference for comparison was the TPS’s own isodose display, not independent measurements or analytical dose.

The protocol comprised four substantive checks grouped as A, B1, B2, and C. **Case A** tested basic DVH outputs: minimum dose (Dmin), maximum dose (Dmax), and structure volume. These were compared with values read from the isodose distribution for the same plan. Dmax was expected near the proximal side of the structure on the beam axis unless flattening-filter horns displaced it laterally; Dmin was generally expected at the distal side. This is conceptually a low-gradient basic-consistency test.

**Case B1** targeted high-dose-gradient behaviour using two opposed beams placed 5 cm off-axis so that the penumbra passed through the structure. [Exact beam energies per centre: DETAIL NOT REPORTED.] For each beam energy, the authors compared the structure volume lying between the 80% and 20% isodose contours from the isodose display with the corresponding DVH-derived volume. The isodose-derived penumbra volume was computed as `Vis = Dis * ystr * zstr`, where `Dis` is the 80%-to-20% separation and `ystr = zstr = 5 cm`; if `Dis` varied with position, the user estimated `Vis` from the x-y and y-z planes. The DVH-derived penumbra volume was taken from the cumulative DVH as `Vdvh = V(20%) - V(80%)`. A linear DVH fall-off through this interval was expected if the penumbra were represented correctly.

**Case B2** tested whether the DVH representation of penumbra was invariant to beam placement. The same opposed-beam concept was used, but the beams were placed 4, 5, 6, and 7 cm off-axis in both x and z directions. The expectation was that the DVH slope representing the penumbra should remain unchanged as long as the penumbra remained fully inside the structure. **Case C** tested Boolean structure operations. Two equal substructures S1 and S2 of size 5 × 2.5 × 5 cm³ were created, plus a summed structure `SS = S1 + S2`. The TPS should give identical cumulative and differential DVHs for SS and for the addition of S1 and S2; similarly, the DVH of S1 should match the DVH of `SS - S2`.

The six TPS and their user-selected DVH computation settings were: **Isis-3D v2.0** with random-point sampling and 2000 points; **Helax TMS 3.0A** with grid sampling and 4400 points, 0.25 cm grid step and 11 slices; **Dosigray** with combined sampling and 31,250 points, using random `x,y` and gridded z; **Focus rpl 1.3.0** with grid sampling and 125,000 points, 0.1 cm DVH grid and dose interpolation from a 0.3 cm dose table; **Plato v1.4** with combined sampling and 100,000 points, random `x,y`, gridded z, and random sampling inside a box enclosing the structure; and **Cadplan 2.62 R 2.00A** with grid sampling, 1000 points, and 0.5 cm grid step. The authors explicitly chose not to standardise these settings; each centre used parameters representative of routine clinical use. That makes the study more realistic as a QC survey, but less suitable for fair algorithm-to-algorithm comparison.

Several methodological details crucial to modern DVH validation were **[DETAIL NOT REPORTED]**: dose algorithm type and version for each TPS, energy list by centre beyond examples such as Co-60 and 12 MV, dose normalisation, isodose computation grid settings, DVH bin width, partial-volume weighting rule, end-capping method, contour interpolation between slices, and any inferential statistics. The authors also acknowledge three important limitations: the isodose reference itself may be imperfect; some measurements (Dmin, Dmax, `Vis`) are manually read and thus uncertain; and the protocol deliberately leaves the number and placement of contour slices unspecified, which both preserves flexibility and exposes structure-capping sensitivity.

### 5. Key results: quantitative

For **Case A** (basic DVH statistics), agreement was generally good. Across all systems and all three quantities (Dmax, Dmin, volume), the largest reported variation was 3.4%, and most variations were less than 1% relative to the isodose-derived reference. Visual reading of the page-7 histogram suggests the largest single discrepancy was centre D, Dmin about 3.4%, while other notable deviations were centre B volume about 2.4% and centre D volume about 1.6%. Approximate centre-level values from the figure are: A **0.18/0.24/0.37%** for `Dmax/Dmin/volume`; B **0.62/0.82/2.42%** C **0.19/0.62/~0%** D **0.89/3.43/1.62%** E **0.05/0.30/0.57%** and F **0.99/1.01/~0%**. These are approximate because the authors did not tabulate the bar heights numerically.

For **Case B1** (penumbra or high-gradient volume), performance deteriorated sharply. The paper reports a variation range of 0.5% to 27% for the volume between the 80% and 20% isodoses. The authors give two explicit examples: centre A showed 0.5% error for a Co-60 beam and 14% for a 12 MV beam, demonstrating strong energy dependence within the same TPS and settings; centre F showed the worst result, 27%, and this centre used only 1000 DVH calculation points. Visual reading of the page-8 histogram suggests approximate per-centre ranges of A **0.5-14.0%** across six energies, B **2.2-12.5%** across three energies, C **0.7-2.7%**, D **0.9-2.2%**, E **2.0-6.7%**, and F **27.6%** for one energy. With the exception of centre F, the other systems stayed roughly within 10% or less according to the authors’ narrative, although the figure suggests some A and B bars slightly above that level.

For **Case B2**, all tested systems that actually performed the test were marked **OK**: the DVH penumbra slope stayed the same when the beam offset changed from 4 to 7 cm along both x and z, indicating no detected dependence on relative beam positioning within this simple geometry. For **Case C**, structure addition and subtraction worked correctly whenever implemented. Exact outcomes were: centre A **B2 OK**, **subtraction OK**, addition not performed; centre B **B2 OK**, **addition OK**, subtraction not performed; centre C **all OK** centre D addition and subtraction **OK**, B2 not performed; centre E **B2 OK**, but no direct DVH was produced for addition, so `DVH(S1)+DVH(S2)` was added manually and matched DVH(SS); centre F behaved similarly to E for addition, with B2 and subtraction not performed.

The authors interpret the pattern across figures 3 and 4 together with table 1 as evidence that number of calculation points matters much more in high-gradient regions than in low-gradient ones. High-point systems (centres C, D, E) generally had better B1 results than low-point systems (A, B, F). They also argue that in lower-gradient situations, random or mixed sampling (A, C, E) appeared somewhat better than pure grid sampling (B, D, F), although all systems were already within clinically small error for Case A. This latter claim is plausible but only suggestive, because the study did not hold beam energies, dose grids, or sampling densities constant across systems. No p-values, confidence intervals, or formal effect sizes were reported.

### 6. Authors' conclusions

The authors conclude that their DVH QC protocol is practical, user-friendly, and suitable as part of a broader 3D TPS QA programme. They argue that, under typical clinical settings, the examined TPS were generally consistent with their own isodose displays for basic DVH statistics and structure algebra, but that high-gradient regions require special caution because errors can become much larger there, especially when too few calculation points are used. They therefore recommend using a high number of calculation points when DVHs are evaluated in high-gradient situations or used for downstream quantities such as TCP and NTCP.

That overall interpretation is well supported for the narrow claim of self-consistency testing within the paper’s phantom geometries. The stronger implication that certain sampling methods are intrinsically better is less secure, because settings were not standardised and the comparison is confounded by TPS-specific implementation details, beam energies, and dose interpolation schemes. Likewise, the paper does not demonstrate absolute DVH correctness against an independent reference; it demonstrates whether the DVH agrees with the same system’s isodose display under selected conditions.

### 7. Implications for reference DVH calculator design

#### 7a. Algorithm and implementation recommendations

A reference-quality DVH calculator should treat this paper as a warning against sparse sampling in high-gradient regions. In this simple 125 cc cube, clinically chosen settings produced penumbra-volume discrepancies from 0.5% to 27%; the worst-performing system used only 1000 points and a 0.5 cm grid step, while better systems used much denser sampling or finer DVH grids. The practical implication is that a benchmark calculator should not rely on coarse fixed grid sampling as its default. It should implement either exact voxel and ROI intersection with partial-volume weighting, or at minimum adaptive subvoxel supersampling driven by local dose gradient and boundary complexity, with deterministic reproducibility and convergence reporting.

The implementation should also decouple dose interpolation resolution from DVH accumulation resolution and log both explicitly. Focus, for example, used a 0.1 cm DVH grid but interpolated from a 0.3 cm dose table, showing that fine DVH sampling can still sit on top of a coarser dose representation. The calculator should expose traceable metadata for dose grid, interpolation rule, structure rasterisation and capping method, supersampling level, Boolean structure construction, and binning. Support for both cumulative and differential DVHs and exact structure union and subtraction is mandatory, because the paper tests all of these explicitly.

#### 7b. Validation recommendations

Panitsa’s phantom should be reproduced almost verbatim as a baseline regression test: homogeneous 15 cm water cube, central 125 cc cube, 10 × 10 cm² isocentric field, then the four checks A, B1, B2, and C. In particular, the off-axis opposed-beam penumbra case is a strong failure-mode test for sampling inadequacy and should be included in every validation suite. A modern extension should replace same-TPS isodose reading with independent analytical or ultra-high-resolution reference solutions, so the benchmark addresses absolute accuracy rather than self-consistency. Useful acceptance targets suggested by this paper are roughly at or below 1% disagreement for low-gradient basic volume and dose statistics, and substantially tighter performance than the up to 27% seen here in high-gradient volume tests. The discussion’s ICRU context suggests aiming for something closer to less than 2% or less than 2 mm in gradient-sensitive situations when benchmarked against proper ground truth.

A modern validation suite should also add test cases that this paper leaves untouched: very small structures, irregular or concave contours, oblique contours to the dose grid, anisotropic voxels, heterogeneous media, non-cubic derived ROIs, and explicit slice end-capping stress tests. Case C also argues for dedicated validation of ROI Boolean algebra because errors there can corrupt downstream ring, shell, or avoidance-structure metrics even when the raw DVH engine is sound.

#### 7c. Extensibility considerations

The paper explicitly notes that DVHs feed TCP and NTCP calculations, so a reference engine should not stop at cumulative DVH generation. It should expose a stable representation of the underlying dose-volume pairs and support differential DVH generation, because both are needed for biological reduction and were part of the authors’ testing framework. Case C also motivates a generalised ROI algebra layer so derived structures can be built reproducibly and passed downstream to biological or geometric metrics without ad hoc recontouring.

Beyond classic DVH, the architectural lesson is to preserve enough geometric and dosimetric fidelity that later modules can compute EUD or gEUD, probabilistic or uncertainty-aware DVHs, and related histograms such as surface- or mass-based variants. Panitsa et al. do not study those directly, but their core finding; that histogram accuracy depends on sampling, boundary handling, and structure operations; applies equally to any downstream metric built on the same data structures.

#### 7d. Caveats and limitations

The biggest caveat is that this is a same-system consistency test, not an external truth test. If a TPS used the same interpolation assumptions in both its isodose display and DVH engine, a shared bias could go undetected. The homogeneous cube geometry is deliberately simple and does not probe clinically important edge cases such as irregular anatomy, slice anisotropy, heterogeneous density, or modulated fields. Also, because users selected their own typical DVH settings, the study mixes together algorithm design and configuration choice. That makes the results highly relevant for clinical QA, but less definitive for pure algorithm ranking.

A second caveat is under-reporting. Key parameters such as dose algorithm, exact energies per centre, bin width, partial-volume method, and capping behaviour are **[DETAIL NOT REPORTED]**. The reference calculator should therefore avoid inheriting these assumptions and instead make them explicit, user-visible, and testable.

### 8. Connections to other literature

- **Drzymala et al. (1991), _Dose-volume histograms_** foundational DVH background paper that established the role of DVHs in plan evaluation and is directly aligned with the motivation of this study.
- **Niemierko and Goitein (1990), _Random sampling for evaluating treatment plans_** direct methodological precursor for the paper’s discussion of random sampling and point density in treatment plan evaluation.
- **Lu and Chin (1993), _Sampling techniques for the evaluation of treatment plans_** another explicit antecedent on sampling strategy that Panitsa et al. use to frame DVH computation accuracy.
- **Van Dyk et al. (1993), _Commissioning and quality assurance of treatment planning computers_** broader TPS QA framework that Panitsa et al. argue did not yet provide sufficiently specific DVH-focused QC procedures.
- **Kutcher et al. (1994), _Comprehensive QA for radiation oncology: report of AAPM TG-40_** similarly a broad QA document positioned by the authors as insufficiently detailed for advanced 3D DVH functionality.
- **Gossman et al. (2010), _Dose-volume histogram quality assurance for linac-based treatment planning systems_** important later companion work that extended DVH QA toward independent geometry-based checking rather than same-TPS self-consistency.
- **Ebert et al. (2010), _Comparison of DVH data from multiple radiotherapy treatment planning systems_** later multi-system work relevant to inter-system variability and independent recalculation of DVH data.
- **Nelms et al. (2015), _Methods, software and datasets to verify DVH calculations against analytical values: twenty years late(r)_** modern analytical benchmark framework that can be read as addressing the limitations already visible in Panitsa et al.

### 9. Data extraction table

The first two tables below transcribe numerical and configuration data explicitly reported in the paper; the figure tables are approximate visual digitisation from the bar charts on pages 7 and 8 because the authors did not tabulate those values numerically.

#### Table 9a. DVH computation settings used in the intercomparison

| Centre | TPS | Sampling method | No. of calculation points in 125 cc structure | Nominal points/cc [derived] | Comments |
|---|---|---:|---:|---:|---|
| A | Isis-3D v2.0 | Random points | 2,000 | 16.0 | No further comment reported |
| B | Helax TMS 3.0A | Grid | 4,400 | 35.2 | Grid step **0.25 cm**, **11 slices** |
| C | Dosigray | Combination | 31,250 | 250.0 | Random sampling for x and y; z defined by a grid |
| D | Focus rpl 1.3.0 | Grid | 125,000 | 1000.0 | DVH grid step **0.1 cm** dose interpolated from dose table with grid step **0.3 cm** |
| E | Plato v1.4 | Combination | 100,000 | 800.0 | Random `x,y`; z by grid; random sampling in a box enclosing the structure, so effective points are lower for irregular shapes |
| F | Cadplan 2.62 R 2.00A | Grid | 1,000 | 8.0 | Grid step **0.5 cm** |

#### Table 9b. Exact reported outcomes for test cases B2 and C

| Centre | B2: offset beam | C: addition | C: subtraction |
|---|---|---|---|
| A | OK | ;  | OK |
| B | OK | OK | ;  |
| C | OK | OK | OK |
| D | ;  | OK | OK |
| E | OK | * | ;  |
| F | ;  | * | ;  |

*`OK` = performed as expected; `; ` = not performed; `*` = no DVH produced directly for addition, but manual sum of DVH(S1) and DVH(S2) matched DVH(SS).*

#### Table 9c. Case A figure extraction [VISUALLY DIGITISED FROM FIGURE 3; approximate]

| Centre | Dmax variation (%) | Dmin variation (%) | Volume variation (%) |
|---|---:|---:|---:|
| A | 0.18 | 0.24 | 0.37 |
| B | 0.62 | 0.82 | 2.42 |
| C | 0.19 | 0.62 | ~0.00 |
| D | 0.89 | 3.43 | 1.62 |
| E | 0.05 | 0.30 | 0.57 |
| F | 0.99 | 1.01 | ~0.00 |

#### Table 9d. Case B1 figure extraction [VISUALLY DIGITISED FROM FIGURE 4; approximate]

| Centre | No. of energies shown | Approximate variation of penumbra volume (%) |
|---|---:|---|
| A | 6 | 0.5, 4.7, 13.4, 14.0, 11.9, 7.5 |
| B | 3 | 2.2, 10.4, 12.5 |
| C | 3 | 0.7, 0.8, 2.7 |
| D | 3 | 0.9, 1.8, 2.2 |
| E | 2 | 2.0, 6.7 |
| F | 1 | 27.6 |

### 10. Critical appraisal

**Strengths:** The paper is methodologically simple but highly useful: it isolates DVH computation as a QC target, uses a reproducible homogeneous phantom, tests both low- and high-gradient situations, records the actual commercial settings used, and includes ROI addition and subtraction rather than only basic DVH outputs. The multi-vendor design makes the conclusions clinically relevant.

**Weaknesses:** The reference is not independent; it is the same TPS isodose display. The geometry is simple and homogeneous. Important computational details are **[DETAIL NOT REPORTED]**, and the comparison is confounded by user-selected settings, beam-energy differences, and vendor-specific dose interpolation. No inferential statistics are presented.

**Confidence in findings:** **Medium.** There is high confidence in the qualitative result that DVH errors worsen in high-gradient regions and with sparse sampling, because the signal is large and consistent with later literature such as Nelms et al. (2015). There is only moderate confidence in any precise algorithm-ranking implication, because the study design does not isolate algorithm from configuration.

**Relevance to reference DVH calculator:** **High.** This paper directly motivates benchmark tests for gradient sensitivity, sampling convergence, Boolean structure handling, and traceable reporting of DVH computation settings. Even though it is not an independent ground-truth study, it remains a valuable early map of the failure modes a gold-standard DVH engine must eliminate; later QA work such as Gossman et al. (2010) extends these ideas toward stronger external benchmarking.

---

<!-- Source: SUMMARY - Corbett 2002 - The effect of voxel size on the accuracy of DVHs of prostate I-125 seed implants.md -->

## Corbett (2002) - The effect of voxel size on the accuracy of dose-volume histograms of prostate 125I seed implants

### Executive summary

Corbett et al. (2002) examined how dose-grid voxel size affects cumulative dose-volume histogram (DVH) accuracy in permanent prostate I-125 seed brachytherapy, with particular emphasis on hotspot metrics such as V200. Using an in-house MATLAB TG43-based calculator, a hand-computable single-seed benchmark, five clinical prostate implant plans, and comparisons against VariSeed 6.7, the authors showed that V200 is far more sensitive to spatial discretisation than V150 or V100.

The most practically important findings were that **1 mm isotropic voxels** were sufficient to keep prostate V200 within **±5%** of the authors’ 0.5 mm internal reference for the five clinical many-seed plans studied, whereas coarser grids produced large errors: the RMS error in V200 rose to **27% at 2.5 mm** and **69% at 5 mm**. By contrast, V150 remained within **±5%** using **3 mm** voxels, and V100 remained within **±1%** up to **5 mm**. This establishes a clear gradient of discretisation sensitivity: **V200 >> V150 > V100**.

The paper is also notable for exposing likely vendor-specific implementation behaviour. VariSeed 6.7 reported prostate V200 values that were typically **30-43% larger** than the authors’ fine-grid in-house calculation, and its behaviour was closely reproduced by an anisotropic **1×1×5 mm³** voxel scheme rather than a truly isotropic 1 mm grid. This implies that nominal UI grid settings in commercial systems may not fully describe the actual DVH sampling algorithm.

For a reference-quality DVH calculator, the paper strongly supports metric-aware convergence testing, explicit handling of grid-phase effects, independent validation against analytical benchmarks, and provision of both a high-accuracy reference mode and a commercial-system emulation mode. It is especially relevant for any implementation intended to serve as an independent benchmark for brachytherapy DVH validation.

### 1. Bibliographic record

**Authors:** Jean-François Corbett, John Jezioranski, Juanita Crook, Ivan Yeung
**Title:** *The effect of voxel size on the accuracy of dose-volume histograms of prostate 125I seed implants*
**Journal:** *Medical Physics*
**Year:** 2002
**DOI:** [10.1118/1.1477417](https://doi.org/10.1118/1.1477417)
**Open access:** No. The publisher listing is an abstract/full-text access page, and the PubMed record links out to Wiley/Ovid rather than a PMC free full-text version.

### 2. Paper type and scope

**Type:** Original research

**Domain tags:** D1 Computation | D2 Commercial systems

**Scope statement:**
This paper quantifies how dose-grid voxel size affects cumulative DVH accuracy in permanent prostate I-125 seed brachytherapy, with particular attention to the hotspot metric V200. It also uses an independent in-house TG43-based calculator to probe the effective behaviour of the commercial VariSeed 6.7 DVH implementation, making it directly relevant both to reference-calculator design and to vendor-system validation.

### 3. Background and motivation (150-300 words)

In permanent prostate brachytherapy, postimplant evaluation relies heavily on cumulative DVH metrics such as V100, V150, and especially V200. By the time of this paper, the American Brachytherapy Society had already recommended dose-calculation matrix resolutions of **2 mm or less**, reflecting the steep dose gradients around I-125 sources. What had not been quantified well was how fine the dose grid actually needed to be for clinically reported hotspot metrics, particularly V200, which corresponds here to **200% of the 145 Gy prescription dose**, that is **290 Gy**. Because that volume is confined to small regions immediately around seeds, it is intrinsically more sensitive to discretisation than lower-dose coverage metrics.

The problem is not merely theoretical. A commercial treatment planning system may report a seemingly precise DVH, yet the underlying spatial sampling scheme can bias the reported fractional volumes. For a reference-quality DVH engine, this is exactly the failure mode that must be controlled: one needs to disentangle dose-model error, structure discretisation error, and histogramming error. Corbett et al. therefore set out to build an independent MATLAB calculator, validate it against a hand-computable single-seed case, and then quantify voxel-size effects in five prostate implant plans while also benchmarking against VariSeed 6.7. The paper is an early, compact study of discretisation sensitivity in a small-volume, high-gradient brachytherapy setting.

### 4. Methods: detailed technical summary (400-800 words)

The study is best viewed as a mixed **analytical + retrospective plan-based + simulation** investigation. The authors wrote an in-house seed dose calculation program in MATLAB, based on the TG43 formalism. The output of interest was the **cumulative** DVH. Their voxel-wise histogramming rule was simple but important: for a given dose threshold, the **fraction of each voxel volume lying inside the structure** was added to the cumulative bin **if the dose at the voxel centre exceeded the threshold**. In modern numerical terms, this is a structure-weighted midpoint-rule classifier. It accounts for partial-volume inclusion of the structure boundary, but it does **not** account for subvoxel dose variation within the voxel. The paper does **not** report the dose bin width, number of bins, any dose interpolation inside a voxel, any subvoxel supersampling, or the exact method used to compute voxel-structure overlap fractions; these are all **[DETAIL NOT REPORTED]**.

For the **single-source validation**, the authors deliberately simplified the geometry to permit hand calculation. They used a **single 0.4-U I-125 model 6711 seed** in a very large volume and performed dose calculations with a **point-source approximation** and the TG43 anisotropy constant, so that isodose surfaces became spherical. The hand-calculated cumulative DVH was generated for doses from **20 Gy to 800 Gy**. This analytic or hand reference was compared against the in-house algorithm at **0.1 mm** and **0.5 mm** resolution, and against VariSeed at **0.5 mm**, which the paper states was the finest setting available in that system. This is an elegant benchmark because it isolates DVH discretisation from the complexities of contour interpolation or multi-seed superposition.

For the **clinical calculations**, the authors randomly selected **five** patients who had received permanent prostate implants with I-125 model 6711 seeds. The plans contained **96-118 seeds** with a **median of 104**, all at **0.4 U** air-kerma strength. Prostate volumes ranged from **33.2 to 48.3 cc** with a **median of 41.6 cc**. The input data were not postimplant CT reconstructions; rather, the authors imported **planned seed coordinates** and **preimplant prostate contours** from planning-system files. The prostate volume was represented slice by slice: each contour slice was treated as a straight extruded slab of **5 mm** thickness, equal to the spacing between ultrasound images. No between-slice contour interpolation beyond this slab model is described, and superior or inferior end-capping rules are **[DETAIL NOT REPORTED]**. This means the study jointly reflects dose-grid discretisation and a relatively coarse slice-based structure representation.

Dose distributions for the five clinical plans were then calculated at resolutions from **0.5 mm to 5 mm**, with the calculation grid both **aligned** with the seed implant planes and **offset by half a voxel** in **x**, **y**, and **z**. The main evaluated metric was V200, with similar analyses for V150 and V100. For each patient, the **average** of the aligned and offset V200 values at **0.5 mm** was taken as the **reference V200**, and coarser-grid results were compared to that reference. The agreement metric was the **root-mean-square (RMS) percentage error across all five patients**. No p-values, confidence intervals, or formal hypothesis tests were reported. The exact RMS formula is **[DETAIL NOT REPORTED]**.

To interrogate VariSeed, the authors also computed dose distributions with anisotropic voxels of **1×1×5 mm³**, with the **z** coordinates of grid points coincident with the **5 mm**-spaced implant planes. They compared the resulting prostate DVHs with those generated by VariSeed. To push this further, they created **artificial plans** in VariSeed with **1 to 153 seeds** placed in a **40×40×30 mm³** rectangular box and compared VariSeed DVHs against in-house calculations using both **`1×1×1 mm³`** and **1×1×5 mm³** voxels. The aim was effectively reverse engineering: identify what voxel geometry most closely reproduced the commercial system. The paper notes that “several DVH algorithms and voxel shapes were attempted”, but those unsuccessful alternatives are **[DETAIL NOT REPORTED]**.

Dose calculation details beyond the statement “based on TG43” are sparse. For the single-seed validation, the point-source approximation is explicit. For the full clinical calculations, the paper does **not** clearly state whether a point-source or line-source formulation was used, how source orientation was handled, which specific TG43 parameter set was implemented for the 6711 source, or whether any heterogeneity or interseed attenuation corrections were considered; practically, this should be interpreted as a conventional water-based TG43 calculation with **no heterogeneity correction**, but some implementation details remain **[DETAIL NOT REPORTED]**.

### 5. Key results: quantitative (300-600 words)

The **single-seed benchmark** established both the utility and the limitation of simple voxelised DVH computation. Against the hand-calculated reference, the in-house algorithm at **0.1 mm** agreed within **±1% up to 300 Gy** and within **±3% up to 800 Gy**. At **0.5 mm**, agreement remained within **±5% below 100 Gy**, but the high-dose tail became visibly coarse. The log-scale single-seed figure on page 3 makes the scale problem intuitive: the **300 Gy** isodose sphere has a radius of only about **1.5 mm**, so a few tenths of a millimetre of phase or voxel-size error materially changes the enclosed volume. In contrast, VariSeed at its finest **0.5 mm** setting substantially deviated from the hand calculation: it **underestimated** low-dose volume below **120 Gy**, by as much as **50% at about 31 Gy**, and **overestimated** high-dose volume by **more than 50% above 250 Gy**.

The authors explicitly explain the phase-aliasing mechanism for the single-seed case. When the seed lies at the **centre** of a voxel, the highest-dose bin can be overestimated by **one voxel volume** and the next bin underestimated by **six voxels** when the seed lies on **voxel corners**, the highest-dose bin can collapse to **zero** and the next bin be overestimated by **eight voxels**. This is a valuable result for validation design: the error is not just smoothing, it is strong **grid-phase dependence**.

For the **five clinical plans**, the in-house reference at **0.5 mm** had a quoted precision of **0.35%** for V200, supporting its use as an internal benchmark. Using this benchmark, **1 mm isotropic voxels** were sufficient to keep V200 within **±5%**. Coarser isotropic grids failed quickly: the RMS error in V200 was **27% at 2.5 mm** and **69% at 5 mm**, with the sign of the error described as randomly distributed. The lower-dose metrics were much more robust: V150 stayed within **±5%** using **3 mm** voxels, and V100 remained within **±1%** for all voxel sizes tested up to **5 mm**. The page 4 RMS plots therefore show a clear sensitivity ranking: **V200 >> V150 > V100**.

The comparison with VariSeed 6.7 is the paper’s other major quantitative result. Relative to the **small-voxel in-house reference**, the abstract reports VariSeed V200 values **30-43% larger** the Results text broadens this to **30-50% larger**. The Conclusions then state that the in-house V200 values were typically **25-30% lower** than VariSeed. These are not completely contradictory because they use different denominators: “25-30% lower than VariSeed” corresponds to roughly **33-43% higher** when the denominator is the in-house reference. The broader **30-50%** statement in the Results remains somewhat looser, but the core finding is unmistakable: VariSeed systematically reported a substantially larger high-dose prostate subvolume than the fine-grid in-house method.

The reverse-engineering exercise strongly suggested that VariSeed’s nominal “1 mm” DVH setting behaved, for many-seed plans, like **1×1×5 mm³** voxel sampling with plane locations tied to the implant slices. For all **five** patients, the DVH from **1×1×5 mm³** voxels was described as **almost identical** to VariSeed’s DVH at its **1 mm** setting. The same was true for artificial plans with **more than 45 seeds** the page 4 example with **69 seeds** shows near-superposition. However, this emulation broke down for sparse implants: for a **single seed** or **fewer than 10 seeds**, the 1×1×5 mm³ approximation was not good and could be **up to 80% higher near 100% dose** than VariSeed. No formal whole-curve distance metric was reported; agreement here is based on visual comparison plus the stated hotspot discrepancies.

### 6. Authors' conclusions (100-200 words)

The authors conclude that, for prostate 125I seed implants, a **1 mm** dose grid is sufficient to achieve DVH accuracy within **±5%** up to **200% of prescription dose**, and that VariSeed 6.7 reports V200 values materially higher than their small-voxel in-house calculation. They further conclude that a **1×1×5 mm³** voxel geometry reproduces VariSeed’s behaviour well for most patient plans, implying an effective sampling scheme linked to the spacing of transverse implant planes.

These conclusions are reasonably supported **within the limits of the study design**: five many-seed prostate plans, a TG43-based in-house reference, and a 0.5 mm internal benchmark. The strongest conclusion is the relative sensitivity of V200 to discretisation and the likelihood that VariSeed’s effective DVH sampling is anisotropic in the superior-inferior direction. The broader suggestion that doses above **200%** are of limited clinical importance is more context-dependent and less secure for modern applications that scrutinise hotspot tails, extreme dose metrics, or derived radiobiological endpoints.

### 7. Implications for reference DVH calculator design (300-600 words)

#### 7a. Algorithm and implementation recommendations

A reference-quality calculator should **not** adopt the paper’s voxel-centre threshold rule as its final gold-standard implementation. Corbett et al. show that even **0.5 mm** sampling can be inadequate in a single-seed high-gradient field, and they explicitly demonstrate severe **grid-phase dependence**. Their method is appropriate as an independent comparator to a commercial TPS, but a benchmark calculator should go further: exact or adaptive structure intersection, subvoxel dose integration or adaptive supersampling, and explicit convergence testing for requested metrics. The evidence here argues for **metric-aware refinement**: V100 is relatively insensitive, V150 moderately so, and V200 highly sensitive.

The calculator should also separate **reference mode** from **TPS-emulation mode**. Reference mode should use isotropic or adaptive 3D refinement until volume-at-dose metrics converge to a tight tolerance. A practical fast mode for prostate LDR brachy could plausibly use **1 mm isotropic** sampling for V200-level accuracy within **±5%**, because that is what this paper found for five representative many-seed plans. But the reference engine should default to stricter convergence, not to the minimum clinically tolerable grid. In parallel, an emulation layer should allow anisotropic plane-based sampling such as **1×1×5 mm³**, because this study shows that vendor DVH behaviour may depend more on undocumented sampling geometry than on the nominal resolution label shown in the UI.

A further implementation lesson is reporting discipline. Because this paper expresses the VariSeed discrepancy both as **30-43% larger** and **25-30% lower**, depending on denominator, a reference calculator should always state the **reference denominator explicitly** in comparison reports.

#### 7b. Validation recommendations

This paper suggests a very strong validation suite. First, include a **single-source analytic benchmark** in a very large structure, where isodose surfaces are spherical and cumulative volume above threshold is analytically known. Use thresholds spanning at least **20-800 Gy**, with emphasis around **30 Gy**, **100 Gy**, **250-300 Gy**, since those are the regions where the paper observed breakdown. Second, include **grid-phase tests**: source at voxel centre, face, edge, and corner; and aligned versus half-voxel-shifted grids in all three axes. Those tests directly expose the aliasing mechanism the authors describe.

Third, include **multi-seed synthetic boxes** with low seed counts and high seed counts. The paper’s **1-153 seed** artificial-plan series is useful because it separates sparse from dense-source behaviour; a good validation set should intentionally include the failure regime **fewer than 10 seeds** and the many-seed regime **more than 45 seeds**. Fourth, include realistic prostate contour sets at **5 mm** slice spacing and thinner-slice variants, so that dose-grid sensitivity can be separated from contour-interpolation sensitivity. The paper does **not** provide public datasets or code, so these cases would need to be recreated independently. As tolerances, the paper supports using **±5% for V200** and **±1% for V100** as practical clinical-mode expectations in this specific LDR prostate context; for a true reference calculator, tighter internal convergence tolerances should be imposed and the final reported values should be accompanied by a convergence or uncertainty estimate.

#### 7c. Extensibility considerations

Although the paper studies only cumulative DVH, its core message generalises to any metric driven by **small volumes in steep gradients**. A reference engine should therefore store enough geometric and dosimetric detail to support not only Vx and Dx, but also **differential DVH**, **EUD/gEUD**, small-volume maxima such as D0.03cc, hotspot clustering metrics, and downstream radiobiological overlays. The same discretisation sensitivity that corrupts V200 will affect any high-dose-tail statistic. For future support of **DSH**, **DMH**, and dosiomics-like descriptors, the internal representation should preserve structure geometry separately from dose-sampling decisions and make subvoxel refinement reusable across histogram types.

A particularly useful extension would be **uncertainty-aware DVH reporting**: the calculator could expose a discretisation uncertainty estimated from adaptive refinement and or phase-shift ensembles, analogous in spirit to the aligned or offset averaging used here for the V200 reference.

#### 7d. Caveats and limitations

The main caveat is generalisability. The “**1 mm is enough**” result is based on only **five** prostate plans from a single institution, all with relatively dense many-seed implants and slice-based **5 mm** contour extrusion. It is **not** an exact clinical ground truth, because the reference is an internal **0.5 mm** voxel average, not an analytic solution, and the in-house algorithm itself uses centre-dose thresholding. The study also uses planned rather than true postimplant geometry, omits heterogeneity or model-based dose calculation, does not report runtimes, and leaves several implementation details unspecified. A reference DVH calculator should therefore treat Corbett et al. as strong evidence about **failure modes and validation design**, but only medium-strength evidence for any universal numerical threshold.

### 8. Connections to other literature

- **Nath et al. (1995)** This is the TG43 dosimetry foundation on which Corbett et al. built their in-house dose engine.
- **Nag et al. (2000)** The American Brachytherapy Society recommendations are the immediate clinical motivation for the paper’s focus on matrix size and on V100, V150, and V200.
- **Gossman et al. (2014)** [Not in project corpus] ;  Later brachytherapy DVH commissioning work extends the same core idea: independent validation of vendor DVH behaviour rather than blind acceptance of TPS outputs.
- **Gossman et al. (2016)** [Not in project corpus] ;  The addendum on brachytherapy DVH commissioning should be read alongside Corbett because it systematises QA processes that Corbett explored in an earlier, narrower form.
- **Stanley et al. (2021)** Although in stereotactic radiosurgery rather than brachytherapy, this later work on small-volume dose-metric accuracy is conceptually very close: discretisation error grows as clinically relevant volumes shrink.
- **Grammatikou et al. (2025)** A modern analogue in intracranial SRS that uses analytical ground truth and clinical cases to validate DVH accuracy under spatial discretisation, effectively revisiting Corbett’s problem in a different modality.

### 9. Data extraction table

The tables below extract the paper’s explicitly reported quantitative values and a small amount of directly stated figure-summary information from pages 3-5. No exact per-patient V100, V150, or V200 values or full curve coordinates were published.

**Table 1. Study and dataset characteristics**

| Item | Value |
|---|---:|
| Clinical patient plans | **5** |
| Implant type | Permanent prostate I-125 model 6711 seed implants |
| Seeds per plan | **96-118** (median **104**) |
| Seed strength | **0.4 U** |
| Prostate volume | **33.2-48.3 cc** (median **41.6 cc**) |
| Ultrasound / contour slice spacing | **5 mm** |
| Clinical grid resolutions tested | **0.5-5 mm** |
| Artificial-plan seed counts | **1-153** |
| Artificial-plan box dimensions | **40×40×30 mm³** |

**Table 2. Main quantitative findings**

| Scenario | Quantity / condition | Reported result | Reference denominator / note |
|---|---|---:|---|
| Single seed, in-house | DVH agreement at **0.1 mm**, doses up to **300 Gy** | **±1%** | Versus hand calculation |
| Single seed, in-house | DVH agreement at **0.1 mm**, doses up to **800 Gy** | **±3%** | Versus hand calculation |
| Single seed, in-house | DVH agreement at **0.5 mm**, doses below **100 Gy** | **±5%** | Versus hand calculation |
| Single seed, VariSeed | Low-dose discrepancy near **31 Gy** | **up to 50% lower** | Versus hand calculation |
| Single seed, VariSeed | High-dose discrepancy above **250 Gy** | **more than 50% higher** | Versus hand calculation |
| Clinical plans | V200 reference precision at **0.5 mm** | **0.35%** | Based on aligned or offset reference |
| Clinical plans | V200 accuracy with **1 mm** isotropic voxels | **within ±5%** | Versus 0.5 mm internal reference |
| Clinical plans | V200 RMS error at **2.5 mm** | **27%** | Versus 0.5 mm internal reference |
| Clinical plans | V200 RMS error at **5 mm** | **69%** | Versus 0.5 mm internal reference |
| Clinical plans | V150 accuracy with **3 mm** voxels | **within ±5%** | Versus 0.5 mm internal reference |
| Clinical plans | V100 accuracy with voxel sizes up to **5 mm** | **within ±1%** | Versus 0.5 mm internal reference |
| VariSeed vs in-house | V200 difference | **30-43% higher** | VariSeed relative to small-voxel in-house reference (abstract) |
| VariSeed vs in-house | V200 difference | **30-50% higher** | VariSeed relative to small-voxel in-house reference (Results text) |
| In-house vs VariSeed | V200 difference | **25-30% lower** | In-house relative to VariSeed (Conclusions; different denominator) |
| VariSeed emulation | 1×1×5 mm³ vs VariSeed for patient plans | “Almost identical” | Qualitative whole-curve agreement |
| Artificial plans | 1×1×5 mm³ emulation valid for | **more than 45 seeds** | Qualitative whole-curve agreement |
| Artificial plans | 1×1×5 mm³ vs VariSeed for sparse plans | **up to 80% higher near 100% dose** | For single seed or **fewer than 10 seeds** |

### 10. Critical appraisal (100-200 words)

**Strengths:** The paper has an unusually clear validation logic for its era: an analytic single-seed benchmark, explicit grid-alignment or offset testing, clinically relevant hotspot metrics, and a direct challenge to a commercial TPS rather than treating it as ground truth. The aliasing explanation around seed-centre versus seed-corner placement is particularly useful for engineering validation.

**Weaknesses:** The clinical sample is very small (**N=5**), single-centre, and based on planned rather than true postimplant geometry. The prostate is represented with coarse **5 mm** slice extrusion, the internal “reference” is numerical rather than exact, and many implementation details are **[DETAIL NOT REPORTED]**. No runtimes, p-values, confidence intervals, or quantitative whole-curve agreement metrics are provided.

**Confidence in findings:** **Medium.** High confidence in the qualitative conclusions that V200 is much more discretisation-sensitive than V100, and that vendor DVH behaviour can deviate materially from a fine-grid independent calculation; moderate confidence in the exact **1 mm** threshold as a universal rule.

**Relevance to reference DVH calculator:** **High.** This paper is directly about the numerical stability of DVH computation in a steep-gradient, small-volume regime and about how to expose opaque commercial-system behaviour with an independent benchmark.

---


## IAEA (2004) - Commissioning and quality assurance of computerized planning systems for radiation treatment of cancer

### Executive Summary

This IAEA technical report is not a primary DVH algorithm paper, but it is one of the clearest early frameworks for commissioning and QA of treatment planning systems (TPSs). Its main importance for a reference-quality DVH calculator is that it treats DVH generation as a separate QA problem, dependent on anatomy modelling, dose calculation, plan normalisation, point sampling, histogram construction, and structure logic rather than on dose calculation alone.

The report was motivated by accidental exposures and lack of public TPS QA guidance. It cites an IAEA review of **92** accidental radiotherapy exposures, with **26** related to treatment planning, and highlights the Panama accident in which 28 patients were affected, **12** later died, and **5** deaths were directly attributed to the error. It also reiterates that a **5%** dose change can alter response by roughly **10-30%**, supporting a target of about **3%** dose-calculation accuracy to help achieve **5%** overall treatment accuracy.

For DVH work, the most useful material is Section 9.6.2 and Table 57, which define **10** commissioning tests covering histogram type, plan normalisation, relative versus absolute dose and volume, bin size, Boolean structures, consistency with dose display, calculation-point sampling, comparison guidelines, and dose/volume statistics. The report also warns that simple rectangular phantoms can be misleading because grid aliasing may create large volume errors. For a gold-standard open-source DVH engine, the message is clear: make assumptions explicit, validate against independent benchmarks, quantify error bars for small/high-gradient structures, and revalidate after software or hardware changes.

### 1. Bibliographic record
- **Authors:** International Atomic Energy Agency (institutional author); contributors to drafting and review included P. Andreo, J. Cramb, B.A. Fraass, F. Ionescu-Farca, J. Izewska, V. Levin, B. Mijnheer, J.-C. Rosenwald, P. Scalliet, K.R. Shortt, J. Van Dyk, and S. Vatnitsky
- **Title:** *Commissioning and quality assurance of computerized planning systems for radiation treatment of cancer*
- **Journal:** Not applicable. Published as *Technical Reports Series No. 430* by the International Atomic Energy Agency
- **Year:** 2004
- **DOI:** Not applicable
- **Open access:** Yes

### 2. Paper type and scope
- **Type:** Task group report
- **Domain tags (one or more):** D1 Computation | D2 Commercial systems
- **Scope statement:** This report provides a full TPS QA framework covering purchase, acceptance testing, commissioning, periodic QA, patient-specific QA, and process management for external beam radiotherapy and brachytherapy. It is highly relevant to a reference DVH calculator because it explicitly identifies DVH creation as a QA-sensitive computational function tied to structure modelling, dose representation, point sampling, binning, and consistency with displayed dose.

### 3. Background and motivation (150-300 words)

The report was produced because radiotherapy planning had become computationally sophisticated and high risk, while practical public guidance for commissioning modern TPSs remained limited. The IAEA had reviewed **92** accidental radiotherapy exposures and found **26** involving the treatment-planning process. The report also highlights the Panama accident, where errors in shielding-block entry and monitor-unit calculation affected 28 patients; **12** later died and **5** deaths were directly attributable to the treatment error. These incidents frame TPS QA as a patient-safety requirement, not simply a technical preference.

The motivation is also dosimetric and radiobiological. The report notes that in the steep part of a clinical dose-response curve, a **5%** dose change can cause roughly **10-30%** change in response, and it reiterates the ICRU expectation of about **5%** overall delivered-dose accuracy, implying roughly **3%** dose-calculation accuracy. Crucially, however, the report does not treat this as a beam-model problem alone. It argues that errors may arise from imaging, anatomy definition, contour interpolation, coordinate conventions, plan normalisation, data transfer, or misunderstanding of software capabilities. For DVHs, that point is fundamental: a discrepant histogram may reflect structure reconstruction, dose-grid choice, point-sampling rules, or display conventions rather than one isolated algorithmic failure. The report therefore adopts a whole-process QA philosophy in which DVH validation is embedded inside broader validation of anatomy, dose, output, and workflow.

### 4. Methods: detailed technical summary (400-800 words)

This is an expert technical report, not an empirical patient study. There is **no patient cohort**, **no inferential statistics**, and **no single experimental ground truth dataset**. Instead, the report synthesises accident analyses, prior QA literature, algorithmic considerations, and commissioning practice into a staged QA programme for purchase, acceptance, commissioning, periodic QA, and patient-specific QA.

A major methodological strength is its decomposition of the TPS problem into anatomy, dose calculation, plan evaluation, and output/transfer. For anatomy, the report asks what 3D object model the TPS uses, for example a contour stack, a tiled surface, a voxel representation, or a point-based model. It specifically identifies superior/inferior end-capping as clinically important and lists possible implementations such as stopping at the last contour, extending by half the next-slice distance, or applying a conical cap. It similarly highlights contour extraction, non-uniform slice spacing, CT-to-density conversion, and separate density grids. The report does **not** prescribe one preferred algorithm, so exact implementation details are **[DETAIL NOT REPORTED]**.

For dose calculation, the report classifies external-beam algorithms as measurement-based, analytical, superposition-based, or Monte Carlo-based, and distinguishes beam-specific checks, algorithm-specific investigations, and clinical calculation verification. It recommends three kinds of reference data: measured beam data, published benchmark data, and internal QA reference data. It also stresses that accuracy expectations differ by beam region and geometry, for example inner beam versus penumbra and homogeneous versus inhomogeneous phantoms. Statistical assessment is discussed through confidence limits, including the example formula `Δ = |average deviation| + 1.5 SD`, but the report acknowledges that full statistical tooling is often unavailable in practice.

The most relevant section here is **9.6.2 Dose-volume histograms**. Table 57 defines **10** DVH QA issues/tests:
1. direct, cumulative, and differential DVH types;
2. plan normalisation;
3. relative versus absolute dose;
4. relative versus absolute volume;
5. histogram dose bin size;
6. compound structures using Boolean logic;
7. consistency between DVH and dose display;
8. calculation-point sampling and geometric resolution;
9. DVH comparison guidelines and error bars;
10. dose and volume statistics.

The proposed methodology is perturbation-based. Users should create simple phantoms with known target and OAR volumes, calculate simple plans such as a four-field box or wedged field, and verify internal consistency among direct, cumulative, and differential histograms. They should then vary plan normalisation, dose and volume display modes, histogram bin size, and point-sampling density. For volume, an independent structure-volume calculation is explicitly recommended. For Boolean logic, the TPS should reproduce the DVH of explicitly contoured OR, AND, and subtraction structures. For dose-display consistency, the report suggests highly conformal cases in which, for example, a minimum target dose of **95%** should correspond to the **95%** isodose just covering the target. For sampling, the report recommends varying grid size, number of random points, or anatomy-sampling density and examining both high- and low-gradient cases.

Equally important are the report’s limitations. It does not define a reference DVH bin width, partial-volume rule, interpolation scheme, or single universal tolerance. It also warns that regular rectangular or cubic phantoms may be deceptive because grid aliasing can generate large percentage volume errors. The report should therefore be read as a commissioning framework and failure-mode inventory, not as a fixed numerical standard or a validated reference implementation.

### 5. Key results: quantitative (300-600 words)

As a technical report, the main quantitative outputs are example tolerances, counts of required tests, and explicit patient-safety numbers rather than measured inter-system effect sizes. The safety context is strong: the report cites **92** accidental radiotherapy exposures reviewed by the IAEA, **26** related to treatment planning, and the Panama incident affecting 28 patients, with **12** later deaths and **5** deaths directly caused by treatment error. It also notes that about **5%** dose variation can translate to **10-30%** biological response variation and that about **3%** dose-calculation accuracy is needed to support **5%** overall treatment accuracy.

For external-beam dose-calculation QA, the report provides illustrative regional tolerances. In homogeneous square fields, example criteria are **0.5%** absolute dose at the normalisation point, **1%** on the central ray, **1.5%** in the inner beam, **2 mm** in the penumbra, **2%** in the outer beam, and **20%** in the buildup region. For MLC-shaped fields they are **1%**, **2%**, **3%**, **3 mm**, **5%**, and **20%**. For slab inhomogeneities they relax to **3%**, **3%**, **5%**, **5 mm**, **5%** for 3D inhomogeneities to **5%**, **5%**, **7%**, **7 mm**, **7%**. In the complementary confidence-limit table, simple geometry uses **2%** in central high-dose low-gradient regions and **2 mm or 10%** in high-gradient penumbra/buildup regions, while more complex geometry increases these values to about **3-4%** and **3 mm or 15%**.

For DVHs, the report’s major quantitative point is not one tolerance but the breadth of commissioning required. It defines **10** separate DVH tests and includes them in the commissioning matrix (Table 66). In the overall summary (Table 62), the whole programme includes **63** basic tests, **81** full tests, and **15** special-issue tests, with the plan-evaluation subsection alone containing **5** dose-display tests, **10** DVH tests, and **3** biological-effects tests. The report also states that if a TPS claims to perform DVH analysis, QA should ask whether it determines volume within something like **0.5 cm³** or **1%** at one standard deviation, although it does not endorse these as universal standards.

Periodic QA examples are also quantitative. Visible checks include digitiser and plotter geometry within **0.2 cm**, CT geometry within **0.2 cm**, and relative electron-density agreement within **0.02**, or approximately **±20 HU**. The report also states explicitly that radiosurgery and similar high-gradient techniques require tighter tolerances than conventional or palliative treatments, reinforcing that one blanket DVH tolerance is inappropriate.

### 6. Authors' conclusions (100-200 words)

The report concludes that TPS QA must be comprehensive, continuous, and adapted to the local clinical environment rather than reduced to a rigid universal protocol. Its strongest message is that commissioning is as much about understanding software capabilities and limitations as it is about checking numerical outputs. The four recurring safeguards are **education**, **verification**, **documentation**, and **communication**.

For plan-evaluation tools, the report’s conclusion is that DVHs, dose displays, and biological models are clinically useful only when their behaviour has been explicitly tested. It repeatedly stresses that commissioning QA can reveal both computational defects and misinterpretation of output within the clinic. Ongoing QA after commissioning is also essential because upgrades, configuration changes, and routine workflow drift can invalidate earlier assumptions.

The report does **not** conclude that one universal DVH algorithm or tolerance exists. Instead, it argues that users must establish and document the acceptable limits of use for their specific TPS, algorithms, and clinical techniques.

### 7. Implications for reference DVH calculator design (300-600 words)

#### 7a. Algorithm and implementation recommendations

A reference DVH calculator should expose, not hide, the choices that commercial systems often bury internally. This report makes clear that DVH behaviour depends on structure representation, end-capping, dose-grid resolution, DVH sampling density, histogram dose bin width, partial-volume logic, and plan normalisation. A benchmark implementation should therefore record each of these in provenance metadata. It should support direct, cumulative, and differential DVHs; absolute and relative dose axes; absolute and relative volume axes; Boolean compound structures; and robust dose/volume statistics such as minimum, mean, maximum, and arbitrary Vx/Dx.

The report also argues implicitly against simplistic binary whole-voxel rules. Although it does not prescribe a partial-volume method, its concern with overlapping, small, and convoluted structures strongly favours either exact geometric intersection or a converged sub-voxel occupancy model. If stochastic sampling is supported, deterministic seeding and convergence reporting should be mandatory. If grid-based sampling is used, grid-position sensitivity must be measurable.

#### 7b. Validation recommendations

The report effectively outlines a modern validation suite: simple phantoms with known target and OAR volumes; plans with controllable minimum and maximum dose; direct/differential/cumulative self-consistency checks; absolute versus relative dose and volume checks; multiple histogram bin sizes; Boolean OR, AND, and subtraction structures; consistency between DVH and isodose display; and sensitivity to dose-grid size, point density, and grid position. Validation should cover small, large, and convoluted structures and should include both high- and low-gradient cases.

Its warning about regular rectangles and cubes is particularly important. A reference calculator should include offset, irregular, and convoluted geometries so that aliasing failure modes are exposed rather than hidden. Highly conformal gradient cases should also be included, for example one where the **95%** isodose should just cover the target if the minimum target dose is **95%**. The regional tolerance tables, with values such as **0.5-2%** in benign homogeneous regions and **2-7 mm** or **10-15%** in penumbra/complex regions, are useful as illustrative context but should not be enforced as universal acceptance criteria.

#### 7c. Extensibility considerations

The report explicitly places biological tools downstream of DVHs. A reference engine should therefore keep physical-dose histograms primary, while BED, NTCP, TCP, and fractionation-aware calculations are optional overlays with explicit model and parameter provenance. Because the report also covers brachytherapy, the calculator architecture should be able to support permanent-implant dose integration, stepping-source geometries, source decay handling, and checks of source-strength conventions. Compatibility with `DICOM-RT` and strong auditability after software updates are also directly motivated by the report.

#### 7d. Caveats and limitations

This report predates much of modern VMAT, adaptive radiotherapy, and cloud-based plan review. It is intentionally vendor-neutral and therefore leaves many details as **[DETAIL NOT REPORTED]**. It does not provide empirical inter-system benchmark data, a public analytical dataset, or one preferred reference algorithm. Many quantitative values are illustrative expert examples rather than validated universal tolerances. A reference DVH engine should therefore use this report as a conceptual framework and failure-mode inventory, then strengthen it with modern analytical phantoms, cross-vendor comparisons, and explicit convergence analysis.

### 8. Connections to other literature

- **Drzymala et al. (1991)** foundational DVH paper explaining contour voxelisation, dose interpolation, and histogram design.
- **Van Dyk et al. (1993)** broader TPS commissioning and QA framework cited among the key earlier references.
- **Fraass et al. (1998) (AAPM TG-53)** closely related QA report using similar benchmark-testing and regional-tolerance concepts.
- **Panitsa et al. (1998)** early DVH-specific QC study showing that low-gradient agreement can coexist with large high-gradient errors.
- **Gossman and Bank, 2010** later independent geometry-based DVH QA benchmark for linac TPSs.
- **Nelms et al. (2015)** analytical DICOM benchmark study that directly addresses the need for explicit DVH validation.
- **Pepin et al. (2022)** multivendor analytical comparison showing the continuing impact of end-capping, supersampling, and binning choices.
- **Penoncello et al. (2024)** multicentre multivendor clinical study showing that structure modelling still drives major DVH inconsistency.

### 9. Data extraction table

**Table 9a. Example criteria of acceptability for external dose calculations extracted from TRS-430**

| Situation | Absolute dose at normalisation point | Central ray | Inner beam | Penumbra | Outer beam | Buildup |
|---|---:|---:|---:|---:|---:|---:|
| Homogeneous square fields | **0.5%** | **1%** | **1.5%** | **2 mm** | **2%** | **20%** |
| Homogeneous rectangular fields | **0.5%** | **1.5%** | **2%** | **2 mm** | **2%** | **20%** |
| Asymmetric fields | **1%** | **2%** | **3%** | **2 mm** | **3%** | **20%** |
| Blocked fields | **1%** | **2%** | **3%** | **2 mm** | **5%** | **50%** |
| MLC-shaped fields | **1%** | **2%** | **3%** | **3 mm** | **5%** | **20%** |
| Wedged fields | **2%** | **2%** | **5%** | **3 mm** | **5%** | **50%** |
| Slab inhomogeneities | **3%** | **3%** | **5%** | **5 mm** | **5%** | Not applicable |
| 3-D inhomogeneities | **5%** | **5%** | **7%** | **7 mm** | **7%** | Not applicable |

**Table 9b. Example region-wise confidence-limit tolerances**

| Region / metric | Simple geometry | Complex geometry | More complex geometry |
|---|---:|---:|---:|
| `δ1` central beam axis, high dose, small gradient | **2%** | **3%** | **4%** |
| `δ2` buildup / penumbra, high dose, large gradient | **2 mm or 10%** | **3 mm or 15%** | **3 mm or 15%** |
| `δ3` off-axis, high dose, small gradient | **3%** | **3%** | **4%** |
| `δ4` outside beam edges, low dose, small gradient | **3%** *(30% cax-referenced)* | **4%** *(40% cax-referenced)* | **5%** *(50% cax-referenced)* |
| `RW50` radiological width | **2 mm or 1%** | **2 mm or 1%** | **2 mm or 1%** |
| `δ50-90` beam fringe | **2 mm** | **3 mm** | **3 mm** |

**Table 9c. DVH-related commissioning content explicitly listed in the report**

| Category | Quantitative detail |
|---|---|
| Total DVH commissioning tests | **10** |
| DVH test topics | Type; plan normalisation; relative/absolute dose; relative/absolute volume; histogram dose bin size; compound structures; consistency with dose display; calculation-point sampling; comparison guidelines; dose/volume statistics |
| Overall commissioning matrix | **63** basic tests, **81** full tests, **15** special-issue tests |
| Plan-evaluation subsection | **5** dose-display tests, **10** DVH tests, **3** biological-effects tests |
| Example periodic QC tolerances visible in report | Digitiser and plotter geometry within **0.2 cm** CT geometry within **0.2 cm** relative electron density within **0.02** or about **±20 HU** |

### 10. Critical appraisal (100-200 words)

- **Strengths:** Broad, technically mature, and still highly relevant. It recognises that DVH error is rarely isolated and usually emerges from interactions among anatomy modelling, dose computation, plan normalisation, sampling, and workflow. The explicit decomposition into **10** DVH tests remains one of the best QA checklists in the literature.
- **Weaknesses:** Not an empirical inter-system comparison. It provides no public benchmark dataset, no reference DVH algorithm, and many details are intentionally vendor-neutral, so numerous implementation specifics remain **[DETAIL NOT REPORTED]**.
- **Confidence in findings:** **High** for the QA philosophy, identified failure modes, and the need for explicit DVH commissioning. **Medium** for direct reuse of the numeric tolerances, because the report itself treats them as illustrative and context dependent.
- **Relevance to reference DVH calculator:** **High**. Even though it is not a DVH algorithm paper, it provides a rigorous checklist of what a gold-standard DVH engine should document, validate, and continue to revalidate after software or workflow changes.



---

<!-- Source: SUMMARY - Chung 2006 - Dose variations with varying calculation grid size in H&N IMRT.md -->

## Chung (2006) - Dose variations with varying calculation grid size in head and neck IMRT

### Executive summary

Chung et al. (2006) examined how dose-calculation grid size in a commercial treatment planning system affects head-and-neck IMRT dose distributions, using both a homogeneous solid-water phantom and three clinical cases. Although the paper did not report DVHs directly, it is highly relevant to DVH computation because it quantified upstream dose-field discretisation error, including both nominal grid-size effects and sensitivity to grid-origin phase. The central finding was that coarser grids produced materially larger dose discrepancies, especially in high-gradient regions, and that a 2 mm grid performed substantially better than 3 mm or 4 mm grids for head-and-neck IMRT.

In the phantom study, using a 1.5 mm grid as the internal reference, the 95% cumulative dose-difference threshold increased from about **1.1-1.3 Gy** for **2 mm** grids to about **1.9-2.5 Gy** for **3 mm** grids and **2.5-3.0 Gy** for **4 mm** grids, depending on target depth. Grid-origin shifts of half a voxel produced additional differences up to about **2.0 Gy**, demonstrating that voxel phase alignment alone can perturb sampled dose meaningfully. Relative dose-difference histograms broadened systematically with increasing local relative gradient, confirming that steep gradients are the dominant failure mode for coarse dose lattices.

For a reference-quality DVH calculator, the paper implies that the engine must distinguish between errors introduced by its own interpolation/integration methods and errors already embedded in the imported dose grid. It supports the use of robust sub-voxel structure integration, explicit warnings for coarse input dose grids, gradient-sensitive validation cases, and optional grid-phase sensitivity testing. It also shows that global summaries can obscure clinically important local failures, so validation should include local, gradient-focused, and near-surface benchmarks rather than relying only on whole-structure or whole-plane aggregate metrics.

### 1. Bibliographic record

**Authors:** Heeteak Chung, Hosang Jin, Jatinder Palta, Tae-Suk Suh, Siyong Kim
**Title:** *Dose variations with varying calculation grid size in head and neck IMRT*
**Journal:** *Physics in Medicine and Biology*
**Year:** 2006
**DOI:** [10.1088/0031-9155/51/19/008](https://doi.org/10.1088/0031-9155/51/19/008)
**Open access:** No

### 2. Paper type and scope

**Type:** Original research.

**Domain tags:** D1 Computation | D2 Commercial systems.

**Scope statement:** This paper quantified how changing dose-calculation grid size in a commercial treatment planning system (`Philips Pinnacle3`) alters head-and-neck IMRT dose distributions in a homogeneous phantom and in three clinical cases. Although it did not compute DVHs, it is directly relevant to DVH accuracy because it studied the upstream spatial discretisation error in the underlying dose field, including grid-origin sensitivity and the amplification of errors in high-gradient regions.

### 3. Background and motivation (150-300 words)

The paper addressed a long-standing planning-system problem: dose is computed on a discrete 3D lattice, so any finite calculation grid introduces interpolation error and spatial aliasing, especially in beam penumbrae and other high-gradient regions. Earlier work by Niemierko and Goitein (1989a, 1989b, 1990), and by Lu and Chin (1993), had already shown in more conventional settings that grid spacing matters and that denser sampling improves accuracy at the cost of computation time. Chung et al. argued that IMRT makes the problem more acute because it creates finer spatial structure in dose distributions, steeper gradients around targets and organs at risk, and more opportunities for missed local peaks and valleys when sampling is too coarse.

The immediate motivation was the theoretical work of Dempsey et al. (2005), which used Fourier and Nyquist arguments to suggest that spacing below **2.5 mm** should limit dose-distribution error to **<1%** for optimised IMRT. Chung et al. sought to test the practical manifestation of this issue in a real commercial TPS rather than an analytical or purely theoretical framework. For a reference DVH calculator, this is important even though the paper itself did not report DVHs: any DVH, D\(_x\), V\(_x\), gEUD, or NTCP derived from a voxelised dose matrix inherits the fidelity limits of that matrix. The paper is therefore best read as a study of dose-field sampling error that sets a lower bound on what downstream DVH algorithms can ever recover.

### 4. Methods: detailed technical summary (400-800 words)

This was a hybrid phantom-plus-clinical evaluation. The phantom was built from **two semi-cylindrical solid-water slabs** placed on **7 cm** of backscatter material. Each slab had a **20 cm** base length, **11.7 cm** height, and **6 cm** thickness. A `GafChromic HS` radiochromic film (lot `K0223HS`) was cut to conform to the phantom surface, inserted in the mid-plane between the slabs, and shimmed with used film pieces plus plastic clamps to reduce air gaps. The phantom was CT scanned with **3 mm slice thickness**, and positioned for irradiation using **eight infrared fiducial markers** and a `BrainLab ExacTrac` system.

Two phantom target configurations were planned. The “shallow” target lay at approximately **0.5 cm** depth from the superior surface; the “deep” target lay at approximately **6.0 cm** depth. Both targets were about **4 cm × 13 cm × 6 cm**. Three critical structures were included: **spinal cord** and **bilateral parotids**. Plans were **five-field step-and-shoot IMRT** head-and-neck plans with total prescription **54 Gy** in **1.8 Gy/fraction**. Gantry angles were **20°, 90°, 165°, 240°, 310°** for the shallow-target case and **0°, 70°, 145°, 220°, 290°** for the deep-target case. The inverse-planning workflow used a two-step process, with fluence optimisation followed by leaf-sequence optimisation. A **pencil-beam** algorithm was used during optimisation, and **superposition/convolution** was used for the final dose calculation. For the shallow case, segment counts ranged **7-21** with collimator sizes **6 × 7 to 14 × 7 cm²** for the deep case, **10-16** segments with collimator sizes **8 × 7 to 13 × 6 cm²**. The exact `Pinnacle3` software version is **[DETAIL NOT REPORTED]**. Whether each grid size involved full re-optimisation or only recomputation of the final dose is also **[DETAIL NOT REPORTED]**.

The key variable was final dose-calculation grid size: **1.5 mm, 2 mm, 3 mm, and 4 mm**. The **1.5 mm** calculation served as the internal reference when comparing grid sizes. To test phase sensitivity, the authors also shifted the grid origin by **half a voxel in all three coordinates**: **1 mm** for the 2 mm grid, **1.5 mm** for the 3 mm grid, and **2 mm** for the 4 mm grid. After dose computation, a **planar dose distribution** was extracted at **1 mm pixel size** by **linear interpolation**. This is not a DVH study: **no DVHs, no voxel-volume binning, no partial-volume dose integration, and no structure-wise D\(_x\)/V\(_x\) endpoints were reported**. Accordingly, DVH-specific implementation details such as contour rasterisation, partial-volume weighting, boundary handling, end-capping, cumulative versus differential DVH conventions, or DVH bin width are **[DETAIL NOT REPORTED / not applicable]**.

Dose delivery used a **Varian 2100C 6 MV** linac. Film received monitor units corresponding to **five fractions** so that exposure sat near the middle of the film’s linear sensitometric range; measured dose was then scaled back to the full **30-fraction, 54 Gy** prescription for analysis. Film dosimetry used a **double-exposure correction** for non-uniformity, a `Molecular Dynamics Personal Densitometer` He-Ne laser scanner at **633 nm**, native scan resolution **100 µm/pixel**, and re-binning to **1 mm/pixel** to match the extracted TPS plane. To reduce scanner artefacts, the authors applied a **low-pass Wiener filter** and a **discrete fast Fourier transform deconvolution** using a measured line-spread function. Calibration films covered **0-17 Gy** and were fit with a **third-order polynomial**. Registration between measured and calculated planes was done **manually** using known geometry.

Comparison metrics were planar rather than structure-based: **dose-difference histograms**, **relative dose-difference histograms**, **cumulative dose-difference histograms**, and **dose-difference maps**. Histogram bin widths were **0.15 Gy** for dose-difference histograms, **0.025 Gy** for cumulative dose-difference histograms, and **1 percentage point** for relative dose-difference histograms. Relative dose gradient was defined on the **1.5 mm reference plane** as \((1/D)\nabla D\) in the **x** and **y** directions, and points were binned into **0-5% mm\(^{-1}\)**, **5-10% mm\(^{-1}\)**, and **10-15% mm\(^{-1}\)** ranges. Gaussian fits were then applied to the relative dose-difference histograms, with mean, standard deviation, and FWHM reported. No formal hypothesis testing, confidence intervals, or goodness-of-fit statistics were reported. Three head-and-neck clinical cases were also recalculated on **1.5/2/3/4 mm** grids; for these, a single axial plane was extracted at **1 mm** with the grid origin kept consistent across grid sizes. Clinical case prescription and plan complexity are **[DETAIL NOT REPORTED]** in Methods, although Table 5 implies a **72 Gy** prescription.

The authors explicitly acknowledged that absolute TPS-versus-film disagreement is not due solely to grid size. They noted potential contributions from radiochromic film uncertainty, TPS modelling limitations, IMRT sequencing effects, and surface/build-up phenomena including electron contamination.

### 5. Key results: quantitative (300-600 words)

Using the **1.5 mm** grid as reference, the phantom study showed progressively larger cumulative dose-difference thresholds as grid size increased. At the authors’ **95% region-of-interest readout**, meaning the absolute dose difference below which **95% of plane points** lie, the shallow-target case differed by **1.26 Gy (2.3% of 54 Gy)** for **2 mm**, **2.482 Gy (4.6%)** for **3 mm**, and **3.018 Gy (5.6%)** for **4 mm**. The deep-target case was similar: **1.10 Gy (2.0%)**, **1.85 Gy (3.4%)**, and **2.49 Gy (4.6%)**, respectively. At the **90%** and **85%** readouts the thresholds were smaller but still rose substantially with coarser grids, reaching **1.818-1.892 Gy** at 90% and **1.418-1.65 Gy** at 85% for the 4 mm calculations. The authors described shallow and deep cases as showing no meaningful overall difference, although no p-value was provided.

Grid-origin sensitivity was itself sizeable. A half-grid translation in all three axes produced **95%** readout differences of **1.00 Gy (1.9% of 54 Gy)**, **1.489 Gy (2.8%)**, and **2.029 Gy (3.8%)** for the shallow **2/3/4 mm** grids, and **1.287 Gy (2.4%)**, **1.828 Gy (3.4%)**, and **2.020 Gy (3.7%)** for the deep case. Thus, simply changing phase alignment of the same nominal grid could induce dose differences of the same order as the fine-versus-coarse grid comparison. The paper’s Figure 9 made the important point that local error is not strictly monotonic with voxel size: because of interpolation phase, a **4 mm** sample can occasionally agree better with a comparison point than a **3 mm** or even **2 mm** sample.

Error spread worsened systematically in steeper gradients. From Table 3, the Gaussian-fit FWHM of the **relative** dose-difference histograms increased both with grid size and with relative gradient range. In the shallow case, FWHM rose from **2.27** to **6.14** to **7.02** for the **2 mm** grid across the **0-5**, **5-10**, and **10-15% mm\(^{-1}\)** bins, from **4.23** to **10.35** to **12.55** for **3 mm**, and from **5.69** to **10.90** to **16.83** for **4 mm**. The deep case showed a similar pattern, ending at **21.34** for the **4 mm**, **10-15% mm\(^{-1}\)** bin. A notable technical issue is that Table 3 labels these quantities in cGy, but they arise from relative-dose histograms and numerically satisfy FWHM ≈ 2.355σ, so they appear to be **percentage points**, not cGy.

Against radiochromic film, the global histograms were much less discriminating. For the shallow target, the cumulative **95%** thresholds versus measurement were **6.812 Gy**, **7.067 Gy**, **7.667 Gy**, and **7.677 Gy** for **1.5/2/3/4 mm**, respectively. The maximum spread among these was only **0.865 Gy**, or **1.60% of 54 Gy**, despite obvious local changes in the dose-difference maps. The maps showed increasing surface inaccuracy and thicker internal discrepancy streaks with coarser grids, but these occupied too small a fraction of the plane to move the overall histogram strongly. This is one of the paper’s most useful findings: global summaries can hide locally important failures.

The three clinical cases reproduced the phantom trend. At the **95%** readout, the difference from the **1.5 mm** reference was **0.50, 0.70, and 0.38 Gy** for **2 mm** in cases 1-3, **2.36, 2.22, and 0.78 Gy** for **3 mm**, and **3.24, 2.96, and 3.60 Gy** for **4 mm**. Expressed against the implied **72 Gy** prescription, these were **0.5-1.0%** for **2 mm**, **1.1-3.3%** for **3 mm**, and **4.1-5.0%** for **4 mm**. At the **90%** readout, the corresponding ranges were smaller: **0.18-0.40 Gy**, **0.44-0.66 Gy**, and **0.46-1.06 Gy**. In case 1, local near-surface differences reached about **−10 Gy** (**14% of 72 Gy**) while the central high-dose region remained within **<2 Gy** (**3%**), and the histograms broadened toward negative dose difference as grid size increased, consistent with systematic underestimation of sharp dose peaks. No formal significance testing was reported for the clinical comparisons.

### 6. Authors' conclusions (100-200 words)

The authors concluded that dose variation from calculation-grid size is real and clinically relevant in head-and-neck IMRT, particularly in regions of high dose gradient. Their practical recommendation was that while **3 mm** and **4 mm** grids may be “acceptable for most IMRT plans”, a **2 mm** grid is required “at least in the region of the high dose gradient” to predict dose distributions accurately. They also concluded that grid-origin phase can materially affect the result, and that high-gradient regions are more sensitive than low-gradient regions.

These conclusions are partly well-supported and partly broader than the data justify. The evidence for greater sensitivity in high-gradient regions and for the superiority of **2 mm** over **3-4 mm** is strong within the study design. However, the statement that **3-4 mm** is generally acceptable is less secure because the study did not analyse DVHs or clinical endpoints, used only a single commercial TPS, and showed local differences as large as **~3 Gy** versus 1.5 mm in the phantom and **~3.6 Gy** in clinical cases at the 95% readout, plus **~10 Gy** local discrepancies near surface in one clinical case.

### 7. Implications for reference DVH calculator design (300-600 words)

#### 7a. Algorithm and implementation recommendations

A reference DVH calculator should treat input dose-grid discretisation as a first-class uncertainty source, not a hidden implementation detail. This paper showed that moving from **1.5 mm** to **4 mm** can change the dose field by about **3.0 Gy** at the 95% plane readout in the shallow phantom, and that merely shifting the origin of a **4 mm** grid can add another **~2.0 Gy** of variation. For DVH work, that means the calculator should do two things: first, use rigorous sub-voxel structure integration so that it does not add further aliasing on top of the source grid; second, explicitly warn when the input dose grid itself is too coarse to support fine-structure or high-gradient metrics. Supersampling can reduce structure-sampling error, but it **cannot recover frequency content lost in the original dose calculation**.

Practically, the engine should support trilinear or higher-order continuous interpolation inside each dose voxel, combined with fractional-volume structure clipping or very high-order quadrature. It should also expose an optional **grid-phase uncertainty mode**, for example by recomputing metrics under several sub-voxel offsets or reporting sensitivity to half-voxel shifts. The non-monotonic local behaviour in Figure 9 means one should not assume that a single coarse-to-fine convergence path will behave monotonically at every point. Metrics dominated by peaks or thin high-gradient regions, such as D\(_{0.03cc}\), D\(_{1cc}\), D\(_2\%\), or shell and surface statistics, deserve explicit caution when dose grids exceed roughly **2-2.5 mm** in head-and-neck IMRT.

#### 7b. Validation recommendations

Validation should not rely only on global histogram agreement, because this paper showed that local failures can be almost invisible in whole-plane distributions when the affected region is small. A robust benchmark suite should therefore include: a **near-surface target** like the paper’s **0.5 cm** case; a **deep target** around **6 cm** high-gradient peak/valley synthetic profiles akin to Figure 9; and repeated evaluations under **half-grid origin shifts**. The phantom geometry in this paper is also a useful template: curved surface, target adjacent to surface, and nearby avoidance structures.

For acceptance criteria, this paper implies that a reference implementation should aim for residual numerical uncertainty well below the paper’s observed **2 mm vs 1.5 mm** differences, ideally much less than about **1 Gy** in high-gradient test cases and preferably **<0.5% of prescription** for stable bulk endpoints after further internal refinement. More importantly, validation should separate three layers: source-dose-grid error, interpolation/integration error inside the DVH engine, and structure discretisation error. Analytical dose fields are needed for the second and third layers, because film-versus-TPS comparisons in this paper were dominated by larger absolute discrepancies and did not cleanly isolate grid-size effects.

#### 7c. Extensibility considerations

This paper strongly motivates capabilities beyond a single cumulative DVH curve. The largest discrepancies occurred near the **surface/build-up region**, so a reference tool should support **dose-surface histograms (DSH)** or shell-based dose summaries. Because the paper stratified error by **relative dose gradient**, a useful extension is a gradient-aware reporting layer, such as DVH uncertainty bands conditioned on local \(|\nabla D|/D\), or supplementary maps showing where coarse-grid input is likely to bias sampled metrics. Since the clinical cases showed systematic underestimation of sharper dose peaks, serial-organ models such as **gEUD** or NTCP formulations sensitive to the high-dose tail may be more affected than mean dose. The data model should therefore allow per-structure uncertainty propagation, not just point estimates.

#### 7d. Caveats and limitations

Generalisability is limited. The phantom was homogeneous solid water, the TPS was a single 2006-era commercial system, the delivery was step-and-shoot head-and-neck IMRT, and the measurement comparison was 2D film-based with manual registration. The paper also studied **dose-distribution** differences rather than **DVH** differences, so translation to structure-specific endpoints must be done cautiously. Some important details are sparse or absent: exact TPS version, whether plans were re-optimised at each grid size, clinical case specifics, and how much of the observed discrepancy came from dose algorithm limitations rather than grid sampling. The very large TPS-versus-film thresholds (**~6.8-7.7 Gy** at the 95% readout) show that measurement/model disagreement can swamp grid-size effects in global summaries. Finally, Table 3’s unit labelling is internally inconsistent, which slightly reduces confidence in that part of the presentation.

### 8. Connections to other literature

- **Niemierko and Goitein, 1989a** Foundational analysis of how dose-calculation grid size affects dose estimation; Chung et al. extend that concern from earlier planning contexts to commercial head-and-neck IMRT.
- **Niemierko and Goitein, 1989b** Variable grid spacing as an acceleration strategy; relevant because Chung et al.’s data suggest fine sampling is most necessary in steep gradients, which is exactly where adaptive refinement would be useful.
- **Niemierko and Goitein, 1990** Random sampling for treatment-plan evaluation; conceptually related to Chung et al.’s demonstration that grid origin and phase materially change sampled results.
- **Lu and Chin, 1993** Sampling techniques for plan evaluation; an early predecessor to the interpolation and sampling problem revisited here under IMRT complexity.
- **Dempsey et al. (2005)** Fourier and Nyquist analysis predicting that **<2.5 mm** spacing should keep IMRT dose-distribution error below **1%** Chung et al. provide a practical commercial-TPS study broadly consistent with the need for about **2 mm** sampling in high-gradient head-and-neck IMRT.
- **Bortfeld et al. (2000)** Fourier treatment of MLC leaf width and resulting dose distributions; relevant because Chung et al.’s gradient sensitivity is another manifestation of insufficient spatial bandwidth in IMRT dose representation.
- **Dempsey et al. (1999)** and **Dempsey et al. (2000)** Radiochromic film dosimetry and scanner-correction methodology used here for the measurement reference.

### 9. Data extraction table

The original paper reported dose in cGy; values below are converted to **Gy**. The authors’ “95%/90%/85% region” values are **cumulative dose-difference histogram thresholds**, not DVH D\(_{95}\)/D\(_{90}\)/D\(_{85}\) endpoints.

**Table A. Phantom cumulative dose-difference thresholds versus 1.5 mm reference, prescription 54 Gy.**

| Grid size | Shallow 95% | Deep 95% | Shallow 90% | Deep 90% | Shallow 85% | Deep 85% |
|---|---:|---:|---:|---:|---:|---:|
| 2 mm | 1.26 Gy (2.3%) | 1.10 Gy (2.0%) | 0.86 Gy (1.6%) | 0.852 Gy (1.6%) | 0.66 Gy (1.2%) | 0.651 Gy (1.2%) |
| 3 mm | 2.482 Gy (4.6%) | 1.85 Gy (3.4%) | 1.18 Gy (2.2%) | 1.472 Gy (2.7%) | 1.38 Gy (2.6%) | 1.17 Gy (2.2%) |
| 4 mm | 3.018 Gy (5.6%) | 2.49 Gy (4.6%) | 1.818 Gy (3.4%) | 1.892 Gy (3.5%) | 1.418 Gy (2.6%) | 1.65 Gy (3.1%) |

**Table B. Phantom cumulative dose-difference thresholds for half-grid origin shifts, prescription 54 Gy.**

| Grid size and half-grid shift | Shallow 95% | Deep 95% | Shallow 90% | Deep 90% | Shallow 85% | Deep 85% |
|---|---:|---:|---:|---:|---:|---:|
| 2 mm (+1 mm origin shift) | 1.00 Gy (1.9%) | 1.287 Gy (2.4%) | 0.642 Gy (1.2%) | 0.887 Gy (1.6%) | ~0.50 Gy (0.9%) | 0.687 Gy (1.3%) |
| 3 mm (+1.5 mm origin shift) | 1.489 Gy (2.8%) | 1.828 Gy (3.4%) | 1.089 Gy (2.0%) | 1.228 Gy (2.3%) | ~0.85 Gy (1.6%) | 0.92 Gy (1.7%) |
| 4 mm (+2 mm origin shift) | 2.029 Gy (3.8%) | 2.020 Gy (3.7%) | 1.329 Gy (2.5%) | 1.420 Gy (2.6%) | ~1.00 Gy (1.9%) | 1.22 Gy (2.3%) |

**Table C. Gradient-conditioned FWHM of relative dose-difference histograms. Values are likely percentage points, although the original Table 3 labels them in cGy.**

| Grid size | Shallow 0-5% mm\(^{-1}\) | Shallow 5-10% mm\(^{-1}\) | Shallow 10-15% mm\(^{-1}\) | Deep 0-5% mm\(^{-1}\) | Deep 5-10% mm\(^{-1}\) | Deep 10-15% mm\(^{-1}\) |
|---|---:|---:|---:|---:|---:|---:|
| 2 mm | 2.27 | 6.14 | 7.02 | 1.74 | 5.11 | 8.78 |
| 3 mm | 4.23 | 10.35 | 12.55 | 2.60 | 5.92 | 9.44 |
| 4 mm | 5.69 | 10.90 | 16.83 | 4.08 | 10.72 | 21.34 |

**Table D. Shallow-phantom cumulative dose-difference thresholds versus radiochromic film, prescription 54 Gy.**

| Grid size | 95% threshold | 90% threshold | 85% threshold |
|---|---:|---:|---:|
| 1.5 mm | 6.812 Gy (12.6%) | 3.812 Gy (7.1%) | 2.612 Gy (4.8%) |
| 2 mm | 7.067 Gy (13.1%) | 3.868 Gy (7.2%) | 2.668 Gy (4.9%) |
| 3 mm | 7.667 Gy (14.2%) | 4.668 Gy (8.6%) | 2.868 Gy (5.3%) |
| 4 mm | 7.677 Gy (14.2%) | 4.268 Gy (7.9%) | 3.068 Gy (5.7%) |

**Table E. Clinical-case cumulative dose-difference thresholds versus 1.5 mm reference. Table percentages use an implied 72 Gy prescription.**

| Grid size | Case 1 95% | Case 1 90% | Case 2 95% | Case 2 90% | Case 3 95% | Case 3 90% |
|---|---:|---:|---:|---:|---:|---:|
| 2 mm | 0.50 Gy (0.7%) | 0.28 Gy (0.4%) | 0.70 Gy (1.0%) | 0.40 Gy (0.6%) | 0.38 Gy (0.5%) | 0.18 Gy (0.3%) |
| 3 mm | 2.36 Gy (3.3%) | 0.62 Gy (0.9%) | 2.22 Gy (3.1%) | 0.66 Gy (0.9%) | 0.78 Gy (1.1%) | 0.44 Gy (0.6%) |
| 4 mm | 3.24 Gy (4.5%) | 0.95 Gy (1.3%) | 2.96 Gy (4.1%) | 1.06 Gy (1.5%) | 3.60 Gy (5.0%) | 0.46 Gy (0.6%) |

### 10. Critical appraisal (100-200 words)

**Strengths:** The study is unusually concrete for its time: it combines a controlled phantom, film measurement, grid-origin perturbation, gradient-stratified analysis, and a small clinical demonstration. It also uses a commercial TPS rather than only analytical arguments, which makes the findings operationally relevant.

**Weaknesses:** It is not a DVH paper, so translation to DVH endpoints is indirect. The phantom is homogeneous, the measurement is 2D film with manual registration, the clinical sample is only **3 cases**, formal statistical testing is absent, and key implementation details are missing, including whether plans were re-optimised at each grid size. Table 3 also contains a likely unit-labelling error.

**Confidence in findings:** **Medium.** The qualitative message, that coarser grids and unfavourable phase alignment worsen high-gradient dose representation, and that **~2 mm** is safer than **3-4 mm**, is convincing. The exact magnitudes are more context-dependent because 1.5 mm is not true ground truth and film/model discrepancies are substantial.

**Relevance to reference DVH calculator:** **High.** Even without DVHs, this paper directly informs how a reference DVH engine should treat input dose-grid resolution, convergence testing, origin sensitivity, and the impossibility of recovering information absent from a coarse TPS dose lattice.

---

<!-- Source: SUMMARY - Kirisits 2007 - Accuracy of volume and DVH parameters determined with different brachytherapy TPSs.md -->

## Kirisits (2007) - Accuracy of volume and DVH parameters determined with different brachytherapy treatment planning systems

### Executive summary

This paper is a foundational benchmark study for anyone building or validating a reference brachytherapy DVH engine. It compares **seven** brachytherapy treatment planning systems (TPSs) for structure-volume reconstruction and **five** HDR-capable TPSs for DVH-derived hotspot metrics using a purpose-built phantom with analytically known volumes. The central result is that by 2007 commercial brachy TPSs had improved substantially compared with older generations, but clinically important discrepancies remained, particularly for **small structures**, **thicker image slices**, **first/last-slice handling**, and **very steep dose gradients near the source**.

With standardised contours on **4 mm CT**, inter-system volume variation was **7%** for the **4.02 cc** small cylinder, **2%** for the **56.54 cc** large cylinder, and **5%** for the **63.02 cc** truncated cone. In a moderate-gradient HDR geometry, inter-system DVH variation was usually modest, for example **1-5%** standard deviation for D2cc, D1cc, and D0.1cc. However, when the source approached the structure more closely, variability increased to **4-8%** standard deviation with maxima of **7-15%**. Sensitivity analyses were even more striking: a **2 mm** contour expansion changed D0.1cc, D1cc, and D2cc by **15%**, **14%**, and **12%**, while a **6 mm** source shift changed them by up to **53%**, **50%**, and **44%**.

For a reference DVH calculator, the engineering message is clear. The software must make its contour reconstruction model explicit, especially the treatment of terminal slices; it should use deterministic, traceable geometry and volume integration rather than opaque stochastic approximations; and it must be stress-tested using small structures and near-source hotspot scenarios. This paper also supports a validation strategy that separates **observer contouring variability**, **source reconstruction uncertainty**, and **TPS-intrinsic numerical differences**, rather than treating all DVH disagreement as a single error term.

### 1. Bibliographic record

**Authors:** Christian Kirisits, Frank-André Siebert, Dimos Baltas, Marisol De Brabandere, Taran Paulsen Hellebust, Daniel Berger, Jack Venselaar

**Title:** *Accuracy of volume and DVH parameters determined with different brachytherapy treatment planning systems*

**Journal:** *Radiotherapy and Oncology*, 84(3), 290-297

**Year:** 2007

**DOI:** [10.1016/j.radonc.2007.06.010](https://doi.org/10.1016/j.radonc.2007.06.010)

**Open access:** No

### 2. Paper type and scope

**Type:** Original research

**Domain tags:** D1 Computation | D2 Commercial systems

**Scope statement:** This is a controlled phantom benchmark of volumetric reconstruction and DVH output across **seven** brachytherapy TPSs, with a separate **five-observer** contouring variability study on **two** systems. Its core question is whether clinically used 3D brachy metrics; especially absolute-volume OAR metrics such as D2cc, D1cc, and D0.1cc; are reproducible enough across observers, image acquisition settings, and vendor-specific reconstruction algorithms to support guideline-based clinical use.

### 3. Background and motivation (150-300 words)

The paper sits at the transition from conventional brachytherapy planning to **3D image-based** planning using CT/MRI and stepping-source afterloaders. By 2007, DVH-derived metrics were already embedded in prostate and gynaecological brachytherapy practice: target metrics such as D90, D100, V100, and V150, and OAR metrics such as urethral D10 and absolute hotspot volumes such as rectum/bladder/sigmoid D2cc. Once such quantities are used for reporting, optimisation, and potentially dose constraints, their **numerical reproducibility** becomes a physics problem, not just a contouring problem.

Two uncertainty classes were already recognised: observer-dependent contouring variation, and technical variation from image acquisition, volume reconstruction, source reconstruction, and DVH computation. An earlier TPS-comparison study from 1998 had reported appreciable volume-calculation errors for simple cylinders and spheres, implying that volume and DVH outputs were not interchangeable across systems. What was missing was a contemporary assessment of **newer brachy TPSs**, with explicit attention to clinically relevant DVH endpoints and to the specific geometric situations likely to break agreement: **small structures**, **thicker slices**, **partial-volume effects in first and last contour slices**, and **very steep near-source gradients**.

This paper directly addresses that gap with a dedicated phantom and cross-system comparison. It is therefore highly relevant to any reference-quality DVH calculator intended to benchmark commercial systems, because it shows that the key uncertainties are not limited to dose calculation alone: they also arise from contour reconstruction conventions and how dose is mapped onto small absolute organ subvolumes.

### 4. Methods: detailed technical summary (400-800 words)

**Study design and phantom.** This was a controlled phantom study organised within the ESTRO BRAPHYQS group, with the comparisons performed during a 2006 expert workshop. The phantom contained **three PMMA structures** mounted with parallel axes: an **80 mm × 8 mm** small cylinder (**4.02 cc**), an **80 mm × 30 mm** large cylinder (**56.54 cc**), and a **45 mm** truncated cone with diameter varying from **28 to 55 mm** (**63.02 cc**). Dimensions were mechanically verified with precision rulers and analytically converted to true volumes, which served as the reference standard for the volume-computation part of the study. The geometries were chosen to approximate, respectively, a urethra-like small organ, a rectum-like larger organ, and a bladder-like variable-diameter organ; their dimensions were informed by measurements from **10** prostate and cervical brachy image series.

**Image acquisition.** CT was acquired on a Siemens Somatom Plus S using **three protocols**: **2 mm CT**, **4 mm CT**, and **4 mm spiral CT**. The phantom was scanned in air with its long axis aligned to the CT axis, and the first slice (`z = 0`) was placed **randomly**, specifically not aligned to the object boundary, so that terminal-slice partial-volume effects would occur naturally. MRI was acquired on a **0.2 T** Siemens Magnetom Open Viva with the phantom in a doped water tank (`6.25 g NiSO4 / 5000 ml`), using an axial **Fast Spin Echo T2** sequence (`TR 4500 ms`, `TE 96 ms`). The MRI slice thickness is shown as **5 mm** in the figure describing image sets. All image series were transferred via DICOM.

**TPSs and volume-reconstruction approaches.** Seven TPSs were compared: `BrachyVision 6.5`, `Flexiplan 1.95`, `Oncentra MasterPlan 1.4.3.1`, `PLATO BPS 14.2.6`, `PLATO EVAL 3.0.3`, `Oncentra Prostate 2.11`, and `VariSeed 7.1 Build 2780`. The paper is especially useful because it describes each system’s approximate reconstruction logic. BrachyVision used a **shape-based interpolation** model that rounded the terminal cylinder edges. VariSeed effectively extended the object through the **full last slice**, with user-entered z resolution and slice replication or interpolation. Oncentra MasterPlan reconstructed a 3D distance matrix and generated a triangulated surface, which the authors note tends to **underestimate convex** and **overestimate concave** volumes. PLATO BPS and PLATO EVAL used **random sampling points** critically, they differed in how terminal contours were treated: `EVAL` took the most superior and inferior contours as organ borders, whereas `BPS` took the **slice edges** containing those contours as the borders. Oncentra Prostate divided the object into sub-volumes between adjacent contours and estimated volume using bounding boxes plus random sampling. Flexiplan used contour areas from **Green’s formula** followed by a slice-to-slice summation. User-adjustable numerical settings included **100,000** sampling points in Flexiplan, PLATO BPS, and PLATO EVAL; **50,000** points in Oncentra Prostate; **1 mm** volume voxel size in Oncentra MasterPlan; **0.5 mm** in VariSeed; and a **0.1 mm** dose grid in BrachyVision. Several other internal settings were [DETAIL NOT REPORTED].

**Inter-observer versus inter-system comparisons.** Inter-observer contouring was tested only on BrachyVision and Oncentra MasterPlan, using the **4 mm CT** dataset. **Five** experienced users contoured independently and were blinded to others’ contours. Observers chose the first and last slices themselves and could adjust zoom and HU windowing. To isolate TPS-intrinsic reconstruction differences, the cross-system comparison then used **standardised contour sets** agreed by all observers, with the same number of slices contoured on each system and diameters adjusted to the real values if necessary. This is an important design feature: the study deliberately separates *observer variability* from *algorithmic variability*. Agreement metrics were descriptive only: relative **1 SD**, offsets versus true volume, and maximum deviations. No formal hypothesis testing, confidence intervals, or p-values were reported. DVH bin width, interpolation between DVH bins, end-capping formalism, and partial-volume weighting rules were [DETAIL NOT REPORTED].

**DVH and dose comparison.** Only **five** systems were included in the DVH comparison, because Oncentra MasterPlan and VariSeed lacked HDR modules. All included systems used the same **TG-43** parameter set for the classic `microSelectron-HDR` source, based on ESTRO consensus data. Two synthetic HDR plans were created on the **4 mm CT** dataset with approved contours. In each plan, **17 dwell positions** were placed along a line parallel to the cylinder axes. In **treatment plan 1**, the dwell line lay between the large cylinder and truncated cone; source-axis-to-surface distance was **2.4 cm** for the large cylinder and **1.15-2.5 cm** for the cone. In **treatment plan 2**, the dwell line lay between the large and small cylinders at **0.5 cm** and **1.6 cm** from their surfaces, respectively. The first dwell position was aligned to the first slice of the large cylinder. Dwell times were **20 s** per position in plan 1 and **10 s** per position in plan 2, for a source strength of **40,800 cGy cm² h⁻¹**. The evaluated endpoints were cumulative-DVH absolute-volume metrics D2cc, D1cc, and D0.1cc. Additional perturbation tests expanded contours concentrically by **2 mm** and shifted the dwell line laterally by **6 mm** to probe sensitivity to contouring and source-reconstruction errors.

**Limitations acknowledged by the authors.** The authors explicitly note that the phantom used simple regular shapes rather than clinical anatomy, and that the dosimetry used a very simple one-catheter or equal-dwell dose distribution rather than realistic optimised multi-catheter implants. Both constraints limit direct clinical generalisation but are appropriate for mechanism-focused benchmarking.

### 5. Key results: quantitative (300-600 words)

**Observer-dependent volume variability was substantial for small objects.** Before any standardised contouring protocol, the relative standard deviation of contoured volume across **five observers** was **13%** of the mean volume for the **small cylinder** on both tested TPSs, versus **3-5%** for the **large cylinder** and **2-3%** for the **cone**. The same observer contouring the same object on two different systems differed on average by **10%** for the small cylinder (**0.4 cc**), **2%** for the large cylinder (**1.0 cc**), and **7%** for the cone (**4.3 cc**). The dominant mechanism was the subjective inclusion or exclusion of the first and last partially filled slices. At **4 mm** slice thickness, a single end slice represents **5%** of an **80 mm** cylinder volume, so terminal-slice choice alone can matter. The authors also note a useful geometric sensitivity result: changing cylinder diameter from **8 mm to 9 mm** increases volume by **27%**, whereas adding **1 mm** to a **30 mm** cylinder increases volume by only **7%**.

**With standardised contours, inter-system volume differences were smaller but not negligible, and worsened with thicker slices.** Relative standard deviation across the **seven TPSs** was lowest for the large cylinder and highest for the small cylinder. For **2 mm CT**, standard deviation and offset versus true volume were: small cylinder **3% / −1.7%**, large cylinder **1% / +0.5%**, and cone **2% / +8.3%**. For **4 mm CT**, they were **7% / +0.4%**, **2% / +2.2%**, and **5% / +3.6%**, respectively. For **4 mm spiral CT**, values were **4% / −3.1%**, **3% / −1.2%**, and **4% / +2.3%**. For **5 mm MRI**, they were **9% / +5.5%**, **3% / +2.2%**, and **6% / +1.8%**. Thus, the standardised **4 mm CT** comparison; **7%**, **2%**, and **5%** variation for the small cylinder, large cylinder, and cone; is a good summary of the clinically most relevant scan condition studied. Systematically, PLATO EVAL tended to give lower-than-mean volumes and VariSeed higher-than-mean volumes.

**DVH metrics were reasonably reproducible in moderate-gradient geometry, but degraded in terminal-slice and near-source scenarios.** In **treatment plan 1**, the more moderate geometry, inter-system relative standard deviation remained at or below **5%** for all reported metrics. For the **large cylinder**, inter-system standard deviation was **3%** for D0.1cc, **1%** for D1cc, and **1%** for D2cc; the reported maximum pairwise spreads were **8%**, **2%**, and **3%**, respectively. For the **cone**, inter-system standard deviation was **3%** for D0.1cc, **5%** for D1cc, and **5%** for D2cc, with maximum spreads of **6%**, **11%**, and **12%**. Inter-observer dosimetric variability on a single TPS was of similar order: for plan 1, large-cylinder inter-observer standard deviation was **5%**, **1%**, and **1%** for D0.1cc, D1cc, and D2cc; cone inter-observer standard deviation was **4%**, **2%**, and **3%**. In the corresponding dose-distribution figure, D2cc corresponded approximately to the **350%** isodose in the large cylinder and **540%** in the cone, while D0.1cc corresponded to about **410%** and **830%**, respectively; the absolute 100% dose level in Gy was [DETAIL NOT REPORTED].

**Sensitivity rose sharply when the source approached the structure or when geometry was perturbed.** In **treatment plan 2**, where the large cylinder was only **5 mm** from the source line, inter-system standard deviation reached **4-8%** and maximum reported spreads **7-15%**. For the **small cylinder**, inter-system standard deviation was **4%** for D0.1cc, D1cc, and D2cc, with maxima **8%**, **7%**, and **7%**. For the **large cylinder**, inter-system standard deviation was **6%**, **8%**, and **5%**, with maxima **13%**, **15%**, and **10%**. A geometric contour perturbation of **2 mm** isotropic expansion of the large cylinder in one TPS raised D0.1cc, D1cc, and D2cc by **15%**, **14%**, and **12%** relative to the unexpanded contour. A **6 mm** lateral source shift produced changes of up to **53%** for D0.1cc, **50%** for D1cc, and **44%** for D2cc relative to the unshifted plan. No formal inferential statistics were reported; all conclusions are based on descriptive variability metrics.

### 6. Authors' conclusions (100-200 words)

The authors conclude that, compared with older TPS generations, modern brachytherapy systems had reduced volumetric and DVH-calculation uncertainty to a level broadly comparable with inter-observer contouring variation. They do **not** claim interchangeability in all situations. Instead, they identify two persistent failure modes: **(1) terminal-slice reconstruction differences**, especially how the first and last contoured slices are interpreted, and **(2) very high dose gradients**, especially for structures close to the source or when the highest-dose subvolumes lie near poorly defined edges. They therefore argue that clinical use of DVH constraints should be informed by knowledge of how a given TPS computes volume and dose-to-volume metrics.

That interpretation is well supported by the phantom data for simple geometries and the tested HDR source arrangements. The broader extrapolation to all clinical anatomy is plausible, but less directly supported because the study did not include irregular patient contours or complex optimised implant geometries.

### 7. Implications for reference DVH calculator design (300-600 words)

#### 7a. Algorithm and implementation recommendations

The strongest design lesson is that a reference calculator must make its **contour-to-volume model explicit**. This paper shows that “volume” is not a uniquely defined quantity once only planar contours are available: vendor differences arose largely from how the **first and last slices** were capped or extended. A reference engine should therefore implement a **documented canonical reconstruction rule** for stacked contours; ideally deterministic, traceable, and mathematically exact within that model; and also support **vendor-emulation modes** for benchmarking commercial TPSs. Relevant modes suggested by this paper include full-slice extrusion, contour-plane border interpretation, mid-plane or shape-based end-capping, triangulated surface methods, and slice-to-slice summation approaches.

Random-point sampling should be avoided as the primary method in a gold-standard tool unless accompanied by fixed seeds and convergence control; deterministic polygon or surface integration is preferable. For dose-to-volume metrics in steep gradients, local **adaptive refinement** is essential. The paper’s plan-1 results imply that a reference implementation should aim for internal numerical error materially below the reported commercial spread; roughly below **1%** for large-structure volume in simple phantoms, below **1-2%** for D2cc in moderate gradients, and below about **3%** for D0.1cc in plan-1-like conditions. These thresholds are engineering inferences rather than paper-stated tolerances. The software should also emit warnings when the requested hot subvolume lies in a terminal slice, when total organ volume is very small, or when source-to-surface distance is on the order of **5 mm**, because those are the situations in which the paper found **>10%** discrepancies.

#### 7b. Validation recommendations

This paper effectively provides a ready-made validation matrix. At minimum, the reference calculator should reproduce the three analytic geometries; **4.02 cc** cylinder, **56.54 cc** cylinder, and **63.02 cc** truncated cone; on slice stacks of **2 mm**, **4 mm**, and **5 mm**, with deliberately randomised object-start z offsets so that terminal-slice ambiguity is exercised. Validation should be split into: **(i)** pure volume reconstruction against analytic ground truth; **(ii)** DVH calculation on a fixed, independently defined dose field; and **(iii)** end-to-end dose plus DVH comparison using the two paper geometries with **17 dwell positions**, the stated source distances, and the same queried endpoints D0.1cc, D1cc, and D2cc.

The paper also identifies two particularly valuable stress tests: a **2 mm** contour expansion and a **6 mm** source shift. Any benchmark suite should include both, because they expose whether the calculator can cleanly separate uncertainty from contour definition versus source reconstruction. The paper does not report publicly released benchmark files, so an open-source reference project should recreate equivalent synthetic DICOM datasets and publish them with expected results under multiple end-cap conventions.

#### 7c. Extensibility considerations

Although the paper is focused on standard cumulative DVH metrics, it strongly motivates a data model that supports **arbitrary dose-at-volume queries**, both absolute and relative. The implementation should natively support D0.1cc, D1cc, D2cc, D10, D90, V100, V150, and generalised Dxcc and Vx calls without special-casing.

More importantly, the very large changes produced by **2 mm contour expansion** and **6 mm source displacement** argue for an **uncertainty-analysis layer**: contour perturbation ensembles, source-shift ensembles, and uncertainty bands on DVHs. That would be more informative than a single scalar DVH when hotspots are driven by edge effects or near-source geometry. The paper does not directly study DSH, DMH, EUD or gEUD, or dosiomics, but because the failure modes are spatially localised, a future-proof calculator should preserve enough local geometric information to support hotspot localisation maps, dose-surface representations, and biological overlays later.

#### 7d. Caveats and limitations

The paper is excellent for exposing **mechanisms** of disagreement, but the exact percentages should not be over-generalised. First, the test objects were regular solids rather than irregular patient contours. Second, dosimetry used a simple one-catheter equal-dwell arrangement rather than realistic inverse-planned implants. Third, DVH differences were not cleanly isolated from dose-calculation settings: vendor-specific grid sizes and internal implementations differed, even though the same TG-43 source dataset was entered. Fourth, only **two TPSs** were used for the contouring study and **five** for DVH comparison. Finally, some crucial computational details; DVH bin width, partial-volume weighting, interpolation kernel, and the denominator for the “maximum” percentage in the main DVH comparison table; were [DETAIL NOT REPORTED]. A reference calculator should therefore treat this paper as strong evidence for *which test cases matter*, but not as definitive numeric tolerance limits for all anatomy or all software generations.

### 8. Connections to other literature

1. **Fellner, Sommer, Siedhoff, and Pötter, 1998** a direct predecessor comparing volume-calculation accuracy across TPSs; the present paper revisits the same problem with newer brachy systems and shows smaller spreads overall.

2. **Herman, Zheng, and Bucholtz, 1992** provides the shape-based interpolation approach cited as the basis for the terminal-slice handling used in BrachyVision.

3. **Crook and colleagues, 2002** showed that interobserver prostate post-implant CT contouring affects brachy quality assessment; this paper complements that finding by quantifying TPS-intrinsic variance.

4. **Han and colleagues, 2003** another prostate brachy study linking interobserver CT interpretation to dosimetric parameter variation; conceptually aligned with the observer-variation arm of the present work.

5. **Haie-Meder and colleagues, 2005** part of the GEC-ESTRO move toward 3D image-based cervix brachy terminology and concepts, helping create the clinical need for accurate volumetric dose reporting.

6. **Pötter and colleagues, 2006** GEC-ESTRO Working Group II recommendations on 3D dose-volume parameters in cervix brachy; the present study functions as a physics validation counterpart for those metrics.

7. **Kirisits and colleagues, 2005** MRI-based intracavitary cervix planning work that used dose-volume parameters clinically; the present study addresses the computational trustworthiness of such parameters.

### 9. Data extraction table

The paper contains substantial quantitative data suitable for extraction. The tables below summarise the benchmark geometry and the main reported variability results.

**Table 9A. Benchmark phantom geometry and imaging datasets**

| Structure | Dimensions | True volume (cc) | Intended clinical analogue |
|---|---:|---:|---|
| Small cylinder | 80 mm length, 8 mm diameter | 4.02 | Urethra-like small organ |
| Large cylinder | 80 mm length, 30 mm diameter | 56.54 | Rectum-like organ |
| Truncated cone | 45 mm length, 28-55 mm diameter | 63.02 | Bladder-like organ |
| CT dataset 1 | 2 mm slice thickness | ;  | Volume comparison |
| CT dataset 2 | 4 mm slice thickness | ;  | Volume comparison; DVH comparison |
| CT dataset 3 | 4 mm spiral CT | ;  | Volume comparison |
| MRI dataset | 5 mm slice thickness | ;  | Volume comparison |

**Table 9B. Inter-system volume variability**

*Standard deviation = relative standard deviation across the seven TPSs. Offset = difference between the across-system mean volume and the analytic true volume, relative to the true volume.*

| Dataset | Small cylinder SD / offset | Large cylinder SD / offset | Cone SD / offset |
|---|---:|---:|---:|
| CT 2 mm | 3% / -1.7% | 1% / +0.5% | 2% / +8.3% |
| CT 4 mm | 7% / +0.4% | 2% / +2.2% | 5% / +3.6% |
| CT 4 mm spiral | 4% / -3.1% | 3% / -1.2% | 4% / +2.3% |
| MRI 5 mm | 9% / +5.5% | 3% / +2.2% | 6% / +1.8% |

**Table 9C. DVH variability**

*“Maximum” is the maximum deviation between two TPS dose values as reported by the authors; percentage denominator [DETAIL NOT REPORTED].*

**Treatment plan 1: large cylinder and cone**

| Structure | Metric | Inter-system 1 SD | Inter-system maximum | Inter-observer 1 SD | Inter-observer maximum |
|---|---|---:|---:|---:|---:|
| Large cylinder | D0.1cc | 3% | 8% | 5% | 11% |
| Large cylinder | D1cc | 1% | 2% | 1% | 1% |
| Large cylinder | D2cc | 1% | 3% | 1% | 3% |
| Cone | D0.1cc | 3% | 6% | 4% | 11% |
| Cone | D1cc | 5% | 11% | 2% | 5% |
| Cone | D2cc | 5% | 12% | 3% | 7% |

**Treatment plan 2: small cylinder and large cylinder**

| Structure | Metric | Inter-system 1 SD | Inter-system maximum | Inter-observer 1 SD | Inter-observer maximum |
|---|---|---:|---:|---:|---:|
| Small cylinder | D0.1cc | 4% | 8% | 0% | 1% |
| Small cylinder | D1cc | 4% | 7% | 2% | 5% |
| Small cylinder | D2cc | 4% | 7% | 3% | 9% |
| Large cylinder | D0.1cc | 6% | 13% | 6% | 16% |
| Large cylinder | D1cc | 8% | 15% | 4% | 10% |
| Large cylinder | D2cc | 5% | 10% | 4% | 9% |

**Additional perturbation results**

| Perturbation | Endpoint | Change |
|---|---|---:|
| 2 mm concentric expansion of large cylinder | D0.1cc | +15% |
| 2 mm concentric expansion of large cylinder | D1cc | +14% |
| 2 mm concentric expansion of large cylinder | D2cc | +12% |
| 6 mm source-line shift | D0.1cc | up to ±53% |
| 6 mm source-line shift | D1cc | up to ±50% |
| 6 mm source-line shift | D2cc | up to ±44% |

### 10. Critical appraisal (100-200 words)

**Strengths:** unusually clean separation of observer variation from TPS-intrinsic reconstruction variation; analytically known phantom volumes; clinically relevant endpoints such as D2cc, D1cc, and D0.1cc; and, most importantly, explicit discussion of vendor-specific end-slice and reconstruction algorithms.

**Weaknesses:** no public benchmark dataset, no absolute dosimetric ground truth beyond cross-system TG-43 consistency, descriptive statistics only, simple one-catheter dose geometry, regular rather than clinical contours, and several missing computational details marked as [DETAIL NOT REPORTED].

**Confidence in findings:** **Medium** high for the qualitative mechanisms and relative ranking of failure modes, but only medium for exact numerical spreads because they are version-specific and partly confounded by vendor dose-grid and sampling implementations.

**Relevance to reference DVH calculator:** **High** this paper directly identifies the algorithmic edge cases a benchmark DVH engine must model, disclose, and test: terminal-slice ambiguity, small-structure behaviour, steep-gradient hotspot metrics, and separation of contour or source uncertainty from numerical integration error.

---

<!-- Source: SUMMARY - Henriquez 2008 - A Novel Method for the Evaluation of Uncertainty in DVH Computation.md -->

## Henríquez (2008) - A novel method for the evaluation of uncertainty in dose-volume histogram computation

### Executive summary

This paper introduces the **dose-expected volume histogram** (DeVH), a probabilistic extension of the conventional cumulative DVH intended to account for **uncertainty in point-dose calculation** during plan evaluation. Rather than treating each voxel dose as exact, the method models dose as a random variable with a specified uncertainty distribution and computes the **expected volume** receiving at least a given dose threshold. In practice, this transforms the differential DVH by redistributing dose-bin contributions according to an assumed dose-error kernel.

The technical contribution is conceptually important for a reference-quality DVH calculator because it separates the deterministic DVH from the **confidence one should place in it**. The paper shows analytically that the standard DVH is recovered in the zero-uncertainty limit, and it provides a computationally simple formulation that can be implemented as a histogram-space operator rather than a Monte Carlo simulation.

In the authors’ clinical examples, using a **uniform relative standard uncertainty of 3.6%** caused relatively small changes in **mean dose** but sometimes very large changes in **PTV coverage and extremal dose metrics**. Selected examples showed **maximum dose increases of up to 4.56 Gy**, **minimum dose decreases of up to 4.56 Gy**, and **V95 reductions as large as 26.9 percentage points**. OAR Vx metrics generally changed much less, especially for broad shallow DVHs.

For development of a benchmark DVH engine, the paper strongly motivates an **optional uncertainty-propagation layer** that sits alongside the standard geometric DVH computation. However, the numerical magnitudes in this study should be interpreted cautiously because the work does **not** validate dose uncertainty against ground truth, uses a **single global uncertainty parameter**, and reports mostly **illustrative worst-case examples** rather than cohort-average effects.

### 1. Bibliographic record

- **Authors:** Francisco Cutanda Henríquez; Silvia Vargas Castrillón
- **Title:** A novel method for the evaluation of uncertainty in dose-volume histogram computation
- **Journal:** International Journal of Radiation Oncology, Biology, Physics
- **Year:** 2008
- **DOI:** [10.1016/j.ijrobp.2007.11.038](https://doi.org/10.1016/j.ijrobp.2007.11.038)
- **Open access:** Preprint (journal article published in *International Journal of Radiation Oncology, Biology, Physics*; preprint available on arXiv)

### 2. Paper type and scope

**Type:** Original research

**Domain tags:** D1 Computation | D2 Commercial systems | D3 Metric innovation

**Scope statement:**
This paper proposes a probabilistic extension of the cumulative DVH, termed the **dose-expected volume histogram** (DeVH), intended to incorporate point-dose calculation uncertainty into plan evaluation. The method is derived analytically, then applied to clinical DVHs from prostate, lung, and brain plans generated in Pinnacle 7.4f, with the main claim that steep target DVHs are much more sensitive to dose uncertainty than most OAR DVHs.

### 3. Background and motivation

By 2008, DVHs were already central to IMRT prescription, evaluation, and optimisation, but most of the methodological work on DVH accuracy had focused on **volume sampling and structure discretisation** rather than on **uncertainty in the underlying dose values**. The paper explicitly positions itself against that gap: prior work by Niemierko and Goitein, Lu and Chin, and Kooy and colleagues had addressed random sampling, grid placement, and small-volume geometry, but not how uncertainty in point-dose computation propagates into a DVH-derived clinical decision.

The authors argue that this omission matters because a DVH point is a composite quantity built from many dose evaluations, each potentially affected by different uncertainty sources: measurement uncertainty in beam data, algorithmic limitations that depend on geometry and heterogeneity, and residual beam-model mismatch. They also note that two voxels with identical computed dose may have very different uncertainty contexts, for example penumbra, proximity to density interfaces, or beam modifier transmission. Existing QA guidance recommended assessment of DVH accuracy, but there was no simple framework analogous to point-dose uncertainty reporting.

For a reference-quality DVH engine, this paper is important not because it improves geometric DVH calculation directly, but because it reframes DVH evaluation as a **probabilistic problem**. It is an early attempt to separate “the reported DVH” from “the confidence one should place in that DVH”, which remains highly relevant when benchmarking commercial TPS outputs.

### 4. Methods: detailed technical summary

This is a **single-centre analytical/method-development study with retrospective computational application** to existing clinical plans. The theoretical contribution is the definition of a cumulative **dose-expected volume histogram**, `DeVHc(x)`, as the expected volume of an ROI receiving dose `>= x`. In voxel form, each sampled dose point `z_i` is treated as a random variable `D_i` with mean equal to the computed dose `D(z_i)` and variance `σ_i^2`; a Bernoulli indicator `T_i^x` denotes whether that voxel receives at least threshold x. By linearity of expectation, the expected volume above threshold is the sum of voxel volumes weighted by `P(D_i >= x)`. When reformulated in dose-bin space, the method operates on the **differential DVH** rather than directly on the raw voxel set. The key computational relation is essentially
`DeVHc(d_j) = Σ_k [1 - F((d_j - d_k)/(u d_k))] DVHd(d_k)`,
where `u` is the relative standard uncertainty and `F` is the cumulative distribution function of the assumed standardised dose-error model. The conventional DVH is recovered exactly in the zero-uncertainty/Dirac-delta limit.

The paper discusses both Gaussian and rectangular point-dose distributions, but for practical calculations chooses a **rectangular distribution** as recommended by the ISO guide when type-B components dominate and no better distribution is justified. With unit SD, that standardised rectangular pdf has support `[-√3, +√3]`; therefore, with a relative standard uncertainty `u`, a bin at dose `d_k` is effectively redistributed across an interval of width `±√3 u d_k`. For the study value `u = 3.6%`, that corresponds to an implicit support of about **±6.2% of local dose**, which is clinically non-trivial. The paper also derives an upper bound on the SD of `DeVHc(x)` by summing Bernoulli variances, while acknowledging that omitted covariance terms make this an overestimate because neighbouring voxel uncertainties are correlated. Figure 1 illustrates the dose-bin redistribution graphically: lower bins can partially contribute to a higher threshold, and some high-dose-bin volume is correspondingly diluted.

The practical application used DVHs from **8 conventional prostate plans**, **6 prostate IMRT plans**, **8 lung plans**, and **6 brain plans**. ROIs were: prostate PTV, bladder, rectum; IMRT prostate PTV1, PTV2, PTV3, bladder, rectum; lung PTV, both lungs, spinal cord; and brain PTV plus brain stem. The TPS was Pinnacle, version `7.4f` (Philips). DVH dose bins were **25-32 cGy** wide, giving roughly **200 histogram points** per case. All calculations used **absolute dose and volume values** in **cGy** and **cc** doses are converted to **Gy** below for consistency. The manuscript does **not** report the native dose-grid resolution, calculation voxel size, dose algorithm, beam energy, heterogeneity correction details, structure rasterisation method, interpolation method, boundary handling, partial-volume weighting, supersampling, end-capping, or whether the input DVHs were exported cumulative or reconstructed from bin counts. These are all **[DETAIL NOT REPORTED]**.

The uncertainty parameter was fixed at **3.6%** for all ROIs in the clinical application. The authors state that this was composed from **3.3%** for the Pinnacle “irregular block case” in the Venselaar/Welleweerd survey and **1.5%** from IAEA TRS-398 reference dosimetry. They explicitly describe this as an **underestimate**, because the survey conditions were idealised and the dosimetry value applies only in reference conditions. A separate figure for an IMRT prostate PTV shows sensitivity for `u = 1%, 2%, 3%, 4%, 5%`.

The comparison was purely **DVH vs DeVH**, not TPS vs measurement or TPS vs independent recalculation. Extracted metrics were mean dose, SD, maximum dose, minimum dose, median dose, first quartile, and third quartile. Maximum dose was defined unusually as the dose corresponding to **1 cc** on the cumulative histogram. They also tabulated selected Vx metrics and V95 target coverage. No formal statistical hypothesis tests, p-values, confidence intervals across patients, or effect-size analyses were reported. Importantly, Tables 1-4 present the **single case with the largest difference for each ROI**, not cohort means; Table 5 presents **minimum- and maximum-difference cases** for selected Vx metrics. There is therefore **no ground-truth reference standard** and no estimate of typical-case performance across the cohort.

### 5. Key results: quantitative

The dominant quantitative result is that DeVH changed **PTV coverage far more than mean dose**, and far more than most OAR Vx metrics. Across the largest-difference examples in Tables 1-4, **mean dose changed only from -0.19 Gy to +0.01 Gy**, whereas **maximum dose increased by 0.88-4.56 Gy** and **minimum dose decreased by up to 4.56 Gy**. For example, in the worst IMRT prostate PTV examples, maximum dose rose from **76.00 Gy to 80.56 Gy** in PTV1, PTV2, and PTV3, while minimum dose fell from **53.20 Gy to 50.16 Gy** (PTV1), **63.84 Gy to 59.66 Gy** (PTV2), and **69.54 Gy to 64.98 Gy** (PTV3). In brain PTV, maximum dose increased from **62.31 Gy to 66.03 Gy** and minimum dose fell from **36.58 Gy to 34.10 Gy**. In lung PTV, the corresponding change was **58.31 Gy to 61.82 Gy** for maximum dose and **43.36 Gy to 40.43 Gy** for minimum dose. These shifts are visible in the paper’s plotted PTV curves, which become visibly broadened once uncertainty is included.

Target coverage changes in Table 5 are even more striking. Using the paper’s selected minimum- and maximum-difference cases, V95 dropped from **99.95% to 81.1%** in one conventional prostate case (**-18.85 percentage points**), and from **99.8% to 72.9%** in another (**-26.9 percentage points**). In prostate IMRT, V95 dropped from **100.0% to 88.9%** (**-11.1 pp**) in the smaller-change case and from **99.6% to 80.6%** (**-19.0 pp**) in the larger-change case. Lung PTV V95 decreased from **96.3% to 79.4%** (**-16.9 pp**) in one case and from **88.0% to 82.0%** (**-6.0 pp**) in another. Brain PTV V95 decreased from **97.7% to 90.0%** (**-7.7 pp**) and from **99.9% to 83.2%** (**-16.7 pp**). The associated DeVH uncertainty reported for V95 ranged from **±1.1 to ±5.6 percentage points**.

OAR metrics changed much less, and not always in the same direction. The largest bladder change reported was conventional-prostate V40 from **46.8 cc to 45.3 cc** (**-1.5 cc**, **-3.2% relative to the DVH value**). Rectal changes were smaller: conventional-prostate V40 shifted at most from **23.61 cc to 23.42 cc** (**-0.19 cc**), and IMRT rectum V50 from **27.6 cc to 26.7 cc** (**-0.9 cc**). Lung V30 shifts were numerically larger in absolute volume because of organ size, but still modest relative to baseline: right-lung V30 changed from **1102.82 cc to 1094.23 cc** (**-8.59 cc**, **-0.78% relative to the DVH value**). A left-lung case actually increased slightly, from **61.0 cc to 61.3 cc** (**+0.3 cc**), showing that the method does not enforce one-way bias in shallow DVHs. Brain-stem V50 changed from **0.27 cc to 0.28 cc** in one case and **9.5 cc to 9.3 cc** in another.

The figure with `u = 1-5%` for IMRT prostate PTV shows the expected monotonic pattern: larger assumed uncertainty produces greater PTV edge blurring and larger divergence from the conventional DVH, especially around the steep fall-off region. No p-values, cohort-mean confidence intervals, or formal significance testing were provided. Because Tables 1-4 are worst-case exemplars rather than averages, the results are best interpreted as **illustrative sensitivity bounds under the chosen model**, not estimates of typical clinical impact.

### 6. Authors' conclusions

The authors conclude that DeVH is a practical way to account for point-dose calculation uncertainty during treatment-plan evaluation, and that the effect is **largest for PTVs with steep DVH gradients**. They emphasise two consequences: apparent target homogeneity worsens once uncertainty is included, and reported maximum dose may be substantially higher than the value read directly from a conventional DVH. They therefore argue that uncertainty associated with dose calculation should be considered alongside prescription-dose uncertainty when judging whether a plan meets the usual **±5%** target-accuracy goal.

That interpretation is **well supported** qualitatively: the mathematics predicts the strongest effect at steep gradients, and the illustrative tables and figures do show large V95 and max/min-dose changes for PTVs with much smaller mean-dose changes. The stronger claim that plans may need **re-evaluation or re-optimisation** is plausible but less secure, because the paper does not validate the assumed uncertainty model against measurement or delivered-dose data, and it presents exemplar rather than cohort-average numerical effects.

### 7. Implications for reference DVH calculator design

#### 7a. Algorithm and implementation recommendations

A reference DVH calculator should treat this paper as a strong argument for making **uncertainty propagation a first-class, optional layer** on top of the baseline geometric/dosimetric DVH engine. The DeVH formalism is attractive because it is **analytical and efficient**: once a differential DVH exists, the uncertainty-adjusted cumulative histogram is just a weighted bin redistribution. In implementation terms, this is a sparse dose-bin operator, not a Monte Carlo simulation. However, it should **not** replace the standard DVH; it should be a parallel output with explicit provenance: uncertainty model, parameter values, distribution family, and whether uncertainty is constant, dose-dependent, or spatially varying.

The reference tool should support at least **rectangular**, **Gaussian**, and **custom user-defined** dose-error models. This paper’s rectangular choice is reasonable for dominant type-B uncertainty, but it is only one assumption. Likewise, the paper’s global `u = 3.6%` is too coarse for a benchmark tool. The software should allow `u(x)` or `u(d,x)` maps, because the authors themselves note that low-dose/low-gradient regions may have worse accuracy and that using a single high-dose `u` **underestimates** the effect. Also, because the rectangular model with `u = 3.6%` implies support of roughly **±6.2%**, the UI and documentation must distinguish clearly between **standard uncertainty** and **full support interval** otherwise users will underestimate how aggressive the smoothing actually is.

The paper also reinforces that single-point or tiny-volume hotspot metrics are fragile under uncertainty. Since maximum dose rose by as much as **4.56 Gy** in the worked examples, the reference calculator should prefer robust finite-volume metrics such as D0.03cc, D0.1cc, D1cc, or configurable hot-spot volumes, rather than a single “maximum dose” concept. Finally, this uncertainty layer should be applied preferably to the **raw voxel-dose/structure representation**, not only to a pre-binned TPS DVH, because otherwise TPS binning and rasterisation artefacts are silently inherited.

#### 7b. Validation recommendations

This paper suggests several excellent validation tests. First, the **zero-uncertainty limit** must reproduce the standard DVH exactly; the paper proves this analytically, so any implementation should recover it to machine precision. Second, synthetic differential-DVH test cases should be used to verify the rectangular-kernel redistribution: a single occupied dose bin, a box distribution, and a steep step-like PTV fall-off should all have closed-form expected behaviour. Third, volume conservation and cumulative monotonicity should be regression-tested for all supported distributions.

To expose the paper’s observed failure modes, validation datasets should include: a steep target edge, a small serial OAR hotspot, a large shallow OAR DVH, and low-dose bins near zero. The steep target case should reproduce the sort of V95 sensitivity seen here (**up to -26.9 percentage points** in selected examples), while the shallow OAR case should remain relatively stable. Because the study gives no public dataset, a reference implementation should construct analytical phantoms plus public DICOM test sets and keep the uncertainty-propagation tests separate from geometric DVH-accuracy tests. Tolerances should be much tighter than clinical bin widths: exact-limit tests at numerical precision, and histogram-operator conservation errors below **0.01 cc** or an equivalent fractional-volume threshold are reasonable engineering targets, though these thresholds are extrapolated from the method rather than specified by the authors.

#### 7c. Extensibility considerations

The central extensibility lesson is that the calculator should not stop at a deterministic cumulative DVH. This paper motivates a general interface for **probabilistic histogram outputs**: expected Vx, expected Dx, uncertainty bands, and eventually distributions of derived metrics. The same framework can naturally extend to `gEUD/EUD`, NTCP/TCP inputs, dose-surface histograms (DSH), and dose-mass histograms (DMH) by changing the weighting measure from volume to surface element or mass element.

A modern implementation should also support **scenario ensembles** and **spatial uncertainty models**, because the paper explicitly separates its point-dose uncertainty model from setup, motion, and anatomical uncertainty and notes that such methods could be combined. In practice, that argues for data structures that can store per-voxel pdf parameters, scenario probabilities, and possibly covariance surrogates, rather than only a single scalar `u` per ROI.

#### 7d. Caveats and limitations

The biggest caveat is conceptual: this is **not** a validation of DVH computation accuracy against ground truth. It is a deterministic transformation of an already-computed TPS DVH under an assumed uncertainty model. Therefore, it cannot disentangle dose-engine error, TPS DVH geometry error, export/binning error, or structure discretisation error. For a benchmark DVH engine, those components must be separated.

The numerical magnitudes also do not generalise cleanly. The fixed **3.6%** uncertainty came from older Pinnacle benchmarking plus reference dosimetry and was acknowledged by the authors as an underestimate and approximation. Modern algorithms, Monte Carlo-based TPSs, VMAT, adaptive workflows, proton plans, or MRI-linac contexts will have different uncertainty structure. In addition, the paper ignores volume-computation uncertainty, spatial covariance, and geometric or anatomical uncertainties, and its tables emphasise **largest-difference cases** rather than typical cases. A final minor but important caveat: Table 5’s abbreviation line defines V95 as volume receiving at least **95 Gy**, but the text clearly states it is the volume covered by the **95% isodose** this is almost certainly a typographic error and should not be copied into a databank uncritically.

### 8. Connections to other literature

- **Niemierko and Goitein (1990):** Foundational study of random sampling for treatment-plan evaluation; this paper extends the conversation from geometric sampling accuracy to probabilistic dose uncertainty.
- **Lu and Chin (1993):** Comparison of sampling techniques for plan evaluation; complementary because Henríquez and Castrillón assume a baseline DVH already exists and ask how uncertain dose values modify it.
- **Kooy et al. (1993):** Improved DVH computation for small intracranial volumes; should be read alongside this paper when both small-structure geometry error and dose uncertainty are relevant.
- **Venselaar, Welleweerd and Mijnheer (2001):** TPS dose-calculation tolerance framework; supplies the Pinnacle uncertainty value used here to set `u = 3.6%`.
- **Cho et al. (2002):** Evaluates the effect of setup uncertainties, contour changes, and heterogeneities on target DVHs; complements this work by addressing spatial and scenario uncertainties rather than point-dose probability distributions.
- **Jin et al. (2005):** Dose-uncertainty modelling for verification; cited by the authors as related probabilistic uncertainty work feeding into DVH interpretation.
- **Wahl et al. (2020):** Later analytical probabilistic modelling of DVH points; conceptually adjacent modern extension of probabilistic DVH mathematics.

### 9. Data extraction table

**Table 9A. Largest-difference example per ROI from paper Tables 1-4; doses converted from cGy to Gy; arrows denote `DVH → DeVH`.**

| Site | ROI | Mean dose (Gy) | Maximum dose (Gy) | Minimum dose (Gy) |
|---|---|---:|---:|---:|
| Conventional prostate | PTV | 49.20 → 49.07 | 49.88 → 52.61 | 47.25 → 44.25 |
| Conventional prostate | Bladder | 42.72 → 42.59 | 49.69 → 52.15 | 26.00 → 24.25 |
| Conventional prostate | Rectum | 36.81 → 36.69 | 49.20 → 51.04 | 27.25 → 25.50 |
| Prostate IMRT | PTV1 | 69.13 → 68.94 | 76.00 → 80.56 | 53.20 → 50.16 |
| Prostate IMRT | PTV2 | 71.75 → 71.56 | 76.00 → 80.56 | 63.84 → 59.66 |
| Prostate IMRT | PTV3 | 73.38 → 73.19 | 76.00 → 80.56 | 69.54 → 64.98 |
| Prostate IMRT | Bladder | 51.36 → 51.18 | 76.00 → 80.56 | 12.54 → 11.40 |
| Prostate IMRT | Rectum | 49.25 → 49.06 | 73.34 → 77.90 | 6.84 → 6.08 |
| Lung | PTV | 54.14 → 54.00 | 58.31 → 61.82 | 43.36 → 40.43 |
| Lung | Spinal cord | 8.22 → 8.23 | 24.03 → 25.49 | 0.00 → 0.00 |
| Lung | Left lung | 4.07 → 3.94 | 16.99 → 17.87 | 0.00 → 0.00 |
| Lung | Right lung | 22.39 → 22.25 | 58.31 → 61.82 | 0.00 → 0.00 |
| Brain | PTV | 60.10 → 59.94 | 62.31 → 66.03 | 36.58 → 34.10 |
| Brain | Brain stem | 25.74 → 25.58 | 55.80 → 59.21 | 2.79 → 2.48 |

**Table 9B. V95 coverage changes from paper Table 5; `pp` = percentage points.**

| Site | Case | DVH V95 (%) | DeVH V95 (%) | Δ V95 (pp) | DeVH uncertainty (pp) |
|---|---|---:|---:|---:|---:|
| Prostate | min difference | 99.95 | 81.1 | -18.85 | 3.0 |
| Prostate | max difference | 99.8 | 72.9 | -26.9 | 3.5 |
| Prostate IMRT | min difference | 100.0 | 88.9 | -11.1 | 2.6 |
| Prostate IMRT | max difference | 99.6 | 80.6 | -19.0 | 3.2 |
| Lung | min difference | 96.3 | 79.4 | -16.9 | 2.3 |
| Lung | max difference | 88.0 | 82.0 | -6.0 | 1.1 |
| Brain | min difference | 97.7 | 90.0 | -7.7 | 5.6 |
| Brain | max difference | 99.9 | 83.2 | -16.7 | 3.0 |

**Table 9C. OAR Vx changes from paper Table 5.**

| Site | Metric | Case | DVH | DeVH | Δ | DeVH uncertainty |
|---|---|---|---:|---:|---:|---:|
| Prostate | Bladder V40 (cc) | min difference | 34.95 | 34.91 | -0.04 | 0.59 |
| Prostate | Bladder V40 (cc) | max difference | 46.8 | 45.3 | -1.5 | 1.2 |
| Prostate | Rectum V40 (cc) | min difference | 19.47 | 19.30 | -0.17 | 0.88 |
| Prostate | Rectum V40 (cc) | max difference | 23.61 | 23.42 | -0.19 | 0.94 |
| Prostate IMRT | Bladder V50 (cc) | min difference | 32.8 | 32.2 | -0.6 | 1.5 |
| Prostate IMRT | Bladder V50 (cc) | max difference | 26.0 | 24.2 | -1.8 | 1.8 |
| Prostate IMRT | Rectum V50 (cc) | min difference | 25.3 | 25.2 | -0.1 | 1.2 |
| Prostate IMRT | Rectum V50 (cc) | max difference | 27.6 | 26.7 | -0.9 | 1.7 |
| Lung | Left lung V30 (cc) | min difference | 61.0 | 61.3 | +0.3 | 2.7 |
| Lung | Left lung V30 (cc) | max difference | 330.5 | 328.6 | -1.9 | 2.5 |
| Lung | Right lung V30 (cc) | min difference | 182.6 | 179.8 | -2.8 | 3.1 |
| Lung | Right lung V30 (cc) | max difference | 1102.82 | 1094.23 | -8.59 | 4.5 |
| Brain | Brain stem V50 (cc) | min difference | 0.27 | 0.28 | +0.01 | 0.09 |
| Brain | Brain stem V50 (cc) | max difference | 9.5 | 9.3 | -0.2 | 1.3 |

**Note:** The paper states in the main text that V95 is the volume covered by the **95% isodose**, but the Table 5 abbreviation line defines it as volume receiving at least **95 Gy**. Given the prescription levels in the paper, this is almost certainly a table-footnote typo. Also, Tables 1-4 are **largest-difference examples**, not cohort averages.

### 10. Critical appraisal

**Strengths:** This is a genuinely useful methodological paper. It gives a clean probabilistic definition of uncertainty-adjusted DVHs, derives a practical closed-form computation, proves consistency with the standard DVH in the zero-uncertainty limit, and demonstrates clinically interpretable effects across multiple disease sites. It is especially valuable for highlighting how steep-gradient PTV metrics can be much more fragile than mean dose.

**Weaknesses:** There is no ground-truth validation, no independent dose recalculation, no spatial uncertainty model, no handling of volume-computation uncertainty, and many implementation-critical DVH details are **[DETAIL NOT REPORTED]**. The numerical results are strongly model-dependent because they rely on a single uniform `u = 3.6%` rectangular uncertainty model. Tables 1-4 report only worst-case exemplars, so typical-case effect size remains unknown.

**Confidence in findings:** **Medium.** The qualitative conclusion; that steep DVHs are more sensitive to dose uncertainty than broad shallow OAR DVHs; is well supported and mathematically credible. The exact magnitudes are much less generalisable.

**Relevance to reference DVH calculator:** **High.** Not because it solves structure rasterisation or partial-volume accuracy, but because it strongly motivates an uncertainty-propagation layer, probabilistic DVH outputs, robust hotspot definitions, and validation tests that distinguish geometric DVH accuracy from dose-engine uncertainty.

---

<!-- Source: SUMMARY - Ebert 2010 - Comparison of DVH data from multiple radiotherapy TPSs.md -->

## Ebert (2010) - Comparison of DVH data from multiple radiotherapy treatment planning systems

### Executive summary

This technical note addresses a foundational question for multicentre radiotherapy studies: whether dose-volume histogram (DVH) data exported from different commercial treatment planning systems (TPSs) are sufficiently consistent to be pooled directly, or whether independent recomputation is needed. Using **36 plans** from **33 centres** in an anthropomorphic pelvic phantom study, the authors compared TPS-exported cumulative DVHs with independently recalculated DVHs generated in the review system SWAN. The comparison covered **227 structures** spanning approximately **2-1500 cc**, with a separate analysis of **50 target volumes** from **25 prostate plans**.

The main result is that agreement was generally good, but strongly dependent on **structure size** and **TPS implementation**. With a stringent DVH gamma-style criterion of **1% volume / 1% dose**, only **78%** of DVHs achieved the study’s acceptance threshold of at least **95% of bins passing**. Relaxing the volume criterion had a much larger effect than relaxing the dose criterion: at **5% volume / 1% dose**, the pass rate rose to **96%**, whereas loosening dose tolerance alone had comparatively limited impact. This points to **volume-definition and boundary-handling effects** as the dominant source of disagreement, especially for small structures. Larger structures showed very small differences, with relative volume discrepancies **<0.1%** and **<5%** failing bins.

Target **mean** and **maximum** dose agreed closely between TPSs and SWAN (both approximately **−0.1%**), but **minimum dose** was notably less stable, differing by **−0.9% ± 1.5%** on average. For a reference-quality DVH calculator, the paper strongly motivates a **deterministic, high-resolution, explicitly documented** computation pathway with configurable contour end-capping, boundary rules, interpolation, and provenance tracking. It also supports using stringent internal convergence tests for algorithm validation, while recognising that broader tolerances such as **5% volume / 2% dose** may be reasonable for interoperability with legacy multicentre TPS datasets.

### 1. Bibliographic record

**Authors:** Martin A. Ebert; Annette Haworth; Rachel Kearvell; Ben Hooton; Benjamin Hug; Nigel A. Spry; Sean A. Bydder; David J. Joseph.
**Title:** *Comparison of DVH data from multiple radiotherapy treatment planning systems*.
**Journal:** *Physics in Medicine and Biology*.
**Year:** 2010.
**DOI:** [10.1088/0031-9155/55/11/N04](https://doi.org/10.1088/0031-9155/55/11/N04).
**Open access:** No.

### 2. Paper type and scope

**Type:** Technical note.
**Domain tags:** **D1 Computation | D2 Commercial systems**.
**Scope statement:** This paper compares TPS-exported cumulative DVHs from multiple commercial radiotherapy planning systems with independently recalculated DVHs generated in the non-commercial review system SWAN. Its practical aim is to determine whether multicentre trial DVH data can be pooled directly across vendors, or whether independent recomputation is needed to reduce vendor- and resolution-dependent inconsistency.

### 3. Background and motivation (150-300 words)

The motivation is straightforward but important for any reference DVH engine: multicentre radiotherapy studies routinely aggregate DVH-derived metrics from different treatment planning systems, yet those DVHs are not purely physical observables. They depend on discretised CT geometry, contour representation, dose grid resolution, DVH binning, interpolation, and vendor-specific sampling algorithms. The authors note that it is tempting to assume pooled TPS DVHs are mutually consistent, but prior literature had already suggested that resolution and implementation differences can alter derived dose-volume quantities. What was missing was a clinically grounded, multicentre comparison using real exported plans from departments in routine use, rather than a purely analytical or single-system test.

This matters directly to DVH computation accuracy and trial QA. If exported DVHs vary materially across TPSs for the same phantom geometry and similar planning objectives, then outcome-modelling inputs, protocol compliance checks, and pooled normal-tissue analyses may inherit systematic bias. The paper therefore asks whether an independent recalculation pathway is justified for trial review, and which technical factors most influence disagreement: structure size, CT slice/pixel resolution, dose grid size, DVH dose-bin resolution, or TPS manufacturer. That question remains foundational for a benchmark-grade DVH calculator because it separates “DVH computation consistency” from “dose calculation accuracy” and highlights the need for traceable handling of boundaries, voxelisation, interpolation, and export semantics.

### 4. Methods: detailed technical summary (400-800 words)

The study was a multicentre comparative analysis based on exported plans from a prior Australasian dosimetric intercomparison using an anthropomorphic pelvic phantom. The phantom contained variable-density organs distinguishable on CT and was planned according to prostate and/or rectal protocols at **33 centres** across Australia and New Zealand. A total of **36 treatment plans** were collected, exported in RTOG and/or `DICOM-RT` format. Across all plans, the authors compared **227 delineated structures** spanning approximately **2 cc to 1500 cc**. A subset of **50 target volumes** from **25 prostate plans** was analysed separately for minimum, mean, and maximum dose differences. Site technique details, beam energies, and TPS dose-algorithm names were **[DETAIL NOT REPORTED]**.

The independent recalculation platform was SWAN version **2.0.3**, a non-commercial review/analysis system previously developed for clinical-trial plan review. SWAN recalculated DVHs using a method based on Straube et al. (2005). The structure handling is especially relevant. Contoured 3D elements were given superior/inferior extent using half-distance to adjacent axial slices, i.e. effectively a half-slice end-cap formulation. The image volume was then sampled on a user-defined voxel grid. For each sampled voxel, the **voxel centre** was tested for inclusion inside the structure; if inside, that voxel contributed to structure volume. This is therefore a **binary voxel-centre inclusion** method, not fractional partial-volume weighting. Dose at the voxel centre was obtained by **3D tri-linear interpolation** from the dose grid. The authors describe the method as computationally inefficient but robust for concave and bifurcated structures. The SWAN sampling resolution was chosen finer than the minimum exported image pixel size, specifically **<0.7 mm** whether this was isotropic in all three dimensions is **[DETAIL NOT REPORTED]**. The actual SWAN DVH dose bin size used in the study is also **[DETAIL NOT REPORTED]**, although table 2 notes that SWAN supports user-defined bin size.

The exported TPS DVHs were first checked against hardcopy outputs from the contributing centres by visual inspection for gross discrepancies. Manufacturer-reported DVH algorithms differed. XiO, Pinnacle, and Theraplan Plus used regular sampling on user-defined grids; XiO explicitly interpolated from the dose grid; Eclipse used regular sampling on a user-defined grid based on an interpolated structure outline; and Plato used **random sampling** on a user-defined dose grid. All systems used user-defined DVH dose-bin size. Nominal acquisition/calculation parameters also varied by vendor: CT slice thickness ranged from **2.5-5.0 mm**, in-plane pixel width from **0.78-1.25 mm**, dose-grid voxel width from **1.95-5.0 mm**, and exported DVH dose resolution from **0.01-0.70 Gy** (**1-70 cGy**, paper units). Again, the underlying photon dose algorithms, heterogeneity corrections, and delivery modalities were **[DETAIL NOT REPORTED]**.

Agreement was assessed using a DVH-adapted gamma-like metric. For each TPS DVH point, the authors searched all points in the paired SWAN DVH and computed a normalised Euclidean distance in the dose-volume plane. The pass condition was `γ_i < 1`, with dose criterion `D_R` expressed as a percentage of the maximum DVH dose Dmax, and volume criterion `V_R` expressed as a percentage of total structure volume `Vtot`. In compact form, they used
`γ_i = min_r sqrt([100(v_r-v_i)/(V_R Vtot)]^2 + [100(d_r-d_i)/(D_R Dmax)]^2)`.
The **higher-resolution DVH of the pair** was chosen as reference, which is a subtle but important methodological point: the gamma comparison was not always asymmetrically TPS-versus-SWAN. The authors examined the percentage of all DVHs for which at least **95% of bins** passed gamma, absolute total-volume difference relative to SWAN, and per-DVH percentage of bins failing gamma. Because cumulative target DVHs can be near-rectangular under uniform target coverage, they also separately extracted **minimum, mean, and maximum dose** for target volumes. Structure volume was taken as the cumulative DVH value at **zero dose**.

Statistical analysis used **SPSS 17.0** with multivariate regression and backward elimination. Independent variables were TPS manufacturer, CT slice thickness, CT pixel size, dose-grid resolution, and DVH dose-bin size; interactions were also investigated. The regression analysis used **`V_R = 1%` and `D_R = 1%`** because the authors judged these settings sensitive to DVH mismatch while remaining above the DVH dose resolution encountered. Important acknowledged limitations were that SWAN was only an **independent reference**, not absolute ground truth; plan export may not preserve the original TPS semantics perfectly; only a **single phantom geometry** was tested; and some TPSs were represented by only **one or two** samples, limiting generalisability. Manufacturer information on whether TPSs included half-slice regions beyond superior/inferior contour limits was also not consistently clear.

### 5. Key results: quantitative (300-600 words)

Overall agreement was good but not perfect, and the DVH gamma results were much more sensitive to the **volume criterion** than to the **dose criterion**. Using the study’s acceptance definition; at least **95% of bins** with `γ < 1`; only **78%** of all **227** DVHs passed at **(ΔV, ΔD) = (1%, 1%)**. Keeping `ΔD = 1%` and relaxing `ΔV` to **2%**, **5%**, and **10%** increased the pass proportion to **88%**, **96%**, and **100%**, respectively. By contrast, keeping `ΔV = 1%` and relaxing `ΔD` to **2%**, **5%**, and **10%** improved pass proportion only from **78%** to **82%**, **85%**, and **88%**. This is a very clear quantitative indication that the dominant disagreement mechanism, for these datasets, was volumetric/boundary-related rather than dose-bin-related.

Structure size was a major practical determinant. The scatterplots in figure 2 showed widening disagreement as structure volume decreased, especially below roughly **250 cc**. For larger structures (not plotted in the main panel), relative volume differences were reported as **<0.1%** and gamma-failing bins as **<5%**. Across all 227 structures, the authors further translated volume differences into equivalent-sphere radii and concluded that TPS and SWAN volumes agreed within **0.5 mm** in effective radius, i.e. **<2%** radius difference. Multiple regression found that **TPS manufacturer** was the only significant predictor of percentage volume difference (**p = 0.011**). At the stringent **1%/1%** gamma setting, the percentage of DVH samples with **>10% of bins failing** was **0% for XiO**, **29% for Plato**, **2% for Pinnacle**, **14% for Theraplan Plus**, and **13% for Eclipse**. The percentage of failing bins depended on dose-grid resolution (**p < 0.001**, univariate coefficient **−15% mm⁻¹**), TPS manufacturer (**p < 0.02**), and CT pixel size (**p < 0.03**, univariate coefficient **+57% mm⁻¹**), although the authors explicitly warn that manufacturer was correlated with grid and CT characteristics, so these coefficients should not be interpreted causally.

For target structures with relatively uniform dose distributions, mean and maximum dose agreed very well, but minimum dose did not. Across **50 target volumes** from **25 prostate plans**, the mean difference in **minimum dose** was **−0.9%** with absolute SD **1.5%** (**TPS relative to SWAN**, **p = 0.0001**). By contrast, the mean difference in **mean dose** was **−0.1% ± 0.2%**, and in **maximum dose** was **−0.1% ± 0.3%**. Figure 3 also shows that most minimum-dose differences clustered between about **0%** and **−2%**, with a few outliers approaching **−3% to −5%**. One important caveat is that the paper’s discussion text later states that almost all TPS-exported minimum doses were greater than SWAN; that statement conflicts with the figure and with the reported **−0.9%** mean difference. The quantitative result and plotted data support the negative sign, not the verbal statement.

A secondary qualitative result is that systems with DVH calculation methods most similar to SWAN; especially XiO and Pinnacle; also appeared to agree most closely with it. The authors specifically point to Plato’s random sampling as a likely contributor to its poorer performance on a limited sample count. Null/near-null findings were the excellent agreement in target **mean** and **maximum** dose, and the absence of appreciable large-structure disagreement under the study conditions.

### 6. Authors' conclusions (100-200 words)

The authors conclude that exported DVH data from multiple commercial TPSs are broadly consistent with independently recalculated DVHs, but that discrepancies increase as structures become smaller and depend significantly on TPS model. They interpret this as support for independent DVH recalculation when pooling multicentre trial data, because such recalculation can improve consistency and reproducibility of dose-volume quantities across vendors and export settings. They also argue that, in the context of clinical-trial uncertainties, the observed differences are acceptable: from their table 3 they infer that, under the tested conditions, DVH data can generally be expected to agree within about **5% in volume** and **2% in dose**.

That interpretation is mostly supported as a **pragmatic multicentre-trial statement**, but less so as a statement about **absolute DVH accuracy**. The study did not establish ground truth, only consistency relative to an independent reference implementation, and some manufacturer groups were sparsely sampled. Their conclusion that the agreement is “acceptable within the noise level” of trial data is reasonable operationally, but should not be mistaken for a benchmark standard for a reference-quality DVH engine.

### 7. Implications for reference DVH calculator design (300-600 words)

#### 7a. Algorithm and implementation recommendations

A reference calculator should decouple structure-set geometry from CT image geometry, as Test 0 showed that several commercial systems could not even process mismatched CT and structure spacings. The calculator should implement a **deterministic** high-resolution sampling mode, not a low-count stochastic mode, for benchmark operation. This paper shows that the vendor with explicitly reported **random sampling** (Plato) had the poorest agreement profile, with **29%** of DVH samples showing **>10%** failing bins at **1%/1%** gamma. Even if stochastic methods are efficient, a gold-standard reference should avoid random noise unless it can also report convergence and uncertainty bounds.

The engine should make boundary handling explicit and configurable. SWAN used voxel-centre inclusion plus superior/inferior half-slice extension, and the paper specifically identifies peripheral definition choices; half-slice inclusion, dose-grid/image-plane coincidence, and interpolation at structure edges; as likely causes of minimum-dose discrepancy. For reference use, boundary policy must therefore be a first-class parameter, not an undocumented implementation detail. At minimum, the engine should support: (1) explicit superior/inferior end-capping, (2) documented in-plane contour rasterisation rules, and (3) dose interpolation choice. Given the strong size dependence seen below about **250 cc**, a benchmark engine should additionally support **adaptive supersampling or fractional occupancy** rather than relying only on coarse binary inclusion at native grid resolution. That last point is an engineering inference from the observed small-structure failures, not something directly tested by the authors.

The reference implementation should also separate **legacy compatibility** from **benchmark accuracy**. The paper’s independent reference used sampling **<0.7 mm**, finer than the native CT pixel size, which is a sensible lower bound for a validation mode. But the authors’ practical tolerance of roughly **5% volume / 2% dose** is too loose as an internal target for a gold-standard engine; that level is better treated as a **legacy cross-TPS comparison envelope**. For clinically sensitive minima, the calculator should report Dmin but also expose more stable near-minimum metrics such as D98, D99, or D0.03cc as a robustness complement; that recommendation is an inference from the paper’s clear demonstration that Dmin is boundary-sensitive.

#### 7b. Validation recommendations

This paper suggests a two-tier validation programme. First, use **sensitive internal convergence tests**: compare DVHs generated at progressively finer sampling with a DVH-plane gamma metric at **1% volume / 1% dose**, using the paper’s convention that a valid DVH should have at least **95% of bins** passing. Second, use **pragmatic interoperability tests** against historical TPS exports, where **5% volume / 2% dose** can serve as an outer comparison envelope because the paper found near-universal passing there.

The specific test cases that would expose the failure modes seen here are: small structures down to **~2 cc** structures around and below the paper’s practical instability region of **~250 cc** concave and bifurcated structures; superior/inferior contour end-caps with non-uniform slice spacing; and uniformly irradiated targets where cumulative gamma is insensitive but Dmin is unstable. Validation datasets should include both `DICOM-RT` and legacy RTOG import pathways, because the paper used both. Publicly available benchmark data were **not provided** in the paper, and SWAN itself was non-commercial rather than openly released, so a modern reference project should create and publish an analogous phantom/export suite.

#### 7c. Extensibility considerations

The most obvious extension motivated by this paper is not a biological metric but a **comparison metric**: a reusable dvh_gamma or equivalent dose-volume-plane distance measure. That is useful for TPS benchmarking, regression testing, and QA of future algorithm changes. The engine should store full cumulative and differential histograms, original bin widths, structure volumes, and provenance metadata for CT slice width, pixel width, dose-grid spacing, interpolation method, and contour end-capping, because this paper shows those factors are analytically relevant.

A second extensibility implication is support for **boundary-centric metrics** such as DSH/DWH/DMH-style quantities and thin-wall representations. The paper cites boundary and partial-volume effects as dominant sources of disagreement, especially for small structures and peripheral minima; those issues become even more important for surface- and wall-based metrics. Finally, if stochastic sampling is ever supported for speed, the API should include uncertainty reporting and fixed seeding so that “reference” outputs remain reproducible.

#### 7d. Caveats and limitations

The study does **not** isolate DVH computation error from all other influences. It conflates export semantics, contour interpretation, grid resolution, and vendor implementation; it does not benchmark against analytical ground truth. It is also restricted to an anthropomorphic pelvic phantom, mostly prostate/rectal planning contexts, and old TPS versions (XiO 4.x, Eclipse 7.x, Pinnacle 6-8, etc.), so direct quantitative extrapolation to modern systems should be cautious. Plato and Theraplan Plus were represented by only **2** and **1** samples, respectively. Finally, the minimum-dose sign inconsistency noted above weakens confidence in that specific narrative interpretation, even though the plotted and tabulated numbers themselves remain useful.

### 8. Connections to other literature

- **Straube et al. (2005):** direct methodological precursor for the independent DVH calculation approach used in SWAN; the authors state that their method was based on this work.
- **Panitsa et al. (1998):** earlier DVH quality-control study on 3D TPS computation characteristics; this paper extends that concern into a multicentre export-comparison setting.
- **Low et al. (1998):** source of the spatial gamma-analysis concept that the authors adapted into the dose-volume plane.
- **Lu and Chin (1993):** classic treatment-plan sampling paper, used here to contextualise why random sampling may generate discrepancies when sample counts are limited.
- **Niemierko and Goitein (1990):** theoretical support for efficient random sampling; cited by the authors to explain that stochastic methods can be acceptable for optimisation even if they are unattractive for deterministic benchmark comparison.
- **Ackerly et al. (2003):** relevant companion paper on volume discrepancies between TPSs, especially for boundary and slice-thickness interpretation.
- **Chung et al. (2006):** related evidence that dose-grid size affects calculated quantities; this paper sees similar parameter dependence, though confounded by manufacturer.

### 9. Data extraction table

**Table 9.1. TPS representation and nominal acquisition/calculation parameters reported in the study.**

| TPS | Number in study | CT slice thickness (mm) | CT pixel width (mm) | Dose-grid voxel width (mm) | DVH dose resolution (Gy [cGy]) |
|---|---:|---:|---:|---:|---:|
| XiO | 9 | 2.5-3.0 | 0.80-0.89 | 2.5-3.0 | 0.10-0.15 [10-15] |
| Plato | 2 | 3.0 | 0.98 | 1.95 | 0.06-0.11 [6-11] |
| Theraplan Plus | 1 | 3.0 | 0.94 | 5.0 | 0.70 [70] |
| Pinnacle | 13 | 2.5-5.0 | 0.78-1.25 | 3.5-4.0 | 0.05-0.15 [5-15] |
| Eclipse | 8 | 2.5-3.0 | 0.86-0.98 | 2.5 | 0.01-0.15 [1-15] |

**Table 9.2. Percentage of all 227 DVHs with at least 95% of bins satisfying `γ < 1` for each DVH gamma criterion pair.**

| ΔV (% of total structure volume) | ΔD = 1% of max dose | ΔD = 2% | ΔD = 5% | ΔD = 10% |
|---|---:|---:|---:|---:|
| 1% | 78% | 82% | 85% | 88% |
| 2% | 88% | 89% | 93% | 94% |
| 5% | 96% | 99% | 99% | 99% |
| 10% | 100% | 100% | 100% | 100% |

**Table 9.3. Additional extracted quantitative findings.**

| Metric | Value | Notes |
|---|---:|---|
| Total structures compared | 227 | Approximate volume range **2-1500 cc** |
| Target volumes with separate dose analysis | 50 | From **25 prostate plans** |
| Significant predictor of percentage volume difference | `TPS manufacturer`, **p = 0.011** | Other tested variables not independently significant for this endpoint |
| DVH samples with >10% failing bins at `ΔV=1%`, `ΔD=1%` | XiO **0%** Plato **29%** Pinnacle **2%** Theraplan Plus **14%** Eclipse **13%** | Manufacturer-specific comparison |
| Predictors of percentage of failing gamma bins | Dose-grid resolution **p < 0.001**, coefficient **−15% mm⁻¹** manufacturer **p < 0.02** CT pixel size **p < 0.03**, coefficient **+57% mm⁻¹** | Authors warn of strong collinearity with manufacturer |
| Target minimum dose difference | **−0.9% ± 1.5%** | TPS relative to SWAN; **p = 0.0001** |
| Target mean dose difference | **−0.1% ± 0.2%** | TPS relative to SWAN |
| Target maximum dose difference | **−0.1% ± 0.3%** | TPS relative to SWAN |
| Performance for larger structures | Relative volume difference **<0.1%** failing gamma bins **<5%** | For larger volumes not shown in figure 2 |
| Equivalent-sphere radius difference | Within **0.5 mm** | **<2%** effective-radius difference across all structures |

### 10. Critical appraisal (100-200 words)

**Strengths:** multicentre design; clinically realistic exported data rather than a single-TPS toy example; explicit reporting of vendor-specific DVH algorithms and resolution ranges; use of an independent recalculation path; and a genuinely useful DVH-plane gamma formalism for comparison. The size dependence, vendor dependence, and target Dmin sensitivity are all directly relevant to reference DVH-engine design.

**Weaknesses:** no analytical ground truth; only one phantom geometry; sparse representation for some TPSs; limited reporting of dose-calculation details; strong collinearity between manufacturer and imaging/grid parameters; and an internal inconsistency in the narrative interpretation of target minimum-dose sign. These issues mean the study is stronger on **consistency** than on **absolute accuracy**.

**Confidence in findings:** **Medium.** The principal qualitative findings; small-structure sensitivity, manufacturer dependence, and Dmin fragility; are well supported, but the absence of ground truth and sparse vendor sampling prevent a higher rating. **Relevance to reference DVH calculator:** **High.** This is exactly the sort of paper that motivates explicit boundary rules, high-resolution resampling, deterministic reference modes, provenance tracking, and multicentre interoperability validation.

---

<!-- Source: SUMMARY - Gossman 2010 - DVH QA for linac-based TPSs.md -->

## Gossman (2010) - Dose-volume histogram quality assurance for linac-based treatment planning systems

### Executive summary

This paper presents a practical, synthetic benchmark for quality assurance of treatment-planning-system dose-volume histogram (DVH) output using a simple homogeneous phantom and a geometric structure of known volume. Gossman and Bank used a **40.0 cc** rectangular block (parallelepiped with dimensions 10 cm x 4 cm x 1 cm) embedded in an artificial water-equivalent CT dataset, calculated dose with Eclipse AAA for open **6 MV** and **18 MV** photon beams, and compared the TPS DVH with independent spreadsheet-based calculations derived from commissioned beam data. Agreement was good for this controlled scenario: the reported D/V ratio deviation ranged from **0.0% to -1.7%** for **6 MV** and from **-0.2% to -1.3%** for **18 MV**, with mean absolute deviations of about **0.62%** and **0.44%**, respectively. However, the TPS-reported structure volume was **40.8 cc** rather than the known **40.0 cc**, corresponding to a **+2.0%** absolute volume bias.

For a reference DVH calculator, the paper is valuable less because it proves general TPS DVH accuracy than because it demonstrates the importance of traceable synthetic test cases. It also shows that apparently close agreement in relative DVH percentages can coexist with meaningful error in absolute structure volume. The strongest engineering lessons are to validate against simple analytic or semi-analytic geometries, to report absolute and relative volume separately, to use explicit partial-volume handling rather than opaque voxel rules, and to test resampling, contour boundary, and grid-size effects directly. The study is narrow; one TPS, one dose algorithm, one simple rectangular geometry, no heterogeneity, and no small or irregular structures; but it remains directly relevant as a baseline QA pattern for commissioning and regression testing of a high-accuracy independent DVH engine.

### 1. Bibliographic record

**Authors:** Michael S. Gossman, Morris I. Bank
**Title:** *Dose-volume histogram quality assurance for linac-based treatment planning systems*
**Journal:** *Journal of Medical Physics*
**Year:** 2010
**DOI:** [10.4103/0971-6203.71759](https://doi.org/10.4103/0971-6203.71759)
**Open access:** Yes

### 2. Paper type and scope

**Type:** Original research

**Domain tags:** D1 Computation | D2 Commercial systems

**Scope statement:** The paper proposes a practical quality-assurance benchmark for treatment-planning-system DVH statistics using a synthetic homogeneous phantom and a structure of known volume. The authors compare Eclipse-generated cumulative DVH outputs with independent spreadsheet and hand calculations for simple open-field photon beams, aiming to support TPS commissioning, annual QA, and post-upgrade verification.

### 3. Background and motivation (150-300 words)

By 2010, DVHs were already central to radiotherapy plan evaluation, but the literature had concentrated more on what DVHs are and how clinicians use them than on how to verify that a TPS computes them correctly. The authors emphasise that radiation oncologists often decide between plans using dose-volume constraints, even though a DVH discards spatial information. In that setting, incorrect volumetric statistics could alter plan choice despite apparently reasonable isodose displays. They note that concise verification of 3D dose-summary data was needed, that quality assurance of DVH output had been recommended in broader TPS QA guidance, and that there was little or no published step-by-step procedure for independently checking computerised DVH analysis against a known 3D structure.

Their solution is deliberately reductionist: replace patient anatomy with an artificial homogeneous CT dataset, contour a simple geometric object whose volume is exactly known, calculate dose to that object from commissioned beam data, and then compare those independent results with the TPS DVH. For a reference-quality DVH engine, this is important not because the benchmark is exhaustive, but because it articulates a key design principle: synthetic, traceable test cases are essential if one wants to decouple DVH computation behaviour from the many confounds present in clinical patient data.

### 4. Methods: detailed technical summary (400-800 words)

Study design was a single-system analytical and simulation QA exercise rather than a patient, phantom-measurement, or multi-institutional study. No clinical cases were used. The authors created an artificial homogeneous water-like CT dataset inside Eclipse; density was set to **1.0** and phantom HU to **0**. CT slice spacing was **1.25 mm**. Within that synthetic dataset, they drew a rectangular contour of **2 cm × 10 cm** on one superior slice, copied it to consecutive inferior slices through an additional **2 cm**, and obtained a parallelepiped of stated dimensions **2 × 2 × 10 cm³ = 40.0 cc**. This known structure volume formed the basis of the benchmark.

Dose computation in the TPS used a commissioned Varian 21EX Clinac model with the `Anisotropic Analytical Algorithm` (AAA) version **8.6** in `External Beam Planning Software` build **8.6.17**. Two flattened photon energies were tested: **6 MV** and **18 MV**. Beam calibration followed `AAPM TG-51`; the paper states **1.00 cGy/MU** at SAD and at the depth of maximum dose, which is **0.01 Gy/MU** in SI-consistent units. A single open field of **30 × 30 cm²** was used. Isocentre and calculation reference point were placed at **10 cm** depth in the phantom, corresponding to **5 cm** inside the block, and the prescription at that point was **1.00 Gy**. Geometry was SAD **100 cm**, SSD **90 cm**, with gantry, collimator, and couch each at **180°**. The plan was duplicated so that the 6 MV and 18 MV cases were otherwise identical. The TPS dose grid was **0.15 cm = 1.5 mm**, chosen explicitly because larger voxel sizes were known to degrade DVH accuracy. Heterogeneity handling was effectively irrelevant because the phantom was homogeneous.

The independent calculation was spreadsheet-based; the spreadsheet software is [DETAIL NOT REPORTED]. The authors first computed the required monitor units from standard point-dose parameters: output, TMR, Sc, and Sp. They then calculated percentage depth-dose at other depths using inverse-square scaling and commissioned beam data. Importantly, they did not treat the problem as a central-axis depth-dose exercise only. Because the structure lay inside a broad flattened field, they attempted to account for horn-induced curvature of isodose lines and the fact that more than half of the structure could receive **100%** of the prescription dose. To do that, they used scanned OAR data to adjust the geometric volume receiving a given dose at each depth. The benchmark was evaluated in **10%** volume increments, effectively assigning dose to each tenth of the structure volume along the beam direction. The mean OAR correction was **1.001** for **6 MV** and **1.000** for **18 MV**.

For the TPS side, the paper describes Eclipse DVH generation only qualitatively. The structure is registered in 3D coordinate space, voxel doses are binned and iteratively weighted with neighbouring bins within the dose matrix, and the cumulative DVH is generated as the integral of sampled dose over interpolated structures. Critical implementation details are missing: DVH bin width [DETAIL NOT REPORTED], differential-histogram binning before cumulative conversion [DETAIL NOT REPORTED], supersampling strategy [DETAIL NOT REPORTED], contour interpolation and end-capping rule [DETAIL NOT REPORTED], exact boundary partial-volume rule [DETAIL NOT REPORTED], and whether Dmin and Dmax were voxel-based or interpolated [DETAIL NOT REPORTED]. The comparison metric was also unusual: instead of comparing dose and volume separately, they computed percentage deviation of the ratio `(%DD_calc/%V_calc)` relative to the TPS ratio `(%DD_DVH/%V_DVH)`. They additionally compared TPS-reported total structure volume with the known **40.0 cc**. No formal statistical tests, confidence intervals, repeated calculations, or uncertainty propagation were reported; this was a deterministic benchmark comparison.

Two reproducibility issues should be noted. First, the text says dose-depth studies ranged from phantom depth **6 cm** to **13 cm**, but Table 1 actually reports values from **6 cm to 15 cm**. Second, the paper later says the object was **5 cm** wide for OAR averaging, which is inconsistent with the earlier stated **2 × 2 × 10 cm³** block. These internal inconsistencies do not change the published agreement numbers, but they do reduce the fidelity with which a third party can reconstruct the exact benchmark. The authors themselves acknowledge that imported CT data can introduce resampling errors when the image grid and dose grid differ, and they recommend artificial datasets precisely to suppress that confound.

### 5. Key results: quantitative (300-600 words)

Agreement between the spreadsheet calculation and the TPS DVH was close throughout the benchmark, but not exact. For **6 MV**, the paper’s dose/volume-ratio deviation metric ranged from **0.0% to -1.7%**, referenced to the TPS D/V ratio. The largest magnitude occurred at the shallowest sampled depth, **6 cm**, where the independent calculation gave **119.8%** relative dose to **10.01%** volume, while the TPS DVH gave **120.5%** to **9.9%** volume, yielding **-1.7%**. At the prescription depth of **10 cm**, the independent result was **100.0%** to **50.06%** volume versus TPS **100.2%** to **50.0%**. At the deepest sampled point, **15 cm**, the values were **78.9%** to **100.12%** versus **78.8%** to **100.0%**. The mean absolute deviation across the 10 tabulated depths is **0.62%**, consistent with the authors’ quoted average accuracy of about **0.6%**.

For **18 MV**, the same ratio metric ranged from **-0.2% to -1.3%**, again worst at **6 cm** depth: independent **116.3%** to **10.00%** volume versus TPS **117.1%** to **9.9%**, giving **-1.3%**. At **10 cm**, the comparison was **100.0%** to **50.00%** versus **100.3%** to **50.1%** at **15 cm**, **82.6%** to **100.00%** versus **82.7%** to **99.9%**. The mean absolute deviation across the tabulated depths is **0.44%**, matching the authors’ rounded summary of **0.4%** average accuracy. Across both energies, TPS-reported relative doses were consistently a little higher than the hand calculation, by roughly **0.1-0.8 percentage points**, producing the small systematic negative bias in the ratio metric.

The most important absolute volumetric finding is that the TPS reconstructed the block as **40.8 cc** rather than the known **40.0 cc**, that is **+0.8 cc** or **+2.0% relative to the known volume**. This matters because the per-depth volumes in Table 1 are expressed as percentages; relative percentage agreement can therefore look very good even when absolute volume is biased. Figure 3 also provides whole-structure DVH summary statistics. For **6 MV**, the TPS reported **79.1%** minimum dose, **126.4%** maximum dose, **101.4%** mean dose, and **13.6%** standard deviation. For **18 MV**, the corresponding values were **82.6%**, **121.7%**, **100.9%**, and **11.2%**. Thus the **18 MV** case had a somewhat narrower dose spread within the block. No p-values, confidence intervals, effect sizes, or null-hypothesis tests were reported, because the study was not designed as an inferential statistical comparison.

### 6. Authors' conclusions (100-200 words)

The authors conclude that their method is reproducible, accurate, and efficient enough for routine TPS QA. They recommend it for commissioning, annual QA, and after major algorithm upgrades, arguing that one need only recalculate the dose in the prebuilt benchmark plan and re-run the spreadsheet comparison. They interpret the observed **1.3-1.7%** maximum dose/volume-ratio deviation, **0.4-0.6%** mean absolute deviation, and **2.0%** total-volume difference as acceptable performance for the commercial system tested. They further suggest that, when scan data and algorithms are well controlled, DVH accuracy can be verified to within a few percent.

That conclusion is well supported for the specific scenario studied: a simple, homogeneous, broad-field benchmark in Eclipse AAA. It is less secure if interpreted as general validation of TPS DVH behaviour across modern clinical cases, because the comparator is not exact ground truth and the paper does not test irregular contours, small structures, heterogeneity, or steep dose gradients.

### 7. Implications for reference DVH calculator design (300-600 words)

#### 7a. Algorithm and implementation recommendations

A reference calculator should include synthetic-geometry benchmarks that are traceable and analytically interpretable, not just patient DICOM workflows. This paper shows that even a very simple homogeneous cuboid can expose **~1-2%** discrepancies in commercial DVH output. The implementation should report **absolute structure volume in cc**, **relative volume in %**, and **dose-volume accumulation results** as separate quantities. Gossman’s data are a good cautionary example: the relative volume deciles match closely, yet the total structure volume is still **+2.0%** high (**40.8** vs **40.0 cc**). A reference engine should therefore never let normalised DVH percentages hide absolute volumetric bias. The calculator should also use explicit partial-volume handling; ideally exact voxel-structure intersection or adaptive supersampling with convergence logging; because the paper’s volume error persists despite a fine **1.5 mm** grid and because the TPS boundary rule is opaque. Finally, compare `D(v)` and `V(d)` separately as well as together; the paper’s single D/V ratio can mask compensating dose and volume errors.

#### 7b. Validation recommendations

This paper’s setup should be recreated as a canonical baseline test, but with stricter specification than the article itself provides. A validation case should explicitly define homogeneous water, HU 0, block **2 × 2 × 10 cm³ = 40.0 cc**, **30 × 30 cm²** open field, SAD **100 cm**, SSD **90 cm**, point prescription **1.00 Gy** at **10 cm** depth, flattened photon beams analogous to **6 MV** and **18 MV**, CT slice spacing **1.25 mm**, and dose grid **1.5 mm**. Acceptance for reproducing a clinical TPS benchmark of this kind can reasonably be at the few-percent level: this paper achieved **≤1.7%** ratio deviation and **2.0%** total-volume deviation, while older TPS QA guidance often used **5.0%** as an investigation threshold. For the reference engine’s own self-validation, tighter internal tolerances are appropriate [engineering inference], because the reference calculator should outperform the system under test. Add shifted-cuboid, coarser-grid, imported-CT resampling, small-volume, and high-gradient variants; those cases would expose exactly the failure modes this paper identifies but does not systematically study.

#### 7c. Extensibility considerations

Direct motivation for advanced biological metrics is limited here, but the paper still argues for a richer statistics interface than “just cumulative DVH”. The benchmark should natively yield cumulative and differential histograms, Dmin, Dmax, Dmean, standard deviation, `D(v)` queries, and `V(d)` queries, because the paper uses both per-volume dose points and whole-structure summary statistics. The engine should also support profile-aware or analytic benchmark plugins, not only sampled dose grids, since the independent comparison here depends on TMR, Sc, Sp, inverse-square correction, and OAR beam-profile information. If those provenance objects are retained in the data model, later extensions to gEUD and EUD, probabilistic DVH, or other derived metrics can remain traceable to the underlying geometric and dosimetric sampling pathway.

#### 7d. Caveats and limitations

The paper should not be over-generalised. It covers one vendor TPS, one dose algorithm (AAA 8.6), one machine model, one broad open field, one simple rectangular structure, and a homogeneous phantom. There is no heterogeneity, no IMRT or VMAT, no MLC modulation, no tiny structures, and no clinically irregular contour geometry. More importantly, the comparator is not exact ground truth: it relies on commissioned beam data, averaged OARs, and a residual correction for curved isodose geometry, so observed disagreement conflates dose-modelling error and DVH computation error. The internal inconsistencies in object width and analysed depth range further reduce reproducibility. A reference DVH calculator should therefore treat this paper as a useful benchmark pattern and QA philosophy, not as a definitive tolerance study for all DVH use cases.

### 8. Connections to other literature

- **Drzymala et al. (1991):** Foundational DVH paper; Gossman addresses the practical QA gap left after early conceptual adoption of DVHs in radiotherapy planning.
- **Kessler et al. (1994):** Emphasised concise summary-data verification in 3D treatment planning; cited by Gossman as motivation for independent volumetric checking.
- **Panitsa, Rosenwald and Kappas (1998):** Closest direct antecedent on quality control of DVH computation characteristics; should be read alongside this paper for early TPS DVH QA thinking.
- **Van Dyk et al. (1993):** Broader TPS commissioning and QA framework; Gossman operationalises one narrow but clinically relevant component, namely DVH statistical verification.
- **Fraass et al. (1998) (AAPM TG-53):** Recommends comprehensive TPS QA, but without the simple hand and spreadsheet DVH routine presented here.
- **IAEA TRS-430, 2004:** International guidance on TPS commissioning and QA; Gossman’s benchmark is a concrete implementation that fits that QA philosophy.
- **Corbett et al. (2002):** Demonstrated voxel-size sensitivity of DVH accuracy; directly relevant to Gossman’s deliberate choice of a **1.5 mm** calculation grid.

### 9. Data extraction table

The following tables extract benchmark parameters and quantitative results from the paper’s methods, Table 1, and Figure 3. All doses below are relative to the **1.00 Gy** reference-point prescription unless stated otherwise.

#### Table 9a. Benchmark setup

| Parameter | Value |
|---|---|
| Phantom | Artificial homogeneous water CT; density 1.0; HU 0 |
| CT slice spacing | **1.25 mm** |
| Known structure | Rectangular parallelepiped, **2 × 2 × 10 cm³ = 40.0 cc** |
| TPS / algorithm | Eclipse with AAA v**8.6** (`External Beam Planning` build **8.6.17**) |
| Dose grid | **1.5 mm** |
| Beam arrangement | Single open field, **30 × 30 cm²** |
| Geometry | SAD **100 cm** SSD **90 cm** gantry/collimator/couch **180°/180°/180°** |
| Reference point | **10 cm** depth in phantom; **5 cm** within block |
| Prescription | **1.00 Gy** at reference point (paper reports 100 cGy) |
| Energies tested | **6 MV**, **18 MV** |
| Hand-calculated MU | **112.2** (6 MV), **102.2** (18 MV) |
| Mean OAR used | **1.001** (6 MV), **1.000** (18 MV) |

#### Table 9b. Per-depth comparison for 6 MV

| Phantom depth (cm) | Calc volume with OAR (%) | Calc relative dose (%) | TPS DVH relative dose (%) | TPS DVH volume (%) | D/V deviation (%) |
|---|---:|---:|---:|---:|---:|
| 6 | 10.01 | 119.8 | 120.5 | 9.9 | -1.7 |
| 7 | 20.02 | 114.5 | 115.1 | 20.0 | -0.8 |
| 8 | 30.04 | 109.4 | 110.1 | 29.9 | -0.9 |
| 9 | 40.05 | 104.7 | 105.0 | 39.9 | -0.6 |
| 10 | 50.06 | 100.0 | 100.2 | 50.0 | -0.4 |
| 11 | 60.07 | 95.3 | 95.7 | 60.0 | -0.5 |
| 12 | 70.08 | 90.9 | 91.1 | 70.0 | -0.4 |
| 13 | 80.10 | 86.7 | 86.9 | 80.0 | -0.4 |
| 14 | 90.11 | 82.5 | 82.8 | 90.0 | -0.5 |
| 15 | 100.12 | 78.9 | 78.8 | 100.0 | -0.0 |

#### Table 9c. Per-depth comparison for 18 MV

| Phantom depth (cm) | Calc volume with OAR (%) | Calc relative dose (%) | TPS DVH relative dose (%) | TPS DVH volume (%) | D/V deviation (%) |
|---|---:|---:|---:|---:|---:|
| 6 | 10.00 | 116.3 | 117.1 | 9.9 | -1.3 |
| 7 | 20.00 | 112.0 | 112.6 | 20.1 | -0.2 |
| 8 | 30.00 | 107.9 | 108.3 | 30.0 | -0.4 |
| 9 | 40.00 | 104.1 | 104.2 | 40.0 | -0.2 |
| 10 | 50.00 | 100.0 | 100.3 | 50.1 | -0.2 |
| 11 | 60.00 | 96.1 | 96.6 | 60.0 | -0.4 |
| 12 | 70.00 | 92.6 | 93.3 | 69.9 | -0.5 |
| 13 | 80.00 | 89.0 | 89.5 | 80.0 | -0.5 |
| 14 | 90.00 | 85.7 | 86.1 | 90.0 | -0.5 |
| 15 | 100.00 | 82.6 | 82.7 | 99.9 | -0.2 |

#### Table 9d. Whole-structure DVH summary statistics from Figure 3

| Energy | TPS volume (cc) | Min dose (%) | Max dose (%) | Mean dose (%) | Std dev (%) |
|---|---:|---:|---:|---:|---:|
| 6 MV | 40.8 | 79.1 | 126.4 | 101.4 | 13.6 |
| 18 MV | 40.8 | 82.6 | 121.7 | 100.9 | 11.2 |

D/V deviation is the paper’s ratio metric, that is percentage deviation of the independent `(%D/%V)` ratio relative to the TPS `(%D/%V)` ratio, not a pure dose-difference metric.

### 10. Critical appraisal (100-200 words)

**Strengths:** This is a clear, clinic-friendly early paper on DVH QA with a reproducible synthetic benchmark and full per-depth quantitative reporting. It also correctly recognises resampling and voxelisation as important confounds and tries to suppress them with an artificial dataset.

**Weaknesses:** The reference standard is only semi-analytic, not exact; the comparison metric is unconventional and can obscure separate dose and volume errors; only one TPS, one dose algorithm, and one simple geometry are studied; and there are internal inconsistencies in reported dimensions and analysed depth range.

**Confidence in findings:** **Medium** the published numbers are probably reliable for this exact benchmark, but external generalisability is limited.

**Relevance to reference DVH calculator:** **High** despite its simplicity, the paper is directly relevant because it motivates synthetic benchmark phantoms, explicit auditing of absolute structure volume, profile-aware dose integration, and separation of dose, relative volume, and absolute volume agreement in QA.

---

<!-- Source: SUMMARY - Grimm 2011 - Dose tolerance limits and DVH evaluation for stereotactic body radiotherapy.md -->

## Grimm (2011) - Dose tolerance limits and dose volume histogram evaluation for stereotactic body radiotherapy

### Executive Summary

Grimm et al. compiled **500 published SBRT normal-tissue dose tolerance limits** into a single review table spanning mainly **1-5 fractions**. The paper is highly relevant to a reference DVH engine because it shows that clinically used constraints are heterogeneous: some are maximum point doses, others are dose-to-cc, dose-to-%, or “critical volume must be spared” rules. The authors repeatedly warn that these are not validated universal limits. Only **4%** of listed limits include the number of patients actually exposed to the dose level, long-term follow-up is sparse, and DVH endpoints alone may miss clinically important spatial information. For DVH calculator design, the key lessons are to support mixed constraint semantics, compute robustly for sub-cc endpoints such as **0.25 cc** and **1.2 cc**, preserve spatial hotspot information for serial organs, and treat biological conversion methods as optional overlays rather than replacements for physical-dose reporting.

### 1. Bibliographic record

- **Authors:** Jimm Grimm, Tamara LaCouture, Raymond Croce, Inhwan Yeo, Yunping Zhu, Jinyu Xue
- **Title:** Dose tolerance limits and dose volume histogram evaluation for stereotactic body radiotherapy
- **Journal:** Journal of Applied Clinical Medical Physics
- **Year:** 2011
- **DOI:** [10.1120/jacmp.v12i2.3368](https://doi.org/10.1120/jacmp.v12i2.3368)
- **Open access:** Yes.

### 2. Paper type and scope

- Type: Review
- Domain tags (one or more): D1 Computation | D4 Outcome modelling
- Scope statement: This paper is Phase I of a broader programme to establish SBRT normal-tissue tolerance limits. It aggregates published organ-at-risk constraints from clinical papers and protocol documents, then discusses why DVH-based interpretation is complicated by fractionation, hotspot location, motion, targeting accuracy, modality differences, and dose-calculation uncertainty.

### 3. Background and motivation (150-300 words)

The paper addresses a gap that emerged when SBRT entered routine use. Conventional radiotherapy had the Emami tolerance tables, framed around **5%** and **50%** complication probabilities at five years and based on **1.8-2 Gy** fractions. SBRT instead uses ablative schedules, commonly **5-20 Gy per fraction** over **1-5 fractions**, so normal-tissue response may differ substantially from conventional practice. Grimm et al. argue that the field lacked a comprehensive SBRT-specific catalogue of normal tissue limits even though such constraints were already guiding prescription decisions.

The motivation is closely tied to DVH usage. In SBRT, prescription is often limited by organ-at-risk tolerances rather than ideal tumour dose, so small errors in dose-volume interpretation can become clinically decisive. The authors note that simple BED-based conversion of conventional limits is attractive but not sufficiently validated for extreme hypofractionation. Earlier reviews tabulated only a few dozen limits, leaving many structures and schedules uncovered. Grimm et al. therefore set out to assemble a much broader catalogue of currently used limits, while highlighting caveats that matter for any reference DVH calculator: limits are expressed in multiple non-equivalent forms, often rely on tiny hot volumes, and can be confounded by motion, targeting uncertainty, and inaccurate dose calculation.

### 4. Methods: detailed technical summary (400-800 words)

**Study design.** This is a narrative literature review, explicitly labelled **Phase I** of a three-phase effort. Phase I was to gather published SBRT dose tolerance limits already used clinically. The paper does not derive new tolerances or perform prospective validation.

**Data sources and included material.** The authors state that they searched **hundreds of journal articles** and compiled **500 dose tolerance limits** for normal structures. Included sources span RTOG protocols, institutional series, multi-institutional trials, review articles, and some single-case reports. Most entries relate to **1-5 fractions**, consistent with the paper’s SBRT definition, but some **6-fraction** and post-conventional-radiotherapy or HDR-derived limits are also included when the authors considered them clinically informative.

**How the limits were represented.** Table 1 is the core output. Each row records the organ, number of fractions, and then either an absolute volume in cc, a relative volume in %, a dose limit in Gy, or a maximum point dose in Gy. The volume-dose and point-dose columns are mutually exclusive. The table also lists references, notes, number of adverse events, number of patients who received the relevant dose level, and total study size. Toxicity reporting is centred on CTCAE Grade 3 or higher, although some Grade 2 events are included.

**DVH computation details.** The authors did **not** recompute DVHs from raw dose grids or structure sets. They aggregated whatever endpoints the source publications used. As a result, treatment planning system, dose grid resolution, structure rasterisation, interpolation method, cumulative versus differential DVH format, bin width, supersampling, partial-volume handling, end-capping, and boundary rules are all **[DETAIL NOT REPORTED]** at the review level and heterogeneous across the source literature. This lack of harmonisation is itself an important finding.

**Dose calculation and delivery context.** The compiled limits come from mixed technologies, including HDR brachytherapy, Gamma Knife, CyberKnife, and linac-based SBRT. The authors explicitly note that Gamma Knife uses about **1.25 MV** photons, whereas conventional linac SBRT typically uses **6-18 MV**. Targeting accuracy also varies by platform. Dose calculation algorithm, heterogeneity correction method, and TPS version are **[DETAIL NOT REPORTED]** for the review as a whole.

**Comparison methodology and reference standard.** The work is descriptive. There is no formal meta-analysis, pooled toxicity modelling, or harmonised statistical framework. The practical reference standard is “published with clinical intent”, which is much weaker than an analytical ground truth. The authors also exclude purely theoretical tolerance limits from simulations, animal studies, or cell culture unless those limits had already been translated into clinical use.

**Software and tools.** No bespoke software or programming environment is identified for the compilation **[DETAIL NOT REPORTED]**.

**Acknowledged limitations.** The authors note short follow-up, sparse late-toxicity data, mixed patient populations, mixed technologies, incomplete reporting of concomitant drugs or systemic therapy, incomplete reporting of how many patients actually received each dose level, and persistent data gaps for several organs. They also stress that retreatment is mostly outside scope even though some retreatment-like constraints appear in the table.

### 5. Key results: quantitative (300-600 words)

The main result is the creation of a catalogue of **500 SBRT dose tolerance limits** across many organs and fractionation schedules. Coverage is broader than prior reviews but still incomplete; the authors specifically identify missing SBRT tolerance data for gallbladder, oral mucosa, ovaries, pancreas, parotid, pituitary, spleen, testes, thyroid, ureter, and vagina.

A major quantitative finding is the heterogeneity of endpoint syntax. Constraints are variably expressed as maximum point dose, dose to a small absolute volume, dose to a percentage volume, or a requirement that a critical volume be spared. Examples of spared-volume rules include composite kidney constraints that spare **200 cc** below **8.4 Gy** in **1 fraction**, **14.4 Gy** in **3 fractions**, and **17.5 Gy** in **5 fractions** liver constraints that spare **700 cc** below **9.1 Gy**, **15-17.1 Gy**, and **21 Gy** for **1**, **3**, and **5 fractions** and lung constraints that spare **1500 cc** below **7.0 Gy**, **10.5 Gy**, and **12.5 Gy**, or **1000 cc** below **7.4 Gy**, **11.4 Gy**, and **13.5 Gy**.

The table also shows how clinically important sub-cc serial-organ metrics had become. For spinal cord, the compilation includes hottest **0.25 cc** limits of **10 Gy** in **1 fraction**, **18 Gy** in **3 fractions**, and **22.5 Gy** in **5 fractions** corresponding hottest **1.2 cc** limits are **7 Gy**, **11.1 Gy**, and **13.5 Gy**. The authors caution against older **8 cc** cord metrics because they can hide circumferential high-dose patterns.

Exposure denominators matter. For single-fraction optic nerve or chiasm irradiation, the paper highlights that **7 of 9** exposed patients developed radiation-related optic neuropathy above **15 Gy**, which is **77.8%**, not **14% (7/50)** across the whole cohort. In the **10-15 Gy** range, **4 of 15** exposed patients developed optic toxicity, or **26.7%**. At **12 Gy**, the cited source suggested about **7% (2/29)** risk, versus **1.1%** below **12 Gy**.

The review also captures delayed toxicity and dosimetric confounding. A permissive single-fraction duodenal limit allowing **5%** of the organ above **22.5 Gy** initially showed no Grade 3 or higher acute GI toxicity, yet later follow-up reported **2 Grade 3-4** complications **8-10 months** after treatment. Separately, the authors cite work showing posterior skin dose can be **80% higher** than expected if couch or immobilisation material creates a bolus effect. No pooled p values or confidence intervals are reported because the paper is descriptive rather than meta-analytic.

### 6. Authors' conclusions (100-200 words)

The authors conclude that currently available SBRT normal-tissue dose limits are useful as an organised early reference, but remain preliminary and insufficiently validated. They explicitly state that they are **not** claiming any listed limit is safe, nor that any listed limit is the true maximal safe dose. Their practical message is that a broad summary of published limits is still valuable because SBRT prescriptions often end up being set by organ-at-risk tolerances.

This conclusion is mostly well supported. The paper clearly demonstrates heterogeneous evidence quality, short follow-up, and inconsistent reporting. The most defensible conclusion is therefore not “these are the right limits”, but “these are the limits people were using, with important caveats”. A slightly less secure inference is the suggestion that commonly reused limits may be reasonably accurate for short-term effects because many early SBRT patients had short life expectancy and acute toxicity would have appeared quickly. That claim is plausible, but not formally proven by the review itself.

### 7. Implications for reference DVH calculator design (300-600 words)

**7a. Algorithm and implementation recommendations**

The reference calculator should support more than standard cumulative DVH queries. Grimm et al. show clinically used SBRT rules expressed as maximum point dose, hottest `x cc`, hottest `x%`, and “critical volume must be spared” constraints. A benchmark tool therefore needs first-class support for all of these forms, including spared-volume logic for liver, kidney, and lung. Fractionation and schedule metadata must also be attached to the metric itself.

Sub-cc endpoints are common. The implementation should compute robustly for volumes such as **0.035 cc**, **0.1 cc**, **0.25 cc**, and **1.2 cc**. Because these are clinically used reporting points, numerical uncertainty must be much smaller than the endpoint itself. The paper also argues that BED conversion alone is not enough for SBRT, so biological transforms should be optional overlays rather than replacements for physical-dose reporting.

Finally, the calculator should preserve spatial information. Grimm et al. explicitly warn that DVH compliance can hide clinically dangerous circumferential irradiation of serial organs. A reference system should therefore retain hotspot topology or slice-wise spatial maps, not just cumulative histograms.

**7b. Validation recommendations**

This paper motivates several benchmark classes. First, use serial-organ phantoms such as spinal cord cylinders with focal versus circumferential hotspots that produce similar DVHs but different spatial risk. Second, test small structures and hotspots on coarse and fine dose grids to assess stability of `D0.035cc`, D0.1cc, `D0.25cc`, and `D1.2cc`. Third, validate spared-volume logic with liver, kidney, and lung phantoms, including cases where some protocols allow subtraction of GTV.

Fourth, include motion-sensitive bowel-like test cases. The paper notes that the dose to **1 cc** of bowel is more uncertain than the dose to **1/3** of the bowel, so uncertainty-perturbed or deforming benchmarks are appropriate. Fifth, include skin-surface buildup tests with couch or immobilisation material, because the cited posterior skin dose error reached **80%**. Grimm’s table plus publicly accessible protocol constraints from `RTOG 0631`, `RTOG 0915`, and `RTOG 0813` provide a practical semantic validation library.

**7c. Extensibility considerations**

Constraint objects should carry provenance and context, not just organ, volume, and dose. This review makes clear that modality, prior radiotherapy, fractionation, and whether a rule is “allowed volume above dose” versus “critical volume below dose” all matter. The data model should also support optional biological overlays such as BED or `EQD2`, with explicit `α/β` assumptions and schedule metadata.

The paper does not directly develop DSH, DMH, dosiomics, or formal EUD/gEUD models, but it strongly motivates interfaces that can attach toxicity evidence, exposed-patient denominators, and uncertainty descriptors to standard DVH endpoints.

**7d. Caveats and limitations**

This paper compiles clinical usage, not validated truth. Many source constraints come from mixed technologies, mixed disease sites, and short-survival populations. Some are single-case observations or retreatment-like scenarios. A reference DVH calculator should therefore use this paper primarily as a map of metric semantics and known failure modes, not as a final source of biologically validated tolerance thresholds.

### 8. Connections to other literature

- **Emami et al. (1991)**: Historical conventional-tolerance baseline; Grimm explicitly positions SBRT as needing a new, fractionation-specific equivalent.
- **Papiez and Timmerman, 2008**: Direct motivation for the review; identified absent prescription and fractionation data as a key barrier to safe SBRT.
- **Chang and Timmerman, 2007**: Earlier comprehensive SBRT review that supplied many practical limits, including older spinal cord conventions later questioned here.
- **Timmerman (2008)**: Updated hypofractionation review that Grimm cites when shifting spinal cord reporting from **8 cc** to **0.25 cc** and **1.2 cc**.
- **Ryu et al. (2007)**: Key spinal cord partial-volume tolerance study underlying the use of very small hot-volume endpoints.
- **Sahgal et al. (2009)**: Important spinal cord tolerance update with complication cases; essential companion reading for serial-organ hotspot risk.
- **Koong et al. (2004)**: Pancreatic SBRT study that contributed permissive duodenal limits later criticised by Grimm.
- **Schellenberg et al. (2008)**: Follow-up pancreatic experience showing delayed Grade 3-4 GI toxicity despite initially reassuring acute toxicity results.

### 9. Data extraction table

**Table 1. Summary-level quantitative extractions from Grimm 2011**

| Extracted item | Value | Notes |
|---|---:|---|
| Compiled SBRT normal-tissue dose tolerance limits | **500** | Broad literature-derived catalogue, not a validated consensus set |
| Fractionation coverage | Mainly **1-5 fractions** | Some **6-fraction** and post-conventional or HDR-like entries also included |
| Limits with exposed-patient denominator reported | **4%** | Column nine was populated for only a small minority of entries |
| Optic pathway toxicity above 15 Gy, single fraction | **7/9 exposed patients (77.8%)** | Key example showing why exposed-patient denominator matters |
| Optic pathway toxicity at 10-15 Gy, single fraction | **4/15 exposed patients (26.7%)** | No RON reported below **10 Gy** |
| Delayed GI toxicity after permissive single-fraction duodenal dosing | **2** Grade **3-4** complications at **8-10 months** | Delayed toxicity despite initially negative acute signal |
| Posterior skin dose error from couch or immobilisation bolus effect | Up to **80% higher** than expected | Confounds tolerance assessment with dose calculation accuracy |

**Table 2. Selected constraint forms relevant to DVH implementation**

| Organ | Fractions | Endpoint form | Extracted constraint(s) | Implementation relevance |
|---|---|---|---|---|
| Composite kidney | 1 / 3 / 5 | Critical volume spared | Spare **200 cc** below **8.4 / 14.4 / 17.5 Gy** | Requires “must spare” logic |
| Liver | 1 / 3 / 5 | Critical volume spared | Spare **700 cc** of normal liver below **9.1 / 15-17.1 / 21 Gy** | Requires normal-parenchyma accounting |
| Lungs | 1 / 3 / 5 | Critical volume spared | Spare **1500 cc** below **7.0 / 10.5 / 12.5 Gy** spare **1000 cc** below **7.4 / 11.4 / 13.5 Gy** | Requires absolute-volume spared metrics |
| Spinal cord | 1 / 3 / 5 | Small hot-volume metric | Hottest **0.25 cc** ≤ **10 / 18 / 22.5 Gy** hottest **1.2 cc** ≤ **7 / 11.1 / 13.5 Gy** | Demands stable sub-cc evaluation |
| Rectum | 5 | Relative-volume metric | **5% ≤ 36.25 Gy**, **10% ≤ 32.625 Gy**, **20% ≤ 29 Gy**, **50% ≤ 18.125 Gy** | Requires accurate `D%` support |
| Optic pathway | 1 / 3 / 5 | Point-dose and tiny-volume style metrics | Single-fraction practical caution around **10-12 Gy** also **0.2 cc ≤ 15 Gy** in **3 fractions** and **0.2 cc ≤ 20 Gy** in **5 fractions** | Requires distinction between near-point and finite tiny-volume dose |

### 10. Critical appraisal (100-200 words)

- **Strengths:** Broad and clinically useful early catalogue of SBRT constraint semantics; explicit recognition that DVH metrics are heterogeneous and sometimes misleading; inclusion of adverse-event counts and exposed-patient denominators where available; strong discussion of spatial, motion, targeting, and dose-calculation caveats.
- **Weaknesses:** Narrative rather than systematic review; no harmonised dosimetric recomputation; no patient-level data; no formal meta-analysis; mixed modalities and disease sites; many numeric limits are weakly evidenced or context-specific.
- **Confidence in findings:** **Medium**. Confidence is high that the paper accurately documents heterogeneity and reporting gaps, but only medium that any specific numeric threshold is robust and generalisable.
- **Relevance to reference DVH calculator:** **High**. The paper is foundational for constraint representation and validation design because it shows exactly which endpoint types, sub-cc edge cases, and non-DVH failure modes a benchmark calculator must handle.

---

<!-- Source: SUMMARY - Zhang 2011 - Motion-weighted target volume and DVH; a practical approximation of 4-D planning and evaluation.md -->

## Zhang (2011) - Motion-weighted target volume and dose-volume histogram: A practical approximation of four-dimensional planning and evaluation

### Executive summary

This paper proposes a practical approximation to four-dimensional radiotherapy plan evaluation for moving lung targets by introducing a **motion-weighted clinical target volume** (mwCTV) and corresponding **motion-weighted DVH** (mwDVH). Rather than treating the internal target volume as a purely binary union of all respiratory positions, the method preserves **temporal occupancy information** from 4D-CT. Regions occupied for the full breathing cycle contribute more heavily to the DVH than peripheral regions occupied only briefly. The central idea is that tumour motion information can be represented as **weighted volume elements**, allowing a more faithful approximation to 4D dose evaluation without requiring full deformable dose accumulation.

In a retrospective study of **10 lung cancer cases**, the authors compared conventional 3D ITV-based DVHs, 10-phase motion-weighted DVHs, 2-phase motion-weighted DVHs, and a deformable-image-registration-based 4D reference. The motion-weighted approaches matched the 4D reference substantially better than standard 3D evaluation. Mean RMS target-DVH difference versus 4D was **1.70 ± 1.06** for conventional 3D, versus **0.43 ± 0.25** for 10-phase mwDVH and **0.44 ± 0.21** for 2-phase mwDVH. At the **70 Gy** target coverage endpoint, the mean difference versus 4D was **-2.8 ± 0.8 percentage points** for 3D, compared with **0.3 ± 0.7** for 10-phase mwDVH and **0.5 ± 0.5** for 2-phase mwDVH. For a reference DVH calculator, this paper is important because it motivates support for **weighted ROIs**, **occupancy-weighted histogram accumulation**, and explicit distinction between **approximate motion-aware evaluation** and **true 4D deformable dose accumulation**.

### 1. Bibliographic record

**Authors:** Geoffrey Zhang, Vladimir Feygelman, Tzung-Chi Huang, Craig Stevens, Weiqi Li, Thomas Dilling
**Title:** *Motion-weighted target volume and dose-volume histogram: A practical approximation of four-dimensional planning and evaluation*
**Journal:** *Radiotherapy and Oncology*
**Year:** 2011
**DOI:** [10.1016/j.radonc.2011.02.003](https://doi.org/10.1016/j.radonc.2011.02.003)
**Open access:** No

### 2. Paper type and scope

**Type:** Original research.
**Domain tags:** D1 Computation | D2 Commercial systems | D3 Metric innovation.
**Scope statement:** This is a retrospective 10-case lung radiotherapy planning study proposing a motion-weighted clinical target volume (mwCTV) and motion-weighted DVH (mwDVH) as a practical approximation to deformable-image-registration-based 4D dose accumulation. The main question is whether occupancy-weighted evaluation, using only a conventional 3D dose distribution, can reproduce the target and OAR DVH behaviour of full 4D accumulation better than standard ITV-based 3D DVHs, and whether using only the two extreme respiratory phases is sufficient.

### 3. Background and motivation (150-300 words)

The paper addresses a specific deficiency in conventional 4D-CT-based thoracic planning workflows: although tumour motion is used geometrically to create an IGTV/ITV/PTV, the temporal occupancy information embedded in the 4D dataset is then discarded. In standard ITV-based 3D planning, a voxel that is occupied by tumour for only a small fraction of the breathing cycle is treated identically, during optimisation and DVH evaluation, to a voxel occupied throughout the cycle. The authors argue that this is a legacy of static 3D planning and that it distorts both target and OAR DVHs for mobile thoracic targets.

At the same time, full 4D dosimetry based on deformable image registration was already recognised as desirable but operationally difficult: it is computationally heavier, depends on deformable mapping accuracy, and can be degraded by 4D-CT artefacts. The gap, therefore, was not simply that 4D planning existed but was unavailable; rather, clinically practical methods did not preserve phase occupancy information during routine planning and evaluation. The proposed `mwCTV/mwDVH` framework is meant to fill that gap by carrying temporal occupancy into a weighted structure definition and then converting temporal weights into spatial weights during DVH generation, avoiding voxel-by-voxel dose warping altogether. Conceptually, this paper is important because it reframes part of motion-aware dose evaluation as a weighted-ROI problem rather than solely a deformable dose-accumulation problem.

### 4. Methods: detailed technical summary (400-800 words)

This was a retrospective dosimetric and planning study of **10 lung cancer cases** acquired under an IRB-approved protocol. Each patient underwent 4D-CT on a **16-slice Brilliance Big Bore CT scanner** (Philips Medical Systems), reconstructed into **10 respiratory phases** using **phase binning equally spaced in time** across the breathing cycle. The target motion cohort was heterogeneous: lower- and upper-lobe tumours were included, with centroid motion later quantified from end-inhalation to end-exhalation.

The core geometric innovation was to contour the **GTV on each respiratory phase**, then expand each phase-specific GTV by **7 mm isotropically** to create a phase-specific CTV. Instead of collapsing these to a simple binary IGTV/ITV, the union of all phase-specific CTVs was partitioned into sub-volumes according to the fraction of the respiratory cycle for which each spatial region was occupied. The authors call this occupancy-annotated internal CTV the **motion-weighted CTV (mwCTV)**. In the two-phase schematic, the overlap region is mwCTV100 (occupied **100%** of the time), while peripheral regions are lower-occupancy sub-volumes such as mwCTV50. With 10 phases, multiple occupancy shells exist. An in-house **Visual C++** program, using contours exported from the TPS, determined these sub-volumes; the authors state it was validated against Pinnacle, but they do **not** report the validation procedure or error metrics **[DETAIL NOT REPORTED]**. The same occupancy-union concept was applied to OARs to create mwOARs, except **no margin expansion** was used for OARs. Lungs were analysed in all 10 cases; liver was analysed in **2** right lower lobe cases where the organ was fully included on 4D-CT.

Treatment plans were generated retrospectively in **Pinnacle version 8.0m** for a **Varian Trilogy** linac. Dose calculation used **Collapsed Cone Convolution Superposition**. The reported dose distribution used for the approximation was a **single 3D dose** calculated on the **untagged free-breathing CT** for the ICTV/mwCTV envelope. The key mwDVH idea was then to replace temporal occupancy by spatial volume weighting during histogram construction: for example, if a region receives a given dose only **50%** of the time, that is treated as **50% of the original volume receiving that dose 100% of the time**. In modern implementation terms, this is equivalent to a weighted-volume DVH in which each voxel contributes `occupancy × voxel_volume` rather than `voxel_volume`. The authors also define a volume ratio, **`VRx% = UVx / UV`**, where `UVx` is the union volume occupied `x%` of the time and `UV` is the total unweighted union volume. They explicitly assessed whether using only **two extreme phases** (end-inspiration and end-expiration) could approximate the full **10-phase** mwDVH.

For comparison against a “full 4D” reference, the authors used a previously validated **optical-flow deformable image registration** algorithm. Deformation matrices from each respiratory phase to a **base phase of end-inspiration** were generated, dose distributions from all phases were mapped to that base phase, and the mapped doses were **summed with equal weights**. DVHs were then computed for the **CTV and structures defined on the base phase**. Agreement was quantified using **root mean square (RMS)** differences of percentage-volume differences at fixed doses across the **entire dose range (0 Gy to plan maximum dose)**. They then compared RMS distributions across the 10 cases using a **Mann-Whitney** test. Because the same 10 cases were reused for each method, this choice is statistically suboptimal for paired data; a paired non-parametric test would have been preferable, although the effect sizes are large enough that the main conclusion is unlikely to reverse.

Important implementation details for DVH reproduction are missing. The paper does **not** report dose-grid spacing, CT slice thickness, beam arrangement, beam energy, prescription and fractionation, per-phase dose recalculation workflow for the 4D reference, DVH bin width, cumulative versus differential histogram settings, interpolation method, structure rasterisation rules, partial-volume handling, boundary inclusion conventions, or histogram end-capping **[DETAIL NOT REPORTED]**. The curves shown are cumulative `% volume vs dose` plots **[INFERRED FROM FIGURES]**, but the exact internal TPS and in-house histogram construction settings are not disclosed.

### 5. Key results: quantitative (300-600 words)

The geometric spread of the cohort was broad. Across the 10 cases, total centroid motion ranged from **0.4 cm to 1.7 cm** component motion ranges were **0.0-0.5 cm** lateral, **0.1-0.8 cm** anterior-posterior, and **0.3-1.5 cm** superior-inferior, so SI motion dominated. ICTV volumes ranged from **38.9 cc to 610.75 cc**, motion-weighted CTV equivalent volumes from **26.5 cc to 471.6 cc**, and base-phase 4D CTV volumes from **27.1 cc to 432.1 cc**. The key occupancy-core metric, VR100%, ranged from **0.25 to 0.74**. In the worked example (Case 2), total motion was **1.5 cm** the ICTV was **357.2 cc** using 10 phases versus **320.2 cc** using only two extreme phases; VR100% was **0.414** for the 10-phase construction and **0.493** for the two-phase construction, while other VRx% values were only **0.043-0.092**. This supports the authors’ claim that the fully occupied core is often the dominant occupancy sub-volume.

For target DVHs, the main quantitative result is that the occupancy-weighted method closely tracked the deformable-image-registration-based 4D reference, whereas conventional 3D ICTV evaluation systematically deviated. Using the paper’s 70 Gy endpoint, the mean difference in **% target volume covered by 70 Gy** was **-2.8 ± 0.8 percentage points** for **3D minus 4D**, **+0.3 ± 0.7 percentage points** for **mwCTV 10-phase minus 4D**, and **+0.5 ± 0.5 percentage points** for **mwCTV 2-phase minus 4D**. Figure 4 shows this pattern in every case: the conventional 3D bars are consistently below the full 4D values, whereas the 10-phase and 2-phase motion-weighted bars cluster tightly around the full 4D result.

The whole-DVH agreement metric in Table 2 is even more persuasive. The mean RMS difference to full 4D was **1.70 ± 1.06** for conventional 3D, versus **0.43 ± 0.25** for mwDVH using all 10 phases and **0.44 ± 0.21** using only two phases. Medians were **1.43**, **0.33**, and **0.39**, respectively; maxima were **4.25**, **0.87**, and **0.88**. Relative to the conventional 3D mean RMS of 1.70, the motion-weighted approximation reduces mean RMS error by about **75%**. The difference between the `4D-3D` and `4D-mwCTV 10-phase` RMS distributions was reported as **p ≤ 0.0001**, whereas the difference between `4D-mwCTV 10-phase` and `4D-mwCTV 2-phase` was **p = 0.6**, supporting the claim that the two-phase approximation is statistically indistinguishable from the 10-phase version for this endpoint.

Sensitivity to motion magnitude was **not monotonic**. For example, **Case 5** had only **0.4 cm** total motion but a relatively large **4D-3D RMS = 2.37**, whereas **Case 4** had **0.8 cm** motion and **RMS = 0.52**. This implies that error is driven not just by motion amplitude, but by the interaction between motion, occupancy distribution, and dose gradient geometry. For OARs, the results are qualitative rather than cohort-wide. In the Case 10 example shown in the paper, the motion-weighted right-lung curves are **higher** than the conventional 3D lung DVH, whereas the motion-weighted liver curve is **lower** than conventional 3D. The direction of bias therefore depends on whether higher dose falls in higher- or lower-occupancy OAR sub-regions. The authors explicitly note that OAR discrepancies are larger than for the CTV, particularly in high-gradient regions, but they do **not** provide cohort-level OAR summary statistics.

### 6. Authors' conclusions (100-200 words)

The authors conclude that, by altering contouring and preserving occupancy information within a motion-weighted planning volume, one can obtain a DVH that is much closer to full deformable-image-registration-based 4D evaluation than a standard 3D ITV-based DVH, without actually performing deformable dose accumulation. They present the method as requiring only modest modifications to existing clinical TPS workflows and as particularly attractive when deformable image registration is unavailable, labour-intensive, or unreliable because of 4D-CT artefacts. They also argue that using only the two extreme respiratory phases is a valid practical shortcut.

Those conclusions are well-supported for the paper’s narrow claim: **target-DVH approximation** to the chosen 4D reference. They are less fully supported for broader claims about “4D planning” in general, because the method does **not** model dose blurring, does **not** address irregular breathing or day-to-day setup variation, and provides only limited OAR validation. The paper motivates occupancy-weighted optimisation, but the strongest evidence presented is for **evaluation**, not for demonstrable improvement in delivered plan quality or outcomes.

### 7. Implications for reference DVH calculator design (300-600 words)

#### 7a. Algorithm and implementation recommendations

A reference calculator should support **weighted ROIs** as a first-class object, not just binary masks. This paper’s method can be implemented as a weighted cumulative DVH,

\[
V_w(D \ge d)=\frac{\sum_i w_i v_i \mathbf{1}(D_i \ge d)}{\sum_i w_i v_i},
\]

where `w_i` is the temporal occupancy probability of voxel or sub-voxel `i`. That is the cleanest engineering expression of their temporal-to-spatial weighting concept. The calculator should allow both **voxel-wise weights** and **non-overlapping occupancy shells** (`100%`, `90%`, …, `10%`) because the paper’s planning logic depends on shell priority. It should also expose a distinct approximation mode, for example `occupancy_weighted_dvh`, rather than conflating it with true 4D accumulation. The study supports a **fast two-phase mode** as an optional approximation for target DVHs, because the reported mean RMS was **0.44 ± 0.21** versus **0.43 ± 0.25** for 10 phases, but only as long as the extreme phases still overlap.

The reference implementation should **not** hard-code “always prioritise the 100% shell”. In most cases VR100% was dominant, but **Case 1** had `VR100% = 0.25` and the authors note that tighter objectives may need to target a broader combined lower-occupancy region because it represents most total occupancy time. So the software should support flexible shell aggregation and user-defined optimisation and evaluation weights. For OARs, default no-margin motion-weighted structures are reasonable, but the engine should permit optional margins for **small serial OARs with near-maximum-dose constraints**, exactly as the authors caution.

#### 7b. Validation recommendations

This paper suggests several validation cases for a reference DVH engine. First, include moving spherical or ellipsoidal targets with **elliptical trajectories**, not just 1D SI motion, because the authors explicitly note that the centre-of-mass path is often elliptical and that two extreme phases can miss path volume. Second, benchmark both **full 10-phase** and **two-phase** occupancy weighting against a true 4D accumulation workflow. Third, reproduce both “lung-like” and “liver-like” OAR scenarios: one where high dose falls in **high-occupancy** OAR sub-regions, making the weighted DVH move upward relative to 3D, and one where it falls in **low-occupancy** sub-regions, making the weighted DVH move downward. Fourth, include a no-overlap or near-no-overlap extreme-phase case to force automatic rejection of the two-phase shortcut.

As provisional performance targets for an **approximation mode** not for a gold-standard truth engine; the paper implies that target agreement within roughly **±0.5 percentage points** for `% target volume covered by 70 Gy` and mean whole-DVH RMS around **0.4-0.5** against a 4D reference is achievable in this problem class. Those numbers should be treated as **case-class-specific benchmarks**, not universal acceptance tolerances, because the study is small and thorax-only. No public data or code are described, so equivalent validation datasets will need to be synthetic or independently assembled.

#### 7c. Extensibility considerations

The main extensibility lesson is that the DVH denominator need not be a binary anatomical volume; it can be a **probability-weighted effective volume**. That same abstraction would support **probabilistic DVHs**, **EUD/gEUD** computed on weighted volume elements, and potentially **dose-surface** or **dose-mass** histograms if the engine also tracks surface elements or phase-specific mass and density. To do this well, the data model should store: `(i)` per-phase masks, `(ii)` phase probabilities, which need not be equal, `(iii)` derived occupancy maps, and `(iv)` a clean link between weighted evaluation mode and full deformable accumulation mode. The reference tool should generalise beyond equal 10% phase weights, because irregular respiration is one of the paper’s acknowledged failure modes.

#### 7d. Caveats and limitations

For a gold-standard DVH calculator, this method is best viewed as a **useful approximation benchmark**, not as the benchmark itself. Its main limitation is that it changes the **evaluation geometry** without modelling **dose blurring** or full phase-specific density effects. The improved agreement with 4D therefore comes partly from correcting the occupancy semantics of the ITV, not from reproducing the full physical dose accumulation process. The paper also relies on a deformable-image-registration-based reference that is itself uncertain, provides sparse low-level implementation detail, uses a small lung-only cohort, and offers little quantitative OAR validation. Finally, the method assumes respiratory motion from planning 4D-CT is representative of treatment and does not incorporate setup uncertainty, IGRT residuals, or irregular breathing distributions.

### 8. Connections to other literature

- **Admiraal (2008)** compared dose calculations accounting for breathing motion in stereotactic lung radiotherapy; Zhang et al. align with its observation that 4D target evaluation can look more favourable than static ITV-based evaluation.
- **Orban de Xivry (2007)** a foundational deformable-image-registration-based tumour delineation and cumulative-dose paper; this is essentially the “gold-standard” comparator class that Zhang et al. try to approximate without deformable dose accumulation.
- **Glide-Hurst (2008)** proposed a simplified 4D dose accumulation method using mean patient density; similar pragmatic goal, but it still retained dependence on deformable image registration.
- **Rosu (2007)** asked how much 4D data are required for plan-evaluation metrics; directly relevant to Zhang et al.’s 10-phase versus 2-phase comparison.
- **Baum (2006)** introduced coverage-probability-based robust planning in prostate IMRT; Zhang et al. adapt the weighting idea to thoracic respiratory motion and extend it into DVH evaluation.
- **Rietzel (2006)** on design of 4D target volumes; important background for why ITV/PTV geometry alone does not capture the temporal occupancy information exploited here.

### 9. Data extraction table

**Table 9a. Case-level geometry and occupancy characteristics extracted from Table 1.**

| Case | Site | Total motion (cm) | ICTV (cc) | mwCTV (cc) | CTV for 4D (cc) | VR100% |
|---|---|---:|---:|---:|---:|---:|
| 1 | RLL | 1.7 | 99.6 | 60.0 | 54.6 | 0.25 |
| 2 | RLL | 1.5 | 357.2 | 240.7 | 255.6 | 0.41 |
| 3 | RUL | 0.5 | 54.5 | 40.5 | 37.4 | 0.53 |
| 4 | RUL | 0.8 | 388.8 | 315.1 | 306.9 | 0.64 |
| 5 | LUL | 0.4 | 116.5 | 95.6 | 109.1 | 0.71 |
| 6 | RUL | 0.7 | 284.4 | 244.7 | 239.5 | 0.74 |
| 7 | LLL | 1.4 | 38.9 | 26.5 | 27.1 | 0.41 |
| 8 | RLL | 1.6 | 81.4 | 49.5 | 49.2 | 0.30 |
| 9 | LUL | 0.4 | 108.8 | 83.2 | 85.8 | 0.56 |
| 10 | RLL | 1.0 | 610.75 | 471.6 | 432.1 | 0.60 |

**Table 9b. Case-level RMS difference in target DVH versus full 4D reference (smaller = closer to full 4D), extracted from Table 2.**

| Case | 4D-3D RMS | 4D-mw 10ph RMS | 4D-mw 2ph RMS |
|---|---:|---:|---:|
| 1 | 1.68 | 0.87 | 0.88 |
| 2 | 1.29 | 0.70 | 0.40 |
| 3 | 1.15 | 0.67 | 0.65 |
| 4 | 0.52 | 0.38 | 0.33 |
| 5 | 2.37 | 0.58 | 0.39 |
| 6 | 1.04 | 0.15 | 0.23 |
| 7 | 2.18 | 0.28 | 0.60 |
| 8 | 4.25 | 0.24 | 0.26 |
| 9 | 0.93 | 0.17 | 0.40 |
| 10 | 1.57 | 0.27 | 0.28 |
| **Min** | **0.52** | **0.15** | **0.23** |
| **Median** | **1.43** | **0.33** | **0.39** |
| **Max** | **4.25** | **0.87** | **0.88** |
| **Mean ± 1 SD** | **1.70 ± 1.06** | **0.43 ± 0.25** | **0.44 ± 0.21** |

**Table 9c. Summary target-coverage differences at 70 Gy relative to full 4D. Differences are in percentage points of `% target volume covered by 70 Gy` (denominator = total target volume for the compared DVH).**

| Comparison versus full 4D | Mean difference ± 1 SD |
|---|---:|
| 3D - 4D | **-2.8 ± 0.8** |
| mwCTV-10ph - 4D | **0.3 ± 0.7** |
| mwCTV-2ph - 4D | **0.5 ± 0.5** |

### 10. Critical appraisal (100-200 words)

**Strengths:** The paper is algorithmically clear at the concept level, clinically practical, and unusually relevant to DVH-engine design because it formalises motion-aware evaluation as a weighted-volume problem. It provides case-level quantitative data, compares against a deformable-image-registration-based 4D reference, and tests an important simplification (2 phases versus 10).

**Weaknesses:** The cohort is small (10 cases), thorax-only, and quantitatively sparse for OARs. The paper contains a minor internal inconsistency: the results text states the 4D-3D RMS mean as 1.7 ± 1.7, but Table 2 reports 1.70 ± 1.06; the table value is consistent with the case-by-case data and is used in this summary. The “gold standard” is not analytical truth or direct measurement but a previously validated deformable-image-registration workflow. Critical low-level reproducibility details for both dose and DVH computation are missing, and the statistical test used for paired case-wise errors is not ideal. The improvement shown is partly semantic and geometric, through weighted occupancy, rather than full physical 4D dose reproduction because dose blurring is omitted.

**Confidence in findings:** **Medium.** The effect sizes are large and consistent, but the small sample, limited reporting, and imperfect reference and statistics prevent a higher rating.
**Relevance to reference DVH calculator:** **High.** This is not a gold-standard DVH algorithm, but it is highly informative for designing an explicit occupancy-weighted DVH mode, for separating approximate from true 4D evaluation, and for constructing motion-sensitive validation cases.

---

<!-- Source: SUMMARY - Rosewall 2014 - The Effect of Dose Grid Resolution on DVHs for Slender Organs at Risk during Pelvic IMRT.md -->

## Rosewall (2014) - The effect of dose grid resolution on dose volume histograms for slender organs at risk during pelvic intensity-modulated radiotherapy

### Executive summary

This paper is a focused but highly relevant planning-study benchmark for DVH accuracy in a difficult clinical geometry: the **bladder wall** during **prostate IMRT**, where a **thin hollow organ** intersects a **steep dose gradient**. Rosewall and colleagues recalculated **15** prostate IMRT plans in Pinnacle v9.0 using isotropic dose-grid spacings from **1 to 10 mm** and quantified how bladder-wall DVHs changed relative to a **1 mm** benchmark. The central finding was consistent and clinically important: as the grid became coarser, bladder-wall DVHs **overestimated low-dose volume** and **underestimated high-dose volume**.

The most practically important result is that **1.5 mm** was the **only** tested grid spacing that kept the **entire cumulative bladder-wall DVH within 1 cc of the 1 mm benchmark for every patient**. By contrast, **2.0 mm** could already produce local full-curve errors up to **2.5 cc**, and **2.5 mm** up to **5 cc**, despite seemingly acceptable cohort-average differences. High-dose wall metrics such as **V77.8 Gy**, **D2cc**, and **D5cc** were much more sensitive to grid inadequacy than lower-dose measures such as **V30 Gy**, which showed essentially no significant change.

For a reference DVH calculator, this paper strongly supports three design principles. First, **thin hollow structures in penumbrae must be treated as stress-test cases**. Second, validation should use **whole-curve DVH agreement metrics**, not just a handful of summary endpoints. Third, the implementation should support **sub-voxel boundary handling** and ideally explicit **shell or paired-surface representations**, because the failure mode is driven by the interaction between wall thickness and grid spacing. Although the study is limited to one TPS, one dose algorithm, and one clinical scenario, it is highly relevant to benchmark design for a gold-standard DVH engine.

### 1. Bibliographic record

**Authors:** Tara Rosewall, Vickie Kong, Robert Heaton, Geoffrey Currie, Michael Milosevic, Janelle Wheat
**Title:** *The effect of dose grid resolution on dose volume histograms for slender organs at risk during pelvic intensity-modulated radiotherapy*
**Journal:** *Journal of Medical Imaging and Radiation Sciences* **45**(3):204-209. The uploaded PDF is an article-in-press version; the final indexed record is September 2014, Volume 45, Issue 3, pages 204-209.
**Year:** 2014
**DOI:** [10.1016/j.jmir.2014.01.006](https://doi.org/10.1016/j.jmir.2014.01.006)
**Open access:** No (standard Elsevier copyright; PubMed lists Elsevier as the full-text source and does not indicate free full text)

### 2. Paper type and scope

**Type:** Original research.
**Domain tags:** D1 Computation | D2 Commercial systems.
**Scope statement:** This single-centre planning study recalculated 15 prostate IMRT plans in Pinnacle v9.0 (collapsed-cone convolution) using isotropic dose-grid spacings from 1 to 10 mm and quantified the resulting changes in bladder-wall DVHs. The paper matters because it tests a clinically important edge case for commercial TPS dosimetry: a thin, hollow organ at risk crossing a steep penumbra, where coarse dose grids can bias toxicity-relevant high-dose subvolumes even when conventional summary metrics appear acceptable.

### 3. Background and motivation (150-300 words)

The paper addresses a specific but important gap in DVH accuracy: how fine the dose calculation grid must be when the organ of interest is a **slender wall structure** immediately adjacent to the target and therefore intersecting the field edge. Rosewall et al. frame the problem around three main determinants of dose-reporting accuracy in a TPS: heterogeneity correction, dose calculation algorithm, and dose grid resolution. They note that the first two had attracted more consensus, whereas optimal 3D grid spacing remained scenario-dependent and poorly defined. Prior work cited by the authors suggested that **~4 mm** might be adequate for conventional pelvic radiotherapy, but that for IMRT, especially in head-and-neck applications, **~4%** dose discrepancies could persist at **4 mm**, and **~1.5 mm** or finer grids might be necessary in steep gradients.

Their motivation is tightly connected to DVH computation. In pelvic IMRT, the bladder wall can lie partly inside and partly outside the treated region, so it samples the steepest part of the penumbra. Under those conditions, coarse dose grids can systematically **overestimate low-dose volume** and **underestimate high-dose volume**, which is especially problematic because urinary toxicity models often depend on high-dose wall subvolumes. The study therefore asks a practical benchmark question: for bladder-wall DVHs in prostate IMRT, what is the coarsest grid spacing that keeps error below a clinically meaningful threshold, defined here as **<1 cc** volume difference or **<1 Gy** dose difference relative to a **1 mm** benchmark?

### 4. Methods: detailed technical summary (400-800 words)

The authors describe the work as a **single-centre, prospective, quasi-experimental** study with ethics approval. The dataset comprised planning CT scans and clinical plans from **15 prostate cancer patients**, selected consecutively in reverse chronological order from a pool of more than **400** departmental cases. Inclusion criteria were tightly specified: treatment to **78 Gy in 39 fractions** to a prostate-only clinical target volume, **7-field coplanar static-field step-and-shoot IMRT**, departmental dose constraints satisfied, “comfortably full” bladder preparation instructions, and no positive or negative pelvic contrast. This is therefore a controlled planning-study cohort rather than a heterogeneous retrospective sample.

All plans were copied into a research instance of Pinnacle **version 9.0** (Elekta) and de-identified. For each planning CT, the **entire inner and outer bladder surfaces** were manually delineated by a **single observer** using standard Pinnacle tools. This is important: the study did not evaluate a solid bladder contour, but a hollow wall representation intended to reflect functional tissue. The calculation volume for each recomputed dose grid was automatically defined as a **3 cm margin** around the bladder contours plus the clinical target volume. Nine otherwise identical versions of each clinical plan were then created, varying only the isotropic interval between dose calculation points. Tested grid increments were **1, 1.5, 2, 2.5, 3, 4, 5, 7, and 10 mm**. The **dose grid origin was kept constant**, which isolates spacing as the intended experimental variable. Dose was recalculated using the **collapsed cone convolution/superposition** algorithm with **tissue heterogeneity correction**. Beam energy, beam model details, segment statistics, optimisation settings, and CT acquisition parameters were **[DETAIL NOT REPORTED]**.

To help interpret whether thinner or thicker walls were more sensitive to grid spacing, the authors estimated average bladder-wall thickness using a previously validated geometric method. The outer bladder contour was uniformly contracted in **0.1 mm** steps until the contracted volume matched the manual inner bladder volume; that contraction magnitude was then used as an approximate mean wall thickness. This is not a direct histological or image-based thickness measurement, but a geometry-derived surrogate.

The DVH workflow is especially relevant to a reference DVH calculator. The TPS exported **raw differential DVHs** for the manually contoured **inner** and **outer** bladder volumes. Dose-volume pairs were binned in **10 cGy** increments across the full dose range. These differential DVHs were exported to `Excel 2010`, converted to **cumulative** histograms in **10 cGy** bins, and the cumulative inner-bladder histogram was subtracted from the cumulative outer-bladder histogram to derive a **hollow bladder-wall DVH**. Thus, the study did not create a direct wall structure inside the TPS for DVH extraction; instead it constructed the wall DVH by Boolean subtraction in histogram space. The paper does **not** report Pinnacle’s internal contour rasterisation rule, voxel-inclusion criterion, boundary treatment, interpolation kernel, partial-volume weighting, or any supersampling used during DVH export; all are **[DETAIL NOT REPORTED]**. End-capping and maximum-dose definition details are likewise **[DETAIL NOT REPORTED]**.

The **1 mm** grid was treated as the study benchmark. The stated rationale was threefold: prior literature associated **≤1 mm** grids with near-zero dose-calculation error; going below CT voxel resolution was deemed unlikely to improve accuracy meaningfully; and **1 mm** was the smallest increment their hardware could reliably compute over the specified volume, using an `Oracle-based X4470` workstation with **24 cores** and **96 GB RAM**. For comparison, the authors defined a signed subtraction DVH as **ΔV(d) = V_grid(d) - V_1mm(d)** for each dose bin. These pairwise subtraction DVHs were first computed per patient, then averaged across the **15-patient** cohort. They also extracted clinically familiar endpoints: **V77.8 Gy**, **V65 Gy**, **V30 Gy**, **Dmax**, **D2cc**, and **D5cc**. A mean difference greater than **1 cc** for volume or **1 Gy** for dose was deemed clinically different. Statistical testing used paired, two-tailed **Student’s t-tests**, with **P ≤ .001** treated as significant because of multiple testing. Correlation between wall thickness and grid effect was evaluated with **Spearman’s rho**, with **|rho| > 0.7** considered meaningful by the authors.

The main limitations acknowledged by the authors were that the comparator was a **1 mm grid**, not a true physical or Monte Carlo ground truth; that different penumbra shapes or gradients might yield different quantitative thresholds; and that the findings apply to a **hollow wall** model, not a solid bladder contour. Those are important because the study tests combined effects of **dose recalculation on different grids plus TPS DVH extraction**, not an isolated standalone DVH algorithm.

### 5. Key results: quantitative (300-600 words)

All planned procedures were completed, giving **135 bladder-wall DVHs** (**15 patients × 9 grids**). The mean subtraction plot on **page 3, Figure 1** showed a consistent signed bias for every grid coarser than 1 mm: bladder-wall volume receiving **<20 Gy** was systematically **overestimated**, while volume receiving **>60 Gy** was systematically **underestimated**. The largest mean excursions occurred at approximately **10 Gy** and **78 Gy**. Across the full DVH, mean volume differences remained **<1 cc** for **1.5, 2.0, and 2.5 mm**, **<2 cc** for **3.0 and 4.0 mm**, and exceeded **2 cc** for **5.0, 7.0, and 10.0 mm**.

The important nuance is that cohort means hid clinically relevant patient-specific failures. The maximum-patient subtraction plot on **page 4, Figure 2** showed that a **2.0 mm** grid could still deviate by up to **2.5 cc**, and a **2.5 mm** grid by up to **5 cc**, somewhere along the cumulative DVH. Only the **1.5 mm** grid kept the full DVH within **≤1 cc** of the 1 mm benchmark for **every patient**. Expressed another way, **1.5 mm** was the only spacing with **no pairwise differences >1 cc anywhere on the curve**. The paper explicitly reports that the **2 mm** grid had **1%** of the DVH curve more than **1 cc** away from the benchmark; **5, 7, and 10 mm** grids showed **16%**, **27%**, and **40%** of the curve, respectively, beyond that threshold. The printed text then states that “for **2 to 4 mm**” the mean percentage was **7%-9%**, which conflicts with the explicit **2 mm = 1%** value; the exact breakdown for **2.5, 3, and 4 mm** is therefore ambiguous as printed.

Table 1 shows that the **1 mm benchmark** yielded mean values of **80.33 Gy** for **Dmax** (SD **0.86 Gy**), **78.87 Gy** for **D2cc** (SD **0.84 Gy**), **77.53 Gy** for **D5cc** (SD **1.32 Gy**), **5 cc** for **V77.8 Gy** (SD **2 cc**), **12 cc** for **V65 Gy** (SD **4 cc**), and **22 cc** for **V30 Gy** (SD **7 cc**). High-dose endpoints were consistently reduced as the grid coarsened. For example, at **3.0 mm**, **V77.8 Gy** was already **-1.6 cc** versus 1 mm and statistically significant (**P ≤ .001**), even though several dose-to-small-volume metrics had not yet crossed the significance threshold. At **4.0 mm**, **Dmax** was **-1.02 Gy** and **D5cc** **-1.06 Gy** (both significant). At **5.0 mm**, the under-reporting became clearly material: **Dmax -1.29 Gy**, **D2cc -1.01 Gy**, **D5cc -1.44 Gy**, and **V77.8 Gy -2.7 cc**, all significant at **P ≤ .001**. By contrast, **V30 Gy** showed **no significant difference at any grid**, and **V65 Gy** was only minimally affected, reaching significance only at **10.0 mm** (**-1.3 cc**). This is a useful negative result: mid-dose summary metrics were far less sensitive sentinels of grid inadequacy than high-dose wall endpoints.

Mean bladder-wall thickness was **2.4 mm**, ranging from **1.7 to 4.4 mm**. No meaningful association was found between wall thickness and the magnitude of the grid effect: Spearman coefficients for key endpoint differences ranged from **-0.42 to +0.47**, and for the percentage of the curve exceeding **1 cc** difference from **-0.13 to +0.55**, all below the authors’ significance criterion of **|rho| > 0.7**. The authors also provide a clinically interpretable example using a published bladder toxicity threshold (**V77.8 Gy > 2.9%**): with a **5 mm** grid, only **5/15** patients in this cohort would have been classed as “high risk”, whereas with **1 or 1.5 mm** grids **14/15** would have been. That example is illustrative rather than outcome-validated in this dataset, but it shows the potential magnitude of clinical reclassification.

### 6. Authors' conclusions (100-200 words)

The authors conclude that dose-grid resolution is a materially important determinant of DVH accuracy for **slender organs at risk positioned in the penumbra**, and specifically recommend a **1.5 mm** dose-grid increment for bladder-wall DVH calculation during prostate IMRT planning. They further argue that whenever a new planning technique or organ-delineation method is introduced, the appropriate grid resolution should be re-evaluated rather than inherited from older practice. That core conclusion is well supported within the study’s tested scenario: **1.5 mm** was the only grid spacing that maintained **≤1 cc** full-curve agreement for every patient. Their broader suggestion that **1.5 mm** is likely suitable for other IMRT settings is plausible and consistent with the head-and-neck literature they cite, but it remains an extrapolation because only **Pinnacle collapsed-cone prostate IMRT** with bladder-wall contours was directly tested here.

### 7. Implications for reference DVH calculator design (300-600 words)

#### 7a. Algorithm and implementation recommendations

For a reference DVH calculator, the primary lesson is that **thin hollow organs in steep gradients require finer effective sampling than conventional solid-organ pelvic planning would suggest**. In this dataset, **2.0 mm** already produced local full-curve errors up to **2.5 cc**, and **2.5 mm** up to **5 cc**, despite apparently acceptable cohort means. A robust implementation should therefore not rely on mean endpoint agreement alone. For bladder-wall-like shells, a sensible evidence-based warning threshold is: **investigate carefully once grid spacing exceeds 1.5 mm, and avoid treating 2.0-2.5 mm as automatically acceptable for benchmark work**.

The engine should also separate three things explicitly: **dose-field representation**, **structure-overlap integration**, and **histogram binning**. This paper manipulated dose calculation grid spacing, but the wall DVH was built by subtracting inner and outer cumulative histograms. A reference tool should support both approaches: direct shell-object evaluation and exact/validated Boolean composition from paired surfaces. Sub-voxel overlap integration near boundaries is essential; the paper’s failure mode is precisely what would be expected if structure thickness approaches dose grid spacing. A useful heuristic inferred from the study’s numbers is that spacing should remain **comfortably below wall thickness**: the only universally acceptable grid (**1.5 mm**) was well below the cohort mean thickness (**2.4 mm**), whereas **2.5 mm**, approximately the mean thickness, already failed the worst-case criterion. This is an inference from the reported numbers, not a formal theorem.

High-dose wall endpoints should be first-class outputs. **V77.8 Gy**, **D2cc**, and **D5cc** detected clinically relevant degradation earlier than **V30 Gy**, which was essentially insensitive. A reference calculator should therefore prioritise accurate computation of **Dxcc** and **VxGy** for small high-dose subvolumes and should not use mid-dose metrics alone as adequacy checks.

#### 7b. Validation recommendations

A good validation suite should reproduce the Rosewall stress case explicitly: thin hollow shells crossing a steep penumbra. Analytical phantoms should include hollow cylinders, annuli, or spherical shells with wall thicknesses spanning roughly **1.5-4.5 mm**, exposed to known linear or sigmoid dose gradients and sampled at **1, 1.5, 2, 2.5, 3, 4, 5, 7, and 10 mm**. Validation metrics should include not only endpoint differences but also **signed subtraction DVHs**, **maximum |ΔV| anywhere on the cumulative curve**, and the **percentage of the curve exceeding 1 cc** error, because this paper shows that mean errors can look benign while local deviations remain unacceptable.

The reference standard should be stronger than the one used here. Rosewall et al. reasonably used **1 mm** because of hardware and CT-voxel constraints, but a gold-standard calculator should validate against **analytic ground truth** or Monte Carlo / very-fine-grid recalculation, not simply a finer TPS grid. Grid-origin sensitivity should also be tested explicitly: this paper held the **grid origin constant**, so phase effects relative to the structure were controlled rather than explored. Finally, the validation pack should include both **hollow** and **solid** organ representations to demonstrate how wall modelling changes sensitivity. No public dataset or code release was provided in the paper.

#### 7c. Extensibility considerations

Although this is not a metric-innovation paper, it strongly motivates a data model that can represent **paired inner/outer surfaces** or explicit **shell structures**, not just solid voxelised ROIs. Once that exists, extension to **dose-surface histograms** or **dose-mass histograms** for hollow organs becomes natural. At minimum, the calculator API should support generic **D_xcc**, **V_xGy**, and absolute/relative-volume queries, because the paper’s clinically relevant discrepancies concentrate in wall-specific high-dose subvolumes rather than whole-organ averages. It would also be valuable to attach uncertainty metadata based on the relationship between **local structure thickness** and **source dose-grid spacing**, because this paper shows that that ratio governs failure risk.

#### 7d. Caveats and limitations

These findings should not be universalised without care. They derive from **15** prostate plans, one TPS (Pinnacle v9.0), one dose algorithm (collapsed cone), and one delivery style (**7-field step-and-shoot IMRT**). The study is also **not** a pure DVH-algorithm validation: changing the grid changed the recalculated dose field itself, so dose-field discretisation and DVH extraction are confounded. The comparator was **1 mm**, not measured or Monte Carlo ground truth. Important implementation details for a reference calculator ;  CT voxel size, interpolation method, contour rasterisation, partial-volume handling, and boundary rules ;  were **not reported**. The reported wall-thickness range was also narrow (**1.7-4.4 mm**), so “no correlation with thickness” should not be overgeneralised beyond typical full-bladder prostate planning. Finally, the paper contains minor reporting inconsistencies: the French résumé says 12 patients, whereas the English abstract/methods/results clearly support **15**, and the printed text around percentage-of-curve errors is internally inconsistent for the **2 mm** grid.

### 8. Connections to other literature

- **Drzymala et al. (1991)** Foundational DVH paper underpinning Rosewall’s premise that dose-calculation inaccuracies propagate directly into DVH errors.
- **Niemierko and Goitein (1989)** Early theoretical treatment of dose-grid size effects; Rosewall extends that question to a clinical pelvic IMRT bladder-wall setting.
- **Smith et al. (1990)** Conventional radiotherapy grid-size work used by Rosewall both to justify the 1 mm benchmark and to contrast with older **4 mm** pelvic practice.
- **Chung et al. (2006)** Head-and-neck IMRT study cited as showing **~4%** discrepancies at **4 mm** and supporting **~1.5 mm** as a more appropriate IMRT grid size; Rosewall finds a similar threshold for bladder wall.
- **Ebert et al. (2010)** Multi-TPS DVH comparison work relevant because discretisation and sampling differences can masquerade as TPS disagreement.
- **Rosewall et al. (2011)** Same-group paper on bladder-wall delineation and observer variability; directly complementary because organ definition and grid sensitivity both affect wall DVHs.
- **Cheung et al. (2007)** Urinary-toxicity study used here to illustrate how grid-dependent underestimation of **V77.8 Gy** could reclassify patient risk.

### 9. Data extraction table

The paper contains extractable quantitative data. Dose values below are converted to **Gy** for consistency; the original paper reported Table 1 dose values in **cGy**.

**Table 9a. Whole-curve DVH sensitivity summary**

| Grid increment | Mean whole-DVH volume difference vs 1 mm | Worst patient-specific difference across full curve | Mean % of curve with >1 cc difference | Notes |
|---|---:|---:|---:|---|
| 1.5 mm | <1 cc | ≤1 cc for every patient | 0% | Only grid meeting the per-patient full-curve criterion |
| 2.0 mm | <1 cc | up to 2.5 cc | 1% | Mean acceptable, but local failures remain |
| 2.5 mm | <1 cc | up to 5 cc | [DETAIL NOT REPORTED separately] | Substantial worst-case error despite acceptable mean |
| 3.0 mm | <2 cc | [DETAIL NOT REPORTED] | [DETAIL NOT REPORTED separately] | High-dose endpoints begin to fail |
| 4.0 mm | <2 cc | [DETAIL NOT REPORTED] | [DETAIL NOT REPORTED separately] | Dmax and D5cc significantly lower than 1 mm |
| 5.0 mm | >2 cc | [DETAIL NOT REPORTED] | 16% | Large whole-curve deviation |
| 7.0 mm | >2 cc | [DETAIL NOT REPORTED] | 27% | Large whole-curve deviation |
| 10.0 mm | >2 cc | [DETAIL NOT REPORTED] | 40% | Large, more random high-dose behaviour |

Note: the paper also states that “for **2 to 4 mm**” the percentage of the curve with >1 cc difference was **7%-9%**, which conflicts with its explicit **2 mm = 1%** statement; the exact per-grid breakdown for **2.5, 3, and 4 mm** is therefore ambiguous as printed.

**Table 9b. Mean pairwise differences from the 1 mm benchmark (Δ = grid − 1 mm)**

1 mm benchmark means (SD): **Dmax 80.33 Gy (0.86)**, **D2cc 78.87 Gy (0.84)**, **D5cc 77.53 Gy (1.32)**, **V77.8 Gy 5 cc (2)**, **V65 Gy 12 cc (4)**, **V30 Gy 22 cc (7)**. Entries below are **mean difference (SD)**. `*` indicates **P ≤ .001** in the original paper.

| Grid | ΔDmax (Gy) | ΔD2cc (Gy) | ΔD5cc (Gy) | ΔV77.8 (cc) | ΔV65 (cc) | ΔV30 (cc) |
|---|---:|---:|---:|---:|---:|---:|
| 1.5 mm | -0.20 (0.90) | -0.15 (0.86) | -0.16 (1.36) | -0.4 (2.4) | -0.1 (3.8) | 0.0 (6.9) |
| 2.0 mm | -0.25 (0.90) | -0.39 (0.96) | -0.23 (1.31) | -0.6 (2.3) | -0.1 (3.8) | 0.0 (7.1) |
| 2.5 mm | -0.61 (0.79) | -0.49 (0.88) | -0.61 (1.48) | -0.9 (3.3) | -0.2 (3.9) | 0.1 (7.0) |
| 3.0 mm | -0.87 (0.93) | -0.69 (0.86) | -0.87 (1.42) | -1.6 (2.4)\* | -0.3 (3.9) | -0.0 (7.1) |
| 4.0 mm | -1.02 (0.88)\* | -0.83 (0.83) | -1.06 (1.57)\* | -1.9 (3.2) | -0.4 (3.8) | -0.1 (6.9) |
| 5.0 mm | -1.29 (0.75)\* | -1.01 (0.65)\* | -1.44 (1.57)\* | -2.7 (1.9)\* | -0.6 (3.9) | -0.1 (7.2) |
| 7.0 mm | -1.34 (0.74)\* | -1.01 (0.84) | -1.83 (2.32) | -2.4 (2.6)\* | -0.9 (3.9) | -0.2 (7.2) |
| 10.0 mm | -0.80 (1.16) | -0.57 (1.29) | -2.07 (3.35) | -1.6 (2.8) | -1.3 (3.9)\* | 0.0 (7.2) |

### 10. Critical appraisal (100-200 words)

**Strengths:** tightly controlled within-patient design; clinically realistic thin-wall OAR problem; explicit testing of grid spacings from **1 to 10 mm** full-curve subtraction DVHs in addition to standard endpoints; and clinically interpretable thresholds tied to bladder-wall metrics rather than generic gamma-style summaries. **Weaknesses:** small single-centre cohort; one TPS and one algorithm; surrogate **1 mm** benchmark rather than physical ground truth; important implementation details omitted; and minor reporting inconsistencies in the printed paper. **Confidence in findings: Medium.** The direction and scale of the effect are convincing, internally coherent, and consistent with earlier theoretical and IMRT literature, but the absolute **1.5 mm** threshold is scenario-specific and benchmark-dependent. **Relevance to reference DVH calculator: High.** This paper directly informs benchmark design for thin hollow organs, shows why whole-curve agreement matters more than a few summary metrics, and provides an excellent template for stress-testing grid-induced aliasing in pelvic IMRT DVHs.

---

<!-- Source: SUMMARY - Nelms 2015 - Methods, software and datasets to verify DVH calculations against analytical values; 20 years late(r).md -->

## Nelms (2015) - Methods, software and datasets to verify DVH calculations against analytical values: twenty years late(r)

### Executive summary

This 2015 *Medical Physics* paper is a highly relevant benchmark study for reference-quality DVH software. Nelms and colleagues created synthetic `DICOM RT` structure sets and dose grids for simple geometries with **closed-form analytical cumulative DVHs**, allowing commercial DVH implementations to be tested against genuine ground truth rather than against another numerical calculator. They used spheres, cylinders, and cones at multiple contour spacings (**0.2, 1, 2, 3 mm**) combined with linear dose gradients and compared Pinnacle v9.8 with a research version of PlanIQ v2.1.

The main result is that DVH outputs differed substantially between systems, especially at low-volume and low-dose edges, and that these differences were traceable to specific algorithmic choices rather than random noise. In the fine-contour test, Pinnacle had **52/340** endpoint deviations greater than **3%** versus **5/340** for PlanIQ; in the more clinically realistic 1-3 mm test, the counts were **93/255** versus **18/255**. The most striking failures involved Dmin, D99, and D95, with Pinnacle showing Dmin errors up to **60.0%** under superior-inferior gradients.

For a reference DVH calculator, the paper’s central engineering message is that **structure rendering, end-capping, dose-sampling alignment, supersampling, and surface-aware extrema handling must be explicit, internally consistent, and validated against analytical benchmarks**. It also argues strongly for validating the **entire DVH curve**, not just a few derived endpoints.

### 1. Bibliographic record

**Authors:** Benjamin Nelms, Cassandra Stambaugh, Dylan Hunt, Brian Tonner, Geoffrey Zhang, Vladimir Feygelman
**Title:** *Methods, software and datasets to verify DVH calculations against analytical values: twenty years late(r)*
**Journal:** *Medical Physics*
**Year:** 2015
**DOI:** [10.1118/1.4923175](https://doi.org/10.1118/1.4923175)
**Open access:** No (subscription journal article; supplementary benchmark materials were made available by the journal at publication).

### 2. Paper type and scope

**Type:** Original research

**Domain tags:** D1 Computation | D2 Commercial systems

**Scope statement:**
This paper develops an analytical benchmark framework for verifying dose-volume histogram (DVH) calculations independently of any treatment planning or review system. The authors generate synthetic `DICOM RT` structure sets and dose grids for simple shapes with closed-form cumulative DVHs, then use these as ground truth to test two commercial implementations, Pinnacle v9.8 and a research version of PlanIQ v2.1, while also introducing a custom comparison tool, CurveCompare.

### 3. Background and motivation

DVHs are ubiquitous in external beam radiotherapy plan evaluation and underpin many downstream biological and protocol metrics, yet the actual numerical accuracy of commercial DVH implementations has historically been under-specified. The paper notes that AAPM TG-53 identified DVH accuracy as something that should be validated during TPS QA, but did not provide detailed benchmark datasets, failure-mode-oriented tests, or agreed performance criteria. That omission matters because DVH outputs depend on multiple algorithmic choices: 3D rendering of contour-defined structures, interslice interpolation, end-capping, dose-grid resolution, DVH sampling resolution and alignment, dose interpolation, and dose bin width. Different software may therefore report different DVHs from the same `DICOM RT` inputs.

Prior work had already shown cross-system variation, but much of it relied on independent in-house calculators to provide consistency rather than absolute truth. Ebert and colleagues’ SWAN software, for example, was positioned as a consistent reference for cross-TPS comparison rather than a demonstrably more accurate calculator; Panitsa and colleagues had earlier used simple geometries, but with standards derived from the same TPS isodoses and therefore limited precision. The immediate practical motivation here was clinical introduction of PlanIQ, where the authors observed occasional discrepancies between TPS-reported DVH values and PlanIQ recomputation from the same exported plan, structure, and dose objects. That led to the central question: which result, if either, is numerically correct? The paper’s answer is to create benchmark cases whose DVHs are analytically calculable in closed form, so software outputs can be judged against genuine ground truth rather than another numerical implementation.

### 4. Methods: detailed technical summary

This was an analytical/programmatic phantom study rather than a clinical or patient-based investigation. The authors created four synthetic CT datasets with contiguous slice thicknesses of **0.2, 1, 2, and 3 mm**. They then generated `DICOM RT` structure sets for a **sphere**, **cylinder**, and **cone** the cylinder and cone were each modelled in two orientations: an “axial” form with the major axis along **Y**, and a “rotated” form with the major axis along **Z**. Structure contours were generated programmatically in `MATLAB R2011a` by finely discretising analytical cross-sections with point spacing **≤0.2 mm**. Boundary slices that geometrically reduced to a point or line were replaced with tiny polygons of negligible area to avoid ambiguity at the end slices. All principal dimensions were **24 mm** (sphere diameter; cylinder/cone base diameter and height), producing relatively small volumes of approximately **7.3 cc** (sphere), **11.0 cc** (cylinder), and **3.7 cc** (cone). These sizes were deliberately chosen to stress voxelisation and interslice interpolation for small structures.

Synthetic dose grids were also generated programmatically. An arbitrary dose grid was first created in Pinnacle, exported as `DICOM RT Dose`, and then its pixel values were overwritten with a simple analytical function before re-saving. Each dose grid was set to **16 Gy** at the structure centre, with a **1 Gy/mm** linear 1D gradient, yielding nominal **Dmax = 28 Gy** and **Dmin = 4 Gy** across the structure extent. One gradient was along the superior-inferior **Y** axis; the manuscript then inconsistently refers to the orthogonal in-plane gradient as **X** in Methods but **Z/anterior-posterior** in Results and Discussion, which appears to be a notation inconsistency rather than a change in test design. The smallest dose-grid resolution used was **0.4 × 0.2 × 0.4 mm³**, limited by Pinnacle support for axial-plane pixels no smaller than **0.4 × 0.4 mm²** additional cubic grids of **1, 2, and 3 mm** were created to match the coarser structure spacings. Because the dose was synthetic, clinical beam energy, beam model, algorithm version, and heterogeneity correction are **not applicable**.

The two tested DVH engines were Pinnacle v9.8 and a research version of PlanIQ v2.1. Pinnacle was described, based on prior literature and direct observation, as using regular sampling on the plan dose grid with user-selected dose bin width **≥1 cGy** the authors used the finest available setting, **1 cGy**, producing about **2400 bins**. Pinnacle also automatically expanded structures by **half the CT slice width** superiorly and inferiorly. However, the public domain did not document the remainder of its DVH algorithm; interpolation scheme, exact boundary handling, supersampling strategy, and partial-volume formulation are therefore **[DETAIL NOT REPORTED]**. PlanIQ, by contrast, is described in more detail: it first builds a 3D surface from axial contours, then reslices that surface with an orthogonal grid of arbitrary resolution and alignment. The grid is constrained to include the original dose-grid points exactly. For small or complex ROIs, PlanIQ supersamples in odd integer factors (**3×, 5×, 7×**) until the ROI contains at least **40 000 voxels** the threshold defining “small/complex” is **[DETAIL NOT REPORTED]**. Odd factors were deliberately chosen so that new interpolated planes were not centred exactly between original dose planes. End-capping in PlanIQ is user-configurable from none to half the spacing to the next slice; here it was set to the half-slice option to mimic Pinnacle. The interpolation method used for intermediate dose values is **[DETAIL NOT REPORTED]**, but PlanIQ additionally samples dose at every original contour coordinate in a post-processing step so that extrema on the surface can contribute to Dmin and Dmax. Its DVH binning uses fine decimal precision such that the total number of bins from zero to the grid maximum is **≥10 000**. Neither system is described as performing exact geometric fractional voxel intersection; practical partial-volume handling is therefore mediated through voxel resolution/supersampling rather than an explicitly reported exact overlap calculation.

The reference standard was a set of **closed-form analytical cumulative DVHs**. The authors derived cumulative `V(D)` from the cross-sectional area of each object as a function of position along the gradient axis, integrating the volume above dose `D`. They also modified the analytical DVHs to account for the **half-slice superior/inferior structure extension** used by both tested systems; this affects analytical Dmin/Dmax when the gradient is along **Y**, and total volume for the axial cylinder and cone. For the other orientation/shape combinations, the volume effect of this expansion was reported as **<0.01%**. The appendix explicitly presents the rotated-cone derivation, the most mathematically challenging case, and the authors note that inverse dose-at-volume queries such as D95 can then be solved numerically from the analytical `V(D)` relation; the numerical solver details and tolerances are **[DETAIL NOT REPORTED]**.

Three complementary tests were used. **Test 1** held contour spacing at **0.2 mm** to minimise structure-rendering error while varying the dose grid from fine to coarse, isolating dose-sampling behaviour. **Test 2** paired contour spacing and dose-grid resolution at **1, 2, and 3 mm** to mimic common practice. For both, the discrete DVH metrics evaluated were total volume, Dmean, Dmax, Dmin, D99, D95, D5, D1, and D0.03 cc. The primary summary metric was the count of points whose dose difference exceeded **3%**, with percentage differences normalised to the **local dose**, not the maximum dose; this makes low-dose endpoints appear especially sensitive. **Test 3** used the same data conditions as Test 2 but analysed the **entire curve** using custom noncommercial software CurveCompare, which imported analytical and exported numerical DVH data, sampled each pair at **301 points** (approximately every **0.1 Gy**), and generated volume-error histograms plus minimum, maximum, mean, and standard deviation of volume error after normalisation to total structure volume. No inferential hypothesis tests, p-values, or confidence intervals were reported, which is appropriate for a deterministic benchmark study. The full results table, `DICOM RT` objects, and CurveCompare were made available as supplementary material at publication.

### 5. Key results: quantitative

For **Test 1** (fine **0.2 mm** contour spacing, variable dose grid), Pinnacle produced **52/340** parameter deviations above **3%** (**15%**) versus only **5/340** for PlanIQ (**1.5%**). Total volumes were already reasonably close for both systems: within **2%** of analytical for Pinnacle and within **1%** for PlanIQ. The most striking separation was at the low-dose edge. Pinnacle’s Dmin was consistently **7.5% low** for the in-plane gradient reported as **Z** and **2.6% high** for the **Y** gradient, whereas PlanIQ showed **0.0% deviation to one decimal place**. For D99, Pinnacle exceeded the **3%** threshold in **20/40** cases, with a range of **−1.4% to 7.5%** PlanIQ exceeded it only **3/40** times, all associated with the rotated cylinder, at **3.8%-5.2%**. For D95, the counts were **12** versus **2**, with ranges **−6.6% to 5.2%** for Pinnacle and **−0.8% to 3.9%** for PlanIQ. Neither system exceeded **3%** for D5, D1, or D0.03 cc in this fine-contour test. The page-6 figure shows visibly broader histogram bars for Pinnacle, especially for D99 and D95, indicating a wider spread of low-dose-edge errors.

For **Test 2** (matched contour and dose resolutions of **1-3 mm**), the performance gap widened: Pinnacle had **93/255** deviations above **3%** (**36%**) versus **18/255** for PlanIQ (**7%**). Almost all structure volumes remained within **3%** of analytical, except one PlanIQ case: the rotated cylinder at **3 mm**, which was **−4.2%** low; the authors attributed this to the coarse stack of rectangular axial contours insufficiently approximating the true circular cross-section, with the volume bias worsening from **−1.0%** at **1 mm** to **−4.2%** at **3 mm**. PlanIQ again reported **0.0%** deviation for Dmin and Dmax, and the text notes a **0.7%** Dmean error for the rotated cylinder, although Table II lists a Dmean range of **0.0%**, a minor table/text inconsistency. In Pinnacle, Dmin exceeded **3%** in **30/30** cases, with a range of **−7.5% to 60.0%** for the **Y** gradient, the error increased from **14.3%** at **1 mm** to **60.0%** at **3 mm** for all structures. Dmax exceeded **3%** in 10 cases, range **−5.1% to 1.1%**. D99 exceeded **3%** in **18** Pinnacle cases and **11** PlanIQ cases, with maximum errors of **44.4%** and **22.3%**, respectively. The worst D95 error was Pinnacle’s rotated cone with **Y** gradient at **3 mm**, **19.5%**. At the high-dose edge, Pinnacle still showed failures: D5 in 2 cases, D1 in **7**, and D0.03 cc in **7** PlanIQ had only two >3% failures there, both in the rotated cylinder with **Y** gradient at **3 mm** (`D1 = −3.9%`, `D0.03 cc = −4.6%`).

**Test 3** quantified whole-curve volume errors rather than only discrete dose-at-volume endpoints. Averaged across the five shapes, for **1 mm** data and the superior-inferior gradient, Pinnacle showed volume-error statistics of **−4.4% to 2.2%** with mean **−0.3%** and SD **1.3%**, whereas PlanIQ showed **−0.4% to 0.4%**, mean **0.0%**, SD **0.2%**. At **3 mm** in the same gradient direction, the average worsened to **−11.2% to 7.9%**, mean **−0.7%**, SD **3.5%** for Pinnacle, versus **−1.5% to 0.6%**, mean **−0.5%**, SD **0.5%** for PlanIQ. The worst individual Pinnacle case was the axial cone at **3 mm** with superior-inferior gradient: **−16.7% to 13.0%**, mean **0.9%**, SD **4.4%**. The worst PlanIQ whole-curve cases were mostly rotated cylinders: at **3 mm** with superior-inferior gradient, **−4.2% to 0.0%**, mean **−2.2%**, SD **1.0%** at **3 mm** with anterior-posterior gradient, **−4.2% to 0.7%**, mean **−1.8%**, SD **1.5%**. Figure 5 visually reinforces this: the dotted Pinnacle curves are visibly stair-stepped and diverge at the curve ends for the **3 mm** sphere and rotated cylinder, whereas PlanIQ’s dotted curves are much smoother and lie almost on top of the analytical curves for the easier cases.

Two additional sensitivity analyses matter. First, excluding the clinically less important Dmin and Dmax, the >**3%** failure counts still favoured PlanIQ: **32 (12%) vs 5 (2%)** in Test 1, and **53 (25%) vs 17 (8%)** in Test 2. Second, tightening the threshold to **2%** produced **84 (25%) vs 11 (3.2%)** deviations in Test 1 and **106 (42%) vs 24 (9%)** in Test 2 for Pinnacle versus PlanIQ, so the ranking was unchanged under stricter commissioning-like tolerances. The authors did not report p-values or confidence intervals; results are deterministic comparisons against analytical ground truth rather than inferential statistics.

### 6. Authors' conclusions

The authors conclude that the combination of analytical formulas, fabricated `DICOM RT` datasets, and custom comparison software provides a general method for evaluating any DVH-capable system against absolute standards rather than against another numerical implementation. Within the tested scenarios, PlanIQ showed fewer deviations than Pinnacle, and the paper attributes a major fraction of Pinnacle’s failures to a specific implementation inconsistency: the structure volume includes half-slice end-caps, but dose voxels in that added region are apparently omitted from the DVH tally. They further argue that the benchmark suite can identify algorithmic failure modes, not merely measure aggregate agreement. Those claims are well supported by the controlled design and the highly specific error patterns, especially the systematic **Y-gradient** failures and the visible whole-curve stair-stepping in Pinnacle. Where the paper is more speculative is in implying broader generalisability to all clinical circumstances; the actual tests are deliberately synthetic stress tests with simple shapes and linear gradients.

### 7. Implications for reference DVH calculator design

#### 7a. Algorithm and implementation recommendations

A reference DVH engine should treat this paper as strong evidence that **internal consistency of geometric definition and dose tally is non-negotiable**. If a structure volume includes end-capped regions, the DVH accumulation must include dose samples from exactly that same region. The Pinnacle failure mode; volume expanded but dose voxels excluded; drove Dmin errors up to **60%** and propagated into D99, Dmax, D1, and D0.03 cc under superior-inferior gradients. A gold-standard engine should therefore implement a single shared geometric kernel for both volume and dose accumulation, with end-capping policy explicitly parameterised and documented.

The second design lesson is that **3D sampling density and alignment matter**. PlanIQ’s better behaviour was associated with two specific ideas: inclusion of all original dose-grid points in the sampling lattice, and adaptive odd-factor supersampling until a sufficiently dense ROI discretisation (**≥40 000 voxels**) was reached. A reference engine should at minimum support adaptive 3D supersampling with dose-grid-point preservation; preferably, it should go further to exact geometric volume-dose integration or exact fractional voxel intersection where feasible, to avoid remaining sampling artefacts. Surface-aware extrema handling also appears essential: PlanIQ’s contour-point post-processing eliminated observed Dmin/Dmax errors, whereas centre-only sampling failed. Fine dose binning should be default, not optional. The paper suggests that **reproducible dose or volume errors >2%** deserve attention in commissioning, so an internal regression suite for a reference engine should aim for **well below 2%** on analytical benchmarks, especially when fine-contour data remove input discretisation as the dominant uncertainty.

#### 7b. Validation recommendations

This paper’s downloadable benchmark set should be part of any reference calculator’s permanent validation corpus. Critically, this paper provides publicly available downloadable `DICOM RT` objects and the CurveCompare analysis tool (Ref. 15 and 21 in the original paper), making it one of the most directly actionable benchmark resources in the DVH literature. The most informative test pattern is the paper’s three-tier structure: (1) **fine contours + varying dose grid** to isolate dose sampling/interpolation; (2) **matched 1/2/3 mm contour and dose grids** to reflect clinically realistic discretisation; and (3) **whole-curve analysis** with hundreds of sample points, not just endpoint checks. Validation should cover both discrete metrics (`V`, Dmean, Dmin, Dmax, D99, D95, D5, D1, D0.03 cc) and continuous volume-at-dose or dose-at-volume errors.

Several test geometries are especially diagnostic. The **axial cylinder** with superior-inferior gradient exposes end-capping logic. The **rotated cylinder** with coarse axial spacing exposes interslice reconstruction limits and curve errors concentrated in the corners. The **cone** and **rotated cone** probe rapidly changing cross-sectional area, with the axial cone at **3 mm** giving the worst whole-curve Pinnacle error range (**−16.7% to 13.0%**). A robust validation framework should also preserve the paper’s separation of **dose error** and **volume error** the authors explicitly caution against gamma-like hybrid curve metrics because they can hide high local errors at clinically important points such as D95 or D99. For acceptance testing, the paper’s practical recommendation is to scrutinise **anything above 2%**, especially if reproducible across shapes, orientations, or gradient directions.

#### 7c. Extensibility considerations

Although this paper is about cumulative DVH accuracy, it implicitly argues for an engine architecture that exposes the **entire sampled curve**, not only a handful of derived endpoints. Their CurveCompare workflow depends on dense pointwise access to the numerical and analytical curves, and their discussion emphasises that clinical evaluation uses both **dose-at-volume** and **volume-at-dose** quantities. A reference implementation should therefore provide a reusable curve API supporting cumulative and differential histograms, inverse queries, pointwise curve export, and continuous error analysis. That same infrastructure is the natural substrate for extending to gEUD, EUD, DSH/DMH-style metrics, biological overlays, and dosiomics, because all of those depend on trustworthy low-level volume-dose sampling.

The paper also motivates preserving a high-fidelity **surface representation** alongside the voxelised volume. Their Dmin/Dmax findings show that boundary behaviour is not a minor implementation detail; it can materially change reported extrema. For extensibility, the reference engine should therefore maintain both volumetric and surface-aware data structures so that future modules can evaluate surface dose, shell metrics, dose fall-off, and boundary-sensitive radiobiological quantities without retrofitting the core.

#### 7d. Caveats and limitations

The paper’s strongest caveat is that it tests **synthetic, simple shapes** under **axis-aligned linear gradients**, chosen precisely because they are analytically solvable. Those conditions are excellent for diagnosing software failure modes, but they do not reproduce the complexity of clinical IMRT/VMAT dose fields, heterogeneous media, oblique gradients, holes, islands, or multiply connected structures. Coarse-slice cases also partly conflate **input representation error** with DVH algorithm error: for the rotated cylinder, the contour stack itself becomes an inadequate representation of the ideal shape, so not every deviation should be interpreted as a pure software defect. Finally, the comparison is version-specific (Pinnacle v9.8, PlanIQ v2.1), and the paper has a small number of reporting inconsistencies, notably the **X/Z** label switch for the orthogonal gradient and the **PlanIQ Dmean** discrepancy between Table II and text. Those do not undermine the core findings, but a reference calculator should not adopt any threshold or failure interpretation from this paper without reproducing the actual benchmark cases end-to-end.

### 8. Connections to other literature

The following are the key adjacent papers explicitly cited or discussed by Nelms and colleagues as context for this work.

- **Drzymala et al. (1991)** foundational DVH paper; Nelms and colleagues build on the standard DVH construct but shift attention from interpretation to numerical verification.
- **Fraass et al. (1998) (AAPM TG-53)** identified DVH accuracy as part of TPS QA, but without detailed benchmark methods; this paper is essentially a concrete response to that gap.
- **Panitsa et al. (1998)** early DVH QC using simple geometries; Nelms and colleagues argue their own analytical standard is more precise because it is not derived from the same TPS isodose output.
- **Corbett et al. (2002)** demonstrated voxel-size effects on brachytherapy DVHs; Nelms and colleagues extend the voxelisation and sampling problem to external-beam `DICOM RT` validation.
- **Straube et al. (2009)** electronic phantom for DVH QA in multi-institutional trials; Nelms and colleagues add closed-form analytical truth and downloadable benchmark objects.
- **Ebert et al. (2008)/2010** SWAN software enabled consistent cross-TPS DVH comparison, but its authors avoided claiming absolute accuracy; Nelms and colleagues explicitly target analytical verification.
- **Low et al. (1998)** gamma analysis is acknowledged but argued to be less suitable than separate dose- and volume-error analyses for DVH validation.

### 9. Data extraction table

**Table 1. Test 1 summary: constant 0.2 mm contour spacing, variable dose-grid resolution.**

| Parameter | Pinnacle n >3% | Pinnacle range (%) | PlanIQ n >3% | PlanIQ range (%) |
|---|---:|---:|---:|---:|
| Volume | 0 | -2.0 to 1.9 | 0 | -0.4 to 0.9 |
| Dmin | 20 | -7.5 to 2.6 | 0 | 0.0 |
| Dmax | 0 | -1.1 to 1.1 | 0 | 0.0 |
| Dmean | 0 | -1.9 to 0.0 | 0 | -0.1 to 0.7 |
| D99 | 20 | -1.4 to 7.5 | 3 | -1.8 to 5.2 |
| D95 | 12 | -6.6 to 5.2 | 2 | -0.8 to 3.9 |
| D5 | 0 | -1.8 to 1.0 | 0 | -0.4 to 0.8 |
| D1 | 0 | -0.9 to 2.2 | 0 | -0.4 to 0.4 |
| D0.03 cc | 0 | -0.9 to 1.3 | 0 | -0.4 to 0.3 |

**Table 2. Test 2 summary: matched contour spacing and dose-grid resolution at 1, 2, and 3 mm.**

| Parameter | Pinnacle n >3% | Pinnacle range (%) | PlanIQ n >3% | PlanIQ range (%) |
|---|---:|---:|---:|---:|
| Volume | 0 | -2.8 to 2.1 | 1 | -4.2 to 0.6 |
| Dmin | 30 | -7.5 to 60.0 | 0 | 0.0 |
| Dmax | 10 | -5.1 to 1.1 | 0 | 0.0 |
| Dmean | 0 | -1.9 to 0.0 | 0 | 0.0 |
| D99 | 18 | -4.2 to 44.4 | 11 | -4.2 to 22.3 |
| D95 | 19 | -7.8 to 19.5 | 4 | -2.9 to 7.0 |
| D5 | 2 | -3.6 to 5.3 | 0 | -1.7 to 0.5 |
| D1 | 7 | -8.1 to 2.6 | 1 | -3.9 to 0.8 |
| D0.03 cc | 7 | -7.8 to 0.9 | 1 | -4.6 to 0.9 |

**Note:** the main text separately states that PlanIQ Dmean was **0.7%** off for the rotated cylinder in Test 2, which conflicts with Table II’s reported `0.0%` range.

**Table 3. Average whole-curve volume-error statistics across five shapes (Test 3).** Values shown as **minimum to maximum (mean, SD)** in percent volume error.

| Resolution (mm) | Gradient | Pinnacle volume error (%) | PlanIQ volume error (%) |
|---|---|---|---|
| 1 | Superior/inferior | -4.4 to 2.2 (mean -0.3, SD 1.3) | -0.4 to 0.4 (mean 0.0, SD 0.2) |
| 1 | Anterior/posterior | -3.5 to 0.8 (mean -0.8, SD 1.0) | -0.4 to 0.6 (mean 0.1, SD 0.2) |
| 3 | Superior/inferior | -11.2 to 7.9 (mean -0.7, SD 3.5) | -1.5 to 0.6 (mean -0.5, SD 0.5) |
| 3 | Anterior/posterior | -4.1 to 0.8 (mean -1.2, SD 1.1) | -1.5 to 0.8 (mean -0.3, SD 0.6) |

**Table 4. Selected worst-case whole-curve Test 3 datasets.** Values shown as **minimum to maximum (mean, SD)** in percent volume error.

| Dataset | Resolution (mm) | Gradient | Pinnacle volume error (%) | PlanIQ volume error (%) |
|---|---:|---|---|---|
| Cone | 3 | Superior/inferior | -16.7 to 13.0 (mean 0.9, SD 4.4) | -0.7 to 1.4 (mean 0.5, SD 0.2) |
| Rotated cylinder | 3 | Superior/inferior | -9.9 to 5.0 (mean -2.1, SD 3.3) | -4.2 to 0.0 (mean -2.2, SD 1.0) |
| Rotated cylinder | 3 | Anterior/posterior | -5.7 to 0.0 (mean -3.0, SD 1.3) | -4.2 to 0.7 (mean -1.8, SD 1.5) |
| Rotated cone | 3 | Superior/inferior | -13.5 to 8.6 (mean -1.7, SD 3.6) | -0.3 to 1.1 (mean 0.3, SD 0.3) |

### 10. Critical appraisal

**Strengths:** Elegant use of analytically solvable phantoms; strong separation of failure modes through Tests 1-3; unusually detailed reporting of algorithmic behaviour; public benchmark objects and comparison tool; and whole-curve error analysis rather than reliance on a few endpoints.

**Weaknesses:** Only two commercial systems and specific software versions were tested; the clinical generalisability of simple linear-gradient phantoms is limited; coarse-slice cases partly mix true algorithmic error with contour-representation inadequacy; and the paper contains a few minor reporting inconsistencies (gradient-axis labelling, PlanIQ Test-2 Dmean). No formal statistical analysis was performed across the test matrix; error characterisation is descriptive rather than inferential. There is also a potential conflict-of-interest concern because the work received support from Sun Nuclear and one author was a consultant to that company, although the analytical design reduces room for interpretive bias.

**Confidence in findings:** **High** for the core methodological conclusions and for the identified failure modes in the tested software versions, because the comparisons are against closed-form analytical ground truth rather than another numerical implementation.

**Relevance to reference DVH calculator:** **High**. This paper is one of the clearest direct demonstrations that end-capping, surface handling, interslice reconstruction, sampling alignment, and supersampling materially alter DVH outputs, and it provides concrete benchmark cases that a reference-quality calculator should reproduce or surpass.

---

<!-- Source: SUMMARY - Sunderland 2016 - Effects of voxelization on DVH accuracy..md -->

## Sunderland (2016) - Effects of voxelization on dose volume histogram accuracy

### Executive summary

This paper is a focused computational study of how binary structure voxelisation alters downstream dose-volume histogram (DVH) results. Using analytically defined head/head-and-neck and prostate phantom structures, Sunderland and colleagues compared a coarse **2.5 mm** binary labelmap representation against much finer reference voxelisations (**0.05 mm**, **0.15 mm**, or **0.3 mm** depending on structure size). They found that voxelisation-induced DVH error is usually small for large structures, but can become substantial for small structures and for structures located in steep dose gradients. The worst case in the study, the **right optic nerve**, showed only **28.48%** agreement acceptance at **1% dose-to-agreement (DTA)** and **59.39%** at **3% DTA**, despite a seemingly respectable **Dice coefficient of 0.884**.

A key engineering lesson is that geometric overlap metrics alone are not reliable surrogates for DVH fidelity. For example, the **left lens** had the worst Dice score in the study (**0.794**) yet almost perfect DVH agreement (**99.19%** at both 1% and 3% criteria), whereas the **brain stem** had a high Dice (**0.958**) but poor DVH agreement at the stricter criterion (**59.23%** at 1%). This means a reference-quality DVH calculator must validate dosimetric outputs directly rather than infer adequacy from structure overlap measures.

For a benchmark-grade open-source DVH engine, this paper strongly supports moving beyond binary centre-inclusion masks toward **fractional occupancy** or other **sub-voxel integration** methods. It also motivates validation datasets that deliberately stress small structures, steep gradients, sharp geometric features, and grid-alignment sensitivity. The main caveat is that the study changes both structure and dose resolution together, so the reported discrepancies reflect a combined effect rather than purely isolated structure voxelisation error.

### 1. Bibliographic record

**Authors:** Kyle Sunderland, Csaba Pinter, Andras Lasso, and Gabor Fichtinger
**Title:** *Effects of voxelization on dose volume histogram accuracy*
**Journal:** *Proceedings of SPIE: Medical Imaging 2016: Image-Guided Procedures, Robotic Interventions, and Modeling* (Vol. 9786, article 97862O)
**Year:** 2016
**DOI:** [10.1117/12.2216310](https://doi.org/10.1117/12.2216310)
**Open access:** Yes (public author-hosted PDF available on Queen’s University infrastructure; licence [DETAIL NOT REPORTED])

### 2. Paper type and scope

**Type:** Original research (conference proceeding).
**Domain tags:** D1 Computation.

**Scope statement:** This paper studies how converting continuous anatomical structures into binary voxel labelmaps changes downstream DVH results. Using analytically defined phantom structures, the authors compare a coarse **2.5 mm** “clinical” voxelisation against finer reference voxelisations (**0.05 mm**, **0.15 mm**, or **0.3 mm**) and show that the resulting DVH disagreement is small for large structures but can be severe for small structures and structures placed in steep dose gradients.

### 3. Background and motivation (150-300 words)

The paper addresses a ubiquitous but often under-analysed step in radiotherapy planning: delineated structures are typically created as contour sets, but most planning and evaluation algorithms operate on voxelised binary masks. The authors note that this contour-to-labelmap conversion is mandatory in treatment planning systems (TPS), yet different implementations can produce different structure volumes. For large structures the effect may be small, but for small organs at risk and targets represented by only a small number of voxels, the information loss from voxelisation can be substantial. They specifically highlight small head-and-neck organs such as the optic chiasm and also the rectum as examples where the problem can matter clinically, especially in regions with high dose gradient.

The motivation is directly DVH-centric. The authors frame DVH as a core plan-evaluation metric, important both for clinician review and for automated or inverse planning workflows. They explicitly argue that if voxelisation distorts the effective structure volume or boundary location, then the computed DVH can be wrong even if the dose engine itself is correct, with the consequence that a plan may appear acceptable on paper while being supported by an inaccurate DVH. This paper therefore targets a specific gap: isolating the contribution of structure voxelisation to DVH error using controlled analytical phantoms rather than patient contours alone.

### 4. Methods: detailed technical summary (400-800 words)

This was an **analytical/simulation phantom study**, not a patient or multi-institutional dataset study. The structures were defined as **implicit functions**, treated as the “ground truth analytical representation” with effectively infinite spatial resolution. The authors constructed anatomical approximations from simple primitives such as **spheres, cones, and cylinders**, combined with Boolean add/subtract operations to create more complex target and OAR shapes. An important methodological nuance is that these Boolean combinations introduce **infinitely sharp edges** at intersections; the authors explicitly state that such edges can never be exactly voxelised at any finite resolution, so the voxelised structures are expected to have volumes slightly larger than the original implicit objects. This means the study isolates voxelisation error from a continuous 3D description, but it also bakes in a geometry class with especially hostile boundary conditions.

The evaluated structure set appears to comprise **19 structures** across a **head/head-and-neck phantom** and a **prostate phantom**, as listed in Table 1: head GTV/CTV/PTV, bilateral lenses, bilateral orbits, bilateral optic nerves, optic chiasm, brain stem, brain, body, prostate GTV/CTV/PTV, bilateral femoral heads, and rectum. Exact structure volumes in cc are **[DETAIL NOT REPORTED]**. Because the structures were analytic 3D objects rather than contour stacks, several clinically relevant contour-processing steps are **not tested here**: slice spacing effects, contour interpolation between planes, polygon filling, and end-capping of open contours are effectively bypassed. That makes the paper valuable for isolating voxelisation from a continuous geometry, but less representative of full `RTSTRUCT` import pipelines.

Binary labelmaps were created by **sampling the implicit function at the centre of each voxel**. Voxels whose centre evaluated to **≤ 0** were classified as inside the structure; all others were outside. This is a strict **binary centre-inclusion rule** with **no partial-volume weighting** and no anti-aliasing. The coarse labelmap used **cubic 2.5 mm voxels**. The reference labelmaps used **0.05 mm**, **0.15 mm**, or **0.3 mm** voxels, with larger structures assigned larger “high-resolution” voxels to keep memory demands manageable. Thus, the reference was not a single common isotropic baseline; it was structure-dependent. Small structures such as lenses, orbits, optic nerves, and optic chiasm used **0.05 mm** reference voxels; many targets and pelvic structures used **0.15 mm** brain and body used **0.3 mm**. Supersampling is not reported as part of the evaluated method, and the future-work section instead proposes fractional labelmaps as an alternative to “current use of binary labelmaps and supersampling.”

For geometric comparison, the authors used **Dice similarity coefficient** and **Hausdorff distance**. To compute Dice, the low-resolution labelmap was resampled to the high-resolution voxel spacing using **nearest-neighbour interpolation**, preserving binarity, after which true positive, false positive, and false negative voxels were counted. Hausdorff distance was computed from sets of **border voxels** in 3D, taking the maximum of the two directed nearest-neighbour distances. No other surface-distance metrics (mean surface distance, 95% Hausdorff, etc.) were reported.

For dosimetry, the authors created a **simulated dose volume** rather than using a commercial dose engine. The plan contained **multiple beams** Figure 4 specifies a **dose plan of five simulated beams**, with **source-axis distance 100 cm** and **focal region 10 cm²**. Dose generation used a **clinically observed tissue phantom ratio** plus **clinical cross-plane and in-plane dose profiles**. The paper explicitly says these dose volumes were “not generated to be clinically perfect” but were considered “qualitatively sufficient” for the evaluation. Critically, the **dose voxels were sampled at the same resolution as the corresponding labelmaps**, so DVH differences reflect a **combined change in structure voxelisation and dose discretisation**, not purely structure voxelisation in isolation. The named dose algorithm, beam energy, heterogeneity correction method, density handling, and absolute dose normalisation are **[DETAIL NOT REPORTED]**.

DVH comparison used the algorithm of **Ebert et al. (2010)** to compute an **agreement acceptance percentage**, defined in the paper as the percentage of DVH bins that satisfy a chosen threshold. The authors used two threshold sets: **1% volume-difference plus 1% dose-to-agreement (DTA)**, and **3% volume-difference plus 3% DTA**. The exact DVH bin width, number of bins, dose interpolation scheme for DVH sampling, and whether the histogram was stored as cumulative or differential are **[DETAIL NOT REPORTED]** the figures show monotonic fractional-volume-versus-dose curves consistent with **cumulative DVH [INFERRED FROM FIGURES]**. No formal statistical hypothesis tests, confidence intervals, or p-values were reported. Implementation was done in SlicerRT on the 3D Slicer platform, using **Python scripted modules**, **C++ loadable modules**, and VTK implicit-function libraries.

### 5. Key results: quantitative (300-600 words)

The central result is that coarse binary voxelisation had little dosimetric impact for many large structures but produced substantial DVH disagreement for selected small structures and for structures in steep gradients. Across Table 1, **Hausdorff distance** was comparatively uninformative: it lay between **2.729 mm** and **3.402 mm** for 18 of 19 structures, with only the **body** standing out at **5.555 mm**. **Dice** varied more meaningfully, from **0.794** (left lens) to **0.990** (body). However, the most relevant endpoint, DVH agreement acceptance, spanned from **28.48%** to **100.0%** at **1% DTA**, and from **53.66%** to **100.0%** at **3% DTA**. The authors’ headline worst cases were **28.48%** and **53.66%**, demonstrating that even a relaxed 3% criterion did not eliminate major disagreement in some small/high-gradient cases.

Large or relatively low-gradient structures generally showed near-perfect agreement. Examples include **brain** (**Dice 0.987**, **100.0%/100.0%** acceptance at 1%/3%), **body** (**Dice 0.990**, **Hausdorff 5.555 mm**, **100.0%/100.0%**), **left femoral head** (**0.946**, **100.0%/100.0%**), **right femoral head** (**0.953**, **100.0%/100.0%**), and prostate **GTV/CTV/PTV** (**Dice 0.952-0.958**, **99.50%/100.0%** for all three). Head target structures were also highly concordant: head **CTV** and **PTV** both achieved **100.0%/100.0%**, while head **GTV** was **97.77%/100.0%**.

The failures were concentrated in small structures and/or structures affected by high gradients. The **right optic nerve** was the worst structure in the study, with **Hausdorff 3.229 mm**, **Dice 0.884**, but only **28.48%** acceptance at **1% DTA** and **59.39%** at **3% DTA**. Other poor performers were **right lens** (**Dice 0.808**, **51.22%/53.66%**), **right orbit** (**0.929**, **50.42%/76.47%**), **left orbit** (**0.929**, **75.00%/79.84%**), **brain stem** (**0.958**, **59.23%/100.0%**), and **rectum** (**0.925**, **80.20%/100.0%**). These examples show two distinct patterns: some structures remain poor even after relaxing to 3% criteria, while others improve dramatically when the tolerance is loosened.

A particularly important qualitative result is that **geometric agreement did not map cleanly to dosimetric agreement**. The **left lens** had the worst Dice in the table (**0.794**) but almost perfect DVH acceptance (**99.19%/99.19%**), whereas the **brain stem** had excellent Dice (**0.958**) but poor **1%** DVH acceptance (**59.23%**). Likewise, the **body** had the **largest Hausdorff distance** (**5.555 mm**) yet perfect DVH agreement. This means that neither Dice nor Hausdorff alone is a reliable surrogate for DVH fidelity; local dose gradient matters strongly. Figure 6 reinforces this by showing two artefact modes in low-resolution DVH: a **staircase-like quantisation pattern** and **consistent offset between curves**. From the reported Table 1 values, the seven **0.05 mm** reference structures average **69.6%** acceptance at 1% criteria and **79.4%** at 3% criteria, versus **93.6%** and **100.0%** for the ten **0.15 mm** structures [reviewer calculation from Table 1]. No formal statistical significance testing was performed.

### 6. Authors' conclusions (100-200 words)

The authors conclude that voxel size is an important determinant of DVH accuracy and should be considered relative to the total size of the structure. They argue that voxelisation error has only a small effect for large structures or low-gradient regions, but can become severe for small structures and steep gradients, potentially corrupting DVH-derived V and D metrics used for plan assessment. They further suggest that such errors could allow a suboptimal plan to be accepted, particularly in inverse-planning settings that optimise against DVH goals.

Those conclusions are **well supported** in the narrow sense that the reported structure-level acceptance percentages plainly show large DVH discrepancies under coarse sampling. The stronger clinical extrapolation about acceptance of suboptimal plans is **plausible but not directly demonstrated**, because the study did not re-optimise plans, compare commercial TPS outputs, or quantify endpoint-specific changes such as Dmean, Dmax, D0.03cc, or Vx.

### 7. Implications for reference DVH calculator design (300-600 words)

#### 7a. Algorithm and implementation recommendations

A reference DVH engine should **not rely on binary centre-inclusion voxelisation as its primary structure representation**, because this paper shows that a centre-sampled binary mask at **2.5 mm** can degrade DVH agreement to **28.48%** at 1% criteria and **53.66%** at 3% criteria for vulnerable structures. The minimum design lesson is to support **fractional occupancy** or an equivalent sub-voxel integration method at structure boundaries. The authors’ own future-work proposal of **fractional labelmaps** is directly aligned with this.

The engine should also **decouple structure discretisation from dose discretisation**. In this study the dose volume was sampled at the same resolution as the labelmap, so the reported DVH error is a combined effect. A benchmark-grade calculator should be able to hold the dose grid fixed while refining only the structure integration, and vice versa. Finally, the paper strongly suggests that **geometric QA metrics are insufficient** as sole validators: **left lens Dice 0.794 with 99.19% DVH agreement**, **body Hausdorff 5.555 mm with 100% DVH agreement**, and **right optic nerve Dice 0.884 with only 28.48% DVH agreement** show that boundary overlap and DVH accuracy are related but non-equivalent objectives.

#### 7b. Validation recommendations

This paper motivates an excellent **stress-test suite** for a reference calculator. At minimum, include analytic phantoms made from **spheres, cones, cylinders, and Boolean composites** explicit small-OAR analogues such as **lens**, **optic nerve**, and **optic chiasm** and medium structures in gradient regions such as **brain stem** and **rectum**. Reproduce comparisons against a coarse **2.5 mm** rasterisation and use both **1%** and **3%** volume-difference/DTA acceptance metrics as reported here. The key failure cases to reproduce are **right optic nerve**, **right lens**, **right orbit**, **brain stem**, and **rectum**.

For a modern benchmark, go beyond the paper by varying **grid phase** as well as voxel size. A centre-inclusion algorithm is inherently sensitive to sub-voxel shifts of the structure relative to the grid origin, even though this paper did not explicitly study that. Validation should also report not only Dice/Hausdorff and whole-curve acceptance but clinically recognisable endpoints such as Dmean, Dmax, D0.03cc, D95, and Vx, because the paper shows whole-curve disagreement but does not quantify endpoint error. The implementation environment (SlicerRT, 3D Slicer, VTK) provides a named reproduction stack, but direct release of the exact study phantoms/modules is **[DETAIL NOT REPORTED]**.

#### 7c. Extensibility considerations

The explicit future-work proposal is **fractional labelmaps**, with voxel values representing the fraction of the voxel occupied by the structure and potentially stored as **0-255** integers instead of binary 0/1. For a reference calculator, that argues for internal support for **continuous occupancy fields**, not just Boolean masks. Such a representation naturally supports more accurate DVH, but it also creates a clean bridge to **differential DVH**, **dose-surface histogram (DSH)**, **dose-mass histogram (DMH)** if density is available, **EUD/gEUD**, radiobiological overlays, and uncertainty-aware or probabilistic histogram variants.

Architecturally, the calculator should store or expose both the **original continuous geometry** (surface mesh, contour stack, or signed-distance-like representation) and the **derived occupancy map**, along with provenance of rasterisation settings. That would permit convergence testing, reproducible re-computation, and later extraction of dosiomics features without silently locking the workflow to a single binary mask. This paper is small, but it clearly motivates that direction.

#### 7d. Caveats and limitations

Several limitations constrain generalisation. First, this is **not** an evaluation of actual patient `RTSTRUCT` data or commercial TPS implementations; it studies analytic phantoms. Second, the coarse comparator is **2.5 mm isotropic**, which was called “traditional clinical” by the authors but does not span all contemporary planning/image sampling scenarios. Third, the dose model was only “qualitatively sufficient”; named algorithm, energy, and heterogeneity handling were **[DETAIL NOT REPORTED]**. Fourth, because dose and structure resolution changed together, the reported DVH differences cannot be attributed solely to structure voxelisation.

Fifth, the implicit-function phantoms include **infinitely sharp Boolean edges**, which are useful as stress tests but are not a perfect analogue of clinical anatomy. Sixth, the study does not report actual structure volumes, voxel counts, or local gradient magnitudes, so the error cannot be parameterised in cc or Gy/mm. Finally, the reference DVH is still voxel-based rather than exact analytic dose integration over the continuous structure, so even the baseline is an approximation. A reference-quality calculator should therefore relax these assumptions rather than copy them.

### 8. Connections to other literature

- **Fraass et al. (1998)** foundational TPS QA guidance that treats DVH as an important evaluation endpoint; Sunderland et al. effectively examine one specific QA failure mode within that broader framework.
- **Peter et al. (2000)** methodologically adjacent analytical-versus-voxelised phantom work in radiological imaging; Sunderland et al. adapt the same general logic to DVH accuracy rather than Monte Carlo imaging accuracy.
- **Zaidi and Tsui (2009)** provides background on computational anthropomorphic phantoms; Sunderland et al. use analytically defined phantom structures in that tradition.
- **Ebert et al. (2010)** directly underpins the DVH comparison metric used here; Sunderland et al. narrow the broader inter-TPS variability problem to one mechanistic contributor, voxelisation.
- **Pinter et al. (2012)** describes the SlicerRT platform in which the authors implemented their analysis modules.
- **Li et al. (2013)** supports the claim that DVH can actively drive automated replanning/optimisation, strengthening the downstream importance of voxelisation-induced DVH error.

### 9. Data extraction table

Extracted from Table 1 of the paper. All rows compare the stated **reference voxel size** against a **2.5 mm** clinical voxel size.

| Structure | Ref voxel (mm) | Hausdorff distance (mm) | Dice | Agreement acceptance % (1% DTA) | Agreement acceptance % (3% DTA) |
|---|---:|---:|---:|---:|---:|
| GTV (Head Phantom) | 0.150 | 2.970 | 0.946 | 97.77 | 100.0 |
| CTV (Head Phantom) | 0.150 | 2.783 | 0.970 | 100.0 | 100.0 |
| PTV (Head Phantom) | 0.150 | 2.920 | 0.956 | 100.0 | 100.0 |
| Left Lens | 0.050 | 2.861 | 0.794 | 99.19 | 99.19 |
| Right Lens | 0.050 | 2.901 | 0.808 | 51.22 | 53.66 |
| Left Orbit | 0.050 | 3.021 | 0.929 | 75.00 | 79.84 |
| Right Orbit | 0.050 | 3.021 | 0.929 | 50.42 | 76.47 |
| Left Optical Nerve | 0.050 | 3.085 | 0.866 | 90.24 | 94.51 |
| Right Optical Nerve | 0.050 | 3.229 | 0.884 | 28.48 | 59.39 |
| Optical Chiasm | 0.050 | 2.941 | 0.897 | 92.56 | 93.02 |
| Brain Stem | 0.150 | 3.015 | 0.958 | 59.23 | 100.0 |
| Brain | 0.300 | 2.858 | 0.987 | 100.0 | 100.0 |
| Body | 0.300 | 5.555 | 0.990 | 100.0 | 100.0 |
| GTV (Prostate Phantom) | 0.150 | 2.960 | 0.952 | 99.50 | 100.0 |
| CTV (Prostate Phantom) | 0.150 | 2.739 | 0.955 | 99.50 | 100.0 |
| PTV (Prostate Phantom) | 0.150 | 2.729 | 0.958 | 99.50 | 100.0 |
| Left Femoral Head | 0.150 | 3.021 | 0.946 | 100.0 | 100.0 |
| Right Femoral Head | 0.150 | 3.021 | 0.953 | 100.0 | 100.0 |
| Rectum | 0.150 | 3.402 | 0.925 | 80.20 | 100.0 |

Note: “Agreement acceptance %” is the percentage of DVH bins meeting the stated criterion; the exact DVH bin width and total number of bins are **[DETAIL NOT REPORTED]**.

### 10. Critical appraisal (100-200 words)

**Strengths:** The study isolates an important computational failure mode with a clean analytic-phantom design, reports structure-level quantitative results rather than only narrative conclusions, and uses an implementation stack (SlicerRT/3D Slicer) that is technically reproducible. The table is especially useful because it shows that poor DVH agreement can coexist with fairly ordinary Dice/Hausdorff values.
**Weaknesses:** It is brief, uses no patient data, no commercial TPS, no formal statistics, no exact analytic DVH reference, and it confounds structure voxelisation with dose-grid resolution by sampling both at the same spacing. It also omits endpoint-specific dosimetric errors (Dmean, Dmax, Vx, etc.) and exact structure volumes.
**Confidence in findings:** Medium ;  the effect sizes are large and the methodology is transparent enough to trust the qualitative conclusion, but the simplifications limit external validity.
**Relevance to reference DVH calculator:** High ;  despite its simplicity, the paper directly motivates sub-voxel occupancy handling, gradient-aware validation, and the need to validate DVH itself rather than relying on geometry surrogates alone.

---

<!-- Source: SUMMARY - Snyder 2017 - Investigating the dosimetric effects of grid size on dose calculation accuracy using VMAT in spine stereotactic radiosurgery.md -->

## Snyder (2017) - Investigating the dosimetric effects of grid size on dose calculation accuracy using volumetric modulated arc therapy in spine stereotactic radiosurgery

### Executive summary

This paper retrospectively recalculated **50** single-fraction VMAT spine SRS plans using AAA v11 at **1.0 mm**, **1.5 mm**, and **2.5 mm** isotropic dose-grid spacing to quantify how dose-calculation grid size changes reported target and spinal cord DVH metrics. The clinically dominant finding was that spinal cord subvolume doses were highly grid-sensitive in steep target-cord gradients: relative to **1.0 mm**, the **2.5 mm** grid increased mean Cord_D10% from **8.19 Gy** to **9.25 Gy** (**+13.0%**) and mean Cord_D0.03cc from **10.50 Gy** to **11.52 Gy** (**+10.1%**), with worst-case increases of **23.2%** and **22.7%**, respectively. By contrast, mean PTV coverage changes were smaller, generally around **<2-3%**, although statistically significant.

The study therefore shows that coarse grids can materially distort small-volume serial-organ metrics even when target metrics appear comparatively stable. The sharpest discrepancies occurred in the shortest fall-off cases, with distance-to-fall-off (DTF) between the **90%** and **50%** isodose lines around **1.5-2 mm**. Physical verification with EBT3 film and cross-system DVH comparison (Eclipse versus Velocity) suggested that **1.0 mm** better represented the high-gradient cord interface, while **1.5 mm** gave the best overall compromise between dosimetric fidelity and calculation time. Mean calculation time rose from **1 min 53 s** at **2.5 mm** to **11 min 36 s** at **1.0 mm**.

For a reference DVH calculator, the paper is highly relevant because it isolates a core benchmarking failure mode: small serial-OAR endpoints such as D0.03cc and D10% can change by clinically meaningful amounts purely because of dose-grid resolution and DVH extraction behaviour. It argues strongly for native-grid-aware processing, explicit sub-voxel volume handling, gradient-sensitive validation cases, and caution when benchmarking against TPS-reported DVHs in spine SRS-like geometries.

### 1. Bibliographic record

- **Authors:** Karen Chin Snyder, Manju Liu, Bo Zhao, Yimei Huang, Ning Wen, Indrin J. Chetty, M. Salim Siddiqui
- **Title:** Investigating the dosimetric effects of grid size on dose calculation accuracy using volumetric modulated arc therapy in spine stereotactic radiosurgery
- **Journal:** Journal of Radiosurgery and SBRT
- **Year:** 2017; Volume/Issue: 4(4); Pages: 303-313
- **DOI:** Not reported / not readily identifiable in the article PDF or the PMC/PubMed records reviewed. PMCID: [PMC5658825](https://pmc.ncbi.nlm.nih.gov/articles/PMC5658825/)
- **Open access:** Yes (PMC free full-text article)

### 2. Paper type and scope

**Type:** Original research.
**Domain tags:** D1 Computation | D2 Commercial systems.
**Scope statement:** This paper retrospectively recalculates **50** VMAT spine SRS plans with AAA v11 at **1.0 mm**, **1.5 mm**, and **2.5 mm** isotropic dose-grid spacing, then compares target coverage, spinal cord subvolume metrics, dose fall-off, film agreement, calculation time, and inter-system DVH differences (Eclipse versus Velocity). Its importance for DVH work is that it directly probes a failure mode central to reference-quality benchmarking: small serial OAR subvolumes (D0.03cc, D10%) embedded in millimetre-scale gradients can change materially when the dose grid and DVH sampling method change.

### 3. Background and motivation

The paper addresses a specific gap left by earlier grid-size literature. Prior work had suggested that **2.5 mm** dose-grid spacing was generally sufficient for IMRT dose calculation and that **3 mm** could be practical for lung stereotactic arc therapy. However, those recommendations arose from settings with broader penumbrae, different treatment geometries, and less extreme serial-organ constraints than modern spine SRS. In spine SRS, the spinal cord is the dose-limiting structure and may lie immediately adjacent to, or even be partly enveloped by, epidural disease. The relevant clinical quantities are therefore not only target coverage metrics, but very small-volume cord endpoints such as Cord_D10% and Cord_D0.03cc, evaluated in steep target-cord gradients.

The authors argue that modern image guidance and delivery hardware have shifted the balance. With CBCT and 6-DoF couches, localisation uncertainty is reported in the **0.2-0.6 mm** range, while HD-MLC/FFF combinations can produce penumbrae on the order of **2-2.5 mm**. Under those conditions, the default AAA calculation grid of **2.5 mm** may be too coarse, especially when dose is sampled inside small structures after interpolation and re-sampling. The paper is therefore motivated by a combined dosimetric and computational question: how much of the reported cord sparing and target coverage in VMAT spine SRS depends on the chosen dose grid, and how much additional uncertainty arises from the TPS DVH implementation itself? For a reference DVH calculator, this is directly relevant because it exposes where grid resolution, structure discretisation, and DVH extraction become inseparable in high-gradient clinical plans.

### 4. Methods: detailed technical summary

This was a **retrospective analytical/recalculation study** of **50** previously treated spine radiosurgery patients from a single institution. The cohort comprised **36 thoracic**, **1 cervical**, and **13 lumbar** cases. All were treated in **1 fraction**, with prescriptions of **12 Gy**, **16 Gy**, or **18 Gy** to the **90% isodose line**. Planning CT used **2 mm slice thickness** and a **600 mm** field of view, yielding **1.12 × 1.12 mm** in-plane pixel resolution. CT was rigidly fused to contrast-enhanced axial `T1` and `T2` MRI using a mutual-information algorithm in Eclipse; target and cord were contoured on MRI and verified on CT. The structures were drawn as **high-resolution segments**. The mean target volume was **45.19 cc** (range **8.62-164.95 cc**), and the mean minimum target-to-cord distance was **0.77 mm** (range **0-3.4 mm**). Counting the entries in Table 1 gives target classes **A/B/C = 12/21/17** and epidural involvement **Yes/No = 26/24**.

Planning and dose calculation were performed in Eclipse v11 using AAA v11. All plans used **VMAT** with **two partial arcs** spanning posterior-oblique start/stop angles (**215°-145°**) to avoid couch rails. Treatments were planned and delivered on a `Varian EDGE` equipped with **HD-MLC**, using either **6 MV FFF** or **10 MV FFF** beams. Plans were optimised so that prescription dose covered **≥95%** of the PTV. The partial spinal cord constraint for clinical treatment was `Cord_D10% ≤ 10 Gy` and `Cord_D0.03cc ≤ 14 Gy`, where the “partial cord” was defined as cord visible on MRI extending **6 mm superior and 6 mm inferior** to the PTV. Each clinical plan was then **recalculated with fixed MU** at **1.0 mm**, **1.5 mm**, and **2.5 mm** isotropic grid size, giving **150** recalculated plans. Because the study was retrospective, the original clinical plans had not all been evaluated on the same grid: **17** were originally calculated at **2.5 mm**, **14** at **1.5 mm**, and **19** at **1.0 mm**. This is important because recalculation at a different grid could move a previously acceptable cord metric above tolerance.

Plan evaluation used PTV metrics `PTV_D99%`, `PTV_D95%`, `PTV_D5%`, and `PTV_D0.03cc`; spinal cord metrics Cord_D10% and Cord_D0.03cc; and a geometric gradient descriptor, the **distance-to-fall-off (DTF)** between the **90%** and **50%** isodose lines measured **in the axial plane at isocentre**. Statistical comparison used the **paired Student’s t-test**, with significance defined as `p < 0.05`. However, many DVH implementation details that matter to a reference engine were **not reported**: cumulative versus differential DVH construction is **[DETAIL NOT REPORTED]** (though the metric conventions imply cumulative use), dose bin width is **[DETAIL NOT REPORTED]**, contour rasterisation/inclusion rule is **[DETAIL NOT REPORTED]**, interpolation kernel is **[DETAIL NOT REPORTED]**, supersampling is **[DETAIL NOT REPORTED]**, end-capping is **[DETAIL NOT REPORTED]**, and partial-volume weighting is **[DETAIL NOT REPORTED]**. Likewise, no independent analytical or Monte Carlo 3D reference dose was used.

For physical verification, each original plan was delivered to **Gafchromic EBT3** film placed axially at the centre of a **Brainlab acrylic slab phantom** (**30 × 30 × 10 cm**, composed of two **30 × 30 × 5 cm** slabs). Because recalculated plans used fixed MU, delivery parameters were identical across grid sizes. Film calibration used **9** dose steps spanning **2.5-23.3 Gy**, depending on prescription. Films were scanned on an `Epson Expression 10000XL` at **150 dpi**, approximately **16 hours** post-irradiation. Dose conversion and gamma were performed with **in-house software**. The comparison dose plane was recalculated on the slab phantom and exported at **0.5 mm** resolution. Gamma used **absolute dose analysis** with **3% dose / 1 mm DTA** whether the 3% normalisation was global or local is **[DETAIL NOT REPORTED]**. Film dosimetry uncertainty for the green channel was approximately **1.7%**. They also recorded film-versus-plan isocentre dose difference as a point metric, though not as a formal absolute dosimetry endpoint.

Calculation time was recorded on a **distributed calculation framework** with **13** framework agent servers: **10** servers with **64 GB RAM, Intel Xeon E5-2690, 16 cores** and **3** servers with **64 GB RAM, Intel Xeon E5-2680, 24 cores**. To assess DVH-algorithm uncertainty separately from dose-grid effects, the authors exported a **subset of 10 cases** with the shortest DTFs (**1.5-2 mm**) to `Velocity v3.2.0` and re-evaluated the same dosimetric parameters there. This comparison used the same dose planes and structures, but again the internal Velocity DVH implementation details were **[DETAIL NOT REPORTED]**. A notable internal inconsistency is that Table 3’s caption says “all fifty cases”, whereas the methods clearly state a 10-case subset.

### 5. Key results: quantitative

Across all 50 plans, all grid-size comparisons for the reported dosimetric indices were statistically significant at **`p < 0.001`**. The key cord result is that coarser grids systematically inflated reported spinal cord dose relative to the **1.0 mm** calculation. Mean Cord_D10% was **8.19 ± 1.24 Gy** at **1.0 mm**, **8.83 ± 1.36 Gy** at **1.5 mm**, and **9.25 ± 1.43 Gy** at **2.5 mm**. Mean Cord_D0.03cc was **10.50 ± 1.66 Gy**, **11.15 ± 1.68 Gy**, and **11.52 ± 1.61 Gy**, respectively. Relative to **1.0 mm**, that corresponds to approximately **+7.8%** (D10%) and **+6.4%** (D0.03cc) at **1.5 mm**, and **+13.0%** and **+10.1%** at **2.5 mm**. The worst individual-case discrepancies between **2.5 mm** and **1.0 mm** were **23.2%** for Cord_D10% and **22.7%** for Cord_D0.03cc, equivalent to absolute differences of **1.8 Gy** and **2.0 Gy**. For a single-fraction spine SRS context, those are clinically material differences.

The target metrics behaved differently. Mean `PTV_D99%` / `PTV_D95%` / `PTV_D5%` / `PTV_D0.03cc` at **1.0 mm** were **17.03 ± 1.24 Gy / 17.72 ± 1.20 Gy / 20.09 ± 1.54 Gy / 20.96 ± 1.58 Gy**. At **1.5 mm**, these became **17.31 ± 1.25 Gy / 18.11 ± 1.20 Gy / 20.34 ± 1.54 Gy / 21.07 ± 1.57 Gy**, i.e. apparent increases of about **1.7%**, **2.2%**, **1.3%**, and **0.5%** relative to **1.0 mm**. At **2.5 mm**, they were **16.93 ± 1.22 Gy / 17.84 ± 1.17 Gy / 20.05 ± 1.52 Gy / 20.65 ± 1.56 Gy**. Thus, the **1.5 mm** grid produced the highest apparent PTV coverage and hotspot, whereas the direct **1.0 vs 2.5 mm** PTV differences were generally **<1%** in mean coverage terms despite statistical significance. This is a useful reminder that clinically small PTV changes can coexist with much larger serial-OAR differences. The reported DTF sharpened with finer grid: **2.52 ± 0.54 mm** at **1.0 mm**, **2.83 ± 0.58 mm** at **1.5 mm**, and **3.30 ± 0.64 mm** at **2.5 mm**. Relative to **1.0 mm**, DTF increased by **0.31 ± 0.2 mm** at **1.5 mm** and **0.78 ± 0.3 mm** at **2.5 mm**. Figure 2 further shows that the largest relative cord-dose errors clustered in the shortest-gradient cases, particularly **DTF 1.5-2 mm**, with the discrepancy falling as DTF lengthened toward **3-4 mm**.

The inter-system DVH comparison (Velocity - Eclipse) was modest on average but non-negligible in worst cases. Mean differences were generally within **±1.2%**. For the **1.0 mm** grid, mean `PTV_D99%` difference was **-1.2%**, and mean Cord_D0.03cc difference was **-0.5%**, but the reported range for Cord_D0.03cc extended to **-5.9%**. For **1.5 mm**, mean Cord_D0.03cc difference was **-0.8%** for **2.5 mm**, **+0.3%**. Film analysis showed the highest global gamma pass rate at **1.5 mm**: **95.9 ± 5.4%**, versus **94.3 ± 6.0%** at **1.0 mm** and **93.6 ± 5.4%** at **2.5 mm** using **3%/1 mm** criteria. However, the line-profile figure showed **better agreement for 1.0 mm in the high-gradient cord region**, while `1.0 mm` appeared more non-uniform in the high-dose PTV region. Mean film-plan isocentre dose difference was **1.22 ± 1.8%** at **1.0 mm**, **-0.06 ± 2.03%** at **1.5 mm**, and **0.40 ± 2.09%** at **2.5 mm**. Mean calculation times were **11 min 36 s ± 2 min 48 s** at **1.0 mm**, **4 min 30 s ± 47 s** at **1.5 mm**, and **1 min 53 s ± 32 s** at **2.5 mm** equivalently, **1.5 mm** and **2.5 mm** were about **61%** and **84%** faster than **1.0 mm**, respectively.

### 6. Authors' conclusions

The authors conclude that **1.0 mm** grid size provides the most accurate representation of dose delivered to the spinal cord in VMAT spine SRS, primarily because it yields lower cord DVH values, steeper reported fall-off, and better line-profile agreement in the highest-gradient region adjacent to the cord. They also conclude that this finer grid comes at a cost: it produces a less uniform or “mottled” high-dose PTV region, slightly poorer global film gamma performance, and a major increase in calculation time. Their practical recommendation is therefore that **1.5 mm** may be the best clinical compromise, balancing cord-dose accuracy, target coverage, and computational efficiency.

That interpretation is partly well supported and partly extrapolative. The data clearly support the statement that coarser grids inflate reported cord dose and flatten apparent gradient. The claim that **1.0 mm** is the “most accurate” is more tentative, because the study lacks an independent 3D patient-specific ground truth; its physical validation is limited to **2D film in a homogeneous slab phantom**, plus qualitative line-profile agreement. Likewise, the recommendation of **1.5 mm** as a general compromise is sensible but not universally validated across other dose algorithms, MLC models, or spine SRS workflows.

### 7. Implications for reference DVH calculator design

**7a. Algorithm and implementation recommendations**
A reference DVH calculator should **not** accept **2.5 mm** as a benchmark-resolution standard for spine SRS-like high-gradient cases. In this paper, moving from **1.0 mm** to **2.5 mm** changed mean cord D10% by **13.0%** and mean D0.03cc by **10.1%**, with worst-case deviations of **23.2%** and **22.7%**. For benchmarking, the calculator should support evaluation on **1.0 mm or finer dose grids**, or implement robust sub-voxel integration when the native grid is coarser. Partial-volume handling is essential: `0.03 cc` corresponds to roughly **30 voxels** at **1.0 mm**, **8.9 voxels** at **1.5 mm**, but only about **1.9 voxels** at **2.5 mm** [inference from the reported isotropic voxel sizes]. Whole-voxel inclusion rules are therefore unacceptable for serial-OAR hotspot metrics. The implementation should also preserve **native-grid evaluation**, make interpolation explicit, support **grid-shift sensitivity analysis**, and include **spatial gradient tools** such as line profiles and DTF, because global gamma alone did not capture the clinically relevant cord-edge behaviour seen here.

**7b. Validation recommendations**
A useful validation suite should include synthetic and/or curated clinical cases with **PTV-cord separations of 0-3.4 mm**, **DTF values around 1.5-4 mm**, and small serial-OAR subvolumes such as D0.03cc and D10%. The most revealing benchmarks will be those in which the physical dose field is identical but the sampling grid changes, because this paper’s failure mode is primarily a sampling/resolution problem. Add **sub-voxel grid-offset tests**, since the authors explicitly highlight the importance of dose-grid placement relative to the structure. Also include **cross-platform DVH validation** using identical RTDOSE/RTSTRUCT inputs, because this study found average Velocity-Eclipse differences generally within **1.2%** but worst-case Cord_D0.03cc discrepancies up to **5.9%**. For acceptance criteria, this paper suggests a hierarchy rather than one blanket tolerance: expect very tight agreement for bulk PTV metrics, but scrutinise any **>5%** difference in tiny high-gradient cord metrics, especially when DTF is **<2 mm**. No public dataset was released, so an open reference project will need to create and share its own benchmark cases.

**7c. Extensibility considerations**
Although the paper uses standard cumulative-DVH style endpoints, it strongly motivates **spatially aware extensions**. The metric most explanatory of the grid effect was not another DVH point, but **DTF** between **90%** and **50%** isodose levels. A reference platform should therefore support gradient-aware quantities such as dose-distance/interface metrics, line sampling, and substructure-specific analysis at the target-cord interface. The study also shows the importance of derived structures: the clinically relevant organ was a **cropped partial cord** extending **±6 mm** around the PTV, not the whole cord. Biological overlays are not directly analysed, but any serial-organ NTCP, EUD/gEUD, or probabilistic hotspot model built on D0.03cc-type inputs will inherit the same resolution sensitivity. Dose-grid metadata and uncertainty descriptors should therefore be available to downstream modelling layers. The authors also cite prior motion work suggesting cord dose can rise by up to **13%** with small motion, which argues for future **robust/probabilistic DVH** capability in spine SRS benchmarking.

**7d. Caveats and limitations**
Several aspects may not generalise. This is a **single-institution**, **single-vendor**, **single-dose-algorithm** study (AAA v11, EDGE, HD-MLC, VMAT). The apparent 1 mm PTV “mottling” may be specific to Eclipse/HD-MLC modelling rather than a universal property of fine grids. The work also does **not cleanly separate dose-calculation resolution from DVH integration**, because both are embedded in the TPS workflow. There is no analytical or Monte Carlo ground truth, and the film validation is **2D** in a **homogeneous phantom**, whereas the patient cases involved vertebral anatomy and CT with **2 mm** slice thickness. DTF was measured only in the **axial plane at isocentre**, not as a full 3D surface-to-surface gradient descriptor. Finally, Table 3 is methodologically ambiguous because the methods describe a **10-case shortest-DTF subset**, while the caption says “all fifty cases”. These limitations mean the numerical trends are highly informative, but the paper should not be read as a universal accuracy ranking of all grids and all algorithms.

### 8. Connections to other literature

- **Niemierko and Goitein, 1989** Foundational theoretical work on how dose-grid size influences dose-estimation and positional error; this study is effectively a modern spine SRS stress-test of that principle.
- **Dempsey et al. (2005)** Earlier Fourier-based IMRT analysis suggesting **2.5 mm** may be sufficient; the present study shows that this is not necessarily adequate for contemporary spine SRS cord metrics.
- **Chung et al. (2006)** Earlier head-and-neck IMRT work showing **2-4%** dose discrepancies with changing grid size; the present study observes substantially larger effects for small high-gradient cord subvolumes.
- **Park et al. (2014)** Lung SBRT dynamic conformal arc study identifying **3 mm** as practical; this provides a contrast case showing that “optimal” grid size is site- and geometry-dependent.
- **Snyder et al. (2015)** Prior paper from the same group on jaw tracking in spine SRS, establishing sharper dose drop-off at the cord-target interface and helping explain why grid size matters so much here.
- **Wen et al. (2016)** Source of the EBT3 film dosimetry methodology used for stereotactic QA in this paper.
- **Yang et al. (2016)** Relevant to the discussion that improved tongue-and-groove and fluence sampling may reduce the apparent 1 mm high-dose-region artefacts.

### 9. Data extraction table

The following tables extract the paper’s quantitative results; where noted, counts were derived by counting entries in Table 1.

**Table 9.1. Study cohort and planning characteristics**

| Parameter | Value |
|---|---|
| Number of plans | 50 |
| Site distribution | 36 thoracic / 1 cervical / 13 lumbar |
| Target class distribution | A: 12 / B: 21 / C: 17 *(derived from Table 1)* |
| Epidural involvement | Yes: 26 / No: 24 *(derived from Table 1)* |
| Mean target volume | 45.19 cc |
| Target-volume range | 8.62-164.95 cc |
| Mean minimum target-cord distance | 0.77 mm |
| Distance range | 0-3.4 mm |
| Prescription | 12, 16, or 18 Gy in 1 fraction to 90% IDL |
| Planning / dose engine | Eclipse v11 / AAA v11 |
| Delivery | VMAT, 2 partial arcs (215°-145°), EDGE, HD-MLC, 6 MV or 10 MV FFF |
| Recalculated dose grids | 1.0 mm / 1.5 mm / 2.5 mm |
| Original clinical grid distribution | 19 plans at 1.0 mm / 14 at 1.5 mm / 17 at 2.5 mm |
| Partial cord definition | MR-visible cord from 6 mm below to 6 mm above PTV |

**Table 9.2. Effect of dose-grid size on key dosimetric metrics**

| Metric | 1.0 mm | 1.5 mm | 2.5 mm | 1.5 mm vs 1.0 mm | 2.5 mm vs 1.0 mm |
|---|---:|---:|---:|---:|---:|
| `PTV_D99%` (Gy) | 17.03 ± 1.24 | 17.31 ± 1.25 | 16.93 ± 1.22 | +1.7% | -0.54% |
| `PTV_D95%` (Gy) | 17.72 ± 1.20 | 18.11 ± 1.20 | 17.84 ± 1.17 | +2.2% | +0.7% |
| `PTV_D5%` (Gy) | 20.09 ± 1.54 | 20.34 ± 1.54 | 20.05 ± 1.52 | +1.3% | -0.2% |
| `PTV_D0.03cc` (Gy) | 20.96 ± 1.58 | 21.07 ± 1.57 | 20.65 ± 1.56 | +0.5% | -1.5% |
| Cord_D10% (Gy) | 8.19 ± 1.24 | 8.83 ± 1.36 | 9.25 ± 1.43 | +7.8% | +13.0% |
| Cord_D0.03cc (Gy) | 10.50 ± 1.66 | 11.15 ± 1.68 | 11.52 ± 1.61 | +6.4% | +10.1% |
| DTF 90%→50% IDL (mm) | 2.52 ± 0.54 | 2.83 ± 0.58 | 3.30 ± 0.64 | +0.31 mm | +0.78 mm |

*Note:* All reported grid-to-grid dosimetric comparisons were statistically significant at **`p < 0.001`**. Worst casewise differences for **2.5 mm vs 1.0 mm** were **+23.2%** for Cord_D10% and **+22.7%** for Cord_D0.03cc (absolute differences **1.8 Gy** and **2.0 Gy**).

**Table 9.3. Velocity versus Eclipse DVH differences**

| Grid | Mean Velocity - Eclipse `PTV_D99%` | Mean Velocity - Eclipse Cord_D0.03cc | Reported range for Cord_D0.03cc |
|---|---:|---:|---:|
| 1.0 mm | -1.2% | -0.5% | -5.9% to +2.5% |
| 1.5 mm | -1.0% | -0.8% | -3.4% to +2.5% |
| 2.5 mm | -1.2% | +0.3% | -2.7% to +4.1% |

*Note:* Methods state this comparison used the **10 cases with shortest DTF (1.5-2 mm)**, although the table caption says “all fifty cases”. Mean cross-system differences were generally within **±1.2%**.

**Table 9.4. Film QA and computation time**

| Grid | Gamma pass rate (3%/1 mm) | Film-plan isocentre dose difference | Mean calculation time |
|---|---:|---:|---:|
| 1.0 mm | 94.3 ± 6.0% | 1.22 ± 1.8% | 11 min 36 s ± 2 min 48 s |
| 1.5 mm | 95.9 ± 5.4% | -0.06 ± 2.03% | 4 min 30 s ± 47 s |
| 2.5 mm | 93.6 ± 5.4% | 0.40 ± 2.09% | 1 min 53 s ± 32 s |

*Note:* The authors reported the highest gamma pass rate at **1.5 mm**, but the line-profile figures showed **1.0 mm** matched the cord-adjacent high-gradient region better. Relative to **1.0 mm**, calculation time was approximately **61% shorter** at **1.5 mm** and **84% shorter** at **2.5 mm**.

### 10. Critical appraisal

**Strengths:** This is a clinically focused, quantitatively rich study in an edge-case regime that matters for reference DVH work: small serial OAR subvolumes adjacent to very steep gradients. The cohort is reasonably sized (**50 plans**), the recalculation design isolates grid-size effects better than a plan-reoptimisation study would, and the authors add both film QA and a cross-TPS DVH comparison.
**Weaknesses:** There is no independent 3D ground truth, no analytical benchmark, and no Monte Carlo reference. The physical validation is 2D and homogeneous. Important DVH implementation details are missing. The Velocity comparison appears to be a 10-case subset despite a caption implying 50. The observed 1 mm PTV “noise” may reflect TPS/MLC modelling limits rather than true dosimetric degradation.
**Confidence in findings:** **Medium.** The numerical trends are consistent and plausible, but “accuracy” is inferred rather than proven against a gold standard.
**Relevance to reference DVH calculator:** **High.** The paper directly quantifies how grid resolution and DVH extraction can shift Cord_D0.03cc and Cord_D10% by clinically meaningful amounts in exactly the high-gradient, small-structure scenarios a reference implementation must handle robustly.

---

<!-- Source: SUMMARY - Stanley 2021 - Accuracy of dose-volume metric calculation for small-volume radiosurgery targets.md -->

## Stanley (2021) - Accuracy of dose-volume metric calculation for small-volume radiosurgery targets

### Executive summary

This paper is directly relevant to any reference-grade DVH engine because it isolates a regime where commercial software often disagrees: **very small radiosurgery targets** combined with **steep dose gradients**. Using analytically generated DICOM `RTSTRUCT` and `RTDOSE` datasets with known ground truth, the authors compared five commercial systems across spherical targets from **3 mm to 20 mm** diameter. The main finding is that cross-system disagreement becomes substantial for the smallest targets, especially for **reported target volume** and **V100%**, while **V50%** is much more stable. Those discrepancies then propagate into **RTOG conformity index** and **Paddick gradient index**, meaning that the same nominal SRS plan can appear materially different depending on the software used.

For a reference DVH calculator, the engineering lesson is that correctness cannot be judged only on larger structures or on broad low-dose metrics. Validation must deliberately stress **sub-0.1 cc targets**, **phase sensitivity relative to the sampling grid**, and **boundary-dominated metrics** such as prescription isodose volume. The paper supports implementing transparent, explicitly documented handling of contour rasterisation, partial-volume treatment, dose interpolation, and isodose-volume calculation. It also argues for validation suites that assess not only mean bias but also the range across repeated subvoxel placements, because some systems in this study showed near-zero mean error while still having large placement-dependent excursions.

---

### 1. Bibliographic record

**Authors:** Dennis N Stanley, Elizabeth L Covington, Haisong Liu, Ara N Alexandrian, Rex A Cardan, Daniel S Bridges, Evan M Thomas, John B Fiveash, Richard A Popple
**Title:** *Accuracy of dose-volume metric calculation for small-volume radiosurgery targets*
**Journal:** *Medical Physics*
**Year:** 2021 (accepted-article version dated 2020)
**DOI:** [10.1002/mp.14645](https://doi.org/10.1002/mp.14645)
**Open access:** Yes

### 2. Paper type and scope

**Type:** Original research.
**Domain tags:** D1 Computation | D2 Commercial systems.
**Scope statement:** This paper benchmarks the accuracy of small-volume SRS dose-volume metrics across five commercial DVH analysis systems using analytically generated DICOM `RTSTRUCT` and `RTDOSE` data with known ground truth. It is important because it isolates post-processing/DVH-calculation behaviour from treatment-plan optimisation and shows that for very small targets, hidden implementation choices can materially alter reported target volume, V100%, V50%, conformity index, and gradient index.

### 3. Background and motivation (150-300 words)

The clinical problem is not whether DVHs are useful, but whether commonly used software computes the same scalar metrics for the same small SRS target and dose distribution. The paper notes that DVHs are central to target/OAR evaluation, protocol compliance, and published outcome correlations, while TG-263 standardises nomenclature rather than the underlying numerical calculation. Prior literature had already examined DVH behaviour under changing grid size, bin width, and across planning systems, and Ma et al. had shown that contour-based radiosurgery volume calculation itself can vary between platforms. What remained insufficiently characterised was the combined problem most relevant to SRS: **very small structures**, **steep dose gradients**, and **plan-quality indices derived from dose-cloud volumes**, especially conformity and gradient indices.

That gap matters because a 3-5 mm intracranial target occupies only a few CT pixels and slices, so small differences in structure rasterisation, interpolation, or partial-volume treatment can create large *relative* errors even when absolute volume differences are tiny. Those errors then propagate into derived plan-quality metrics widely used in the SRS literature. The authors therefore aimed to create an analytically defined, importable DICOM benchmark that avoids manufacturing/imaging artefacts from physical phantoms and permits direct cross-system comparison of scalar DVH metrics relevant to SRS. They also explicitly frame the work as relevant to multi-institutional trials, where metric comparability across software ecosystems matters.

### 4. Methods: detailed technical summary (400-800 words)

This was an **analytical/simulation benchmark study** rather than a patient or phantom study. The authors generated synthetic DICOM data in MATLAB and imported those files independently into five commercial systems: Eclipse 15.6.05, Elements 3.0/Dose Review 3.0 prototype, MIM 6.7, RayStation 8B, and Velocity 3.1.0. Two synthetic CT datasets were created with **0.6 mm in-plane pixel size** and either **0.5 mm** or **1.0 mm** slice spacing. For each CT spacing, the authors created structure sets containing **50 randomly placed spherical targets** at each diameter: **3, 5, 7, 10, 15, and 20 mm**, giving **600 evaluated structures** in total. The random placement is important because it samples grid-phase sensitivity, even though target shape is spherical.

Dose was not computed by a clinical beam model. Instead, the study used an **analytic radial dose model** from Suh et al. for linac-based SRS, implemented in MATLAB. For a sphere of diameter `C` and radial distance `r`, the reported model was piecewise exponential with parameters **`s1=0.249`, `s2=7.019`, `s3=0.029`, `s4=1.927`**: inside the sphere `D(r)=1-s1*exp[-s2(C/2-r)]`, outside the sphere `D(r)=s3+(1-s1-s3)*exp[-s4(r-C/2)]`. The abstract calls this a **1 mm grid**, while the methods clarify that the actual `RTDOSE` matrix was **`1 mm x 1 mm x CT slice spacing`**, i.e. `1 x 1 x 0.5 mm` or `1 x 1 x 1 mm` depending on dataset. For each sphere, a spherical evaluation volume was created where dose was at least **25% of the target-surface dose** the figure legend indicates a **20 Gy to 5 Gy** display range, so V100% corresponds to **V20 Gy** and V50% to **V10 Gy**. Spheres were separated so evaluation volumes did not overlap, and dose outside all evaluation volumes was set to **25%**. Heterogeneity handling, beam energy, and dose-algorithm version are therefore **not applicable** here: this is a direct test of metric computation on known `RTDOSE`/`RTSTRUCT` inputs.

The primary outputs were reported target volume, `V100% [cc]`, and `V50% [cc]` in the evaluation shell. Analytical references were sphere volume `πD^3/6` and dose-cloud volumes derived from Eq. 1. From those values, the authors computed the **RTOG conformity index** and **Paddick gradient index** the paper cites the standard radiosurgery definitions, and the implied formulas from the available quantities are `CI_RTOG = V100/TV` and `GI = V50/V100`, although those equations are not explicitly written in the methods text. They also compared structure-volume results with **slice stacking** and **improved slice stacking (SSI)** as described by Ma et al. in 2012. Slice stacking multiplies contour area by slice thickness; SSI adds superior/inferior end corrections. These contour-based methods were used only for structure volume, not V100/V50.

System-specific handling is noteworthy. Eclipse values were extracted with ESAPI, giving more significant figures than the UI; its DICOM import used low- or high-resolution internal structure voxelisation, with high resolution automatically enabled for spheres **≤15 mm** when image size criteria were met. Elements results were evaluated by Brainlab product engineering, using an adaptive voxel grid of **0.5 mm** for **3 and 5 mm** targets and **1 mm** for **7 mm and larger**. MIM exported cumulative DVHs to Excel; RayStation used an internal Python script to export absolute DVH values; Velocity used manual text export via its secondary DVH analysis feature. Critically, the paper does **not** report the internal voxel-inclusion rule, dose interpolation method, end-capping method, partial-volume weighting, or histogram bin width for most systems: these are precisely the “black-box” elements the study is probing. No formal statistical tests, confidence intervals, or effect sizes were reported; the analysis is descriptive, using mean differences and ranges across the 50 random placements. The authors also intentionally anonymised the systems as `TPS-A` to `TPS-E` in the results.

### 5. Key results: quantitative (300-600 words)

The dominant result is that **small targets are highly vulnerable to cross-system metric disagreement**, and the error collapses rapidly with increasing sphere size. For reported structure volume, the paper’s overall average differences across all sizes were **-4.73%**, **+0.11%**, **-0.39%**, **-2.24%**, and a reported **+1.15%** for `TPS-A` to `TPS-E`, with ranges extending to **-33.2%**, **+9.5%**, **-12.1%**, **-21.0%**, and **-15.1%/+0.8%** respectively. The worst mean error occurred for the **3 mm sphere at 1 mm slice spacing**, where `TPS-A` was **-23.7%** and ranged **-33.2% to -20.1%**. At the same 3 mm/1 mm condition, `TPS-D` averaged **-8.9%**, while `TPS-B` was near-unbiased on average (**+1.3%**) but still had a broad **-8.3% to +9.5%** range, showing that low mean bias can hide strong phase sensitivity. By **20 mm**, all systems were within about **±0.9%** mean error. The 3 mm sphere’s nominal volume is only **0.0141 cc**, so a **-23.7%** error corresponds to an absolute miss of only about **0.0033 cc**.

V100%/V20 Gy was the second major failure mode. Overall mean differences were **-0.40%**, **-2.73%**, **-3.01%**, **-3.79%**, and **+0.26%** for `TPS-A` to `TPS-E`, but again the smallest targets drove the problem. For **3 mm spheres at 0.5 mm slice spacing**, mean V100 errors were **-0.2%**, **-12.4%**, **-13.1%**, **-11.1%**, and **+0.2%**. At **3 mm and 1 mm slice spacing**, they were **-4.3%**, **-10.6%**, **-10.8%**, **-20.1%**, and **+2.0%**. Particularly important is `TPS-E`, whose mean at 3 mm/1 mm was only **+2.0%** but whose range was **-36.3% to +20.3%**: again, the average obscures strong placement dependence. Conversely, V50%/V10 Gy was far more stable: overall means were **-0.05%**, **-0.18%**, **-0.44%**, **-0.26%**, and **+0.09%**, and even at the worst small-target condition (3 mm/1 mm), mean errors were only **-0.2%**, **-0.6%**, **-0.8%**, **-1.0%**, and **+0.2%**, with ranges mostly inside about **±1-3%**. This strongly suggests that the most fragile quantities are those tied closely to the target boundary/prescription isodose, not broader low-dose shells.

The derived radiosurgery indices magnified these discrepancies. Using the tabulated mean errors, the implied mean **RTOG CI** for **3 mm** targets was approximately **1.106, 0.875, 0.882, 0.924, 1.012** at **0.5 mm** slice spacing and **1.254, 0.883, 0.904, 0.877, 1.045** at **1 mm** slice spacing for `TPS-A` to `TPS-E`, consistent with Figure 6. Thus, the same nominal plan could appear substantially **over-conformal** or **under-conformal** depending on the software. The implied **GI deviation from expected** at **3 mm** was approximately **+0.2%, +13.5%, +14.0%, +11.7%, +0.1%** at **0.5 mm**, and **+4.3%, +11.2%, +11.2%, +23.9%, -1.8%** at **1 mm**, consistent with Figure 5. By **10-20 mm**, both CI and GI clustered close to expected values. Figure 2 also shows that simple slice stacking stayed roughly near **0 to +2%** for the smallest volumes, whereas the plotted SSI comparator still underestimated the **3 mm** sphere by roughly **-3.9%** at **0.5 mm** slices and **-8.9%** at **1 mm** slices. No formal hypothesis tests were reported; all findings are descriptive.

### 6. Authors' conclusions (100-200 words)

The authors conclude that commercially used SRS DVH-analysis systems can produce materially different values for small-structure volume and dose-volume metrics, and that this lack of standardisation/transparency is problematic for SRS plan evaluation and especially for multi-institutional clinical trials. They also position the paper as an extension of earlier DVH-validation literature because it adds small-volume SRS targets, steep gradients, and derived SRS plan-quality metrics, while providing a downloadable analytical DICOM benchmark for local validation. They explicitly argue that vendor implementation details remain largely opaque and that users therefore lack a reliable basis for understanding software-specific shortcomings.

Those conclusions are mostly well supported. The empirical data clearly demonstrate cross-system spread for **3-5 mm** targets and show that CI/GI can be distorted as a consequence. The broader extrapolation to trial comparability is plausible and important, although the paper does not directly test any clinical-trial dataset or outcome model.

### 7. Implications for reference DVH calculator design (300-600 words)

**7a. Algorithm and implementation recommendations**

A reference calculator should not rely on naïve binary voxel inclusion or opaque structure rasterisation. This paper shows that for tiny SRS targets, errors near the target boundary dominate: some systems had near-zero mean structure-volume bias yet still showed **~10-13%** V100 underestimation for **3 mm** targets, proving that accurate contour volume alone is insufficient. The engine should therefore implement explicit, documented handling of: contour-to-volume conversion, end-capping, dose interpolation, partial-volume weighting, and Vx thresholding. It should expose these as provenance metadata with every metric, not bury them in a black box.

For small structures, the calculator should support either exact polygon/mesh integration or controlled supersampling with convergence checks. The worst case in this study is effectively a **3 mm** sphere sampled on **0.6 mm** pixels and **1 mm** slices, i.e. only about **5 pixels across** and **3 axial samples**. In that regime, the reference implementation should target substantially tighter agreement than the commercial spread seen here: as an engineering goal, **<1%** error for spheres **≥10 mm**, **<2-3%** for **5-7 mm**, and explicit uncertainty reporting for **3 mm** cases rather than pretending deterministic exactness. Because CI/GI amplification was severe, derived metrics should be computed from the same underlying geometry/dose objects as the base Vx values.

A particularly valuable design choice would be two operational modes: a **DICOM-faithful mode** that computes exactly from the encoded `RTSTRUCT`/`RTDOSE`, and a **continuous-estimate mode** that attempts subvoxel reconstruction or supersampled integration and reports uncertainty. This paper measures the end-to-end effect of both DICOM representation and vendor computation, so a gold-standard tool should help separate those components.

**7b. Validation recommendations**

This paper’s supplementary DICOM dataset should be a core regression suite. At minimum, validation should replicate the full matrix used here: diameters **3, 5, 7, 10, 15, 20 mm** slice spacings **0.5 mm** and **1.0 mm** **50 random translations** per size; and metrics `TV`, V100, V50, CI, and GI. Crucially, pass/fail should examine both **mean error** and **range across placements**, because this paper shows that small mean bias can coexist with very large phase-dependent excursions, especially for V100.

However, the Stanley benchmark should not be the only test. Because the inputs are contour-based `RTSTRUCT`s on finite slice spacing, the validation programme should add true analytical-shape tests that bypass DICOM contour discretisation altogether, plus oblique/rotated ellipsoids, irregular targets, non-spherical dose clouds, and heterogeneous media. The reference engine should also include unit tests for the exact derived quantities most exposed here: Vx isodose volumes, `CI_RTOG`, GI, and low-volume scalar metrics for structures below **0.1 cc**.

**7c. Extensibility considerations**

The paper motivates a calculator architecture that treats dose-cloud volumes as first-class objects, not merely outputs of a cumulative DVH. A reusable Vx/isodose-volume kernel would naturally support CI, GI, `R50`, and later extensions such as D_x, differential DVH, cumulative DVH, gEUD/EUD, and biological overlays. Since the failure mode here is fundamentally one of geometric/discretisation sensitivity, the engine should also be able to report a **metric uncertainty band** or **grid-sensitivity estimate** for very small volumes.

Mesh-aware data structures would also be useful. This study is about volumes, but the same need for traceable geometry handling will matter if the tool later supports dose-surface histograms, distance-to-isodose metrics, or dosiomics features extracted near structure boundaries. In other words, the extensibility lesson is not “add more metrics”, but “build the geometry/dose core so that advanced metrics inherit transparent, validated numerics.”

**7d. Caveats and limitations**

Generalisability is limited. The benchmark uses spheres, a radially symmetric analytic SRS dose model, and only two CT slice spacings. There is no anatomical irregularity, no heterogeneous density, no clinical beam model, and no full DVH-curve analysis. Results are version-specific, and one system (Elements) was assessed through a vendor engineering workflow on a prototype release. The systems were also deliberately anonymised, so algorithm-level attribution is limited.

There are also manuscript-quality caveats. The uploaded accepted-article tables label mean differences as `ΔV [cc]`, although the values clearly behave as **percentage deviations** for the smallest spheres, and at least one published summary value appears sign-inconsistent. There is also a minor notation ambiguity in the shell definition (`D(C)/4`) because Eq. 1 places the sphere boundary at `r=C/2`. None of that invalidates the main conclusion, but it reinforces the need to use the supplementary DICOM files and not rely solely on hand-transcribed summary rows.

### 8. Connections to other literature

The paper explicitly builds on or should be read alongside the following literature:

- **Nelms et al. (2015)** analytical DVH-verification datasets and methods; Stanley et al. extend that logic to the small-volume, steep-gradient SRS regime.
- **Ma et al. (2012)** reliability of contour-based radiosurgery volume calculation using physical spheres; Stanley et al. replace the physical phantom with an analytic DICOM benchmark and add dose-volume metrics and derived indices.
- **Ebert et al. (2010)** comparison of DVH data across treatment planning systems; Stanley et al. focus the comparison on much smaller SRS targets.
- **Panitsa et al. (1998)** early quality control of DVH computation characteristics; conceptually an antecedent to this cross-system QA work.
- **Corbett et al. (2002)** voxel-size effects on DVH accuracy for prostate seed implants; analogous evidence that discretisation matters most for small-volume structures.
- **Paddick (2000)** conformity-index definition used in the derived analysis.
- **Paddick and Lippitz (2006)** gradient-index definition used here and directly impacted by `V50/V100` accuracy.

### 9. Data extraction table

The tables below extract the paper’s quantitative results. Because the manuscript table header `ΔV [cc]` is inconsistent with the magnitudes for the smallest spheres, I interpret the tabulated values as **mean percentage difference relative to the analytical reference**, with the bracketed term as the reported range across the 50 random placements. The analytical reference table is derived from the paper’s sphere geometry and Eq. 1.

**Table 9a. Analytical reference values derived from the paper’s geometry and dose model**

| Diameter (mm) | Analytical target volume / V100 (cc) | Analytical V50 (cc) | Expected GI (V50/V100) |
|---:|---:|---:|---:|
| 3 | 0.0141 | 0.0279 | 1.972 |
| 5 | 0.0654 | 0.1002 | 1.530 |
| 7 | 0.1796 | 0.2449 | 1.363 |
| 10 | 0.5236 | 0.6526 | 1.246 |
| 15 | 1.7671 | 2.0504 | 1.160 |
| 20 | 4.1888 | 4.6860 | 1.119 |

**Table 9b. Structure-volume error, mean % [range %]**

| Slice (mm) | Diameter (mm) | TPS-A | TPS-B | TPS-C | TPS-D | TPS-E |
|---:|---:|:---|:---|:---|:---|:---|
| 0.5 | 3 | -9.8 [-16.4,-6.9] | +0.1 [-10.9,+8.2] | -1.5 [-12.1,+7.0] | -3.8 [-8.5,-0.8] | -1.0 [-1.0,-1.0] |
| 0.5 | 5 | -3.1 [-5.7,-2.2] | -0.1 [-2.1,+1.8] | -0.4 [-2.6,+1.5] | -1.6 [-3.2,-0.8] | -0.5 [-0.7,+0.8] |
| 0.5 | 7 | -1.3 [-2.6,-0.9] | +0.1 [-1.2,+1.2] | -0.1 [-1.3,+1.1] | -0.9 [-1.6,-0.3] | -0.1 [-0.3,+0.2] |
| 0.5 | 10 | -1.3 [-2.6,-0.9] | +0.1 [-1.2,+1.2] | -0.1 [-1.3,+1.1] | -0.5 [-0.8,-0.1] | -0.1 [-0.3,+0.2] |
| 0.5 | 15 | -0.4 [-1.0,-0.3] | 0.0 [-1.1,+0.5] | -0.1 [-1.1,+0.5] | -0.2 [-0.4,-0.1] | 0.0 [-0.3,+0.1] |
| 0.5 | 20 | -0.1 [-0.3,+0.2] | 0.0 [-0.4,+0.2] | 0.0 [-0.4,+0.2] | -0.1 [-0.2,-0.1] | 0.0 [-0.2,0.0] |
| 1.0 | 3 | -23.7 [-33.2,-20.1] | +1.3 [-8.3,+9.5] | -1.3 [-10.9,+7.0] | -8.9 [-21.0,-1.8] | -2.4 [-15.1,+13.2] |
| 1.0 | 5 | -9.6 [-14.0,-7.4] | 0.0 [-5.4,+4.0] | -0.6 [-5.9,+3.4] | -4.9 [-10.0,-2.0] | -3.8 [-9.9,+0.8] |
| 1.0 | 7 | -5.4 [-9.5,-3.9] | -0.1 [-2.4,+2.4] | -0.5 [-3.2,+2.0] | -3.2 [-6.0,+1.3] | -3.1 [-5.9,-0.9] |
| 1.0 | 10 | -5.4 [-9.5,-3.9] | -0.1 [-2.4,+2.4] | -0.5 [-3.2,+2.0] | -1.5 [-2.9,-0.8] | -3.1 [-5.9,-0.9] |
| 1.0 | 15 | -2.2 [-3.6,-1.8] | 0.0 [-1.2,+1.0] | -0.1 [-1.3,+0.7] | -0.8 [-1.5,-0.5] | -1.4 [-3.2,-0.3] |
| 1.0 | 20 | -0.9 [-1.8,-0.7] | 0.0 [-0.5,+0.6] | -0.1 [-0.7,+0.5] | -0.5 [-0.8,-0.3] | -0.9 [-1.6,-0.2] |

**Table 9c. V100% / V20 Gy error, mean % [range %]**

| Slice (mm) | Diameter (mm) | TPS-A | TPS-B | TPS-C | TPS-D | TPS-E |
|---:|---:|:---|:---|:---|:---|:---|
| 0.5 | 3 | -0.2 [-24.5,+9.8] | -12.4 [-19.8,-5.8] | -13.1 [-20.7,-6.8] | -11.1 [-16.4,-6.6] | +0.2 [-22.2,+13.2] |
| 0.5 | 5 | 0.0 [-6.5,+6.2] | -3.5 [-6.5,-2.1] | -3.9 [-7.1,-2.4] | -3.6 [-8.1,-1.5] | -0.2 [-3.7,+7.0] |
| 0.5 | 7 | +0.1 [-3.0,+2.1] | -1.3 [-2.5,+0.3] | -1.5 [-2.8,0.0] | -1.6 [-3.8,-0.7] | -0.2 [-3.7,+3.0] |
| 0.5 | 10 | +0.1 [-3.0,+2.1] | -1.3 [-2.5,+0.3] | -1.5 [-2.8,0.0] | -0.2 [-0.7,+0.4] | -0.2 [-3.7,+3.0] |
| 0.5 | 15 | +0.4 [-2.1,+1.0] | -0.3 [-1.4,+0.3] | -0.5 [-1.5,+0.1] | +0.2 [-0.6,+0.8] | +0.2 [-2.6,+1.0] |
| 0.5 | 20 | +0.3 [-0.2,+0.7] | +0.1 [-0.4,+0.2] | -0.2 [-0.6,+0.1] | +0.3 [-0.1,+0.9] | +0.1 [-0.7,+0.7] |
| 1.0 | 3 | -4.3 [-24.5,+2.7] | -10.6 [-23.6,-0.7] | -10.8 [-23.6,-0.7] | -20.1 [-27.3,-16.6] | +2.0 [-36.3,+20.3] |
| 1.0 | 5 | -1.4 [-7.2,+5.4] | -3.4 [-7.8,+0.1] | -3.6 [-8.1,-0.1] | -6.3 [-10.6,-4.0] | -0.5 [-16.0,+10.0] |
| 1.0 | 7 | -0.5 [-3.9,+1.6] | -1.5 [-4.2,+1.1] | -1.8 [-4.3,+0.6] | -3.0 [-4.5,-2.0] | -0.5 [-5.9,+3.6] |
| 1.0 | 10 | -0.5 [-3.9,+1.6] | -1.5 [-4.2,+1.1] | -1.8 [-4.3,+0.6] | -0.7 [-1.3,0.0] | -0.5 [-5.9,+3.6] |
| 1.0 | 15 | +0.2 [-2.3,+0.7] | -0.3 [-1.6,+0.8] | -0.5 [-1.8,+0.5] | +0.4 [-1.2,+1.3] | +0.2 [-4.7,+4.7] |
| 1.0 | 20 | +0.2 [-0.2,+0.8] | 0.0 [-0.5,+0.7] | -0.2 [-0.7,+0.4] | +0.2 [-0.7,+0.9] | +0.1 [-1.3,+1.2] |

**Table 9d. V50% / V10 Gy error, mean % [range %]**

| Slice (mm) | Diameter (mm) | TPS-A | TPS-B | TPS-C | TPS-D | TPS-E |
|---:|---:|:---|:---|:---|:---|:---|
| 0.5 | 3 | 0.0 [-0.7,+0.6] | -0.6 [-1.2,+0.2] | -0.9 [-1.3,-0.2] | -0.7 [-1.5,-0.3] | +0.3 [-0.6,+1.6] |
| 0.5 | 5 | 0.0 [-0.5,+0.5] | -0.3 [-0.9,+0.5] | -0.6 [-1.2,+0.2] | -0.3 [-0.6,0.0] | +0.1 [-1.1,+0.9] |
| 0.5 | 7 | 0.0 [-0.3,+0.3] | -0.2 [-0.5,+0.4] | -0.4 [-0.7,+0.1] | -0.2 [-0.3,+0.1] | +0.1 [-0.2,+0.6] |
| 0.5 | 10 | 0.0 [-0.3,+0.3] | -0.2 [-0.5,+0.4] | -0.4 [-0.7,+0.1] | -0.2 [-0.4,+0.1] | +0.1 [-0.2,+0.6] |
| 0.5 | 15 | 0.0 [-0.3,+0.3] | -0.1 [-0.3,+0.1] | -0.3 [-0.4,-0.1] | 0.0 [-0.1,+0.2] | +0.1 [-0.4,+0.8] |
| 0.5 | 20 | 0.0 [-0.1,+0.2] | 0.0 [-0.1,+0.1] | -0.3 [-0.4,-0.1] | +0.2 [0.0,+0.4] | +0.1 [-0.2,+0.3] |
| 1.0 | 3 | -0.2 [-0.8,+0.4] | -0.6 [-1.2,+0.1] | -0.8 [-1.4,0.0] | -1.0 [-1.8,-0.8] | +0.2 [-1.1,+2.7] |
| 1.0 | 5 | -0.2 [-0.6,+0.4] | -0.3 [-0.7,+0.1] | -0.6 [-1.0,-0.1] | -0.5 [-0.8,-0.2] | 0.0 [-1.4,+1.1] |
| 1.0 | 7 | -0.1 [-0.4,+0.3] | -0.2 [-0.5,+0.5] | -0.4 [-0.7,+0.3] | -0.3 [-0.5,+0.1] | 0.0 [-0.7,+0.7] |
| 1.0 | 10 | -0.1 [-0.4,+0.3] | -0.2 [-0.5,+0.5] | -0.4 [-0.7,+0.3] | -0.3 [-0.6,+0.1] | 0.0 [-0.7,+0.7] |
| 1.0 | 15 | -0.1 [-0.3,+0.3] | -0.1 [-0.4,+0.3] | -0.3 [-0.6,0.0] | 0.0 [-0.1,+0.3] | 0.0 [-0.6,+0.7] |
| 1.0 | 20 | 0.0 [-0.2,+0.2] | 0.0 [-0.1,+0.3] | -0.3 [-0.4,-0.1] | +0.2 [+0.1,+0.5] | 0.0 [-0.5,+0.3] |

### 10. Critical appraisal (100-200 words)

**Strengths:** analytically defined ground truth; direct `RTSTRUCT`/`RTDOSE` import rather than cross-system contour export; clinically relevant SRS diameters and steep gradients; inclusion of derived radiosurgery metrics (CI, GI); and public benchmark data for local QA.

**Weaknesses:** only spheres and a radial analytic dose model; no irregular anatomy or heterogeneity; descriptive statistics only; no full DVH-curve/bin-width audit; one software version per system; differing extraction workflows across systems; anonymised result labels; and some likely table/sign/notation inconsistencies in the accepted manuscript. The benchmark also conflates contour representation error with downstream metric computation, which is clinically relevant but limits mechanistic attribution.

**Confidence in findings:** **Medium.** Internal validity is strong for the central qualitative message ;  small-volume SRS metrics differ substantially across systems ;  but exact magnitudes are version-specific and slightly undermined by presentation inconsistencies.

**Relevance to reference DVH calculator:** **High.** This paper directly targets the regime most likely to break a benchmark DVH engine: sub-0.1 cc targets, prescription-isodose volumes, steep gradients, and derived plan-quality metrics that amplify tiny geometric differences.

---

<!-- Source: SUMMARY - Pepin 2022 - Assessment of DVH precision for 5 clinical systems.md -->

## Pepin (2022) - Assessment of dose-volume histogram precision for five clinical systems

### Executive summary

Pepin et al. benchmarked five commercial DVH calculators; Eclipse, Mobius3D, MIM Maestro, ProKnow DS, and RayStation; using synthetic DICOM datasets with analytically known volumes and DVH curves, then checked whether similar effects appeared in two clinical structures. The paper shows that apparently modest implementation choices, especially inter-slice interpolation, superior/inferior endcapping, supersampling, dose interpolation, and histogram binning, can materially alter reported structure volumes, DVH shapes, and derived dose statistics even when all systems ingest the same `RTSTRUCT` and `RTDOSE` objects.

The most useful contribution for a reference-quality DVH engine is the paper’s precision concept: staircase artefacts in a computed DVH can be interpreted as a discretisation-driven uncertainty band around Dx%, Dmin, Dmax, and related metrics. Across all analytical tests, median precision-band widths were approximately **0.90%** for MIM, **0.93%** for Eclipse, **1.05%** for ProKnow, **1.96%** for Mobius3D, and **3.22%** for RayStation. However, the paper also shows that a low aggregate median does not guarantee robustness; some systems had strong directional dependence or large outliers.

For design of a gold-standard open-source calculator, the paper strongly supports explicit, configurable modelling of contour interpolation, endcaps, occupancy estimation, dose integration, and metric extraction, together with public validation on analytical phantoms. It also argues against relying on native CT or dose-grid voxelisation alone, against coarse internal DVH binning, and against assuming that near-maximum metrics such as D0.03cc are automatically more stable than reported maxima.

### 1. Bibliographic record

**Authors:** Mark D. Pepin, Gregory P. Penoncello, Kevin M. Brom, Jon M. Gustafson, Kenneth M. Long, Yi Rong, Luis E. Fong de los Santos, Satomi Shiraishi
**Title:** *Assessment of dose-volume histogram precision for five clinical systems*
**Journal:** *Medical Physics*
**Year:** 2022
**DOI:** [10.1002/mp.15916](https://doi.org/10.1002/mp.15916)
**Open access:** No

### 2. Paper type and scope

**Type:** Original research
**Domain tags:** D1 Computation | D2 Commercial systems
**Scope statement:** This paper benchmarks five commercial DVH calculators; Eclipse, Mobius3D, MIM Maestro, ProKnow DS, and RayStation; using synthetic DICOM datasets with analytically known structure volumes and cumulative DVH curves, then checks whether the same phenomena appear in two clinical examples. The main contribution is not only inter-system comparison, but a formal “precision” framework that interprets staircase artefacts in a computed DVH as a discretisation-induced uncertainty band around Dx% and related summary metrics.

### 3. Background and motivation (150-300 words)

The paper addresses a basic but still unresolved problem in radiotherapy informatics: DVH calculation is ubiquitous in plan evaluation, prescription checking, optimisation, outcomes research, and trial reporting, yet there is no single accepted computational standard for how a DVH should be produced from a dose grid plus contour set. Prior studies had already shown dependence on grid size, slice thickness, and implementation details, with consequences for clinical decision-making, multi-institutional comparisons, and TPS acceptance testing under AAPM TG-53. TG-263 standardised nomenclature, but not the underlying calculation.

A second gap was epistemic rather than practical: many earlier comparisons only showed that systems differed, not which one was closer to truth, because no analytical ground truth existed. The paper therefore builds directly on Nelms et al.’s analytical DICOM phantom concept. The authors were additionally motivated by discrepancies already visible in their own clinic when comparing a primary planning system with secondary dose-evaluation software; their introductory example showed visibly different cochlea and penile bulb DVH curves, especially in staircase behaviour. Pepin et al. therefore set out to do two things simultaneously: quantify how discretisation affects DVH behaviour relative to analytical truth, and link observed behaviour back to concrete vendor implementation choices such as supersampling, contour interpolation, endcapping, and dose-statistic extraction.

### 4. Methods: detailed technical summary (400-800 words)

This was primarily an analytical in silico benchmarking study, supplemented by two clinical resampling examples. The analytical dataset came from the supplemental DICOM files distributed by Nelms et al., originally generated in MATLAB. Pepin et al. selected two shapes: a cylinder and a cone, both with rotation axis perpendicular to the CT axial plane, height **24 mm**, and diameter **24 mm** (base diameter for the cone). Structure-set slice thicknesses were **0.2, 1, 2, or 3 mm** the superior-most and inferior-most contour slices were always present, so only the number of interior slices changed. Matching CT series were provided with the same slice thicknesses, **0.6 × 0.6 mm²** in-plane resolution, and `HU = 0` everywhere. Dose files were available at isotropic **1, 2, and 3 mm** spacing, plus a finer non-isotropic grid of **0.4 × 0.4 × 0.2 mm³**. A simple analytical dose distribution with gradient **1 Gy/mm** was applied either in the superior-inferior (SI) or anterior-posterior (AP) direction. Ground-truth structure volumes were **10.86 cc** for the cylinder and **3.62 cc** for the cone; analytical Dmin and Dmax were **4 Gy** and **28 Gy** for all shape-gradient combinations. Analytical mean dose was **16 Gy** for the cylinder in both gradient directions, **16 Gy** for the cone in AP, and **22 Gy** for the cone in SI. Analytical cumulative DVH expressions were available for all four geometry/gradient combinations.

Five commercial systems were assessed: Eclipse, Mobius3D, MIM Maestro, ProKnow DS, and RayStation. The paper reports Eclipse as version `15.5.52` in §2.2 but `15.1.52` in Table 3, so the exact sub-version is internally inconsistent in the article. Mobius3D was `v3.1`, MIM Maestro `v6.9.6`, ProKnow DS `v1.22`, and RayStation `v9A`. Export workflows differed materially. Eclipse, MIM, and ProKnow exported absolute DVH curves directly as text. Mobius3D and RayStation exported only normalised curves, so absolute curves were reconstructed offline by multiplying by reported volume. Mobius3D required a dummy anterior-photon plan created in Eclipse, then re-linked to the synthetic structure sets via Python scripting. RayStation required the DICOM dose-summation tag to be changed from `fraction` to `plan` before import. The authors also performed a vendor methodology survey based on manuals and private communications, explicitly targeting the calculation choices listed in their Table 1: CT dependence, supersampling, dose-structure comparison, inter-slice interpolation, superior/inferior endcapping, extremum-dose estimation, structure-volume calculation, and DVH binning.

Table 3 is the technical core of the paper. Mobius3D, MIM, and ProKnow treated contour slices as right prisms between slices; Eclipse and RayStation used shape-based interpolation between slices. Endcapping was especially heterogeneous: Eclipse used rounded, shape-based endcaps; Mobius3D, MIM, and RayStation extended half a slice beyond the terminal contours; ProKnow also used half-slice endcaps but capped the extension at **1.5 mm**. Supersampling also varied strongly: Eclipse sampled dose at **100,000** points in the structure; ProKnow used `>10,000` points; MIM broke contours into approximately **1 mm³** subvoxels or finer if the dose grid was finer; Mobius3D used CT voxels directly with **no supersampling** RayStation used a hybrid model with **3× axial supersampling** from dose resolution and in-plane relative-volume voxels at dose-grid size. Dose interpolation was trilinear in Mobius3D and MIM; RayStation used dose-grid voxels with non-zero relative volume; Eclipse and ProKnow compared dose supergrids against structure boundaries. DVH resolution ranged from fixed **10 cGy** bins in Mobius3D, to `400` equal bins in RayStation, to dynamic bins in ProKnow (`≥1000`), to Eclipse’s effective **100,000-bin** internal resolution. How Mobius3D computed minimum and maximum dose was [DETAIL NOT REPORTED].

The study then ran four perturbation tests. Test 0 held `RS = 0.2 mm`, `RD = 1 mm`, AP gradient fixed and varied CT slice spacing (**0.2, 1, 2, 3 mm**) to probe nominal CT independence. Test 1 held `RD = 1 mm` and varied matched CT/structure slice spacing (**0.2, 1, 2, 3 mm**) for both AP and SI gradients. Test 2 fixed `CT = 2 mm` and `RS = 2 mm`, and varied dose-grid spacing (**1, 2, 3 mm**) for AP and SI. Test 3 varied CT, structure set, and dose together with matched spacings (**0.2, 1, 2, 3 mm**), again for both gradients; here “0.2 mm” for dose referred to the **0.4 × 0.4 × 0.2 mm³** dose grid. Accuracy versus truth was assessed qualitatively rather than by a simple error metric because different endcap conventions can make a clinically reasonable implementation appear “wrong” against a flat-ended analytical object. Precision was instead quantified with a six-step algorithm: fit the known analytical DVH shape to the calculated curve with Dmin and Dmax free; identify staircase corners above and below the best fit; fit upper and lower bounding curves; then compute percent differences for D5, D10, …, D95, plus Dmin and Dmax, where the denominator was the corresponding best-fit metric. After excluding Test 0 from aggregate summaries and removing duplicate perturbations, the authors had **18** unique grid-size combinations per geometry and **42** percent-difference values per combination.

Two clinical examples were added for translational sanity checking: a cochlea from a head-and-neck plan and a penile bulb from a prostate plan. Original CT and structures had **2 mm** slice spacing and **1.27 mm** in-plane CT resolution. CT/structure sets were resampled in MIM to isotropic **1, 2, and 3 mm** voxels; original plans were recalculated in Eclipse on a **1 mm** isotropic dose grid, then downsampled by Python to **2 mm** and **3 mm**. This produced **nine** CT/RS/RD combinations per plan. Because no analytical ground truth exists for these clinical DVHs, the authors summarised variability as percent uncertainty `100σ/μ` for mean dose and maximum dose across the nine perturbations. Clinical treatment technique, beam energy, dose algorithm, and heterogeneity settings were [DETAIL NOT REPORTED]. Aside from a Levene test comparing variance of D0.03cc versus maximum dose, the paper is primarily descriptive rather than inferential.

### 5. Key results: quantitative (300-600 words)

The vendor methodology survey already explained much of the observed behaviour. ProKnow was the most CT-independent in Test 0: all CT slice spacings produced identical curves and statistics. MIM also gave identical normalised curves and dose metrics in Test 0, but structure volume increased with CT slice spacing because it mapped contours onto a CT slice and then propagated CT thickness. RayStation could process only the **0.2 mm** and **1.0 mm** CT scenarios when paired with the **0.2 mm** structure set, and failed to import the coarser CT cases. Eclipse and Mobius3D could not process mismatched CT/structure spacings at all. This is an important result for any benchmark intended to decouple `RTSTRUCT` semantics from CT image geometry.

For the synthetic phantoms, all systems showed high qualitative agreement with the analytical curves at the finest discretisation (**0.2 mm** slice thickness / finest available grid). However, behaviour diverged quickly as discretisation became coarser. Increasing CT/structure slice spacing enlarged endcaps, which in turn increased absolute structure volume in all systems, and increased SI-gradient extremum behaviour to vendor-specific degrees. Eclipse produced the smoothest SI curves but was less smooth in AP; Mobius3D became notably more stair-stepped as CT/RS spacing increased in SI; increasing dose-grid size reduced precision for RayStation in both gradients, and for MIM and Mobius3D particularly in SI. The paper’s sagittal rendering example showed a **5%** volume difference between Eclipse and MIM for the 2-mm cone, visually attributable to rounded versus prism-like endcaps, with additional truncation of the cone tip in Eclipse.

The new precision metric yielded the paper’s most important quantitative finding. Across all geometries combined, the median percent-difference width of the precision band relative to the best-fit metrics was **0.902%** for MIM with IQR **0.517%-2.50%**, **0.925%** for Eclipse with IQR **0.022%-2.86%**, **1.05%** for ProKnow with IQR **0.699%-1.79%**, **1.96%** for Mobius3D with IQR **1.27%-4.15%**, and **3.22%** for RayStation with IQR **1.95%-5.86%**. ProKnow was the most consistent across geometries and dose directions, whereas MIM achieved the lowest overall median but with broader tails. RayStation had the worst overall precision and the broadest spread. Eclipse was strongly bimodal by gradient direction: cone AP **2.86% [2.19-3.79]** versus cone SI **0.0470% [0.0217-0.143]**, and cylinder AP **2.79% [2.09-4.09]** versus cylinder SI **0.00733% [0.00237-0.0226]**. Mobius3D showed the opposite tendency, with poorer SI precision: cylinder AP **1.56% [1.19-2.25]** versus cylinder SI **4.63% [1.78-8.54]**. MIM, Mobius3D, and RayStation all produced outliers approaching **100%** difference for some metrics/grid combinations, and the distributions were asymmetrical with long high tails rather than near-Gaussian.

Clinical behaviour broadly tracked the synthetic findings but not perfectly. Qualitatively, staircase prevalence ranked approximately Eclipse < ProKnow < MIM < RayStation < Mobius3D, consistent with the degree of supersampling. However, the smoothest-looking curves did not always have the lowest cross-resampling metric uncertainty. For the penile bulb, mean-dose uncertainty across the nine resampled variants was **6.51%** for ProKnow, **6.17%** for Eclipse, **5.26%** for MIM, **5.05%** for Mobius3D, and **4.98%** for RayStation; maximum-dose uncertainty among systems reporting a maximum ranged from **0.25%** (ProKnow) to **0.90%** (MIM). For the cochlea, mean-dose uncertainty was lower overall but still non-negligible: **3.37%** for MIM, **1.86%** for ProKnow, **1.73%** for RayStation, **1.63%** for Mobius3D, and **1.10%** for Eclipse; maximum-dose uncertainty ranged from **0.43%** to **0.89%**. Eclipse showed the largest spread in absolute clinical volume, grouped by CT/structure resolution, with larger voxels producing smaller volumes. Finally, the commonly recommended near-maximum metric D0.03cc was **not** significantly less variable than maximum dose in the synthetic SI tests: Levene `p = 0.51` for the cone and `p = 0.53` for the cylinder.

### 6. Authors' conclusions (100-200 words)

The authors conclude that commercial dose-evaluation systems can produce different DVH curves, structure volumes, and dose statistics from identical input DICOM objects because of differing internal methodologies, especially supersampling and treatment of superior/inferior structure ends. They argue that physicists should explicitly investigate DVH calculation behaviour when commissioning a new system and should be cautious when transferring DVH data between systems or institutions. That conclusion is well supported by the analytical benchmark and the methodology survey. Their broader implication; that this variability can affect patient care and multi-institutional studies; is plausible and likely correct, but the paper itself provides only limited direct clinical evidence because the clinical component comprised just **two** structures from **two** plans.

### 7. Implications for reference DVH calculator design (300-600 words)

#### 7a. Algorithm and implementation recommendations

A reference calculator should make every major methodological choice explicit and configurable: contour-to-volume model, inter-slice interpolation, endcap policy, dose interpolation, supersampling strategy, volume definition, extremum definition, and DVH binning. This paper shows that hiding any of these choices inside proprietary code materially changes output. In particular, the engine should **not** let CT slice thickness silently alter DVH results when `RTSTRUCT` contour coordinates already define the geometry; ProKnow’s Test 0 behaviour is closer to that ideal than MIM’s CT-thickness-dependent volume calculation.

For the core geometry/dose integration, the reference implementation should use a **fully 3D** occupancy model and dose integration method, not simple dependence on native CT or dose-grid voxels. The paper strongly suggests that sampling on input-grid resolution alone produces anisotropic precision and can miss endcap dose effects. A gold-standard engine should therefore prefer exact polyhedral/lofted volume intersection or very dense adaptive 3D subvoxel integration with convergence testing. It should also use the **same geometric model** for volume, mean dose, extrema, and all Dx%/Dxcc metrics; the paper found systems where endcaps affected reported volume but not reported extremum dose. Internally, metric computation should avoid coarse histogram quantisation wherever possible; fixed **10 cGy** bins or `400` equal bins are not benchmark-grade design choices.

Numerically, the paper implies that aggregate median precision **around 1%** is achievable in commercial software (MIM **0.902%**, ProKnow **1.05%**), while aggregate performance around **3%** (RayStation **3.22%**) is clearly inferior on these tests. A reference engine intended as a gold standard should therefore target **better than 1% median precision** on the Pepin/Nelms-style perturbation suite, with no geometry-direction bimodality like Eclipse and no extreme outliers approaching **100%**. Small contour features must also be preserved exactly or flagged: Eclipse’s loss of a **0.09 mm²** cone-tip polygon is a cautionary example of why internal segmentation models should never truncate imported structures without warning.

#### 7b. Validation recommendations

The Nelms analytical DICOM files, reused here, should be a mandatory validation tier for any reference DVH engine. At minimum, validation should reproduce the cone and cylinder cases with height/diameter **24 mm**, true volumes **3.62 cc** and **10.86 cc**, linear dose gradient **1 Gy/mm**, analytical `Dmin/Dmax` **4/28 Gy**, and analytical means **16 Gy** or **22 Gy** depending on geometry/direction. Validation should be separated into: geometry/volume accuracy, normalised DVH shape, absolute DVH, mean dose, extrema, and arbitrary Dx% metrics. The Pepin precision-band method is particularly useful for commissioning because it directly tests staircase uncertainty rather than only bias from truth.

The specific stress cases that exposed failures here should be reproduced: mismatched CT and structure-set spacing (CT independence), matched/coarsened CT/RS spacing, coarsened dose grid, AP versus SI gradients, and small-tip structures vulnerable to truncation. Additional cases the authors explicitly did **not** cover; but which a reference calculator should; include rotated geometries, offsets between dose-grid and contour slices, and more complex non-linear gradients. Public benchmarking should also include the Stanley small-target SRS datasets alongside these phantoms. A practical acceptance rule derived from this paper would be: require aggregate precision at least as good as the best commercial systems (approximately **≤1%** median band width relative to best-fit metrics), while separately reporting residual sensitivity from endcap-policy choices rather than burying it inside one number.

#### 7c. Extensibility considerations

The main extensibility lesson is that a trustworthy engine should expose the continuous dose-occupancy representation, not just final cumulative DVH bins. That supports arbitrary Dx%, Dxcc, mean/min/max, and both cumulative and differential DVH outputs from the same underlying calculation. It also enables **uncertainty-aware** outputs: Pepin et al.’s central insight is that staircase behaviour can be interpreted as a metric band, so a future reference engine should be able to report not just a single value but a discretisation or convergence envelope.

The paper does not directly motivate DSH, DMH, EUD/gEUD, or biological overlays, but it does imply a necessary software architecture for them. Those higher-order metrics should sit on top of a reusable, queryable volume-dose representation with method provenance, convergence metadata, and possibly emulation modes for vendor-specific behaviour. That would let the same core engine support both “reference truth” mode and “commercial mimic” mode for cross-system audits. Near-extremum metrics such as D0.03cc should certainly be supported, but the paper warns against assuming they are automatically more stable than voxel- or point-like maxima.

#### 7d. Caveats and limitations

Not all findings generalise cleanly. The synthetic study used only **two** simple geometries, one gradient magnitude (**1 Gy/mm**), and only AP and SI directions. There were no rotated structures, no dose/contour offsets, no heterogeneous media, and no real dose-calculation uncertainty because the synthetic `RTDOSE` files were analytical constructs. Clinical translation is therefore suggestive, not definitive. In the clinical examples, variation also reflects image/structure resampling and import semantics, not purely DVH mathematics.

The reported commercial rankings are version-specific and partly dependent on vendor disclosures obtained by private communication. The precision metric itself also assumes the analytical DVH shape is known and is computed on **normalised** curves, so it does not directly capture volume imprecision; volume must be validated separately. Finally, for systems with rounded endcaps (Eclipse, partly RayStation), fitting the flat-ended analytical form is an approximation rather than a perfect model. A reference calculator should therefore use this paper as a high-value benchmark, but not as the final word on all anatomy or all clinical workflows.

### 8. Connections to other literature

- **Drzymala et al. (1991)** foundational DVH paper establishing the broader clinical and conceptual importance of dose-volume representations that this benchmarking work assumes.
- **Fraass et al. (1998; AAPM TG-53)** provides the QA context; Pepin et al. operationalise DVH-related TPS QA with a concrete analytical benchmark.
- **Nelms et al. (2015)** the direct precursor; Pepin et al. reuse Nelms’ analytical DICOM files but shift emphasis from accuracy alone to precision under discretisation.
- **Herman et al. (1992)** shape-based interpolation paper relevant to interpreting why Eclipse and RayStation behaved differently from right-prism systems between contour slices.
- **Ebert et al. (2010)** multi-TPS DVH comparison relevant to inter-system and multi-institution data transfer; Pepin adds analytical truth and vendor-method detail.
- **Kirisits et al. (2007)** analogous finding in brachytherapy that volume and DVH parameters vary across TPSs and with slice thickness/endcapping choices.
- **Stanley et al. (2021)** complementary analytical validation study for small SRS targets; Pepin extends the idea to cone/cylinder phantoms, precision bands, and explicit vendor algorithm comparison.

### 9. Data extraction table

**Table 9a. Analytical ground-truth objects used in the benchmark.**

| Structure | True volume (cc) | Dose gradient | Analytical Dmin (Gy) | Analytical Dmax (Gy) | Analytical mean dose (Gy) |
|---|---:|---|---:|---:|---:|
| Cone | 3.62 | AP | 4 | 28 | 16 |
| Cone | 3.62 | SI | 4 | 28 | 22 |
| Cylinder | 10.86 | AP | 4 | 28 | 16 |
| Cylinder | 10.86 | SI | 4 | 28 | 16 |

**Table 9b. Precision-band width for derived metrics, expressed as percent difference relative to the best-fit metric value (median [IQR], %).**

| System | Cone AP | Cone SI | Cylinder AP | Cylinder SI | All |
|---|---:|---:|---:|---:|---:|
| Eclipse | 2.86 [2.19-3.79] | 0.0470 [0.0217-0.143] | 2.79 [2.09-4.09] | 0.00733 [0.00237-0.0226] | 0.925 [0.022-2.86] |
| Mobius3D | 1.56 [1.27-2.01] | 3.46 [1.61-5.10] | 1.56 [1.19-2.25] | 4.63 [1.78-8.54] | 1.96 [1.27-4.15] |
| MIM Maestro | 0.627 [0.511-8.07] | 1.76 [1.01-3.77] | 0.626 [0.479-0.902] | 2.88 [1.26-5.98] | 0.902 [0.517-2.50] |
| ProKnow DS | 1.21 [0.829-1.77] | 0.773 [0.61-1.16] | 1.01 [0.736-1.79] | 1.34 [0.724-2.59] | 1.05 [0.699-1.79] |
| RayStation | 3.45 [2.33-6.81] | 2.16 [1.78-3.90] | 3.57 [2.15-6.84] | 3.61 [1.89-6.40] | 3.22 [1.95-5.86] |

**Table 9c. Clinical uncertainty across nine CT/structure/dose resampling combinations, reported as `100σ/μ` (%).**

| Structure | System | Mean dose uncertainty (%) | Maximum dose uncertainty (%) |
|---|---|---:|---:|
| Penile bulb | Eclipse | 6.17 | 0.85 |
| Penile bulb | Mobius3D | 5.05 | - |
| Penile bulb | MIM Maestro | 5.26 | 0.90 |
| Penile bulb | ProKnow DS | 6.51 | 0.25 |
| Penile bulb | RayStation | 4.98 | 0.37 |
| Cochlea | Eclipse | 1.10 | 0.43 |
| Cochlea | Mobius3D | 1.63 | - |
| Cochlea | MIM Maestro | 3.37 | 0.89 |
| Cochlea | ProKnow DS | 1.86 | 0.57 |
| Cochlea | RayStation | 1.73 | 0.53 |

### 10. Critical appraisal (100-200 words)

**Strengths:** Analytical ground truth for both volume and DVH shape; unusually detailed reverse-engineering of vendor methodology; inclusion of multiple commercial systems; and a genuinely useful precision concept that separates staircase uncertainty from conventional accuracy. The paper is especially valuable because it links observed errors to specific algorithmic choices rather than merely ranking black boxes.

**Weaknesses:** Only two synthetic geometries and two clinical structures were studied; most analyses are descriptive rather than statistically powered; some key implementation details rely on vendor private communication; and the clinical examples cannot disentangle all resampling/import effects from pure DVH computation. The Eclipse version reporting is internally inconsistent, and the precision method is limited to cases where the true DVH functional form is known.

**Confidence in findings:** **High** the central claim that DVH outputs vary materially with implementation and discretisation is strongly supported by the analytical phantoms and the cross-system methodology comparison, although exact cross-vendor ranking is version-specific.

**Relevance to reference DVH calculator:** **High** this is one of the clearest papers showing why a benchmark calculator must explicitly define geometry interpolation, endcaps, dose sampling, and metric extraction, and why validation must include analytical phantoms plus discretisation perturbations rather than single-case curve overlays.

---

<!-- Source: SUMMARY - Penoncello 2024 - Multicenter Multivendor Evaluation of DVH Creation Consistencies for 8 Commercial Radiation Therapy Dosimetric Systems.md -->

## Penoncello (2024) - Multicenter multivendor evaluation of dose volume histogram creation consistencies for 8 commercial radiation therapy dosimetric systems

### Executive summary

This multicentre multivendor study compared how **8 commercial radiotherapy dosimetric systems** generate structure volumes and DVH-derived metrics when given the **same imported DICOM dose and structure data**. The central result is that cross-system disagreement persists even when dose calculation itself is held effectively constant, indicating that **DVH construction and structure modelling remain major independent sources of uncertainty**. Across systems, **dosimetric metrics were generally close in median value**, but **volume reporting differed more substantially**, with mean structure-volume ratios relative to Eclipse ranging from **1.036 to 1.101**. All volumetric comparisons were significantly different from Eclipse at **P < .001**.

For reference DVH engine design, the most important conclusion is that **geometry handling matters at least as much as dose-grid sampling, and often more**. Small structures, steep dose gradients, stereotactic targets, and boundary-sensitive metrics such as **V100** and **D0.03 cc** were the most fragile. Dose-grid refinement from **2.5 mm to 1.25 mm** produced only modest overall improvement, whereas differences in **end-capping, between-slice interpolation, voxel inclusion rules, and histogram/binning implementation** plausibly explain much of the remaining spread.

The paper is highly relevant for a gold-standard open-source DVH calculator because it demonstrates that a benchmark tool must explicitly document and validate **structure rasterisation, partial-volume handling, interpolation, and exact metric extraction**, rather than only focusing on dose interpolation. It also argues strongly for validation using **small irregular structures in high-gradient clinical scenarios**, not only simple phantoms.

### 1. Bibliographic record

**Authors:** Gregory P. Penoncello, Molly M. Voss, Yu Gao, Levent Sensoy, Minsong Cao, Mark D. Pepin, Steven M. Herchko, Stanley H. Benedict, Todd A. DeWees, Yi Rong

**Title:** *Multicenter multivendor evaluation of dose volume histogram creation consistencies for 8 commercial radiation therapy dosimetric systems*

**Journal:** *Practical Radiation Oncology*

**Year:** 2024

**DOI:** [10.1016/j.prro.2023.09.009](https://doi.org/10.1016/j.prro.2023.09.009)

**Open access:** No

### 2. Paper type and scope

**Type:** Original research
**Domain tags:** D1 Computation | D2 Commercial systems
**Scope statement:** This paper compares how 8 commercial radiation oncology systems construct structure volumes and DVH-derived metrics when given the same imported DICOM dose and structure data, thereby isolating DVH generation from native dose-calculation differences. Its importance for a reference DVH engine is high because it shows that clinically relevant discrepancies persist across vendors even when the underlying 3D dose grid is nominally the same, with volumetric handling emerging as a larger source of disagreement than dose-grid refinement.

### 3. Background and motivation (150-300 words)

The paper addresses a long-recognised but insufficiently standardised problem: DVHs are central to plan evaluation, optimisation, and downstream clinical decision-making, yet there is no universal vendor guideline for how a commercial system should convert contours and dose grids into volumes and histogram endpoints. The authors emphasise that DVH outputs depend on many subtle implementation choices, including dose-grid sampling, structure resolution, voxel size, histogram binning, between-slice interpolation, and end-capping. Even if two systems display the “same” imported dose distribution, they may not report the same D0.03 cc, mean dose, V100, or structure volume.

Prior work had already shown inter-system variability, but mainly in narrower settings: synthetic structures with analytical ground truth, simple dose gradients, or limited vendor pairs. The paper explicitly positions itself as a clinical follow-on to the earlier synthetic-geometry comparison by Pepin and colleagues by moving from synthetic objects to irregular patient anatomies and sharp gradients such as stereotactic brain and head-and-neck cases. That gap matters for benchmark-engine design because many clinically consequential failures occur exactly where geometry and gradients are least forgiving: small organs adjacent to targets, thin end slices, and target edge coverage in hypofractionated plans. The authors’ premise is therefore not merely that commercial systems differ, but that these differences may alter whether a plan appears to satisfy a clinical constraint.

### 4. Methods: detailed technical summary (400-800 words)

This was a retrospective multivendor comparison using imported clinical data rather than recalculated plans. The study used dose files exported from Eclipse and imported them into 7 other systems: Pinnacle, RayStation, Elements, MIM, Mobius3D, ProKnow DS, and Velocity. The aim was explicitly **not** to compare dose-calculation algorithms; instead, the same DICOM dose and structure data were used across systems so that differences could be attributed primarily to DVH and volume construction. The paper contains a small internal inconsistency in case count: the abstract refers to **10 selected clinically treated plans**, whereas the Methods section states **11 different plans from 10 patients**. The analysed cases spanned brain, head and neck, lung, breast, spine, abdomen, and pelvis, with prescriptions ranging from **18 Gy in 1 fraction** to **70 Gy in 35 fractions**. CT slice thickness was **0.2 cm** for all scans except the stereotactic radiation therapy (SRT) plan, which used **0.1 cm**. All stereotactic body radiation therapy and SRT plans were created in Eclipse using volumetric modulated arc therapy and calculated with the AAA algorithm, version **15.6.1**. Photon energy, non-stereotactic delivery techniques, heterogeneity settings beyond what is implicit in AAA, and the exact plan/OAR list in supplementary Table E1 are [DETAIL NOT REPORTED].

Each plan was computed at two dose-grid sizes: **0.25 cm** (**2.5 mm**) and **0.125 cm** (**1.25 mm**). For each evaluated structure, the authors extracted clinically important dose-volume constraint points; for structures without specified clinical constraints they used **D0.03 cc (Gy), volume, and mean dose**. OARs were included only when close to target and receiving a relevant dose. In total, **812 data points per system** were collected, of which **570 were dosimetric** and **242 volumetric**. Exact endpoint extraction was not uniform across software: Eclipse, Velocity, Mobius, RayStation, and ProKnow allowed direct extraction via templates or scripts, whereas Pinnacle, MIM, and Elements sometimes required interpolation between the two nearest DVH points. The paper does not explicitly state whether exported histograms were cumulative or differential, although the reported clinical endpoints strongly imply routine cumulative DVH usage; this remains [DETAIL NOT REPORTED] as an explicit implementation detail.

A major technical contribution is Table 1, which catalogues vendor-specific DVH construction behaviour. Eclipse supersampled the radiotherapy dose (`RD`) grid to **100,000 points** within the structure, used shape-based trilinear interpolation between slices, and created **rounded endcaps** via shape-based interpolation. RayStation also used shape-based trilinear interpolation between slices, but implemented a relative-volume voxel grid with axial spacing subsampled **3×** from dose-grid resolution and a fixed **400-bin** DVH. Elements used an adaptive dose/object representation with minimum dose voxel **0.3 mm³**, distance-field interpolation for voxel objects, and effectively avoided classic endcaps because contours can exist in 3D space. MIM, Mobius3D, ProKnow DS, and Velocity used variants of right-prism or half-slice extension logic; Pinnacle used a particularly coarse inclusion rule in which any voxel touched by the structure is considered part of it, with ROI volume computed as voxel size × (internal voxels + 0.5 × edge voxels). Mobius3D used a fixed **10 cGy** histogram resolution, whereas Eclipse used **100,000 bins**, Pinnacle allowed up to **10,000 bins**, ProKnow DS used dynamic **1000 bins**, and Velocity used at least **1024** and up to **4096 bins**. Importantly, many of these implementation details were compiled from reference guides and private communication, which means they were not independently benchmarked within the paper. The actual user-selected export/binning settings used during this experiment are [DETAIL NOT REPORTED].

For analysis, each reported metric was normalised to the corresponding Eclipse value, making Eclipse equal to **1.000** by definition. This was a convenience baseline, not a physical gold standard. Pairwise comparisons used the **Wilcoxon rank-sum test** with Bonferroni correction. A multivariable regression model, with gamma-distributed outcome, predicted the value-to-Eclipse ratio using system as a dummy variable and adjusted for **plan, grid size, and distance to target centre** the exact definition of distance to target centre is [DETAIL NOT REPORTED]. To avoid division by zero, all zero-valued metrics were replaced with **0.01** before normalisation. This choice is methodologically important because it inflates ratio ranges when the denominator is near zero.

The authors acknowledged several limitations. DICOM export/import may degrade structure and dose resolution before the receiving system re-samples them, which could bias all non-Eclipse systems relative to Eclipse. Some endpoints had to be estimated by interpolating between adjacent DVH points because exact values were not directly available in all software. Finally, there was **no absolute ground truth** for patient structure volumes or clinical endpoint values; the study therefore measures **inter-system consistency**, not absolute accuracy. The authors also note that a complementary future study would generate plans natively in the other systems rather than always starting from Eclipse.

### 5. Key results: quantitative (300-600 words)

Across **all 812 points per system** (dose metrics plus structure volumes), all non-Eclipse systems had mean ratios above 1.0 relative to Eclipse: Elements **1.028 ± 0.166**, MIM **1.035 ± 0.130**, Mobius3D **1.062 ± 0.272**, Pinnacle **1.057 ± 0.226**, ProKnow DS **1.045 ± 0.244**, RayStation **1.043 ± 0.358**, and Velocity **1.037 ± 0.161**. The overall pooled non-Eclipse mean was **1.044 ± 0.234**. Medians were much closer to unity, ranging only from **1.002 to 1.007**, which is the basis for the abstract statement that all systems were within **1.0%** of one another in median values despite systematic differences from Eclipse. Pairwise comparisons among non-Eclipse systems showed few significant differences in the main paper text; the specific significant pairs reported for all points were Pinnacle versus Elements and RayStation versus Velocity, with other pairwise comparisons non-significant at **P > .05**. Exact P values are in supplementary tables and are [DETAIL NOT REPORTED] in the main article.

For **dosimetric points only** (**N = 570** per system), mean ratios were: Velocity **1.022 ± 0.157**, Elements **1.024 ± 0.193**, MIM **1.026 ± 0.142**, ProKnow DS **1.033 ± 0.237**, Pinnacle **1.038 ± 0.173**, RayStation **1.046 ± 0.425**, and Mobius3D **1.050 ± 0.244**. All dosimetric medians were **1.000**, implying that central tendency was extremely close across systems and that much of the mean spread came from tails/outliers. RayStation showed the largest variability (**SD 0.425**), whereas MIM showed the smallest (**SD 0.142**). The authors state that Eclipse differed significantly from Pinnacle and RayStation, while Pinnacle also differed from Velocity and Elements; exact P values were again relegated to supplementary material. The ranges were very wide, up to **8.000** for RayStation and **5.800** for ProKnow DS, almost certainly reflecting the ratio normalisation strategy for near-zero denominators.

Figure 3 adds clinically useful context by showing that sensitivity depends strongly on metric type and geometry. On the page 8 boxplots, the stereotactic **optic chiasm D0.03 cc** is approximately stable across grid sizes at around **22.2-22.3 Gy**, whereas **small brain PTV V100** falls dramatically from roughly **97-99%** at **0.125 cm** to about **76-78%** at **0.25 cm**. By contrast, for a large head-and-neck target, **V100** shifts only modestly, from roughly **89.5-90.0%** to **87.9-88.5%**, and the **mandible D0.03 cc** shifts by only about **0.1 Gy**. This figure supports the authors’ claim that small structures and edge-coverage metrics in sharp gradients are the most fragile endpoints.

For **volumetric points only** (**N = 242** per system), differences were materially larger. Mean ratios were Elements **1.036 ± 0.062**, RayStation **1.037 ± 0.075**, MIM **1.057 ± 0.091**, Velocity **1.072 ± 0.166**, ProKnow DS **1.073 ± 0.259**, Mobius3D **1.091 ± 0.328**, and Pinnacle **1.101 ± 0.315**. Thus, average structure-volume differences relative to Eclipse ranged from **+3.6%** to **+10.1%**, with medians from **1.007** to **1.030**. All volumetric comparisons were statistically different from Eclipse at **P < .001**. The structures spanned a very wide size range, **0.15 to 3100 cc**. The corresponding figure shows that the optic chiasm has only about **1.1-1.2 cc** absolute volume but with conspicuous relative spread, whereas the bladder (~**121-123 cc**) and total lung (~**2360-2415 cc**) show larger absolute but smaller relative differences, reinforcing that small structures are the most vulnerable to end-cap and interpolation choices.

Dose-grid refinement had only a modest overall effect. For dosimetric points, the pooled non-Eclipse mean ratio changed from **1.036 ± 0.225** at **0.25 cm** to **1.033 ± 0.257** at **0.125 cm**, only a **0.003** absolute reduction. System-specific changes were mixed: agreement with Eclipse improved for Elements (**1.031 → 1.017**), Mobius3D (**1.052 → 1.047**), Pinnacle (**1.040 → 1.037**), RayStation (**1.056 → 1.036**), and Velocity (**1.023 → 1.022**), but worsened for MIM (**1.022 → 1.030**) and ProKnow DS (**1.025 → 1.040**). Most grid-size comparisons were non-significant; the authors specifically note that MIM did not significantly worsen with finer grid (**P = .776**), and that Mobius3D, Pinnacle, and RayStation were significantly different from Eclipse at **0.25 cm** but not at **0.125 cm**.

### 6. Authors' conclusions (100-200 words)

The authors conclude that substantial inter-system variation exists in clinically relevant DVH and volume reporting across 8 commercial platforms, with Eclipse generally returning lower values than the others. They further conclude that reducing dose-grid size from **0.25 cm** to **0.125 cm** produces only small, statistically non-significant improvement overall, implying that geometric modelling of structures in 3D is more important than dose-grid refinement for DVH consistency.

That interpretation is well supported for **volume** differences: all systems were significantly different from Eclipse and the mean volumetric offsets were clearly larger than the dose-metric offsets. It is also reasonably supported for the weak grid-size effect. The stronger causal attribution to “3D modelling of the structure” is plausible, but somewhat extrapolative because several factors co-vary across vendors: end-capping, between-slice interpolation, binning resolution, coordinate-space conversion, and DICOM import behaviour were not experimentally isolated one by one.

### 7. Implications for reference DVH calculator design (300-600 words)

#### 7a. Algorithm and implementation recommendations

A reference calculator should treat **structure modelling as a first-class problem**, not a preprocessing footnote. This paper shows dose-only mean differences typically around **+2.2% to +5.0%** relative to Eclipse, but volume-only differences of **+3.6% to +10.1%**, with all volumetric comparisons significant at **P < .001**. The engine should therefore implement explicit, documented, and testable handling of: between-slice interpolation, end-caps, partial-volume occupancy, voxel/mesh intersection, and coordinate transforms. A binary voxel-centre rule or “any touched voxel counts” rule should be avoided as a default because those choices align with the larger cross-vendor volume spreads seen here.

The calculator should also decouple **geometry volume** from **dose-sampled DVH volume** and report both if they differ, because Elements explicitly distinguishes display volume from DVH dose-voxel volume. Histogram binning should be very fine or bypassed entirely by computing metrics directly from sorted dose-volume samples; fixed coarse schemes such as **10 cGy** bins or **400 bins** are undesirable in a benchmark tool. For extrema, support D0.03 cc and arbitrary `Dx cc`/Dx% as native quantile queries rather than inferring them from exported display points. Given that vendor medians were generally within **1%** for dose metrics, a reference implementation intended as a gold-standard comparator should aim to resolve differences well below that scale.

#### 7b. Validation recommendations

This paper argues strongly for a **two-tier validation programme**: analytical/synthetic phantoms plus clinically realistic cases. Synthetic ground-truth geometries remain essential, but clinical failure modes here are clearly driven by small irregular structures in steep gradients. Benchmark cases should therefore include at minimum: a small optic-chiasm-like OAR abutting an SRT target, a small brain PTV with edge dose fall-off, a mandible-like OAR near high-dose head-and-neck gradients, and medium/large organs such as bladder and lung to separate relative from absolute volume error. Slice thickness should vary, for example **1 mm** and **2 mm**, and dose grids should vary, at least **1.25 mm** and **2.5 mm**.

Validation should not rely only on ratios, because this study’s `0.01` replacement for zero demonstrates how near-zero denominators can create misleading extremes. For near-zero metrics, absolute differences in Gy or cc are preferable. Public benchmark datasets should also test DICOM round-trip robustness, because this paper’s clinically realistic workflow includes export/import degradation as part of the real-world problem. Any systematic volume bias above about **1-2%** on analytical objects, or dose-metric bias above about **1%** in controlled tests, should be treated as a warning sign given the vendor spreads observed here. The paper itself does not provide a public dataset.

#### 7c. Extensibility considerations

The cleanest extension path is to build the engine around a **fractional-occupancy geometry core** that can serve not only cumulative DVHs but also dose-surface histograms, dose-mass histograms, density-weighted metrics, and biological overlays such as EUD/gEUD. This study shows that the hardest problem is robust mapping between structure geometry and sampled fields; once that is solved transparently, the same data structures can support arbitrary Dx, Vx, surface, or mass-weighted queries. Support for both absolute volume (cc) and relative volume (%) should be native, and the API should expose exact metric queries rather than requiring interpolation between displayed histogram points.

#### 7d. Caveats and limitations

The main caveat is that Eclipse is **not** a ground truth. All conclusions are relative to an Eclipse-origin workflow, and the authors themselves note that DICOM export/import may preferentially disadvantage receiving systems. The algorithm descriptions also come partly from vendor documents and private communication, and the exact user-selected histogram/export settings are not fully reported. Finally, only specific software versions were tested, and the study does not isolate end-capping from binning from resampling. A reference calculator should therefore avoid reproducing any one vendor’s behaviour as a normative target; it should instead target traceable agreement with analytical geometry and explicitly document any assumptions it makes that commercial systems usually hide.

### 8. Connections to other literature

- **Drzymala et al. (1991)** Foundational paper establishing the role and interpretation of DVHs; this study relies on that framework for why small algorithmic differences matter clinically.
- **Fraass et al. (1998) (AAPM TG-53)** Recommended treatment-planning QA, but not a modern cross-vendor standard for DVH construction; that gap motivates the present work.
- **Panitsa et al. (1998)** Early quality-control work on DVH computation characteristics in 3D treatment-planning systems; this paper is a contemporary multivendor extension of the same concern.
- **Ebert et al. (2010)** Earlier multi-TPS DVH comparison work; Penoncello et al. broadly agree that dose differences are generally smaller than volume differences.
- **Nelms et al. (2015)** Provided analytical datasets and methods for verifying DVH calculations against ground truth; Penoncello et al. move from synthetic/analytical objects toward clinical cases.
- **Eaton and Alty, 2017** Studied treatment-planning-system dependence of volume calculation for small stereotactic targets; this study is consistent with the finding that small structures are especially sensitive.
- **Kim et al. (2018)** Compared clinical structure dose/volume discrepancies in two systems; Penoncello et al. generalise that question to 8 systems and more diverse clinical geometries.
- **Pepin et al. (2022)** The most direct precursor, comparing 5 systems using synthetic structures; the present paper is essentially the clinically realistic sequel.

### 9. Data extraction table

**Table 9.1. Ratio to Eclipse by system (Table 2 extraction).** Values shown as **mean (SD)** with **median** in brackets.

| System | All points | Dosimetric only | Volumetric only |
|---|---:|---:|---:|
| Elements | 1.028 (0.166) [1.002] | 1.024 (0.193) [1.000] | 1.036 (0.062) [1.008] |
| MIM | 1.035 (0.130) [1.003] | 1.026 (0.142) [1.000] | 1.057 (0.091) [1.016] |
| Mobius3D | 1.062 (0.272) [1.003] | 1.050 (0.244) [1.000] | 1.091 (0.328) [1.016] |
| Pinnacle | 1.057 (0.226) [1.007] | 1.038 (0.173) [1.000] | 1.101 (0.315) [1.030] |
| ProKnow DS | 1.045 (0.244) [1.003] | 1.033 (0.237) [1.000] | 1.073 (0.259) [1.017] |
| RayStation | 1.043 (0.358) [1.002] | 1.046 (0.425) [1.000] | 1.037 (0.075) [1.007] |
| Velocity | 1.037 (0.161) [1.002] | 1.022 (0.157) [1.000] | 1.072 (0.166) [1.016] |

**Table 9.2. Grid-size sensitivity for dosimetric points only (Table 3 extraction).**

| System | 0.125 cm mean (SD) | 0.25 cm mean (SD) | Finer grid effect vs Eclipse |
|---|---:|---:|---|
| Elements | 1.017 (0.262) | 1.031 (0.187) | Improved agreement |
| MIM | 1.030 (0.173) | 1.022 (0.104) | Worse agreement |
| Mobius3D | 1.047 (0.245) | 1.052 (0.243) | Improved agreement |
| Pinnacle | 1.037 (0.190) | 1.040 (0.154) | Improved agreement |
| ProKnow DS | 1.040 (0.311) | 1.025 (0.124) | Worse agreement |
| RayStation | 1.036 (0.425) | 1.056 (0.425) | Improved agreement |
| Velocity | 1.022 (0.142) | 1.023 (0.172) | Slight improvement |

**Additional extracted quantitative findings:**
- Volume-only comparisons for **all systems** were significantly different from Eclipse at **P < .001**.
- For all-points comparisons, the main text reports significant pairwise differences only for Pinnacle vs Elements and RayStation vs Velocity; other non-Eclipse pairwise comparisons were **P > .05**.
- Grid-size differences were mostly non-significant; MIM worsening at finer grid was specifically reported as **P = .776**. Exact supplementary-table P values are [DETAIL NOT REPORTED] in the main text.

### 10. Critical appraisal (100-200 words)

**Strengths:** This is one of the more clinically relevant multivendor DVH consistency studies because it uses real patient plans across diverse anatomical sites and sharp gradients, while holding the imported dose data constant to suppress dose-engine confounding. Table 1 is especially valuable because it documents vendor geometry/binning behaviour in a way most papers do not.

**Weaknesses:** There is no absolute truth standard, all comparisons are anchored to Eclipse, and the DICOM export/import pathway may itself generate asymmetry. Some endpoint values were interpolated from neighbouring histogram points, exact plan details are partly hidden in supplementary material, and the paper contains a minor inconsistency about whether **10** or 11 plans were analysed. The use of a `0.01` substitute for zero also makes ratio ranges difficult to interpret.

**Confidence in findings:** **Medium-High.** The qualitative pattern; dose metrics relatively close, volume metrics materially less consistent; is robust and internally consistent. Confidence is reduced by the absence of an external gold standard and incomplete access to supplementary statistical detail.

**Relevance to reference DVH calculator:** **High.** This paper directly identifies the commercial failure modes a benchmark DVH engine must expose: end-capping, slice interpolation, partial-volume handling, histogram resolution, and small-structure behaviour in steep gradients.

---

<!-- Source: SUMMARY - Grammatikou 2025 - Validation of dose-volume calculation accuracy for intracranial stereotactic radiosurgery with VMAT using analytical and clinical treatment plans.md -->

## Grammatikou (2025) - Validation of dose-volume calculation accuracy for intracranial stereotactic radiosurgery with volumetric-modulated arc therapy using analytical and clinical treatment plans

### Executive Summary

This paper proposes a commissioning-style framework for validating DVH accuracy in intracranial SRS, and applies it to Monaco 6.1.2.0 for single-isocentre VMAT of multiple brain metastases. Validation combined an analytical benchmark of spherical targets and known dose distributions with an independent in-house MATLAB calculation for **15 patients** and **68 PTVs** spanning **6-30 mm** diameter.

At the reference condition of **1 mm ST** and **1 mm DG**, Monaco performed very well. Against analytical data, average percentage differences were within **2.1%** overall and much smaller for spheres **≥7 mm**. Against the in-house clinical reference, **100%** of PTV and isodose volumes were within **±3%**, with essentially ideal linear fits (**R² = 1**). DG coarsening mattered more than ST coarsening. ST changes were usually not significant, but >**5%** deviations still appeared for selected small lesions, particularly when isodose volumes were **<1 cc** for **1.5 mm ST** and **<7 cc** for **2 mm ST**. By contrast, both **2 mm** and **3 mm DG** significantly altered most indices; **2 mm DG** was acceptable only once PTV diameter exceeded **20 mm**, while **3 mm DG** remained problematic even for **30 mm** lesions. GI was the most sensitive metric and D95 the least sensitive. For a reference DVH calculator, the paper strongly supports **1 mm / 1 mm** as the benchmark SRS configuration and argues against `3 mm` dose grids for high-gradient intracranial SRS.

### 1. Bibliographic record

- **Authors:** Ioanna Grammatikou, Alexandra Drakopoulou, Antigoni Alexiou, Georgios Pissakas, Pantelis Karaiskos, Vasiliki Peppa
- **Title:** Validation of dose-volume calculation accuracy for intracranial stereotactic radiosurgery with volumetric-modulated arc therapy using analytical and clinical treatment plans
- **Journal:** Journal of Applied Clinical Medical Physics
- **Year:** 2025
- **DOI:** [10.1002/acm2.70235](https://doi.org/10.1002/acm2.70235)
- **Open access:** Yes

### 2. Paper type and scope

- Type: Original research
- Domain tags (one or more): D1 Computation | D2 Commercial systems
- Scope statement: The paper develops a practical procedure to quantify spatial discretisation errors in DVH-related calculations for intracranial SRS. It validates Monaco against analytical ground truth and an independent in-house clinical reference, then derives target-size-dependent recommendations for CT slice thickness and dose-grid settings in multi-metastasis VMAT.

### 3. Background and motivation (150-300 words)

DVH values depend not only on dose calculation but also on how a TPS reconstructs structures from contours and samples the dose field. Relevant error sources include contour voxelisation, end-capping, inter-slice interpolation, and dose-grid resolution. These effects are amplified in intracranial SRS because targets are small, conformity is high, gradients are steep, and clinically important metrics can shift with very small volume errors.

Earlier work had already shown substantial DVH variability between TPSs and between discretisation settings, with large deviations in some high-gradient cases. However, SRS-specific evidence was limited. Published studies had focused mainly on dose-grid size, whereas the effect of CT slice thickness on DVH accuracy in intracranial SRS had scarcely been studied. Existing guidance recommending approximately **1-2 mm** DG and about **1-1.5 mm** ST is necessarily generic and does not establish what is actually acceptable for a given platform.

The study therefore links analytical ground truth to real VMAT plans for multiple brain metastases and asks when coarser ST or DG settings become clinically unsafe. That combination is directly relevant to design and validation of an independent reference DVH engine.

### 4. Methods: detailed technical summary (400-800 words)

This was a single-institution technical validation study with retrospective clinical data, using analytical validation followed by clinical validation and sensitivity testing.

For the analytical stage, the authors imported the Stanley et al. benchmark DICOM dataset into Monaco 6.1.2.0. The synthetic CT voxel size was **0.6 × 0.6 × 1 mm³** and the analytical dose matrices were **1 × 1 × 1 mm³**. The benchmark contained spherical targets spanning **3-20 mm** diameter with known analytical volumes and analytically defined dose distributions. Using **1 mm ST** and **1 mm DG**, Monaco-reported target volumes and the enclosed volumes for the **100%** and **50%** isodose levels (V100%, V50%) were extracted through the TPS DVH tool. Reference structure volume was `πD³/6`; reference isodose volumes came from the Stanley dose equation. Evaluation regions around each sphere were bounded where dose was **≥25%** of the target dose.

For the clinical stage, the authors retrospectively selected **15 patients** with multiple brain metastases, giving **68 PTVs**. CT was acquired at **1 mm ST**. Each patient received a single-isocentre, five-non-coplanar-arc VMAT plan on an `Infinity` linac with `Agility` MLC (**160 leaves**, **5 mm** leaf width at isocentre). Prescription was **30 Gy in 5 fractions**, with at least **95%** PTV coverage intended. Dose-to-medium in medium (`Dm,m`) was computed with the XVMC Monte Carlo engine using **1 mm isotropic DG**. PTVs were grouped by maximum axial diameter into **6, 10, 15, 20, 25, and 30 mm** classes; median PTV volumes were **0.52, 1.11, 2.47, 5.17, 7.03, and 12.31 cc**.

Clinical validation used Monaco-reported PTV volumes and isodose volumes at **110%, 100%, 98%, 95%, 80%, and 50%** of prescription dose. These were derived per target using **1.5 cm** evaluation shells to avoid contamination from neighbouring lesions. Dose was normalised so that **100% isodose = prescription dose**.

Because analytical ground truth is unavailable for these plans, the authors built an independent MATLAB R2020b reference using `inpolygon`. The in-house MATLAB tool computed isodose volumes by summing all dose voxels exceeding the threshold dose (binary voxel inclusion on the native dose grid) and structure volumes as the sum of contour areas multiplied by slice thickness. That code was first benchmarked against the analytical Stanley dataset, then used to generate the **1 mm ST / 1 mm DG** clinical reference. TPS-versus-reference agreement was assessed with linear fits `y = p1 x + p2`.

To study discretisation effects, the original plans were recalculated with **2 mm** and **3 mm** isotropic DG. Slice-thickness effects were studied by resampling the original **1 mm** CTs to **1.5 mm** and **2 mm** ST while preserving in-plane resolution; the authors used a common DICOM `Image Position Patient` origin, copied the original PTVs to the resampled image sets, and recalculated dose with **1 mm DG**. The CT resampling kernel is [DETAIL NOT REPORTED].

Endpoints included `Vdose(eval)/Vdose(ref)` as a function of `Vdose(ref)`, analysed with Spearman correlation. Clinical indices were D95, V30Gy, Paddick conformity index `CI = (TV_PIV)² / (TV × PIV)`, and gradient index `GI = V50%Rx / V100%Rx`. CI and GI were manually derived per lesion rather than taken from Monaco’s native conformity metric.

Statistical testing used the paired Wilcoxon signed-rank test with **p ≤ 0.05**. Power analysis used `G*Power 3.1.9.7` with **α = 0.05** and **1 − β = 0.8**. Several implementation details important to a reference DVH calculator are not given: DVH bin width [DETAIL NOT REPORTED], cumulative versus differential storage [DETAIL NOT REPORTED], exact end-capping and inter-slice interpolation in Monaco [DETAIL NOT REPORTED], and in-house partial-volume handling [DETAIL NOT REPORTED]. The discussion does, however, state that Monaco sub-divides CT voxels larger than **1 mm³**, then further subdivides them into “mini-voxels” whose volume is at least **27× smaller** than the dose-voxel volume.

### 5. Key results: quantitative (300-600 words)

Against the analytical benchmark, Monaco was highly accurate for spheres **≥7 mm**. Mean percentage differences versus analytical values were approximately **−0.31% to 0.02%** for target volume, **0.05% to 0.15%** for V100%, and **0.04% to 0.11%** for V50%. The difficult **3 mm** spheres exposed the expected small-volume instability: mean target-volume difference was **2.14%** with range **−8.04% to 6.10%** V100% had mean **0.83%** but range **−23.72% to 17.89%** V50% was much more stable at mean **0.17%**.

For clinical **1 mm ST / 1 mm DG** data, Monaco and the in-house reference were almost perfectly concordant. For PTV volumes, the fit was **R² = 1**, `p1 = 1.0010 ± 0.0003`, `p2 = 0.0008 ± 0.0025`; for isodose volumes, **R² = 1**, `p1 = 1.0000 ± 0.0003`, `p2 = 0.0096 ± 0.0014`. **100%** of clinical PTV and isodose volumes were within **±3%** of the in-house reference. Even for volumes **<1 cc**, discrepancies stayed within **2.3%** for PTVs and **1.7%** for isodose volumes.

Slice-thickness changes produced weak, non-monotonic behaviour. For **1.5 mm** and **2 mm ST**, the correlation between `Vdose(eval)/Vdose(ref)` and `Vdose(ref)` was **ρ < 0.04, p > 0.10**. Median isodose-volume ratios were **1.003 [0.972, 1.059]** for **1.5 mm ST** and **1.000 [0.782, 1.080]** for **2 mm ST**. However, >**5%** differences occurred in **9.4%** of points with `Vdose(ref) < 1 cc` (approximately diameter **<12 mm**) for **1.5 mm ST**, and in **10.6%** of points with `Vdose(ref) < 7 cc` (approximately diameter **<24 mm**) for **2 mm ST**. Most Wilcoxon comparisons were not significant, although Table 3 reports small but significant CI differences for **2 mm ST** at **15 mm (p = 0.01)**, **25 mm (p = 0.02)**, and **30 mm (p = 0.02)**. D95 was comparatively stable; the largest median reduction was about **−2.1%** for the **6 mm** class at **2 mm ST**.

Dose-grid coarsening produced a clear size-dependent bias. `Vdose(eval)/Vdose(ref)` increased towards 1 with increasing reference isodose volume, with **ρ = 0.53 (p < 0.001)** for **2 mm DG** and **ρ = 0.58 (p < 0.001)** for **3 mm DG**. The reported power-law fits were `y = -0.089 x^-0.664 + 1.003` for **2 mm DG** and `y = -0.228 x^-0.618 + 1.010` for **3 mm DG**. The ratio exceeded **0.95** only when isodose volume was **>2 cc** (diameter **>16 mm**) for **2 mm DG**, and **>10 cc** (diameter **>27 mm**) for **3 mm DG**.

Clinical indices followed the same pattern. V30Gy and D95 were underestimated, while CI and especially GI were overestimated. For the **6 mm** class, GI rose from **7.81** at **1 mm DG** to **8.52** at **2 mm DG** and **10.26** at **3 mm DG**, i.e. approximately **+9.1%** and **+31.4%** relative to the 1 mm reference. For the same class, CI changed from **0.63** to **0.68** and **0.74** (**+7.9%**, **+17.5%**), while V30Gy fell from **98.49%** to **95.02%** and **92.55%** (**−3.5%**, **−6.0%**). For PTV diameters **>20 mm**, median differences with **2 mm DG** were <**5%**, but **3 mm DG** still gave >**5%** median GI bias even at **30 mm**. The authors report that **1 mm DG** required approximately **14×** and **20×** longer calculation time than **2 mm** and **3 mm DG**, respectively; absolute runtimes were [DETAIL NOT REPORTED].

### 6. Authors' conclusions (100-200 words)

The authors conclude that Monaco can calculate structure and isodose volumes accurately for intracranial SRS when both CT slice thickness and dose grid are **1 mm**. In their VMAT cohort, DG variation was the dominant source of discretisation error, more important than ST variation, and the impact increased as target and isodose volumes decreased. They therefore recommend maintaining **1 mm ST** and **1 mm DG** for small lesions, but allowing **1.5-2 mm ST** and **2 mm DG** as practical compromises when PTV diameter is **>20 mm**. They judge **3 mm DG** clinically unacceptable because conformity- and gradient-related indices remain materially biased even for the largest lesions studied.

That interpretation is well supported for Monaco in this setting. The broader QA argument is also reasonable, but the numerical thresholds are TPS-specific rather than universal.

### 7. Implications for reference DVH calculator design (300-600 words)

#### 7a. Algorithm and implementation recommendations

A reference-quality intracranial SRS DVH calculator should use **1 mm ST / 1 mm DG** as its benchmark mode. This paper shows that coarse DGs distort volume-based metrics before they substantially distort D95. The implementation should therefore emphasise accurate sub-voxel boundary handling for both structures and isodose volumes, not simple voxel-centre inclusion. GI, CI, and per-threshold isodose volumes should be first-class outputs, because GI was the most sensitive discriminator here. The engine should also support per-lesion evaluation shells so that local conformity and spill can be assessed in multi-target SRS.

#### 7b. Validation recommendations

Validation should combine analytical and clinical tests. Analytical tests should include spheres **3-20 mm** with known radial dose fields, scoring target volume, V100%, and V50%. Clinical tests should include multi-metastasis plans and per-lesion outputs at **110%, 100%, 98%, 95%, 80%, and 50%** isodose, plus D95, V30Gy, CI, and GI. A practical target suggested by this paper is that a reference engine on **1 mm** data should keep clinical PTV and isodose volumes within about **±3%** of an independent high-accuracy implementation. Small-volume stress tests are mandatory: lesions or isodose regions **<1 cc** expose ST sensitivity, while the **2 cc** and **10 cc** isodose-volume levels separated acceptable from unacceptable behaviour for **2 mm** and **3 mm DG**, respectively.

#### 7c. Extensibility considerations

The calculator should expose generic isodose-volume and shell-based APIs, not only cumulative DVHs. It should also support uncertainty annotation for very small targets, where discretisation instability is intrinsic even with fine grids. A clean separation between geometry representation and dose sampling would ease extension to OAR-centric local-volume queries, dose-surface histograms, gEUD-style summaries, or re-irradiation support.

#### 7d. Caveats and limitations

The paper’s thresholds are not vendor-agnostic. Monaco uses proprietary contour handling and supersampling, and the observed acceptability of **2 mm** settings above **20 mm** may not transfer to other TPSs, MLCs, or contour engines. DG changes in this study altered both the dose calculation and the subsequent DVH sampling, so the measured bias is a compound effect. The ST analysis used copied contours rather than re-delineation, so it does not capture the full clinical effect of thicker imaging slices. OAR dosimetry, lesions **<6 mm**, and multi-institution generalisability remain untested.

### 8. Connections to other literature

- **Stanley (2021):** Supplies the analytical radiosurgery DICOM benchmark used here; this paper extends that work to real VMAT plans and slice-thickness effects.
- **Nelms (2015):** Foundational methodology for verifying DVH calculations against analytical values; Grammatikou et al. implement that logic in an SRS commissioning context.
- **Pepin (2022):** Multi-system DVH precision study; useful for placing Monaco’s performance in wider inter-system context.
- **Ebert (2010):** Earlier multi-TPS DVH comparison showing that implementation details matter; this paper reinforces that specifically for small SRS targets.
- **Ma (2012):** Radiosurgery contour-volume reliability study; relevant because some failures here are geometric rather than purely dosimetric.
- **Srivastava (2016):** Examined slice-thickness effects in IMRT; this paper shows why the question is more demanding in intracranial SRS.
- **Karen (2017):** Dose-grid effects in spine stereotactic radiotherapy; complementary evidence that coarse grids distort high-gradient metrics.

### 9. Data extraction table

**Table 9a. Analytical benchmark accuracy at 1 mm ST / 1 mm DG (mean percentage difference versus analytical values)**

| Sphere diameter (mm) | TPS target volume (%) | TPS V100% (%) | TPS V50% (%) | In-house target volume (%) | In-house V100% (%) | In-house V50% (%) |
|---|---:|---:|---:|---:|---:|---:|
| 3 | 2.14 | 0.83 | 0.17 | 1.35 | 0.69 | 0.00 |
| 7 | -0.31 | 0.15 | 0.11 | -0.18 | 0.00 | 0.00 |
| 10 | 0.07 | 0.05 | 0.11 | 0.03 | 0.00 | 0.00 |
| 15 | -0.02 | 0.06 | 0.08 | -0.01 | 0.00 | 0.00 |
| 20 | 0.02 | 0.10 | 0.04 | 0.02 | 0.05 | -0.03 |

**Table 9b. Size-dependent discretisation thresholds extracted from isodose-volume analysis**

| Perturbation relative to 1 mm reference | Central result | Region where >5% relative error emerged | Statistical pattern |
|---|---|---|---|
| 1.5 mm ST | `Vdose(eval)/Vdose(ref)` median **1.003 [0.972, 1.059]** | **9.4%** of points with `Vdose(ref) < 1 cc` (diameter **<12 mm**) | **ρ < 0.04**, **p > 0.10** |
| 2.0 mm ST | `Vdose(eval)/Vdose(ref)` median **1.000 [0.782, 1.080]** | **10.6%** of points with `Vdose(ref) < 7 cc` (diameter **<24 mm**) | **ρ < 0.04**, **p > 0.10** |
| 2.0 mm DG | `-0.089 x^-0.664 + 1.003` | Ratio >**0.95** only when `Vdose(ref) > 2 cc` (diameter **>16 mm**) | **ρ = 0.53**, **p < 0.001** |
| 3.0 mm DG | `-0.228 x^-0.618 + 1.010` | Ratio >**0.95** only when `Vdose(ref) > 10 cc` (diameter **>27 mm**) | **ρ = 0.58**, **p < 0.001** |

**Table 9c. Median percentage change in selected DVH indices for coarser dose grids, relative to 1 mm DG**

| PTV diameter (mm) | ΔV30Gy 2 mm (%) | ΔCI 2 mm (%) | ΔGI 2 mm (%) | ΔD95 2 mm (%) | ΔV30Gy 3 mm (%) | ΔCI 3 mm (%) | ΔGI 3 mm (%) | ΔD95 3 mm (%) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 6 | -3.52 | 7.94 | 9.09 | -1.38 | -6.03 | 17.46 | 31.37 | -4.27 |
| 10 | -0.98 | 5.63 | 7.12 | -1.10 | -3.70 | 11.27 | 17.15 | -3.16 |
| 15 | -0.92 | 3.85 | 6.12 | -0.75 | -3.33 | 6.41 | 13.71 | -2.39 |
| 20 | -0.60 | 1.19 | 3.29 | -0.83 | -2.21 | 2.38 | 10.12 | -2.21 |
| 25 | -1.47 | 1.18 | 3.39 | -0.91 | -3.75 | 2.35 | 10.16 | -2.39 |
| 30 | -1.00 | 1.15 | 2.73 | -0.47 | -3.28 | 1.15 | 7.10 | -1.34 |

Percent changes in Table 9c are calculated from the paper’s reported medians, using the **1 mm DG median as denominator**.

### 10. Critical appraisal (100-200 words)

- **Strengths:** Strong two-stage design using both analytical ground truth and clinical VMAT data; independent in-house reference; explicit lesion-size stratification; and inclusion of sensitive SRS metrics such as CI and GI, not only D95.
- **Weaknesses:** Single vendor, single institution, target-only analysis, exclusion of lesions **<6 mm**, and incomplete reporting of some DVH implementation details. DG changes confound dose calculation and DVH sampling. The text also contains minor inconsistencies, including the conclusion’s use of “PI”, the abstract’s claim of no ST-related statistical differences, and a discussion statement that appears to assign a **−4.4%** D95 change to **2 mm DG** although Table 4 suggests **3 mm DG**.
- **Confidence in findings:** Medium. The quantitative trends are convincing, but the study is TPS-specific and has some reporting inconsistencies.
- **Relevance to reference DVH calculator:** High. The paper directly informs benchmark resolution, small-volume stress testing, metric selection, and commissioning strategy for an independent SRS DVH engine.

---

<!-- Source: SUMMARY - Walker 2025 - Clinical impact of DVH uncertainties.md -->

## Walker (2025) - Clinical impact of DVH uncertainties

### Executive summary

Walker and Byrne show that dose-volume histograms (DVHs) are not uniquely determined by a dose grid and structure set alone: commercial systems can report materially different DVHs from the same DICOM inputs because they make different, usually undocumented, choices about contour interpolation, end-capping, dose sampling, supersampling, and histogram construction. The problem is most severe for very small stereotactic structures, where limited contour-stack information and coarse slice spacing make 3D reconstruction intrinsically uncertain.

Using synthetic spherical targets embedded in analytically defined Gaussian dose distributions, the authors demonstrate that small-volume DVH errors can reach clinically important magnitudes. For the smallest tested structures, cumulative DVH deviations reached about 20 percentage points, RayStation’s average DVH difference was close to 10% for a 3 mm radius sphere, and conformity/gradient indices were substantially distorted. In Table 2, PCI for a 0.03 cc sphere fell as low as 0.60 versus a true value of 1.00, while MGI rose as high as 6.34 versus a true value of 3.69.

The clinical comparison across 84 plans from seven centres shows that these discrepancies are not merely theoretical. Differences in D95 between the originating TPS and ProKnow reached up to 9% for the smallest targets, with typical variability of about 2% for 0.5-20 cc, about 1% for 20-70 cc, and less than 0.1% for large volumes. Because plan constraints are often applied with zero tolerance, the receiving system in a secondary review workflow may classify a plan as failing even when it passed in the source TPS.

For a reference-quality DVH calculator, the central lessons are clear: the software must expose rather than hide reconstruction assumptions, validate against analytical benchmarks, quantify uncertainty for sparse contour stacks, and support not only standard cumulative DVHs but also derived stereotactic metrics such as PCI and MGI. Small-volume cases should be treated as an uncertainty-reporting problem, not merely a numerical integration problem.

### 1. Bibliographic record

- **Authors:** Liam Walker, John Byrne *(the article PDF itself lists the authors as L.S. Walker and J.P. Byrne).*
- **Title:** Clinical impact of DVH uncertainties
- **Journal:** Medical Dosimetry, 50(1):1-7
- **Year:** 2025 *(Epub 9 July 2024)*
- **DOI:** [10.1016/j.meddos.2024.06.002](https://doi.org/10.1016/j.meddos.2024.06.002)
- **Open access:** No *(publisher access restricted; a companion synthetic dataset is openly available on Mendeley Data)*

### 2. Paper type and scope

**Type:** Original research

**Domain tags:** D1 Computation | D2 Commercial systems

**Scope statement:** This paper quantifies how much commercially implemented DVH calculators can disagree, even when they ingest the same DICOM structure and dose data. It combines analytically tractable synthetic benchmarks with a multi-system clinical D95 comparison to show that small-volume DVH discrepancies are large enough to alter pass/fail judgements in stereotactic planning and in cross-platform plan review workflows.

### 3. Background and motivation

Walker and Byrne address a longstanding but often under-commissioned problem: a DVH is not a uniquely determined function of “dose grid + structure set” alone. Different systems make different choices about contour interpolation between slices, superior/inferior end-capping, dose resampling, supersampling, and histogram binning; therefore, two TPSs can produce different DVHs from identical inputs. Because DVHs and derived metrics such as D95 are used directly in treatment plan approval, these implementation differences can alter clinical decisions, not merely software outputs. The authors also emphasise that when plans are exported to secondary review or cloud analytics platforms, the receiving system may report plan-constraint failures that were not present in the originating TPS.

The paper is especially motivated by **small stereotactic targets**. With typical CT slice spacing around **1 mm**, structures only a few millimetres across are coarsely digitised, so the contour stack may provide too little information for accurate 3D reconstruction and dose-volume sampling. Prior studies had compared TPS outputs and, importantly, Nelms and colleagues had already shown how analytical phantoms can reveal DVH implementation errors. Walker and Byrne’s specific contribution is to use clinically plausible spherical targets with centred Gaussian dose fall-off, analyse full DVH curves rather than isolated points, extend testing to plan-quality metrics such as **PCI** and **MGI**, and connect these technical differences to concrete clinical pass/fail consequences.

### 4. Methods: detailed technical summary

The study had two linked components: **(1) an analytical/simulation benchmark using synthetic DICOM objects with mathematical ground truth**, and **(2) a comparative clinical dataset study using exported patient plans**. Synthetic structures and dose distributions were generated programmatically with `pydicom`, written as DICOM objects, and imported into **RayStation 9.2**, **MasterPlan 4.3**, and **ProKnow 1.30.0**. For the clinical comparison, the paper additionally included **Precision 2.0.1**, **Pinnacle 16.2**, **Eclipse 15.1**, **Monaco 5.51**, **GammaPlan 11.3.1**, and **ProSoma 4.2**. The synthetic CT geometry was fixed at **1 mm slice spacing** and **0.6 mm in-plane pixel spacing**, chosen to mimic common clinical acquisition. A set of **61 dummy CT headers** with no pixel data was created purely to satisfy DICOM hierarchy requirements. Contour points along each synthetic structure were sampled at **<0.1 mm spacing**, so in-plane digitisation error was intentionally made small relative to inter-slice effects. Synthetic RTDOSE files were created by taking a RayStation-exported dose object and overwriting dose values with mathematically sampled values. To minimise data corruption risk, synthetic DICOM files were uploaded directly into each software package rather than transferred between systems.

The synthetic benchmark geometry consisted of **eight spheres with radii 2-9 mm** (approximately **0.03-3.05 cc**). For one TPS (RayStation), larger spheres up to **28 mm radius** (approximately **92 cc**) were also tested to examine convergence. Each sphere size was generated in two axial positions: **centred on a CT slice** and **centred midway between slices**. This is a clever probe of slice-position dependence, because with small objects the superior and inferior contour planes strongly influence end-capping and interpolation. The synthetic dose distribution was an **isotropic 3D Gaussian** centred on the sphere. The authors set the Gaussian width equal to the sphere radius, that is **σ = R**, and fixed the peak dose at **A = 10 Gy**, so that every sphere had the same **normalised cumulative DVH**. They derived the analytical inverse dose-radius relation `r(D)=σ√(2 ln(A/D))` and from this the cumulative volume-above-dose relation `V(D)=4πr(D)^3/3` within the sphere. The prescription isodose for the synthetic plans was defined at the sphere edge, `D(R)=D(σ)=Ae^{-1/2}≈6.06 Gy`, which yields analytically **PCI = 1.00** and **MGI ≈ 3.69** for all spheres.

DVH comparison was performed visually by overlaying cumulative curves and numerically by a scalar error metric defined as the **average of squared point-by-point DVH differences**, `Error = <x²>`, where `x = DVH_reported − DVH_analytic`. One technical subtlety is that this is **not** an RMS quantity because no square root is taken; formally, Fig. 2 therefore reports a mean-squared deviation in percentage-volume space, even though the narrative later describes some results in plain “% error” language. This is a minor interpretive ambiguity in the paper. The authors also computed two stereotactic plan-quality indices: **Paddick Conformity Index (PCI)** and **Modified Gradient Index (MGI)**, where `PCI = [VPTV(100)/VPTV] × [VPTV(100)/VTotal(100)]` and `MGI = VTotal(50)/VPTV(100)`. These require not only target DVHs but also thresholded **whole-patient/isodose volumes**, which is relevant for reference-calculator design. Histogram bin width, internal dose interpolation kernel, supersampling factor, voxel inclusion rule, partial-volume weighting rule, and end-capping implementation for the commercial systems were all **[DETAIL NOT REPORTED]**, which is central to the paper’s argument that black-box DVH engines are difficult to diagnose.

The clinical component used data from **Task and Finish Group Four** of the UK **IPEM ProKnow Technical Oversight Group**. This structured multi-centre professional body exercise lends institutional weight to the clinical findings. The authors analysed **84 anonymised clinical plans** from **7 radiotherapy centres / 7 TPS environments**, using primarily **lung SABR PTVs** over a range of sizes. Volumes were **predominantly below 50 cc**, with about **25% between 50 and 200 cc**. The chosen clinical endpoint was **D95**, recalculated after export in **ProKnow**, then compared with the original TPS-reported value. Crucially, this was **not** a ground-truth analysis: ProKnow served only as a **common reference system**, and the authors explicitly note that for the smallest targets a specialist system such as **GammaPlan** might actually be closer to truth than ProKnow. The y-axis in Fig. 4 is labelled **“% Difference in D95 (ProKnow − TPS)”**, but the exact percentage denominator is **[DETAIL NOT REPORTED]**. No inferential statistics, p-values, confidence intervals, or formal hypothesis tests were reported; the study is entirely descriptive. Clinical plan-generation details such as treatment technique mix, beam energy, dose algorithm, heterogeneity correction, and native dose-grid resolution are also **[DETAIL NOT REPORTED]**, although because the same dose grids were exported and re-read, the study mainly interrogates **DVH computation**, not dose-calculation physics. The authors additionally checked a small RayStation export sample and found no DICOM transfer differences that would affect DVH results.

### 5. Key results: quantitative

The synthetic benchmarks showed that **DVH shape errors grow rapidly as structure size decreases**. In **Fig. 1**, RayStation and MasterPlan both exhibited increasingly coarse **step-like cumulative DVHs** for **3, 6, and 9 mm radius spheres**, with deviations from the analytical curve of up to about **20 percentage points of cumulative volume**, especially around the steep transition near the prescription boundary at **6.06 Gy**. The authors interpret this as evidence that substantial fractions of the object are effectively being represented by very few dose points when the dose grid is coarse relative to the structure. ProKnow produced much smoother curves, which the authors attribute to substantial internal supersampling, and it agreed very well for **6 mm** and **9 mm** spheres. However, for the **3 mm radius** sphere (approximately **0.11 cc**) ProKnow lay **up to ~5 percentage points below** the analytical curve across much of the dose range, suggesting a systematic structure-interpolation bias rather than simple dose aliasing. The authors note that this sphere spans only **7 contours** at **1 mm** slice spacing, including **2 single-point contours**, which places a fundamental representation limit on achievable accuracy.

The size-dependence was much stronger than dose-width dependence. From the RayStation convergence study, the authors report an average DVH difference of **close to 10%** for a **3 mm radius** sphere, improving to **~1%** at **10 mm radius** (approximately **4.0 cc**) and **~0.1%** at **20 mm radius** (approximately **33 cc**). They further conclude that beyond about **100 cc** there should be relatively little discrepancy for this class of convex object and smooth dose distribution, and that even at about **20 cc** the average difference from true volume-at-dose is only **~0.1%**. They also show that, for a fixed **5 mm** sphere, changing the Gaussian width altered the error much less than changing sphere size. This implies that in the tested regime, **geometric sampling / contour representation** is a stronger driver than the precise smoothness of the dose fall-off. The authors also state that a **10 mm radius** sphere on **1 mm** slices should be roughly comparable to a **20 mm radius** sphere on **2 mm** slices, reinforcing that the key quantity is effectively the number of available contours across the object.

The paper’s Table 2 quantifies just how unstable stereotactic indices become at tiny volumes. For **2 mm radius** spheres (**0.03 cc**), the true **PCI = 1.00**, but reported values ranged from **0.60 to 0.73**, that is about **27-40% underestimation** relative to truth depending on system and slice position. At the same size, the true **MGI = 3.69**, while reported values ranged from **4.52 to 6.34**, that is about **22-72% overestimation**. By contrast, for **9 mm radius** spheres (**3.05 cc**), PCI improved to **0.92-0.95** and MGI to **3.73-3.86**, corresponding to only about **5-8% PCI underestimation** and **1-5% MGI overestimation**. Slice-position dependence was also much greater for the smallest structures: for example, MasterPlan’s **MGI** changed from **5.67** to **6.34** solely by moving the sphere from on-slice to between-slice. A supplementary experiment fixing sphere radius at 5 mm and varying Gaussian width showed that DVH error was far less sensitive to dose-distribution width than to structure size, implying that structure discretisation dominates over dose-gradient steepness for determining DVH accuracy.

The authors summarise that **PCI errors were present for all volumes <3 cc**, reaching **~40%** around **0.1 cc**, and **MGI errors reached ~75%** for **<1 cc** volumes. No p-values or confidence intervals were reported.

In the clinical dataset, cross-system differences in D95 were large enough to matter operationally. Across **84 plans**, variation relative to ProKnow reached **up to 9%** for the smallest volumes, with the paper specifically identifying a **0.48 cc GammaPlan** case as the extreme small-volume outlier. Typical variability was about **2%** for **0.5-20 cc**, about **1%** for **20-70 cc**, and **<0.1%** for large volumes. The scatter plot also shows a clear directional skew: **ProKnow reported a lower D95 than the originating TPS in 50 of 84 plans**, meaning that a plan optimised to exactly meet a D95 constraint could fail after export. The extended **RayStation/Precision** plot suggests residual discrepancies of only a few tenths of a per cent out to **800 cc** **[INFERRED FROM FIGURE]**. A useful negative result is that the authors’ small RayStation file-transfer audit found no export-induced DICOM changes that would materially alter DVH calculations.

### 6. Authors' conclusions

The authors conclude that **commercial DVH calculators can produce clinically meaningful differences from identical dose/structure inputs**, and that the dominant problem is the combination of **limited geometric information for very small structures** and **implementation differences across DVH software**. They argue that this is particularly important for stereotactic planning, for published dose constraints at **0.1-0.035 cc**, and for any workflow that exports plans into secondary review or cloud analytics environments. They recommend that DVH-calculator accuracy should form part of TPS commissioning and that comparison systems should include **appropriate tolerances** rather than using zero-tolerance pass/fail logic.

These conclusions are well supported for the **synthetic benchmark** component, where a genuine analytical reference exists. They are somewhat less strong for the **clinical** component, because ProKnow is only a convenience reference rather than ground truth; the authors themselves acknowledge this and specifically caution that some systems may be closer to truth than ProKnow for small structures.

### 7. Implications for reference DVH calculator design

#### 7a. Algorithm and implementation recommendations

This paper strongly supports building the reference calculator around **explicit, user-visible control of structure reconstruction and dose sampling**, not opaque defaults. Supersampling clearly helps: ProKnow’s smoother curves suggest that coarse whole-voxel sampling is insufficient for sub-cc targets. However, supersampling alone is **not enough** ProKnow still showed an apparent inward-bias for the **3 mm radius** sphere. The reference engine should therefore separate at least three layers of uncertainty: **(i) numerical dose integration error**, **(ii) contour-to-volume reconstruction error** including end-capping, and **(iii) irreducible representation uncertainty from sparse contour stacks**. For structures spanning only about **5-7 contours** at **1 mm** spacing, the tool should not emit a single unqualified number; it should emit the metric together with a warning or uncertainty band. Metrics such as **PCI** and **MGI** should be implemented as first-class citizens, because this paper shows they are more fragile than standard target DVH points.

#### 7b. Validation recommendations

The benchmark cases in this paper should be reproduced almost verbatim in a reference suite: **spheres of 2-9 mm radius**, positioned both **on-slice** and **between-slice**, with **1 mm** slice spacing, **0.6 mm** in-plane spacing, and centred **Gaussian** dose fields with **A = 10 Gy** and **σ = R**. Validation should include cumulative DVH overlays, pointwise volume-at-dose deviations, D95, **PCI**, and **MGI**. The companion synthetic dataset is publicly available on **Mendeley Data** under **CC BY 4.0** with DOI **10.17632/pb55hjf5y3.1**, which makes this unusually reproducible for TPS-comparison work. For a gold-standard engine, the target should be much tighter than inter-system agreement: for simple convex phantoms, the engine should aim for **well below 1%** numerical error once structure size is in the several-cc range, and about **0.1%** by **~20 cc**. For **<1 cc** structures, validation should focus less on a binary pass/fail threshold and more on demonstrating a credible **uncertainty envelope**. Additional tests should extend the paper’s ideas to irregular flat shapes, misaligned dose grids, anisotropic voxels, and sharply varying dose fields, because the authors explicitly note those as remaining risk areas.

#### 7c. Extensibility considerations

The paper motivates a reference calculator that can operate on **arbitrary thresholded isodose volumes**, not only named ROIs, because **MGI** and **PCI** depend on VTotal(50) and VTotal(100) as well as VPTV(100). More broadly, the design should support **uncertainty-aware derived metrics**: volume-stratified confidence bands for D95, conformity/gradient indices, and eventually **gEUD/NTCP** or other biological overlays. A useful extension would be a **probabilistic DVH** mode that varies reconstruction assumptions such as end-capping and contour interpolation model and reports a metric range rather than a point estimate. This paper provides a strong rationale for that feature, especially for sub-cc stereotactic structures.

#### 7d. Caveats and limitations

The exact numerical discrepancies in this paper should not be universalised. The synthetic cases are limited to **centred spheres** in **smooth isotropic Gaussian** dose distributions, so they do not span concavities, thin shells, strongly anisotropic gradients, or heterogeneous dose-calculation artefacts. The commercial systems are also version-specific, and some, notably **MasterPlan**, are legacy platforms. The clinical study is not absolute validation because it uses **ProKnow as a reference rather than truth**, and the figure 4 ProSoma points are not fully independent because the caption states that **Monaco plans were re-used in ProSoma**. Finally, two methodological ambiguities matter for databank use: the figure 2 scalar “error” is formally a **mean squared** quantity, and the percentage denominator for the plotted clinical D95 differences is **[DETAIL NOT REPORTED]**.

### 8. Connections to other literature

- **Chen (1988):** Foundational discussion of DVHs in treatment planning; Walker and Byrne examine the numerical reliability of that foundational representation.
- **Drzymala et al. (1991):** Classic DVH overview; this paper is best read as a computational accuracy supplement to that conceptual work.
- **Ebert et al. (2010):** Prior comparison of DVH outputs from multiple TPSs; Walker and Byrne extend this by using analytical ground truth and explicitly quantifying small-volume clinical impact.
- **Nelms et al. (2015):** The closest methodological predecessor, using analytical datasets to verify DVH calculations; Walker and Byrne adapt the same philosophy to spherical/Gaussian cases and stereotactic metrics.
- **Stanley et al. (2021):** Specifically examined small-volume radiosurgery dose-volume metric accuracy; the present paper broadens the tested systems and volume range, and adds full-DVH shape analysis.
- **Eaton and Alty (2017):** Showed TPS dependence of small-volume calculation and margin growth in SRS; Walker and Byrne complement this by showing downstream effects on DVHs, PCI, and MGI.
- **ICRU Report 91; AAPM TG-101; Diez et al. (2022) UK SABR consensus:** These guideline frameworks use small-volume dose constraints precisely in the size regime where Walker and Byrne show large DVH uncertainty.

### 9. Data extraction table

**Table 9a. High-value quantitative extracts**

| Context | Size / volume | Extracted quantitative result | Reference / denominator |
|---|---:|---:|---|
| Synthetic cumulative DVH | Smallest tested volumes | Up to **20 percentage points** deviation in cumulative % volume at specific dose points along the DVH curve | Difference in cumulative % volume vs analytical DVH |
| RayStation synthetic DVH | **3 mm radius** (~**0.11 cc**) | **Close to 10%** average DVH difference | Authors’ textual summary; volume-at-dose difference |
| RayStation synthetic DVH | **10 mm radius** (~**4.0 cc**) | **~1%** average DVH difference | Authors’ textual summary |
| RayStation synthetic DVH | **20 mm radius** (~**33 cc**) | **~0.1%** average DVH difference | Authors’ textual summary |
| Clinical D95 variation | Smallest SRS volume, **0.48 cc** (GammaPlan) | Up to **9%** | `% Difference in D95 (ProKnow − TPS)`; percentage denominator **[DETAIL NOT REPORTED]** |
| Clinical D95 variation | **0.5-20 cc** | Typically **~2%** | Same as above |
| Clinical D95 variation | **20-70 cc** | Typically **~1%** | Same as above |
| Clinical D95 variation | Large volumes | **<0.1%** | Same as above |
| PCI error | Around **0.1 cc** | Up to **40%** | Relative to analytical truth |
| MGI error | **<1 cc** | Up to **75%** | Relative to analytical truth |

**Table 9b. Extracted PCI values from Table 2 (truth = PCI 1.00). Note: the paper text refers to "9 mm (3.03 cc)" but this is a minor misstatement; the correct volume of a 9 mm radius sphere is 3.05 cc, as given in the table header.**

| System | 2 mm radius on-slice | 2 mm radius between-slice | Relative error vs truth | 9 mm radius on-slice | 9 mm radius between-slice | Relative error vs truth |
|---|---:|---:|---:|---:|---:|---:|
| RayStation | 0.64 | 0.73 | **−36% to −27%** | 0.92 | 0.92 | **−8% to −8%** |
| MasterPlan | 0.60 | 0.65 | **−40% to −35%** | 0.94 | 0.94 | **−6% to −6%** |
| ProKnow | 0.71 | 0.72 | **−29% to −28%** | 0.95 | 0.94 | **−5% to −6%** |

**Table 9c. Extracted MGI values from Table 2 (truth = MGI 3.69)**

| System | 2 mm radius on-slice | 2 mm radius between-slice | Relative error vs truth | 9 mm radius on-slice | 9 mm radius between-slice | Relative error vs truth |
|---|---:|---:|---:|---:|---:|---:|
| RayStation | 5.24 | 4.93 | **+42.0% to +33.6%** | 3.83 | 3.84 | **+3.8% to +4.1%** |
| MasterPlan | 5.67 | 6.34 | **+53.7% to +71.8%** | 3.86 | 3.83 | **+4.6% to +3.8%** |
| ProKnow | 4.52 | 4.83 | **+22.5% to +30.9%** | 3.73 | 3.78 | **+1.1% to +2.4%** |

### 10. Critical appraisal

**Strengths:** analytically grounded benchmark design; clinically relevant synthetic geometry; explicit probing of slice-position and end-capping effects; inclusion of both full DVH curves and clinically used derived metrics; and a valuable second-stage demonstration on real multi-centre clinical plans. The paper is unusually actionable for commissioning because it ties numerical discrepancies directly to plan-check pass/fail risk.

**Weaknesses:** incomplete reporting of key implementation details such as bin width, interpolation rule, supersampling factor, and dose-grid resolution; simple spherical/Gaussian phantoms only; no inferential statistics; ambiguity in the definition and interpretation of the scalar DVH error; and no absolute ground truth for the clinical comparison.

**Confidence in findings:** Medium ;  the direction and scale of the small-volume problem are convincing, especially in the synthetic component, but exact percentages are version-, geometry-, and denominator-dependent.

**Relevance to reference DVH calculator:** High ;  few papers more directly motivate explicit uncertainty quantification, volume-stratified validation, and transparent handling of sub-cc structures in a benchmark DVH engine.

---

## Cross-cutting themes

The 21 papers in this collection span more than three decades of DVH computation research (1991-2025). Read together, they reveal several persistent themes that directly inform the design and validation of a reference-quality DVH calculation engine.

### Small structures are universally the hardest case

Every paper in this collection that tests volume-dependent effects finds dramatically worse DVH accuracy as structure volume decreases. Kooy (1993) showed that uniform Cartesian sampling becomes inefficient for small intracranial volumes, with roughly 7% sampling error for 1 mm thick shells. Corbett et al. (2002) demonstrated that V200 errors in prostate brachytherapy reached 27% RMS at 2.5 mm grid spacing and 69% at 5 mm. Kirisits et al. (2007) found inter-system volume variation of 7% for a 4 cc cylinder versus 2% for a 57 cc cylinder. Ebert et al. (2010) showed that DVH disagreement widened sharply below about 250 cc, with the smallest structures driving the widest spread. Nelms et al. (2015) found that Pinnacle produced deviations above 3% in 36% of test cases at matched coarse resolution, concentrated on small and oblique shapes. Stanley et al. (2021) showed structure-volume errors of up to -23.7% for 3 mm diameter spheres, and V100 errors of up to -20.1% for the same structures. Pepin et al. (2022) reported median precision bands of about 1-3% but with outliers approaching 100% for specific small-structure/coarse-grid combinations. Walker and Byrne (2025) found that PCI errors reached 40% and MGI errors 75% for structures of approximately 0.1 cc. Grammatikou et al. (2025) confirmed that even a well-performing TPS (Monaco) showed 2.1% average volume error for 3 mm diameter targets at the reference 1 mm configuration. The implication for a reference calculator is that small-structure accuracy must be a primary design target, not an afterthought.

### End-capping and between-slice interpolation remain poorly standardised

Despite decades of awareness, the treatment of superior and inferior structure boundaries remains one of the most consequential and least transparent algorithmic choices in DVH computation. Nelms et al. (2015) identified end-capping as a major driver of Pinnacle errors, noting that the system included end-cap volume in structure totals but excluded the corresponding dose voxels from the DVH, a logically inconsistent implementation. Pepin et al. (2022) documented at least four different end-capping strategies across five commercial systems: rounded shape-based caps (Eclipse), half-slice extension (Mobius3D, MIM, RayStation), half-slice extension capped at 1.5 mm (ProKnow), and each approach producing visibly different DVH shapes for the same input contours. Penoncello et al. (2024) found that Elements effectively avoided classical end-capping by allowing contours to exist in 3D space, while Pinnacle used a coarse inclusion rule counting any voxel touched by the structure. Walker and Byrne (2025) showed that positioning a sphere centred on versus between CT slices could change PCI by up to 0.13 and MGI by up to 0.67 for very small structures, demonstrating that end-capping effects interact with slice position. A reference calculator must make its end-capping and interslice interpolation methods explicit, configurable, and testable.

### Volume handling contributes more inter-system disagreement than dose handling

A striking finding across the multi-system comparison papers is that volumetric and boundary effects dominate over dose-grid effects as sources of DVH disagreement. Ebert et al. (2010) found that relaxing the volume criterion from 1% to 5% increased the DVH gamma pass rate from 78% to 96%, whereas relaxing the dose criterion from 1% to 5% improved it only to 85%. Penoncello et al. (2024) reported that volume-only comparisons showed mean ratios of 1.036 to 1.101 relative to Eclipse (all significantly different at P < .001), while dosimetric medians were all 1.000, indicating that central tendency for dose metrics was essentially identical but volume reporting differed materially. This pattern is consistent with the earlier observation by Corbett et al. (2002) that VariSeed's effective DVH sampling geometry mattered more than its nominal resolution label. For a reference engine, this argues that geometry handling (contour rasterisation, partial-volume weighting, boundary classification, and interpolation) deserves at least as much engineering attention and validation effort as dose interpolation.

### Grid resolution matters most in steep gradients and for small serial organs

Multiple papers converge on the finding that dose-grid resolution becomes clinically critical when steep dose gradients intersect small structures. Chung et al. (2006) showed up to 4.6% dose differences at 4 mm grid spacing in head-and-neck IMRT penumbra regions, with the effect scaling approximately linearly with gradient magnitude. Rosewall et al. (2014) demonstrated that only a 1.5 mm grid maintained full-curve bladder-wall DVH agreement within 1 cc for every patient, with 2.5 mm already producing up to 5 cc local failures. Snyder et al. (2017) found that 2.5 mm versus 1.0 mm grids increased spinal cord D10% by 13.0% on average (up to 23.2%) in spine SRS, while PTV coverage changes were comparatively modest. Grammatikou et al. (2025) confirmed that 1 mm dose grid and 1 mm slice thickness are needed for intracranial SRS, with 2 mm dose grids acceptable only for targets exceeding 20 mm diameter. The emerging consensus is that approximately 1.5-2 mm is the threshold for IMRT and 1 mm for SRS, but a reference calculator should not assume any universal safe default; instead, it should support convergence testing and grid-sensitivity analysis as standard validation outputs.

### No commercial TPS provides full algorithmic transparency

A persistent concern across the literature, from Drzymala et al. (1991) to Walker and Byrne (2025), is that commercial DVH implementations are opaque. Nelms et al. (2015) described their analytical benchmark work as being motivated by the inability to determine which commercial DVH output was correct without an independent ground truth. Pepin et al. (2022) conducted an explicit vendor methodology survey but had to rely partly on private communications and vendor reference guides, with several key implementation details remaining undisclosed. Penoncello et al. (2024) compiled the most detailed published table of vendor DVH construction behaviour (their Table 1), yet still noted that many details were obtained through private communication rather than public documentation. This opacity motivates the very existence of an open-source reference calculator: a tool whose algorithms, boundary rules, interpolation methods, binning strategies, and convergence behaviour are fully documented and reproducible.

### Derived stereotactic indices amplify underlying DVH errors

Several recent papers demonstrate that derived plan-quality indices such as the Paddick Conformity Index, Modified Gradient Index, and RTOG Conformity Index magnify small underlying DVH errors into large metric distortions. Walker and Byrne (2025) found 40% PCI and 75% MGI errors for 0.1 cc structures where the underlying DVH deviation was 10-20 percentage points. Stanley et al. (2021) showed that the same nominal plan could appear substantially over-conformal or under-conformal depending on the software used, with implied RTOG CI varying from 0.877 to 1.254 for 3 mm targets at 1 mm slice spacing. Grammatikou et al. (2025) confirmed that GI was the most sensitive of all tested indices to discretisation changes, more so than D95 or CI. For a reference calculator, this means that derived indices must be computed from the same underlying geometry and dose objects as the base Vx values, and that uncertainty reporting for these indices should propagate the sensitivity inherent in their formulation.

### Analytical ground truth is essential but insufficient alone

The methodological evolution across these papers illustrates a clear trajectory. Early papers compared DVH outputs to the same system's isodose data (Panitsa et al. 1998) or to independent recalculation without absolute ground truth (Ebert et al. 2010). Nelms et al. (2015) introduced closed-form analytical DVH solutions using simple geometric shapes and linear dose gradients, a paradigm subsequently adopted by Stanley et al. (2021), Pepin et al. (2022), Walker and Byrne (2025), and Grammatikou et al. (2025). This analytical approach provides clean error attribution and reproducibility, but all authors acknowledge that simple convex shapes in smooth gradients do not reproduce the full complexity of clinical anatomy: concavities, thin shells, multiply connected structures, heterogeneous media, and modulated dose fields remain untested by analytical benchmarks. A robust validation strategy for a reference calculator therefore requires both: analytical phantoms for algorithm verification and clinical datasets for real-world stress testing.

### Uncertainty quantification is an emerging requirement

Several papers argue that reporting a single deterministic DVH is insufficient for clinical decision-making. Henriquez and Castrillon (2008) proposed the dose-expected-volume histogram, showing that a uniform 3.6% dose uncertainty could change V95 coverage by up to 27 percentage points in the worst PTV case. Walker and Byrne (2025) argued for explicit DVH uncertainty tolerances in organ dose constraints. Zhang et al. (2011) demonstrated that temporal occupancy weighting changes the effective DVH without altering the physical dose, highlighting that the DVH is not a unique physical observable but depends on the definition of the volume denominator. Pepin et al. (2022) introduced a precision framework treating staircase artefacts as a discretisation-driven uncertainty band. For a reference calculator, these papers collectively argue for an architecture that can report not only a best-estimate DVH but also a credible uncertainty envelope, whether from discretisation sensitivity, dose-calculation uncertainty, or contouring variability.
