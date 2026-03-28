# PyMedPhys DVH Calculator: Technical RFC and Research Protocol

**Document type:** Hybrid technical RFC and research protocol
**Target audience:** PyMedPhys maintainers and AI coding agents (Claude Code, GPT-5)
**Version:** 0.7
**Module path:** `pymedphys._dvh`

---

> [!WARNING]
> **AI-Assisted Content Notice**
>
> This document was produced with the liberal help of Claude (Anthropic), including literature synthesis, algorithmic specification, data model design, and prose drafting. While every effort was made to minimise hallucinations and other LLM artefacts — including systematic cross-referencing of all citations against source summaries, independent verification of algorithmic descriptions, and explicit labelling of uncertain or inferred claims — the reader should be mindful that not all claims have yet been carefully confirmed by a human domain expert against primary sources. Statements derived from literature are cited; statements reflecting engineering judgement, design choices, or interpolations are labelled as such (see labelling conventions below). Corrections, clarifications, and challenges are graciously welcomed and can be submitted via GitHub issue or pull request.
>
> **Labelling conventions for non-literature-derived statements:**
>
> - *[Design proposal]* — an engineering choice made by the RFC authors, not directly prescribed by the literature.
> - *[Engineering inference]* — a claim derived from standard computational/mathematical knowledge or interpolated from cited evidence, but not explicitly stated in a cited source.
> - *[Assumption]* — a working assumption that has not been validated.
> - *[Open question]* — a point where the correct answer is unknown and requires empirical investigation.
> - *[Future work]* — explicitly deferred to a later phase or version.

---

`pymedphys._dvh` is an open-source DVH calculator designed as a transparent, configurable reference implementation. Every algorithmic choice is explicit and user-adjustable. The tool includes a high-accuracy reference mode whose performance is characterised against a comprehensive suite of analytical ground-truth benchmarks. All validation methodology and results are published openly. The tool aims to be as well-validated as feasible, and to support rigorous cross-system comparison studies.

---

## Table of Contents

- [PyMedPhys DVH Calculator: Technical RFC and Research Protocol](#pymedphys-dvh-calculator-technical-rfc-and-research-protocol)
  - [Table of Contents](#table-of-contents)
  - [1. Executive Summary](#1-executive-summary)
  - [2. Evidence-Bounded Positioning Statement](#2-evidence-bounded-positioning-statement)
    - [2.1 Project Aims](#21-project-aims)
    - [2.2 What the Literature Indicates Is Needed](#22-what-the-literature-indicates-is-needed)
  - [3. Literature Synthesis and Design Implications](#3-literature-synthesis-and-design-implications)
    - [3.1 Foundational DVH Computation and QA Expectations](#31-foundational-dvh-computation-and-qa-expectations)
    - [3.2 Analytical Benchmark Datasets and Whole-Curve Validation](#32-analytical-benchmark-datasets-and-whole-curve-validation)
    - [3.3 Cross-System Variability](#33-cross-system-variability)
    - [3.4 Voxelisation and Slice-Thickness Effects](#34-voxelisation-and-slice-thickness-effects)
    - [3.5 Dose-Grid Resolution and Grid-Origin Effects](#35-dose-grid-resolution-and-grid-origin-effects)
    - [3.6 Small-Volume Stereotactic Behaviour](#36-small-volume-stereotactic-behaviour)
    - [3.7 Between-Slice Interpolation](#37-between-slice-interpolation)
    - [3.8 SBRT Constraint Semantics](#38-sbrt-constraint-semantics)
    - [3.9 Further Concepts Noted for Future Work](#39-further-concepts-noted-for-future-work)
    - [3.10 Summary: What the Literature Implies for Design](#310-summary-what-the-literature-implies-for-design)
  - [4. Product Scope](#4-product-scope)
    - [4.1 v1 Scope](#41-v1-scope)
    - [4.2 Explicitly Out of Scope for v1](#42-explicitly-out-of-scope-for-v1)
    - [4.3 Future Extensions](#43-future-extensions)
  - [5. Design Principles](#5-design-principles)
  - [6. Detailed Tool Specification and Architecture](#6-detailed-tool-specification-and-architecture)
    - [6.1 Design Philosophy for Data Types](#61-design-philosophy-for-data-types)
    - [6.2 Grid Frame and Spatial Model](#62-grid-frame-and-spatial-model)
    - [6.3 Dose Reference Types](#63-dose-reference-types)
    - [6.4 ROI Identity Type](#64-roi-identity-type)
    - [6.5 Metric Request Types](#65-metric-request-types)
    - [6.6 Configuration Types](#66-configuration-types)
    - [6.7 Geometry / Structure Types](#67-geometry--structure-types)
    - [6.8 Dose and Occupancy Types](#68-dose-and-occupancy-types)
    - [6.9 Result Types](#69-result-types)
    - [6.10 Public API](#610-public-api)
    - [6.11 Strategy Protocols (Private/Internal)](#611-strategy-protocols-privateinternal)
  - [7. Algorithmic Design: Detailed Specification](#7-algorithmic-design-detailed-specification)
    - [7.0 Contour Area, Winding Order, and Geometric Validation](#70-contour-area-winding-order-and-geometric-validation)
      - [7.0.1 Signed Area via the Shoelace Formula](#701-signed-area-via-the-shoelace-formula)
      - [7.0.2 Self-Intersection Detection](#702-self-intersection-detection)
    - [7.1 Point-in-Polygon Algorithms](#71-point-in-polygon-algorithms)
      - [7.1.1 Ray Casting (Even-Odd Rule)](#711-ray-casting-even-odd-rule)
      - [7.1.2 Winding Number Algorithm](#712-winding-number-algorithm)
      - [7.1.3 Handling Multi-Component Contours (Holes)](#713-handling-multi-component-contours-holes)
    - [7.2 Contour Interpolation / Structure Reconstruction](#72-contour-interpolation--structure-reconstruction)
      - [7.2.1 Right-Prism Extrusion](#721-right-prism-extrusion)
      - [7.2.2 Shape-Based Interpolation (Signed Distance Field)](#722-shape-based-interpolation-signed-distance-field)
        - [SDF Computation Methods](#sdf-computation-methods)
    - [7.3 End-Capping](#73-end-capping)
      - [7.3.1 No End-Cap (`none`)](#731-no-end-cap-none)
      - [7.3.2 Half-Slice Extension (`half_slice`)](#732-half-slice-extension-half_slice)
      - [7.3.3 Half-Slice Capped (`half_slice_capped`)](#733-half-slice-capped-half_slice_capped)
      - [7.3.4 Rounded End-Cap (`rounded`)](#734-rounded-end-cap-rounded)
    - [7.4 Voxelisation and Partial-Volume Occupancy](#74-voxelisation-and-partial-volume-occupancy)
      - [7.4.1 Binary Centre-Inclusion](#741-binary-centre-inclusion)
      - [7.4.2 Fractional Occupancy via Supersampling](#742-fractional-occupancy-via-supersampling)
      - [7.4.3 Adaptive Supersampling with Gradient-Aware Refinement](#743-adaptive-supersampling-with-gradient-aware-refinement)
      - [7.4.4 SDF-Derived Fractional Occupancy](#744-sdf-derived-fractional-occupancy)
    - [7.5 Dose Interpolation](#75-dose-interpolation)
      - [7.5.1 Trilinear Interpolation](#751-trilinear-interpolation)
      - [7.5.2 Surface-Point Dose Sampling](#752-surface-point-dose-sampling)
      - [7.5.3 Dose-Grid-Point Preservation](#753-dose-grid-point-preservation)
    - [7.6 Histogram Construction](#76-histogram-construction)
      - [7.6.1 Differential Histogram](#761-differential-histogram)
      - [7.6.2 Cumulative DVH (derived)](#762-cumulative-dvh-derived)
    - [7.7 Metric Extraction](#77-metric-extraction)
      - [7.7.1 Dose-at-Volume Metrics (Dx%, Dxcc)](#771-dose-at-volume-metrics-dx-dxcc)
      - [7.7.2 Volume-at-Dose Metrics (VxGy, Vx%)](#772-volume-at-dose-metrics-vxgy-vx)
      - [7.7.3 Stereotactic Indices](#773-stereotactic-indices)
    - [7.8 Extrema and Near-Extrema Handling](#78-extrema-and-near-extrema-handling)
    - [7.9 Invalid-ROI Handling](#79-invalid-roi-handling)
  - [8. Validation and Benchmark Strategy](#8-validation-and-benchmark-strategy)
    - [8.1 Tier 1: Analytical Ground-Truth Tests](#81-tier-1-analytical-ground-truth-tests)
      - [8.1.1 Available Analytical Benchmark Datasets](#811-available-analytical-benchmark-datasets)
      - [8.1.2 Novel Analytical Benchmarks (Project-Specific)](#812-novel-analytical-benchmarks-project-specific)
    - [8.2 Tier 2: Numerical Convergence Tests](#82-tier-2-numerical-convergence-tests)
    - [8.3 Tier 3: Cross-Tool Comparisons](#83-tier-3-cross-tool-comparisons)
      - [8.3.1 Open-Source Comparators](#831-open-source-comparators)
      - [8.3.2 Commercial Comparator Matrix](#832-commercial-comparator-matrix)
    - [8.4 Tier 4: Clinical-Case Benchmarking](#84-tier-4-clinical-case-benchmarking)
    - [8.5 Tier 5: Sensitivity Analysis](#85-tier-5-sensitivity-analysis)
  - [9. Development Plan](#9-development-plan)
    - [Development Practices (applies to all phases)](#development-practices-applies-to-all-phases)
    - [Phase 0: Scaffolding, Core Types, and Test Infrastructure](#phase-0-scaffolding-core-types-and-test-infrastructure)
      - [Task 0.1: Module skeleton and packaging](#task-01-module-skeleton-and-packaging)
    - [Phase 1: Synthetic Benchmark Generation](#phase-1-synthetic-benchmark-generation)
      - [Task 1.1: Analytical geometry library](#task-11-analytical-geometry-library)
      - [Task 1.2: Analytical DVH formulas](#task-12-analytical-dvh-formulas)
      - [Task 1.3: DICOM RTSTRUCT generator](#task-13-dicom-rtstruct-generator)
      - [Task 1.4: DICOM RTDOSE generator](#task-14-dicom-rtdose-generator)
      - [Task 1.5: Benchmark manifest and published dataset integration](#task-15-benchmark-manifest-and-published-dataset-integration)
      - [Task 1.6: Phase-shift sweep generator](#task-16-phase-shift-sweep-generator)
      - [Task 1.7: Novel benchmark case generation](#task-17-novel-benchmark-case-generation)
    - [Phase 2a: Core Geometry Engine — Basic Methods](#phase-2a-core-geometry-engine--basic-methods)
      - [Task 2a.0: `numba` compilation strategy and infrastructure](#task-2a0-numba-compilation-strategy-and-infrastructure)
      - [Task 2a.1: DICOM RTSTRUCT importer](#task-2a1-dicom-rtstruct-importer)
      - [Task 2a.2: Contour validation and repair](#task-2a2-contour-validation-and-repair)
      - [Task 2a.3: Right-prism interpolation](#task-2a3-right-prism-interpolation)
      - [Task 2a.4: End-capping — none and half-slice](#task-2a4-end-capping--none-and-half-slice)
      - [Task 2a.5: Scanline point-in-polygon (even-odd rule)](#task-2a5-scanline-point-in-polygon-even-odd-rule)
      - [Task 2a.5b: Winding number point-in-polygon](#task-2a5b-winding-number-point-in-polygon)
      - [Task 2a.6: Binary centre-inclusion occupancy](#task-2a6-binary-centre-inclusion-occupancy)
      - [Task 2a.7: Fractional occupancy via fixed supersampling](#task-2a7-fractional-occupancy-via-fixed-supersampling)
      - [Task 2a.8: Volume computation golden-data tests](#task-2a8-volume-computation-golden-data-tests)
    - [Phase 2b: Core Geometry Engine — Advanced Methods](#phase-2b-core-geometry-engine--advanced-methods)
      - [Task 2b.1: 2D signed distance field computation](#task-2b1-2d-signed-distance-field-computation)
      - [Task 2b.2: Shape-based interpolation (SDF lofting)](#task-2b2-shape-based-interpolation-sdf-lofting)
      - [Task 2b.3: Rounded and half-slice-capped end-caps](#task-2b3-rounded-and-half-slice-capped-end-caps)
      - [Task 2b.4: Adaptive supersampling with gradient-aware refinement](#task-2b4-adaptive-supersampling-with-gradient-aware-refinement)
      - [Task 2b.5: Comprehensive volume golden-data expansion](#task-2b5-comprehensive-volume-golden-data-expansion)
    - [Phase 3: DVH Computation Engine](#phase-3-dvh-computation-engine)
      - [Task 3.1: DICOM RTDOSE importer](#task-31-dicom-rtdose-importer)
      - [Task 3.2: Trilinear dose interpolation](#task-32-trilinear-dose-interpolation)
      - [Task 3.3: Surface-point dose sampling](#task-33-surface-point-dose-sampling)
      - [Task 3.4: Histogram construction](#task-34-histogram-construction)
      - [Task 3.5: Metric extraction](#task-35-metric-extraction)
      - [Task 3.6: Issue system integration](#task-36-issue-system-integration)
      - [Task 3.7: Raw-array `compute_dvh()` orchestrator](#task-37-raw-array-compute_dvh-orchestrator)
      - [Task 3.8: Full analytical benchmark validation](#task-38-full-analytical-benchmark-validation)
      - [Task 3.9: Convergence study (Tier 2 benchmarks)](#task-39-convergence-study-tier-2-benchmarks)
    - [Phase 4a: DICOM Integration and Pipeline](#phase-4a-dicom-integration-and-pipeline)
      - [Task 4a.1: DICOM coordinate system handling](#task-4a1-dicom-coordinate-system-handling)
      - [Task 4a.2: End-to-end DICOM pipeline](#task-4a2-end-to-end-dicom-pipeline)
      - [Task 4a.3: Invalid-ROI policy framework](#task-4a3-invalid-roi-policy-framework)
    - [Phase 4b: DVH Export, CLI, and Provenance](#phase-4b-dvh-export-cli-and-provenance)
      - [Task 4b.1: DICOM RTDOSE DVH export](#task-4b1-dicom-rtdose-dvh-export)
      - [Task 4b.2: CLI implementation](#task-4b2-cli-implementation)
      - [Task 4b.3: Provenance implementation and anonymisation](#task-4b3-provenance-implementation-and-anonymisation)
    - [Phase 5: Cross-Tool Comparison, Clinical Validation, and Performance](#phase-5-cross-tool-comparison-clinical-validation-and-performance)
      - [Task 5.1: dicompyler-core algorithm documentation](#task-51-dicompyler-core-algorithm-documentation)
      - [Task 5.2: Automated cross-tool comparison framework](#task-52-automated-cross-tool-comparison-framework)
      - [Task 5.3: Clinical case library](#task-53-clinical-case-library)
      - [Task 5.4: Full sensitivity analysis (Tier 5)](#task-54-full-sensitivity-analysis-tier-5)
      - [Task 5.5: Performance benchmarking](#task-55-performance-benchmarking)
    - [Phase 6: Documentation and Release Preparation](#phase-6-documentation-and-release-preparation)
      - [Task 6.1: API documentation](#task-61-api-documentation)
      - [Task 6.2: CLI documentation](#task-62-cli-documentation)
      - [Task 6.3: Benchmark report](#task-63-benchmark-report)
      - [Task 6.4: Algorithm reference document](#task-64-algorithm-reference-document)
      - [Task 6.5: Migration guide from dicompyler-core](#task-65-migration-guide-from-dicompyler-core)
      - [Task 6.6: Contributing guide](#task-66-contributing-guide)
      - [Task 6.7: Gallery and demo outputs](#task-67-gallery-and-demo-outputs)
      - [Task 6.8: Release preparation](#task-68-release-preparation)
  - [10. Risk Register and Open Technical Questions](#10-risk-register-and-open-technical-questions)
    - [10.1 Technical Risks](#101-technical-risks)
    - [10.2 Open Technical Questions](#102-open-technical-questions)
  - [11. Research Agenda](#11-research-agenda)
    - [11.1 Key Gaps in the Literature](#111-key-gaps-in-the-literature)
    - [11.2 Key Experiments This Tool Enables](#112-key-experiments-this-tool-enables)
  - [12. Appendices](#12-appendices)
    - [Appendix A: Glossary of Metric Semantics](#appendix-a-glossary-of-metric-semantics)
    - [Appendix B: Implementation Design Decisions](#appendix-b-implementation-design-decisions)
      - [B.1 ROIRef enriched with `colour_rgb` (Phase 0)](#b1-roiref-enriched-with-colour_rgb-phase-0)
      - [B.2 ContourROI carries geometry-interpretation fields (Phase 0)](#b2-contourroi-carries-geometry-interpretation-fields-phase-0)
      - [B.3 `cached_property` incompatibility with `slots=True` — precompute in `__post_init__` (Phase 0)](#b3-cached_property-incompatibility-with-slotstrueprecompute-in-__post_init__-phase-0)
      - [B.4 `_types/` subdirectory structure (Phase 0)](#b4-_types-subdirectory-structure-phase-0)
      - [B.5 Serialisation format split: TOML input, JSON output (Phase 0)](#b5-serialisation-format-split-toml-input-json-output-phase-0)
      - [B.6 `to_dict()`/`from_dict()` on each type (Phase 0)](#b6-to_dictfrom_dict-on-each-type-phase-0)
  - [13. Future Research Directions: Computer Graphics Algorithms for DVH Computation](#13-future-research-directions-computer-graphics-algorithms-for-dvh-computation)
    - [13.1 SDF-First Architecture](#131-sdf-first-architecture)
    - [13.2 Exact Analytical Partial-Volume Computation](#132-exact-analytical-partial-volume-computation)
    - [13.3 GPU-Accelerated DVH Computation](#133-gpu-accelerated-dvh-computation)
    - [13.4 Sparse Volumetric Storage](#134-sparse-volumetric-storage)
    - [13.5 Neural Implicit Structure Representations](#135-neural-implicit-structure-representations)
    - [13.6 Advanced Surface Reconstruction](#136-advanced-surface-reconstruction)
    - [13.7 Recommended Research Priorities](#137-recommended-research-priorities)
  - [Bibliography](#bibliography)

---

## 1. Executive Summary

This document specifies the design, development plan, validation strategy, and research agenda for a benchmark-grade, open-source dose-volume histogram (DVH) calculator to be integrated into PyMedPhys as a first-class public API. The tool will accept DICOM RTSTRUCT and RTDOSE inputs via pydicom, as well as raw NumPy arrays for research and synthetic test generation, and will target conventional photon, VMAT, SRS, and SBRT plan evaluation in its first release.

The design is motivated by a 35-year evidence base showing that DVH computation is not a solved problem. Cross-system disagreement persists even when dose calculation is held constant: Penoncello et al. found mean structure-volume ratios varying from 1.036 to 1.101 across eight commercial systems given identical DICOM inputs [^19], and Pepin et al. measured median DVH precision-band widths ranging from 0.90% to 3.22% across five systems (Eclipse v15.5, Mobius3D v3.1, MIM Maestro v6.9.6, ProKnow DS v1.22, RayStation v9A) for simple analytical phantoms [^18]. For small stereotactic targets, Stanley et al. showed volume errors up to −23.7% and V100% errors up to −20.1% for 3 mm spheres across five anonymised commercial systems [^17], while Walker and Byrne reported PCI errors up to 40% and GI errors up to approximately 71.8% (termed Modified Gradient Index, MGI, by the authors) for sub-cc structures in synthetic analytical tests [^21].

The proposed tool addresses this by making every algorithmic choice explicit, configurable, and validated against analytical ground truth. It provides a slow, high-accuracy reference mode as part of its validation architecture, alongside faster practical modes with documented accuracy-speed tradeoffs. All results carry comprehensive provenance metadata, convergence diagnostics, and warnings when settings are likely inadequate for the anatomy or metric at hand. v1 targets efficient CPU execution with liberal use of `numba` JIT compilation and parallelisation.

The development plan is staged in small, test-first increments suitable for AI-assisted construction with Claude Code and GPT-5, with synthetic benchmark generation as an early milestone and golden-data regression tests gating every merge.

---

## 2. Evidence-Bounded Positioning Statement

### 2.1 Project Aims

This project aims to produce a DVH calculator that is:

1. **Maximally transparent.** Every algorithmic choice — contour interpolation, end-capping, voxelisation, dose sampling, binning, metric extraction — is explicit, configurable, and recorded in provenance metadata. No opaque defaults.

2. **Maximally configurable.** Users can select preferred subalgorithm choices, adjust every accuracy-speed knob independently, override settings per-ROI or per-metric, and define named configuration profiles.

3. **Comprehensive, reproducible validation.** The tool will be validated against every available analytical ground-truth dataset, via internal convergence studies, and through cross-tool comparison. All validation results, including failures and limitations, will be published openly.

4. **Inclusion of a well-validated, high-accuracy configuration.** Among the available configurations, the tool will include a reference mode whose accuracy is characterised against analytical benchmarks. The degree to which this configuration outperforms or matches other implementations is an empirical question to be answered by future comparison studies, not an a priori claim.

### 2.2 What the Literature Indicates Is Needed

The literature consistently identifies the following as desirable properties for a reference-quality DVH implementation:

- Drzymala et al. [^1] argued that structure discretisation should be decoupled from dose-grid resolution and that cumulative bins finer than 2 Gy are needed; they recommended 0.5 Gy.
- Nelms et al. [^14] showed that internal consistency between geometric definition and dose tally is essential, and that whole-curve validation against analytical truth exposes failure modes that endpoint-only checks miss.
- Pepin et al. [^18] demonstrated that precision-band analysis reveals discretisation-driven uncertainty that single-point metrics conceal. The better-performing systems in their study achieved median precision bands around 1%.
- Multiple studies [^2], [^5], [^15], [^16], [^17], [^21] showed that small structures in steep gradients are the most demanding regime, with errors growing rapidly as structure volume decreases below approximately 1 cc.
- Penoncello et al. [^19] showed that geometry handling (interpolation, end-capping, voxel inclusion) matters at least as much as dose-grid resolution.

---

## 3. Literature Synthesis and Design Implications

This section synthesises 21 publications spanning 1991–2025 into actionable design guidance, organised by theme. Consensus, disagreement, gaps, and design implications are identified explicitly.

### 3.1 Foundational DVH Computation and QA Expectations

The computational foundations of DVH calculation were established by Drzymala et al. [^1], who documented the core pipeline: contour-based structure definition on CT slices, rasterisation via scanline odd-even crossing rules, dose assignment by trilinear interpolation from a separate grid, and histogram construction via equispaced binning. They recommended 0.5 Gy cumulative bins and called 2 Gy crude [^1]. They demonstrated that very small differences in the low-dose DVH tail can reverse biological plan rankings when propagated into TCP/NTCP models [^1].

AAPM TG-53 [^3] formalised DVH generation as a QA-sensitive computational process and identified the algorithmic decision points: VROI construction, Boolean operations, dose interpolation, grid interactions, histogram binning, and plan normalisation. TG-53 deliberately did not prescribe a numeric DVH tolerance [^3]. The IAEA Technical Report Series No. 430 [^25] reinforced this by treating DVH generation as a distinct QA problem, separate from dose calculation, requiring independent commissioning of anatomy modelling, dose sampling, histogram construction, and structure logic. It further documented that a 5% dose change can alter response by roughly 10–30%, supporting a target of about 3% dose-calculation accuracy [^25]. Panitsa et al. [^4] provided early quality control testing of DVH computation using simple geometric phantoms, showing that high-gradient regions are far more demanding than low-gradient regions and that the number of sampling points materially affects DVH accuracy.

**Consensus:** DVH computation depends on multiple interacting algorithmic choices. Structure discretisation should be decoupled from dose-grid resolution [^1], [^3], [^25]. Validation must include synthetic phantoms with known truth [^1], [^3], [^4]. Binary voxel-centre inclusion is a historical baseline, not a gold standard [^1], [^15].

**Design implication:** Every algorithmic choice identified by Drzymala [^1], TG-53 [^3], and the IAEA [^25] must be explicit, configurable, and documented in provenance.

### 3.2 Analytical Benchmark Datasets and Whole-Curve Validation

Nelms et al. [^14] created synthetic DICOM RTSTRUCT and RTDOSE datasets for spheres, cylinders, and cones with closed-form analytical cumulative DVHs. Their benchmark revealed that Pinnacle v9.8 had 52/340 endpoint deviations exceeding 3% versus 5/340 for PlanIQ v2.1 in the fine-contour test, with Pinnacle Dmin errors reaching 60% under SI gradients due to an end-cap inconsistency where the structure volume included half-slice end-caps but dose voxels in the added region were omitted from the DVH tally [^14].

Pepin et al. [^18] extended this by introducing a precision concept: staircase artefacts in computed DVHs interpreted as discretisation-driven uncertainty bands. Their vendor survey revealed heterogeneous implementations (detailed in Section 7). Median precision-band widths: MIM Maestro v6.9.6: 0.90%, Eclipse v15.5: 0.93%, ProKnow DS v1.22: 1.05%, Mobius3D v3.1: 1.96%, RayStation v9A: 3.22% [^18]. Eclipse showed strong directional bimodality: cone AP precision 2.86% versus cone SI 0.047% [^18]. (Note: the Pepin paper reports the Eclipse version as v15.5.52 in §2.2 but v15.1.52 in Table 3; this internal inconsistency in the source is noted for transparency.)

Stanley et al. [^17] created analytically generated DICOM data for spheres from 3–20 mm diameter with 50 random placements per size across five anonymised commercial systems. Their downloadable benchmark is valuable for phase-sensitivity characterisation.

Grammatikou et al. [^20] provided modern validation for intracranial SRS with VMAT, with publicly available synthetic datasets on Mendeley Data under CC BY 4.0 (DOI 10.17632/pb55hjf5y3.1).

Walker and Byrne [^21] used spherical/Gaussian analytical cases and explicitly quantified small-volume stereotactic metric errors (PCI, GI) across multiple systems including RayStation, MasterPlan, and ProKnow.

Gossman et al. [^10] demonstrated a complementary approach using a synthetic benchmark with known depth-dose characteristics against Eclipse AAA v8.6, achieving approximately 0.4–0.6% mean deviation and 2.0% total-volume deviation [^10].

**Consensus:** Analytical benchmarks are indispensable. Whole-curve validation is necessary [^14], [^18]. End-capping and between-slice interpolation are major sources of cross-system disagreement [^14], [^18].

**Design implication:** All available analytical benchmark datasets [^14], [^17], [^20], [^21] should be incorporated into the validation corpus. Precision-band analysis per Pepin [^18] should be a standard diagnostic output.

### 3.3 Cross-System Variability

Ebert et al. [^9] compared DVH data from multiple radiotherapy treatment planning systems using the SWAN software as a consistent reference, finding that volume-definition and boundary-handling effects were a major source of disagreement, especially for small structures. Notably, Ebert et al. found that relaxing the volume criterion from 1% to 5% increased the DVH gamma pass rate from 78% to 96%, whereas relaxing the dose criterion from 1% to 5% improved it only from 78% to 85% [^9] — a clear quantitative indication that volumetric/boundary-related disagreement dominated over dose-bin-related disagreement for these datasets. Kirisits et al. [^7] found inter-system volume variability with standard deviations of 3–9% and D0.1cc standard deviations of 3–6% across seven brachytherapy planning systems, identifying end-slice and reconstruction algorithm effects as major contributors [^7]. (Note: the 3–9% SD range spans CT 4 mm and MRI 5 mm datasets, which differ in both slice thickness and imaging modality; this confound should be kept in mind.)

Penoncello et al. [^19] evaluated eight commercial systems given identical imported DICOM data. Structure-volume ratios relative to Eclipse ranged from 1.036 to 1.101, all significantly different at P < .001. Dose-grid refinement from 2.5 mm to 1.25 mm produced only modest improvement, whereas differences in end-capping, interpolation, and voxel inclusion explained much of the remaining spread [^19].

**Consensus:** Cross-system disagreement is real, persistent, and clinically relevant. It arises primarily from geometry handling rather than dose-grid sampling alone [^9], [^19]. Ebert et al. [^9] and Penoncello et al. [^19] independently confirm that volume-related effects are a larger source of inter-system DVH disagreement than dose-related effects.

### 3.4 Voxelisation and Slice-Thickness Effects

Sunderland et al. [^15] showed that binary centre-inclusion voxelisation at 2.5 mm could degrade DVH agreement to as low as 28.48% (1% acceptance criteria) for small structures in steep gradients, despite Dice coefficients of 0.884 [^15]. Geometric overlap metrics are poor surrogates for DVH fidelity [^15].

Corbett et al. [^5] showed that V200 in prostate brachytherapy was far more discretisation-sensitive than V100: V200 RMS error reached 27% at 2.5 mm voxels and 69% at 5 mm, while V100 remained within approximately 1% even at 5 mm [^5].

Kirisits et al. [^7] found volume reconstruction variability increasing from approximately 1–3% SD at CT 2 mm slices to 3–9% at MRI 5 mm slices [^7].

**Consensus:** Coarse voxelisation disproportionately affects small structures and high-gradient regions [^5], [^15], [^17]. Binary centre-inclusion is fundamentally limited [^15].

**Design implication:** The tool should support fractional-occupancy or exact sub-voxel integration as its primary mode, with binary centre-inclusion as a legacy/emulation option.

### 3.5 Dose-Grid Resolution and Grid-Origin Effects

Chung et al. [^6] found that for H&N IMRT in Pinnacle, moving from 1.5 mm to 4 mm grids produced 95th-percentile dose differences of approximately 3.0 Gy, and that grid-origin shifts of half a voxel alone produced differences up to approximately 2.0 Gy [^6].

Rosewall et al. [^13] showed that for bladder-wall DVHs in prostate IMRT (Pinnacle v9.0), 1.5 mm was the only grid spacing that kept the full DVH within 1 cc of the 1 mm benchmark for *every* patient (i.e. the worst-patient threshold); at 2.0 mm, worst-patient differences reached 2.5 cc, although average performance was better [^13].

Snyder et al. [^16] showed that in spine SRS (Eclipse v11, AAA v11), moving from 1.0 mm to 2.5 mm increased mean Cord_D10% by 13.0% and Cord_D0.03cc by 10.1%, with worst-case increases of 23.2% and 22.7% [^16].

**Consensus:** Dose-grid resolution materially affects DVH outputs, especially for small structures and steep gradients [^6], [^13], [^16]. Grid-origin phase contributes errors of similar magnitude [^6].

**Design implication:** The tool should warn when input dose-grid spacing is likely inadequate. Grid-phase sensitivity analysis should be supported. The tool should distinguish its own interpolation/integration error from error already embedded in the imported dose grid [^6]. *[Engineering inference]*

### 3.6 Small-Volume Stereotactic Behaviour

Stanley et al. [^17] found that for 3 mm spheres at 1 mm slice spacing, mean volume errors across five anonymised systems ranged from −23.7% to +1.3%, with V100% errors of −4.3% to +2.0% in mean but individual-placement ranges to −36.3% to +20.3% [^17]. V50% was far more stable (means within approximately 1%) [^17]. Derived indices (CI, GI) amplified discrepancies [^17].

Walker and Byrne [^21] found, in synthetic analytical tests, cumulative DVH deviations up to 20 percentage points for the smallest tested volumes, with PCI errors up to 40% and GI errors up to approximately 71.8% for sub-cc structures [^21]. RayStation showed approximately 10% average DVH difference for a 3 mm radius sphere, dropping to approximately 1% at 10 mm and approximately 0.1% at 20 mm [^21].

**Consensus:** Sub-cc structures in steep gradients are where all current systems struggle. Phase sensitivity can dominate mean bias [^17]. Kooy et al. [^2] showed that even with their spatially targeted Monte Carlo approach, 1–2 mm thick shells near small intracranial targets exhibited approximately 7% sampling error, demonstrating that thin-walled structures are an especially demanding subclass of the small-structure problem.

**Under-validated:** The literature tests almost exclusively spheres. Irregular, concave, branching, and multi-component small structures remain unvalidated. This is a major gap.

**Derived index sensitivity:** Grammatikou et al. [^20] confirmed that among all tested stereotactic indices, GI was the most sensitive to discretisation changes — more so than D95 or CI. This is consistent with Walker and Byrne's finding [^21] that small underlying DVH deviations are amplified into large GI/PCI errors for sub-cc structures. For validation, this means GI should be treated as a sentinel metric: if GI is accurate, other indices are likely also well-behaved.

### 3.7 Between-Slice Interpolation

Pepin et al. [^18] found that Mobius3D v3.1, MIM Maestro v6.9.6, and ProKnow DS v1.22 treated contour slices as right prisms between slices, while Eclipse v15.5 and RayStation v9A used shape-based interpolation [^18]. The choice materially affected DVH curves, especially for tapered structures like cones where the cross-section changes rapidly between slices [^18].

Shape-based interpolation (originally described by Herman et al. [^24] using discrete chamfer-distance transforms; the modern form uses continuous signed-distance-field interpolation between slices) is more theoretically sound than right-prism extrusion because it produces smooth surfaces that better approximate the continuous anatomy between imaged slices, rather than introducing artificial stair-stepped discontinuities. It also handles tapered and tapering-to-point structures more naturally. However, it is more computationally expensive and introduces its own assumptions about the surface trajectory between slices that may not always match the true anatomy. *[Engineering inference — the continuous SDF formulation described in §7.2.2 is a modern generalisation of the discrete distance-transform approach in Herman et al. [^24]]*

**Design implication:** The tool should support both methods. Shape-based interpolation is the theoretically preferred default for reference mode. Right-prism is the more common commercial approach and should be available for emulation and comparison.

### 3.8 SBRT Constraint Semantics

Grimm et al. [^11] compiled published SBRT normal-tissue dose tolerance limits and found that clinically used constraints are expressed in heterogeneous forms: maximum point dose, dose-to-cc, dose-to-%, and "critical volume must be spared" rules [^11]. Sub-cc endpoints are common: spinal cord constraints use 0.25 cc and 1.2 cc hotspot volumes [^11].

**Design implication:** The metric grammar must support all constraint forms found in clinical practice, including spared-volume logic.

### 3.9 Further Concepts Noted for Future Work

**Uncertainty-propagated DVH.** Henriquez and Castrillon [^8] proposed the dose-expected volume histogram (DeVH), a probabilistic extension that accounts for point-dose calculation uncertainty. The formulation is computationally efficient, operating as a dose-bin redistribution on the differential DVH [^8]. This is noted as a potential future extension; the architecture should not preclude it, but it is not a v1 deliverable.

**Motion-weighted DVH.** Zhang et al. [^12] proposed motion-weighted target volumes using temporal occupancy probability. This is noted as a future extension.

**Dose-mass histograms.** The concept of weighting histogram contributions by tissue mass (or electron density) rather than volume has been discussed in the broader literature. *[Assumption — no specific citation; the concept is well-known but the RFC authors have not identified a single canonical source.]* The architecture should support per-voxel weighting to enable this in future.

### 3.10 Summary: What the Literature Implies for Design

| Design choice | Literature consensus | Key references |
| --- | --- | --- |
| Structure-dose grid decoupling | Strong consensus | [^1], [^3], [^6], [^25] |
| Sub-voxel/fractional occupancy | Strong consensus | [^15], [^17], [^18] |
| Configurable end-capping | Essential; no single "correct" method | [^14], [^18], [^19] |
| Configurable between-slice interpolation | Essential; shape-based is theoretically preferred | [^18], [^19], [^24] |
| Fine histogram binning | Strong consensus | [^1], [^14], [^18] |
| Analytical benchmark validation | Strong consensus | [^14], [^17], [^18], [^20], [^21] |
| Whole-curve validation, not just endpoints | Strong consensus | [^14], [^18] |
| Small-structure uncertainty reporting | Strong consensus | [^17], [^21] |
| Phase-sensitivity testing | Supported but under-practised | [^6], [^17] |
| Grid-resolution warnings | Strong consensus | [^6], [^13], [^16] |
| Surface-aware extrema and near-extrema | Supported | [^14], [^18] |
| Geometry handling $\geq$ dose handling in priority | Strong consensus | [^9], [^19] |
| GI as a sentinel validation metric | Supported | [^20], [^21] |

---

## 4. Product Scope

### 4.1 v1 Scope

**Modalities:** Conventional photon, VMAT, SRS, and SBRT plan evaluation.

**Inputs:**

- DICOM RTSTRUCT + RTDOSE via pydicom
- Raw NumPy arrays (structure mask or contour coordinates + 3D dose array)

**Core capabilities:**

- Full cumulative and differential DVH computation
- Comprehensive metric extraction (Dx%, Dxcc, VxGy, Vx%, mean, median, min, max, and stereotactic indices)
- Per-ROI dose references supporting SIB and multi-target radiosurgery
- Configurable accuracy-speed tradeoffs with named profiles
- Reference mode for validation
- Provenance-rich, JSON-serialisable result objects
- Python API and CLI
- DICOM RTDOSE DVH export (writing computed DVH curves into a valid DICOM RTDOSE object)
- Per-ROI error handling (strict / repair_if_safe / skip_invalid)
- Per-ROI algorithm config override (`config_override` on `ROIMetricRequest`): enables reference-mode computation only for small OARs where it matters, while using faster practical mode for large targets
- Efficient CPU execution with `numba` JIT compilation, parallelisation, and batched memory management

**ROI topology support:** Branching structures, holes, disconnected islands, and other topologies that can legitimately represent anatomy.

### 4.2 Explicitly Out of Scope for v1

- Dose summation / accumulation across fractions or plans
- Proton, brachytherapy
- Biological metrics (EUD, gEUD, NTCP, TCP)
- Derived ROI Boolean algebra (union, intersection, subtraction, rings, cropped structures)
- Weighted or motion-aware ROIs [^12] (architecture should not preclude)
- Dose-surface histograms (DSH), dose-mass histograms (architecture should support per-voxel weighting)
- Uncertainty-propagated DVH / DeVH [^8] (architecture should support)
- GPU acceleration (architecture uses array-oriented patterns amenable to future GPU extension; see Section 13)

### 4.3 Future Extensions

1. Boolean ROI algebra (SDF-based; see Section 13.2)
2. Uncertainty-propagated DVH [^8]
3. Biological metrics (EUD, gEUD, NTCP, TCP)
4. Dose-surface and dose-mass histograms
5. Motion-weighted DVH [^12]
6. Proton-specific considerations
7. Multi-plan dose accumulation with deformable registration hooks
8. Brachytherapy support
9. GPU-accelerated DVH pipeline (Section 13.3)
10. SDF-first architecture with exact analytical partial-volume computation (Section 13.1)
11. Neural implicit structure representations (Section 13.5)

---

## 5. Design Principles

1. **Transparency over magic.** Every algorithmic choice is explicit, configurable, and recorded in provenance.

2. **Evidence-bounded claims.** Performance is stated relative to specific benchmarks. The tool is honest about what it does and does not validate.

3. **Reference mode is a first-class citizen.** The slow, high-accuracy reference pathway exists primarily to validate faster modes and to serve as a benchmark reference. It is part of the validation architecture.

4. **Separation of concerns.** Structure geometry, dose sampling, histogram construction, and metric extraction are distinct, independently testable stages. Request, config, and result are distinct type hierarchies sharing no mutable state.

5. **Deterministic reproducibility.** Identical inputs and configuration produce bit-identical outputs. Non-determinism is explicitly controlled.

6. **Fail loudly and specifically.** Warnings are issued when settings are likely inadequate. One bad ROI never silently corrupts other results. Skipped and failed ROIs are explicitly represented in results, distinguishable from "not requested."

7. **CPU-first with `numba` acceleration.** v1 targets CPU with `numba` JIT compilation and thread-based parallelisation, plus efficient memory management with configurable batching for large structure sets. Architecture uses array-oriented patterns amenable to future GPU extension via CuPy, JAX, or NVIDIA Warp. *[Design proposal]*

8. **Test-first development.** Every feature is preceded by its tests. Property-based tests enforce metric semantics. Golden-data regression tests gate every merge.

9. **Stable public surface, flexible internals.** The public API and result types are designed for long-term stability. Internal intermediates (interpolation strategies, occupancy kernels, geometry models) remain private until implementation proves which abstractions are durable.

10. **Self-describing subobjects.** Result objects carry their own identity and specification. A `MetricResult` carries its `MetricSpec`; an `ROIResult` carries its `ROIRef`. Redundancy at subobject boundaries is preferred over requiring parent-context to interpret a child.

---

## 6. Detailed Tool Specification and Architecture

This section defines every data type in the system. Types at the public API boundary use frozen dataclasses with `slots=True` and, for types containing NumPy arrays, `eq=False` (since default dataclass equality is wrong for `ndarray`). Array-bearing types defensively copy and mark arrays read-only on construction. Validation logic lives in `__post_init__`. Strategy protocols define extension points for algorithmic choices but remain private/internal until implementation proves which abstractions are durable.

### 6.1 Design Philosophy for Data Types

1. **Immutable by default.** Every domain object is a frozen dataclass with `slots=True`. Mutation happens by constructing a new instance via `dataclasses.replace()`. This eliminates accidental state corruption, makes provenance trivial, and enables safe concurrent computation.

2. **Shallow immutability is acknowledged.** `frozen=True` does **not** make `np.ndarray` or `dict` fields immutable. For array-bearing types, arrays are defensively copied on construction and the copy is made read-only via `array.flags.writeable = False`. For mapping-bearing result types, `types.MappingProxyType` is used where practical. These objects are shallowly frozen — deep mutation would require bypassing the read-only flag, which is considered sufficient for the intended use.

3. **Small, composable types.** Even concepts as simple as a dose reference or a grid frame are explicit dataclasses. This avoids primitive obsession (passing bare floats and tuples), enables validation at construction time, and provides self-documenting field names.

4. **Validate at the boundary.** Every dataclass validates its invariants in `__post_init__`. Once constructed, an object is guaranteed valid. Downstream code never re-checks invariants.

5. **Protocols for strategy selection.** Algorithmic choices (interpolation, end-capping, occupancy, dose interpolation) are defined as `typing.Protocol` classes with narrow, mechanically testable signatures. Concrete implementations are selected at configuration time and recorded in provenance. New algorithms can be added without modifying existing code. Protocols and their implementations are **private** — only the public API, request types, config types, and result types are stable.

6. **Separation of request, config, and result.** What to compute (metric requests), how to compute it (config), and what was computed (results) are distinct type hierarchies. They share no mutable state.

7. **Self-describing results.** Result objects carry their own identity. `MetricResult` carries its `MetricSpec`; `ROIResult` carries its `ROIRef` and explicit status. A result is interpretable without its parent context.

8. **Issues are scoped and sourced.** Diagnostic issues live at the level where they originate: metric-level issues on `MetricResult`, ROI-level issues on `ROIResult`, global issues on `DVHResultSet`. Issues carry a `path` tuple identifying their source. A convenience method `DVHResultSet.all_issues()` collects across all levels when a flat view is needed.

### 6.2 Grid Frame and Spatial Model

A single `GridFrame` type defines all regular 3D grids in the system, making array axis order explicit and carrying an index-to-patient affine transform. This eliminates the ambiguity of separate grid-geometry and coordinate-system types.

```python
from __future__ import annotations

import numpy as np
import numpy.typing as npt
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True, slots=True, eq=False)
class GridFrame:
    """Defines a regular 3D grid in patient coordinates with an explicit
    index-to-patient affine transform.

    The canonical array axis order is (z, y, x) — matching the DICOM
    convention where the z-axis (slice direction) is the slowest-varying
    index. All 3D arrays in the system (dose, occupancy, SDF) use this
    axis order.

    The affine transform `index_to_patient_mm` is a 4×4 matrix mapping
    integer voxel indices (iz, iy, ix) to patient coordinates (x, y, z)
    in mm. For axis-aligned grids with uniform spacing, this is:

        [[0,    0,    dx,   origin_x],
         [0,    dy,   0,    origin_y],
         [dz,   0,    0,    origin_z],
         [0,    0,    0,    1       ]]

    where origin is the (x, y, z) patient coordinate of voxel [0, 0, 0].

    For v1, only axis-aligned grids are supported. The affine is
    validated to be axis-aligned on construction. Future versions may
    support oblique grids by relaxing this constraint. If a supplied
    dose grid is not axis-aligned with patient coordinates, the pipeline
    raises `IssueCode.OBLIQUE_DOSE_GRID` with a clear error message
    explaining the v1 limitation and recommending re-export with an
    axis-aligned grid.

    Invariants:

        - shape_zyx has three strictly positive elements
        - index_to_patient_mm is a (4, 4) matrix
        - the affine is axis-aligned (v1 constraint)
        - spacing derived from the affine is strictly positive
    """
    shape_zyx: tuple[int, int, int]
    index_to_patient_mm: npt.NDArray[np.float64]  # (4, 4) affine

    def __post_init__(self) -> None:
        if any(n <= 0 for n in self.shape_zyx):
            raise ValueError(f"Grid shape must be positive, got {self.shape_zyx}")
        if self.index_to_patient_mm.shape != (4, 4):
            raise ValueError(
                f"Affine must be (4, 4), got {self.index_to_patient_mm.shape}"
            )
        # Defensive copy and read-only
        aff = np.array(self.index_to_patient_mm, dtype=np.float64)
        aff.flags.writeable = False
        object.__setattr__(self, 'index_to_patient_mm', aff)

        sp = self.spacing_mm
        if any(s <= 0 for s in sp):
            raise ValueError(f"Derived spacing must be positive, got {sp}")

    @property
    def spacing_mm(self) -> tuple[float, float, float]:
        """(dz, dy, dx) voxel spacing in mm, derived from the affine."""
        aff = self.index_to_patient_mm
        dz = float(np.linalg.norm(aff[:3, 0]))
        dy = float(np.linalg.norm(aff[:3, 1]))
        dx = float(np.linalg.norm(aff[:3, 2]))
        return (dz, dy, dx)

    @property
    def spacing_xyz_mm(self) -> tuple[float, float, float]:
        """(dx, dy, dz) spacing — patient-coordinate order convenience."""
        dz, dy, dx = self.spacing_mm
        return (dx, dy, dz)

    @property
    def origin_mm(self) -> tuple[float, float, float]:
        """(x, y, z) patient coordinate of voxel [0, 0, 0]."""
        return tuple(self.index_to_patient_mm[:3, 3])

    @property
    def num_voxels(self) -> int:
        return self.shape_zyx[0] * self.shape_zyx[1] * self.shape_zyx[2]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GridFrame):
            return NotImplemented
        return (
            self.shape_zyx == other.shape_zyx
            and np.array_equal(self.index_to_patient_mm, other.index_to_patient_mm)
        )

    def __hash__(self) -> int:
        return hash((self.shape_zyx, self.index_to_patient_mm.tobytes()))

    @classmethod
    def from_uniform(
        cls,
        shape_zyx: tuple[int, int, int],
        spacing_xyz_mm: tuple[float, float, float],
        origin_xyz_mm: tuple[float, float, float],
    ) -> GridFrame:
        """Convenience constructor for axis-aligned uniform grids.

        Args:
            shape_zyx: (nz, ny, nx) grid dimensions.
            spacing_xyz_mm: (dx, dy, dz) voxel spacing in mm.
            origin_xyz_mm: (x, y, z) of voxel [0, 0, 0] centre in mm.
        """
        dx, dy, dz = spacing_xyz_mm
        ox, oy, oz = origin_xyz_mm
        aff = np.array([
            [0,    0,    dx,   ox],
            [0,    dy,   0,    oy],
            [dz,   0,    0,    oz],
            [0,    0,    0,    1 ],
        ], dtype=np.float64)
        return cls(shape_zyx=shape_zyx, index_to_patient_mm=aff)
```

### 6.3 Dose Reference Types

A single global dose reference is insufficient for SIB, multi-target radiosurgery, or mixed requests where one ROI uses 42 Gy and another uses 60 Gy. `DoseReferenceSet` provides a named registry of dose references with an optional default, allowing each metric to bind to a specific reference.

```python
from typing import Mapping, Optional

@dataclass(frozen=True, slots=True)
class DoseReference:
    """An explicit dose reference for percentage-dose metric computation.

    The tool never guesses the reference dose. Any metric containing '%'
    on the dose axis must have a DoseReference supplied.

    Invariants:

        - dose_gy is strictly positive
        - source is non-empty (forces the user to document provenance)
    """
    dose_gy: float
    source: str

    def __post_init__(self) -> None:
        if self.dose_gy <= 0:
            raise ValueError(f"Reference dose must be positive, got {self.dose_gy}")
        stripped = self.source.strip()
        if not stripped:
            raise ValueError(
                "DoseReference.source must be non-empty. Document where "
                "this value came from (e.g. 'prescription: 3 fx × 14 Gy')."
            )
        if len(stripped) < 5:
            raise ValueError(
                f"DoseReference.source must be at least 5 characters "
                f"(got '{stripped}'). Provide a meaningful description of "
                f"where this dose reference comes from, e.g. "
                f"'prescription: 3 fx × 14 Gy to 80% IDL'."
            )

@dataclass(frozen=True, slots=True)
class DoseReferenceSet:
    """A named registry of dose references with an optional default.

    Supports SIB and multi-target plans where different ROIs reference
    different prescription doses. Each metric can bind to a reference
    by id; if unspecified, the default is used.

    Examples:
        DoseReferenceSet(
            refs={"ptv60": DoseReference(60.0, "PTV60 prescription"),
                  "ptv42": DoseReference(42.0, "PTV42 prescription")},
            default_id="ptv60"
        )

    Invariants:

        - If default_id is set, it must exist in refs
        - refs is non-empty
    """
    refs: Mapping[str, DoseReference]
    default_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.refs:
            raise ValueError("DoseReferenceSet must contain at least one reference")
        if self.default_id is not None and self.default_id not in self.refs:
            raise ValueError(
                f"default_id '{self.default_id}' not found in refs: "
                f"{list(self.refs.keys())}"
            )

    @property
    def default(self) -> Optional[DoseReference]:
        """The default DoseReference, or None if no default is set."""
        if self.default_id is None:
            return None
        return self.refs[self.default_id]

    def get(self, ref_id: Optional[str] = None) -> DoseReference:
        """Resolve a reference by id, falling back to the default.

        Raises ValueError if neither ref_id nor default_id resolves.
        """
        if ref_id is not None:
            if ref_id not in self.refs:
                raise ValueError(
                    f"Dose reference '{ref_id}' not found. "
                    f"Available: {list(self.refs.keys())}"
                )
            return self.refs[ref_id]
        if self.default_id is not None:
            return self.refs[self.default_id]
        raise ValueError(
            "No ref_id specified and no default_id set in DoseReferenceSet"
        )

    @classmethod
    def single(cls, dose_gy: float, source: str) -> DoseReferenceSet:
        """Convenience for the common single-prescription case."""
        ref = DoseReference(dose_gy=dose_gy, source=source)
        return cls(refs={"default": ref}, default_id="default")
```

### 6.4 ROI Identity Type

`ROIRef` is carried end-to-end from DICOM import through request, internal compute, and result output. Name-based lookup is a convenience method that raises on ambiguity, not the primary key.

```python
@dataclass(frozen=True, slots=True)
class ROIRef:
    """Identifies an ROI across the entire pipeline.

    Provides a single source of truth for ROI identity, carried from
    DICOM import through request, internal compute, and result output.

    The roi_number, when present, comes from the DICOM ROI Number
    (3006,0022) and provides an unambiguous identifier even when ROI
    names are duplicated (which does occur in clinical practice).
    For raw-array inputs, roi_number is None.

    The colour_rgb, when present, comes from DICOM ROI Display Color
    (3006,002A) and is preserved through the pipeline to results,
    enabling downstream plotting in the ROI's DICOM-specified colour
    without requiring a back-reference to the original structure data.

    Identity semantics: two ROIRefs match if their roi_number matches
    (when both have one), otherwise by name. This is the primary key
    throughout the system.

    Invariants:

        - name is non-empty
        - colour_rgb values (when present) are in [0, 255]
    """
    name: str
    roi_number: Optional[int] = None
    colour_rgb: Optional[tuple[int, int, int]] = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("ROI name must be non-empty")
        if self.colour_rgb is not None:
            for i, c in enumerate(self.colour_rgb):
                if not (0 <= c <= 255):
                    raise ValueError(
                        f"colour_rgb values must be in 0..255, "
                        f"got {c} at index {i}"
                    )

    def __str__(self) -> str:
        if self.roi_number is not None:
            return f"{self.name} (#{self.roi_number})"
        return self.name

    def matches(self, other: ROIRef) -> bool:
        """Match by roi_number if both have one, else by name."""
        if self.roi_number is not None and other.roi_number is not None:
            return self.roi_number == other.roi_number
        return self.name == other.name
```

### 6.5 Metric Request Types

`MetricSpec` is a proper metric AST: `subject + operator + threshold + output_unit + dose_ref_id`. The string grammar `"D95%"` remains as a compact parser on top. `MetricSpec` carries its own canonical identity for deduplication, rather than relying on the raw input string.

Note: HI = (D2% − D98%) / D50% depends only on volume-percentage dose queries, not percent-of-reference-dose queries. It therefore does **not** require a dose reference.

```python
from enum import Enum
from typing import FrozenSet

class MetricFamily(str, Enum):
    """The family of metric being requested."""
    DVH_DOSE = "dvh_dose"        # Dx% → dose at volume, Dxcc → dose at volume
    DVH_VOLUME = "dvh_volume"    # VxGy → volume at dose, Vx% → volume at dose
    SCALAR = "scalar"            # mean, median, min, max
    INDEX = "index"              # HI, CI, PCI, GI

class ThresholdUnit(str, Enum):
    """Unit of the threshold/input axis."""
    PERCENT = "percent"
    CC = "cc"
    GY = "Gy"
    NONE = "none"   # for scalars/indices

class OutputUnit(str, Enum):
    """Unit of the metric output."""
    GY = "Gy"
    PERCENT_DOSE = "percent_dose"   # output as % of dose reference
    CC = "cc"
    PERCENT_VOLUME = "percent_vol"  # output as % of total volume
    DIMENSIONLESS = "dimensionless"

@dataclass(frozen=True, slots=True)
class MetricSpec:
    """A fully parsed, unambiguous metric specification.

    This is the metric AST — a structured representation that is
    unambiguous about what is being computed, in what unit, and
    against which dose reference.

    Constructed from a raw string via MetricSpec.parse("D95%") or
    directly for programmatic use.

    Examples:
        MetricSpec.parse("D95%")    → family=DVH_DOSE, threshold=95.0,
                                      threshold_unit=PERCENT, output_unit=GY
        MetricSpec.parse("D0.03cc") → family=DVH_DOSE, threshold=0.03,
                                      threshold_unit=CC, output_unit=GY
        MetricSpec.parse("V10Gy")   → family=DVH_VOLUME, threshold=10.0,
                                      threshold_unit=GY, output_unit=CC
        MetricSpec.parse("V95%")    → family=DVH_VOLUME, threshold=95.0,
                                      threshold_unit=PERCENT, output_unit=CC
        MetricSpec.parse("V20Gy[%]") → output as % of total volume
        MetricSpec.parse("D95%[%Rx]") → output as % of dose reference

    Invariants:

        - threshold is non-negative when present
        - threshold_unit and output_unit are consistent with family
    """
    family: MetricFamily
    threshold: Optional[float] = None
    threshold_unit: ThresholdUnit = ThresholdUnit.NONE
    output_unit: OutputUnit = OutputUnit.GY
    dose_ref_id: Optional[str] = None  # binds to a DoseReferenceSet entry
    raw: str = ""  # Original string, preserved for display/provenance

    def __post_init__(self) -> None:
        if self.threshold is not None and self.threshold < 0:
            raise ValueError(f"Metric threshold must be non-negative, got {self.threshold}")

    @property
    def requires_dose_ref(self) -> bool:
        """Whether this metric needs a DoseReference to be evaluated.

        Required when the threshold is a percentage of the reference dose
        (V95% → need Rx to compute 95% of Rx), or when the output is
        expressed relative to a reference dose (D95%[%Rx]), or for
        whole-field indices (CI, PCI, GI) that require a prescription dose.

        NOT required for HI = (D2% - D98%) / D50%, which uses only
        volume-percentage dose queries.
        """
        if self.threshold_unit == ThresholdUnit.PERCENT and self.family == MetricFamily.DVH_VOLUME:
            return True  # V95% → 95% of Rx
        if self.output_unit == OutputUnit.PERCENT_DOSE:
            return True  # D95%[%Rx]
        if self.family == MetricFamily.INDEX and self.raw in {"CI", "PCI", "GI"}:
            return True  # whole-field indices need Rx
        return False

    @property
    def canonical_key(self) -> str:
        """A canonical string key for deduplication.

        Two MetricSpecs with the same canonical_key compute the same thing.
        This is used for deduplication instead of comparing raw strings,
        which may differ in formatting.
        """
        parts = [self.family.value]
        if self.threshold is not None:
            parts.append(f"{self.threshold}")
        parts.append(self.threshold_unit.value)
        parts.append(self.output_unit.value)
        if self.dose_ref_id:
            parts.append(f"ref={self.dose_ref_id}")
        return "|".join(parts)

    @classmethod
    def parse(cls, raw: str) -> MetricSpec:
        """Parse a metric string into a typed MetricSpec.

        Grammar:
            D{x}%              → DVH_DOSE, threshold=x, threshold_unit=PERCENT, output=GY
            D{x}%[%Rx]         → DVH_DOSE, threshold=x, threshold_unit=PERCENT, output=PERCENT_DOSE
            D{x}cc             → DVH_DOSE, threshold=x, threshold_unit=CC, output=GY
            V{x}Gy             → DVH_VOLUME, threshold=x, threshold_unit=GY, output=CC
            V{x}Gy[%]          → DVH_VOLUME, threshold=x, threshold_unit=GY, output=PERCENT_VOLUME
            V{x}%              → DVH_VOLUME, threshold=x, threshold_unit=PERCENT, output=CC
            mean | median | min | max → SCALAR
            HI | CI | PCI | GI → INDEX

        Raises ValueError on unparseable input.
        """
        # Implementation omitted for brevity; see tests for expected behaviour
        ...

@dataclass(frozen=True, slots=True)
class ROIMetricRequest:
    """Metrics requested for a single ROI.

    Invariants:

        - roi is a valid ROIRef
        - metrics is non-empty
        - no duplicate metrics (by canonical_key)
        - dose_ref_id, if set, overrides the default for this ROI
        - config_override, if set, overrides the global DVHConfig for this ROI

    Per-ROI config override is a v1 feature motivated by clinical need: expensive
    reference-mode computation is only required for small OARs where partial-volume
    accuracy matters most, while faster practical mode is adequate for large targets.
    This avoids applying expensive computation uniformly across all structures.
    """
    roi: ROIRef
    metrics: tuple[MetricSpec, ...]
    dose_ref_id: Optional[str] = None  # per-ROI dose reference override
    config_override: Optional[DVHConfig] = None  # per-ROI algorithm config override (v1)

    def __post_init__(self) -> None:
        if not self.metrics:
            raise ValueError(f"ROI '{self.roi}' must have at least one metric")
        keys = [m.canonical_key for m in self.metrics]
        if len(keys) != len(set(keys)):
            raise ValueError(f"Duplicate metrics for ROI '{self.roi}'")

    @classmethod
    def from_strings(
        cls, name: str, metric_strings: list[str],
        roi_number: Optional[int] = None,
        dose_ref_id: Optional[str] = None,
        config_override: Optional[DVHConfig] = None,
    ) -> ROIMetricRequest:
        return cls(
            roi=ROIRef(name=name, roi_number=roi_number),
            metrics=tuple(MetricSpec.parse(s) for s in metric_strings),
            dose_ref_id=dose_ref_id,
            config_override=config_override,
        )

@dataclass(frozen=True, slots=True)
class MetricRequestSet:
    """Complete specification of what to compute.

    Groups dose references with per-ROI metric requests. Constructible
    from Python code, a dict, or TOML.

    Invariants:

        - If any requested metric requires a dose reference, dose_refs must resolve it
        - No duplicate ROIs (by ROIRef.matches)
    """
    roi_requests: tuple[ROIMetricRequest, ...]
    dose_refs: Optional[DoseReferenceSet] = None

    def __post_init__(self) -> None:
        # Check for duplicate ROIs
        for i, a in enumerate(self.roi_requests):
            for b in self.roi_requests[i+1:]:
                if a.roi.matches(b.roi):
                    raise ValueError(
                        f"Duplicate ROI in request: '{a.roi}' and '{b.roi}'"
                    )
        # Check dose ref availability
        for rr in self.roi_requests:
            for m in rr.metrics:
                if m.requires_dose_ref:
                    ref_id = m.dose_ref_id or rr.dose_ref_id
                    if self.dose_refs is None:
                        raise ValueError(
                            f"Metric '{m.raw}' for ROI '{rr.roi}' requires a "
                            f"dose reference, but no DoseReferenceSet was provided"
                        )
                    # Verify the ref_id resolves
                    try:
                        self.dose_refs.get(ref_id)
                    except ValueError as e:
                        raise ValueError(
                            f"Metric '{m.raw}' for ROI '{rr.roi}': {e}"
                        ) from e

    @property
    def roi_refs(self) -> FrozenSet[ROIRef]:
        return frozenset(rr.roi for rr in self.roi_requests)

    @classmethod
    def from_dict(cls, d: dict) -> MetricRequestSet:
        """Construct from a compact dict representation.

        Expected format:
            {
                "dose_refs": {
                    "ptv60": {"dose_gy": 60.0, "source": "PTV60 prescription"},
                    "ptv42": {"dose_gy": 42.0, "source": "PTV42 prescription"},
                },
                "default_dose_ref": "ptv60",
                "metrics": {
                    "PTV60": {"metrics": ["D95%", "D0.03cc"], "dose_ref": "ptv60"},
                    "PTV42": {"metrics": ["D95%", "mean", "HI"], "dose_ref": "ptv42"},
                    "SpinalCanal": {"metrics": ["D0.03cc"]},
                }
            }

        Simplified format (single dose ref, backward compatible):
            {
                "dose_ref_gy": 42.0,
                "dose_ref_source": "prescription",
                "metrics": {
                    "PTV42": ["D95%", "D99%"],
                    "SpinalCanal": ["D0.03cc"],
                }
            }
        """
        # Build dose references
        dose_refs = None
        if "dose_refs" in d:
            refs = {
                k: DoseReference(dose_gy=v["dose_gy"], source=v["source"])
                for k, v in d["dose_refs"].items()
            }
            dose_refs = DoseReferenceSet(
                refs=refs, default_id=d.get("default_dose_ref")
            )
        elif "dose_ref_gy" in d:
            source = d.get("dose_ref_source")
            if not source or not source.strip():
                raise ValueError(
                    "dose_ref_source must be non-empty when dose_ref_gy "
                    "is specified. Document where this value came from."
                )
            dose_refs = DoseReferenceSet.single(
                dose_gy=d["dose_ref_gy"], source=source
            )

        # Build ROI requests
        roi_requests = []
        for roi_key, spec in d["metrics"].items():
            if isinstance(spec, list):
                # Simple format: just a list of metric strings
                roi_requests.append(
                    ROIMetricRequest.from_strings(roi_key, spec)
                )
            elif isinstance(spec, dict):
                # Rich format: {"metrics": [...], "dose_ref": "..."}
                roi_requests.append(
                    ROIMetricRequest.from_strings(
                        roi_key, spec["metrics"],
                        dose_ref_id=spec.get("dose_ref"),
                    )
                )
        return cls(
            roi_requests=tuple(roi_requests),
            dose_refs=dose_refs,
        )

    @classmethod
    def from_toml(cls, path: str) -> MetricRequestSet:
        """Load from a TOML file. See from_dict for schema."""
        import tomllib  # Python 3.11+; tomli for earlier
        with open(path, "rb") as f:
            d = tomllib.load(f)
        return cls.from_dict(d)
```

**TOML format examples:**

Simple single-prescription case:

```toml
dose_ref_gy = 42.0
dose_ref_source = "prescription: 3 fx × 14 Gy to 80% IDL"

[metrics]
PTV42 = ["D95%", "D99%", "D0.03cc", "mean", "HI"]
SpinalCanal = ["D0.03cc", "max"]
Duodenum = ["D0.03cc", "D5cc"]
```

SIB / multi-target format:

```toml
default_dose_ref = "ptv60"

[dose_refs.ptv60]
dose_gy = 60.0
source = "PTV60 prescription: 30 fx × 2.0 Gy"

[dose_refs.ptv42]
dose_gy = 42.0
source = "PTV42 prescription: 30 fx × 1.4 Gy"

[metrics.PTV60]
metrics = ["D95%", "D99%", "V95%", "HI"]
dose_ref = "ptv60"

[metrics.PTV42]
metrics = ["D95%", "mean"]
dose_ref = "ptv42"

[metrics.SpinalCanal]
metrics = ["D0.03cc", "max"]
```

### 6.6 Configuration Types

Configuration is separated into three distinct groups: `AlgorithmConfig` (choices that change results), `RuntimeConfig` (execution environment), and `PipelinePolicy` (import/output policy). Named profiles are factory methods on a top-level `DVHConfig` that composes all three.

```python
from enum import Enum
from dataclasses import field

class InterpolationMethod(str, Enum):
    RIGHT_PRISM = "right_prism"
    SHAPE_BASED = "shape_based"

class EndCapPolicy(str, Enum):
    NONE = "none"
    HALF_SLICE = "half_slice"
    HALF_SLICE_CAPPED = "half_slice_capped"
    ROUNDED = "rounded"

class OccupancyMethod(str, Enum):
    BINARY_CENTRE = "binary_centre"
    FRACTIONAL_SUPERSAMPLED = "fractional_supersampled"
    ADAPTIVE_SUPERSAMPLED = "adaptive_supersampled"

class PointInPolygonRule(str, Enum):
    SCANLINE_EVEN_ODD = "scanline_even_odd"
    WINDING_NUMBER = "winding_number"

class DoseInterpolationMethod(str, Enum):
    TRILINEAR = "trilinear"
    TRICUBIC_CATMULL_ROM = "tricubic_catmull_rom"
    TRICUBIC_BSPLINE = "tricubic_bspline"

class DVHType(str, Enum):
    CUMULATIVE = "cumulative"
    DIFFERENTIAL = "differential"
    BOTH = "both"

class InvalidROIPolicy(str, Enum):
    STRICT = "strict"
    REPAIR_IF_SAFE = "repair_if_safe"
    SKIP_INVALID = "skip_invalid"

class FloatingPointPrecision(str, Enum):
    FLOAT32 = "float32"
    FLOAT64 = "float64"

class BinningStrategy(str, Enum):
    """Controls how DVH bin edges are chosen.

    UNIFORM_GY (default for practical mode): Uniform-width bins from 0 to
        max_dose_gy * (1 + margin_fraction). Default bin width: 0.5 Gy
        (per Drzymala et al. recommendation). Edges are NOT forced to align
        with dose grid values.

    DOSE_GRID_ALIGNED (default for reference mode): Bin edges coincide with
        dose grid values present in the sampled set. Eliminates interpolation
        artefacts in cumulative DVH.

    CUSTOM: User supplies explicit dose_bin_edges_gy array via BinningConfig.
        Must be strictly monotonically increasing.
    """
    UNIFORM_GY = "uniform_gy"
    DOSE_GRID_ALIGNED = "dose_grid_aligned"
    CUSTOM = "custom"

@dataclass(frozen=True, slots=True)
class SupersamplingConfig:
    """Controls supersampling behaviour.

    Either a fixed integer factor, or adaptive with convergence params.
    """
    factor: Optional[int] = None  # None means adaptive
    adaptive_min_voxels: int = 10000
    adaptive_convergence_tol: float = 0.002
    adaptive_edge_refinement: bool = True

    @property
    def is_adaptive(self) -> bool:
        return self.factor is None

    def __post_init__(self) -> None:
        if self.factor is not None and self.factor < 1:
            raise ValueError(f"Supersampling factor must be >= 1, got {self.factor}")
        if self.adaptive_min_voxels < 1:
            raise ValueError("adaptive_min_voxels must be >= 1")
        if self.adaptive_convergence_tol <= 0:
            raise ValueError("adaptive_convergence_tol must be positive")

    @classmethod
    def adaptive(
        cls,
        min_voxels: int = 10000,
        convergence_tol: float = 0.002,
        edge_refinement: bool = True,
    ) -> SupersamplingConfig:
        return cls(
            factor=None,
            adaptive_min_voxels=min_voxels,
            adaptive_convergence_tol=convergence_tol,
            adaptive_edge_refinement=edge_refinement,
        )

    @classmethod
    def fixed(cls, factor: int) -> SupersamplingConfig:
        return cls(factor=factor)

@dataclass(frozen=True, slots=True)
class AlgorithmConfig:
    """Settings that affect computed results. Any change here can
    produce different outputs from the same inputs.

    Groups: structure geometry, dose sampling, histogram construction.
    """
    # Structure geometry
    interpolation_method: InterpolationMethod = InterpolationMethod.SHAPE_BASED
    endcap_policy: EndCapPolicy = EndCapPolicy.HALF_SLICE
    endcap_max_mm: Optional[float] = None
    occupancy_method: OccupancyMethod = OccupancyMethod.ADAPTIVE_SUPERSAMPLED
    point_in_polygon: PointInPolygonRule = PointInPolygonRule.SCANLINE_EVEN_ODD
    supersampling: SupersamplingConfig = field(default_factory=SupersamplingConfig.adaptive)
    surface_sampling: bool = True

    # Dose sampling
    dose_interpolation: DoseInterpolationMethod = DoseInterpolationMethod.TRILINEAR

    # Histogram construction
    dvh_bin_width_gy: float = 0.5  # 0.5 Gy default per Drzymala et al. recommendation
    dvh_binning_strategy: BinningStrategy = BinningStrategy.UNIFORM_GY
    dvh_type: DVHType = DVHType.BOTH

    # Precision
    floating_point_precision: FloatingPointPrecision = FloatingPointPrecision.FLOAT64

    def __post_init__(self) -> None:
        if self.dvh_bin_width_gy <= 0:
            raise ValueError(f"dvh_bin_width_gy must be positive, got {self.dvh_bin_width_gy}")
        if (
            self.endcap_policy == EndCapPolicy.HALF_SLICE_CAPPED
            and self.endcap_max_mm is None
        ):
            raise ValueError(
                "endcap_max_mm is required when endcap_policy is 'half_slice_capped'"
            )

@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """Settings that affect performance but not results (when
    deterministic=True). Changes here should produce bit-identical
    outputs.
    """
    deterministic: bool = True
    max_threads: Optional[int] = None  # None = cpu_count()
    batch_size_gb: float = 12.0

    def __post_init__(self) -> None:
        if self.batch_size_gb <= 0:
            raise ValueError(f"batch_size_gb must be positive, got {self.batch_size_gb}")
        if self.max_threads is not None and self.max_threads < 1:
            raise ValueError(f"max_threads must be >= 1, got {self.max_threads}")

@dataclass(frozen=True, slots=True)
class PipelinePolicy:
    """Settings controlling import behaviour, error handling, and output
    policy. These do not affect the numerical computation of valid ROIs.
    """
    invalid_roi_policy: InvalidROIPolicy = InvalidROIPolicy.REPAIR_IF_SAFE
    anonymise_provenance: bool = False
    z_tolerance_mm: float = 0.01  # tolerance for normalising slice z-coordinates

@dataclass(frozen=True, slots=True)
class DVHConfig:
    """Complete configuration, composed from three orthogonal sub-configs.

    Named profiles (reference, fast) are factory methods.
    """
    algorithm: AlgorithmConfig = field(default_factory=AlgorithmConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    policy: PipelinePolicy = field(default_factory=PipelinePolicy)

    @classmethod
    def reference(cls) -> DVHConfig:
        """High-accuracy reference mode. TENTATIVE — pending benchmark calibration."""
        return cls(
            algorithm=AlgorithmConfig(
                interpolation_method=InterpolationMethod.SHAPE_BASED,
                endcap_policy=EndCapPolicy.ROUNDED,
                occupancy_method=OccupancyMethod.ADAPTIVE_SUPERSAMPLED,
                point_in_polygon=PointInPolygonRule.WINDING_NUMBER,
                supersampling=SupersamplingConfig.adaptive(
                    min_voxels=40000, convergence_tol=0.001, edge_refinement=True
                ),
                surface_sampling=True,
                dvh_bin_width_gy=0.005,
                dvh_type=DVHType.BOTH,
            ),
            runtime=RuntimeConfig(
                deterministic=True,
                max_threads=1,  # Single-threaded for full determinism
            ),
        )

    @classmethod
    def fast(cls) -> DVHConfig:
        """Speed-optimised practical mode. TENTATIVE — pending benchmark calibration."""
        return cls(
            algorithm=AlgorithmConfig(
                interpolation_method=InterpolationMethod.RIGHT_PRISM,
                endcap_policy=EndCapPolicy.HALF_SLICE,
                occupancy_method=OccupancyMethod.FRACTIONAL_SUPERSAMPLED,
                point_in_polygon=PointInPolygonRule.SCANLINE_EVEN_ODD,
                supersampling=SupersamplingConfig.fixed(3),
                surface_sampling=False,
                dvh_bin_width_gy=0.01,
                dvh_type=DVHType.CUMULATIVE,
            ),
            runtime=RuntimeConfig(deterministic=True),
        )
```

### 6.7 Geometry / Structure Types

`PlanarRegion(exterior, holes=...)` provides validated contour data with explicit hole representation. The system distinguishes between raw imported contours (`Contour`) and canonical validated contours (`PlanarRegion`). Slice z-coordinates are normalised at import time using the policy's `z_tolerance_mm` to eliminate exact-float-equality brittleness from DICOM.

```python
@dataclass(frozen=True, slots=True, eq=False)
class Contour:
    """A single closed 2D polygon on a single axial slice.

    Points are stored as an (N, 2) array of (x, y) coordinates in mm,
    in the patient coordinate system. The contour is implicitly
    closed (last point connects to first).

    This is a raw contour — it may have any winding order and may
    contain defects. Use PlanarRegion for validated geometry.

    Invariants:

        - points has shape (N, 2) with N >= 3
        - z_mm is finite
    """
    points_xy: npt.NDArray[np.float64]   # shape (N, 2)
    z_mm: float

    def __post_init__(self) -> None:
        if self.points_xy.ndim != 2 or self.points_xy.shape[1] != 2:
            raise ValueError(
                f"Expected (N, 2) array, got shape {self.points_xy.shape}"
            )
        if self.points_xy.shape[0] < 3:
            raise ValueError(
                f"Contour needs >= 3 points, got {self.points_xy.shape[0]}"
            )
        if not np.isfinite(self.z_mm):
            raise ValueError(f"z_mm must be finite, got {self.z_mm}")
        # Defensive copy
        pts = np.array(self.points_xy, dtype=np.float64)
        pts.flags.writeable = False
        object.__setattr__(self, 'points_xy', pts)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Contour):
            return NotImplemented
        return self.z_mm == other.z_mm and np.array_equal(self.points_xy, other.points_xy)

    def __hash__(self) -> int:
        return hash((self.z_mm, self.points_xy.tobytes()))

@dataclass(frozen=True, slots=True, eq=False)
class PlanarRegion:
    """A validated 2D region on a single slice: one exterior boundary
    with zero or more holes.

    The exterior is CCW (positive signed area). Each hole is CW
    (negative signed area). All polygons are closed and non-self-
    intersecting.

    This is the canonical post-validation slice geometry. Use this
    for all computation; use raw Contour only for import/repair.
    """
    exterior_xy_mm: npt.NDArray[np.float64]  # (N, 2), CCW
    holes_xy_mm: tuple[npt.NDArray[np.float64], ...] = ()  # each CW

    def __post_init__(self) -> None:
        ext = np.array(self.exterior_xy_mm, dtype=np.float64)
        ext.flags.writeable = False
        object.__setattr__(self, 'exterior_xy_mm', ext)

        validated_holes = []
        for h in self.holes_xy_mm:
            hc = np.array(h, dtype=np.float64)
            hc.flags.writeable = False
            validated_holes.append(hc)
        object.__setattr__(self, 'holes_xy_mm', tuple(validated_holes))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PlanarRegion):
            return NotImplemented
        if not np.array_equal(self.exterior_xy_mm, other.exterior_xy_mm):
            return False
        if len(self.holes_xy_mm) != len(other.holes_xy_mm):
            return False
        return all(
            np.array_equal(a, b) for a, b in zip(self.holes_xy_mm, other.holes_xy_mm)
        )

    def __hash__(self) -> int:
        return hash(self.exterior_xy_mm.tobytes())

@dataclass(frozen=True, slots=True)
class ContourROI:
    """A validated, z-sorted ROI defined by planar regions on axial slices.

    This is the canonical contour-based ROI representation after import,
    z-normalisation, and geometric validation.

    Slices are stored as (z_mm, regions) pairs. z-coordinates are
    normalised at import time using the policy's z_tolerance_mm to
    eliminate exact-float-equality brittleness from DICOM.

    The combination_mode and coordinate_frame fields carry geometry-
    interpretation metadata that was previously on a separate Structure
    type. These live here rather than on ROIRef because they govern
    how contours are combined during voxelisation, not ROI identity.

    Invariants:

        - slices are sorted by z_mm (ascending)
        - no duplicate z values (after normalisation)
        - at least one slice
        - each slice has at least one PlanarRegion
    """
    roi: ROIRef
    slices: tuple[tuple[float, tuple[PlanarRegion, ...]], ...]
    combination_mode: str = "auto"       # "auto", "xor", "slice_union", "vendor_compat_xor"
    coordinate_frame: str = "DICOM_PATIENT"

    def __post_init__(self) -> None:
        if not self.slices:
            raise ValueError(f"ContourROI '{self.roi}' has no slices")
        z_values = [s[0] for s in self.slices]
        if z_values != sorted(z_values):
            raise ValueError(f"Slices not sorted by z for '{self.roi}'")
        if len(z_values) != len(set(z_values)):
            raise ValueError(f"Duplicate z values in '{self.roi}'")
        for z, regions in self.slices:
            if not regions:
                raise ValueError(f"Empty slice at z={z} in '{self.roi}'")

    @property
    def num_slices(self) -> int:
        return len(self.slices)

    @property
    def z_values_mm(self) -> tuple[float, ...]:
        return tuple(s[0] for s in self.slices)

    @property
    def z_extent_mm(self) -> float:
        zs = self.z_values_mm
        return zs[-1] - zs[0]

    @property
    def mean_slice_spacing_mm(self) -> Optional[float]:
        if self.num_slices < 2:
            return None
        return self.z_extent_mm / (self.num_slices - 1)
```

### 6.8 Dose and Occupancy Types

```python
@dataclass(frozen=True, slots=True, eq=False)
class DoseGrid:
    """A 3D dose array on a regular grid with explicit axis contract.

    The array `dose_gy` has shape (nz, ny, nx) — matching GridFrame.shape_zyx.
    Values are in Gy.

    Invariants:

        - dose_gy shape matches frame.shape_zyx
        - all values are finite
    """
    dose_gy: npt.NDArray[np.float64]  # (nz, ny, nx)
    frame: GridFrame
    uncertainty_gy: Optional[npt.NDArray[np.float64]] = None

    def __post_init__(self) -> None:
        expected = self.frame.shape_zyx
        if self.dose_gy.shape != expected:
            raise ValueError(
                f"Dose shape {self.dose_gy.shape} != frame shape {expected}"
            )
        # Defensive copy + read-only
        d = np.array(self.dose_gy, dtype=np.float64)
        d.flags.writeable = False
        object.__setattr__(self, 'dose_gy', d)
        if self.uncertainty_gy is not None:
            if self.uncertainty_gy.shape != expected:
                raise ValueError("Uncertainty shape must match dose shape")
            u = np.array(self.uncertainty_gy, dtype=np.float64)
            u.flags.writeable = False
            object.__setattr__(self, 'uncertainty_gy', u)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DoseGrid):
            return NotImplemented
        return (
            self.frame == other.frame
            and np.array_equal(self.dose_gy, other.dose_gy)
        )

    def __hash__(self) -> int:
        return hash((self.frame, self.dose_gy.tobytes()))

@dataclass(frozen=True, slots=True, eq=False)
class OccupancyField:
    """A 3D float array representing fractional voxel occupancy.

    Values are in [0.0, 1.0]. Interior voxels are 1.0, exterior 0.0,
    boundary voxels have intermediate values.

    Shape is (nz, ny, nx) matching frame.shape_zyx.

    Invariants:

        - data shape matches frame.shape_zyx
        - all values in [0.0, 1.0]
    """
    data: npt.NDArray[np.float64]
    frame: GridFrame
    roi: ROIRef

    def __post_init__(self) -> None:
        expected = self.frame.shape_zyx
        if self.data.shape != expected:
            raise ValueError(
                f"Occupancy shape {self.data.shape} != frame shape {expected}"
            )
        d = np.array(self.data, dtype=np.float64)
        d.flags.writeable = False
        object.__setattr__(self, 'data', d)

    @property
    def volume_cc(self) -> float:
        """Total structure volume in cc (mm³ / 1000)."""
        dz, dy, dx = self.frame.spacing_mm
        voxel_volume_mm3 = dx * dy * dz
        return float(np.sum(self.data)) * voxel_volume_mm3 / 1000.0

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, OccupancyField):
            return NotImplemented
        return (
            self.frame == other.frame
            and self.roi == other.roi
            and np.array_equal(self.data, other.data)
        )

    def __hash__(self) -> int:
        return hash((self.frame, self.roi.name, self.data.tobytes()))
```

### 6.9 Result Types

Key design decisions: (1) `DVHBins` is the canonical DVH storage primitive, storing dose bin edges + differential volume — cumulative and percentage views are derived, avoiding duplicated state; (2) `Issue` provides rich diagnostics with severity level, machine-parseable code, and a `path` tuple identifying the source; (3) `MetricResult` carries its own `MetricSpec` for self-describing results; (4) `ROIResult` carries `ROIRef` and explicit `status` (ok/skipped/failed); (5) `DVHResultSet` stores a tuple of `ROIResult` rather than a name-keyed dict, since ROI names may duplicate.

```python
from typing import Any

class IssueLevel(str, Enum):
    """Severity level for diagnostic issues."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

class IssueCode(str, Enum):
    """Machine-parseable issue codes."""
    STRUCTURE_VOLUME_SMALL = "STRUCTURE_VOLUME_SMALL"
    DOSE_GRID_COARSE = "DOSE_GRID_COARSE"
    SPARSE_CONTOUR_STACK = "SPARSE_CONTOUR_STACK"
    STEEP_GRADIENT_BOUNDARY = "STEEP_GRADIENT_BOUNDARY"
    CONVERGENCE_NOT_REACHED = "CONVERGENCE_NOT_REACHED"
    ENDCAP_LARGE_FRACTION = "ENDCAP_LARGE_FRACTION"
    DOSE_COVERAGE_INCOMPLETE = "DOSE_COVERAGE_INCOMPLETE"
    CONTOUR_REPAIRED = "CONTOUR_REPAIRED"
    CONTOUR_STAGE_BYPASSED = "CONTOUR_STAGE_BYPASSED"
    ROI_SKIPPED = "ROI_SKIPPED"
    ROI_FAILED = "ROI_FAILED"
    METRIC_UNAVAILABLE = "METRIC_UNAVAILABLE"
    Z_TOLERANCE_APPLIED = "Z_TOLERANCE_APPLIED"
    DOSE_REFERENCE_MISSING = "DOSE_REFERENCE_MISSING"
    # Raised when the supplied dose grid is not axis-aligned with patient
    # coordinates. v1 does not support oblique dose grids. The error message
    # must clearly explain this v1 limitation and suggest re-exporting with
    # an axis-aligned grid.
    OBLIQUE_DOSE_GRID = "OBLIQUE_DOSE_GRID"

@dataclass(frozen=True, slots=True)
class Issue:
    """A structured diagnostic issue with source path.

    Each issue carries a severity level, a machine-parseable code,
    a human-readable message, optional structured context, and a
    path tuple identifying its source (e.g. ("PTV60", "D95%") for
    a metric-level issue).

    Issues do NOT shadow the built-in Warning type.
    """
    level: IssueLevel
    code: IssueCode
    message: str
    path: tuple[str, ...] = ()
    context: Optional[dict[str, Any]] = None

@dataclass(frozen=True, slots=True, eq=False)
class DVHBins:
    """Canonical DVH storage: dose bin edges + differential volume.

    This is the single source of truth for DVH data. Cumulative DVH,
    percentage volumes, and metric extraction are all derived from this
    representation, avoiding duplicated state and inconsistency.

    dose_bin_edges_gy has length N+1 for N bins. differential_volume_cc
    has length N. The bin for index j spans [dose_bin_edges_gy[j],
    dose_bin_edges_gy[j+1]).

    Invariants:

        - dose_bin_edges_gy has length N+1 with N >= 1
        - dose_bin_edges_gy is strictly monotonically increasing
        - differential_volume_cc has length N
        - differential_volume_cc values are non-negative
        - total_volume_cc is positive

    Note: `functools.cached_property` cannot be used with `slots=True` (no
    `__dict__`). Derived arrays are precomputed in `__post_init__` and stored
    as private fields, exposed via regular `@property`. See Appendix B.3.
    """
    dose_bin_edges_gy: npt.NDArray[np.float64]   # (N+1,)
    differential_volume_cc: npt.NDArray[np.float64]  # (N,)
    total_volume_cc: float

    # Precomputed derived arrays (slots=True requires explicit field declarations)
    _cumulative_volume_cc: npt.NDArray[np.float64] = field(init=False, repr=False)
    _cumulative_volume_pct: npt.NDArray[np.float64] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        edges = np.array(self.dose_bin_edges_gy, dtype=np.float64)
        dv = np.array(self.differential_volume_cc, dtype=np.float64)
        if len(edges) < 2:
            raise ValueError("DVHBins needs at least 2 bin edges (1 bin)")
        if len(dv) != len(edges) - 1:
            raise ValueError(
                f"differential_volume_cc length {len(dv)} != "
                f"dose_bin_edges_gy length {len(edges)} - 1"
            )
        edges.flags.writeable = False
        dv.flags.writeable = False
        object.__setattr__(self, 'dose_bin_edges_gy', edges)
        object.__setattr__(self, 'differential_volume_cc', dv)
        # Precompute cumulative arrays
        cum = np.concatenate([
            np.cumsum(dv[::-1])[::-1],
            [0.0]
        ])
        cum.flags.writeable = False
        object.__setattr__(self, '_cumulative_volume_cc', cum)
        pct = cum / float(self.total_volume_cc) * 100.0
        pct.flags.writeable = False
        object.__setattr__(self, '_cumulative_volume_pct', pct)

    @property
    def bin_width_gy(self) -> float:
        """Uniform bin width (assumes uniform spacing)."""
        return float(self.dose_bin_edges_gy[1] - self.dose_bin_edges_gy[0])

    @property
    def cumulative_volume_cc(self) -> npt.NDArray[np.float64]:
        """Cumulative DVH: V(D) at each bin edge (N+1 values).

        cumulative_volume_cc[j] = total volume receiving >= dose_bin_edges_gy[j].
        """
        return self._cumulative_volume_cc

    @property
    def cumulative_volume_pct(self) -> npt.NDArray[np.float64]:
        """Cumulative DVH as percentage of total volume.
        """
        return self._cumulative_volume_pct

    @property
    def min_dose_gy(self) -> float:
        """Minimum dose in the DVH (lowest bin edge with nonzero volume)."""
        nonzero = np.nonzero(self.differential_volume_cc)[0]
        if len(nonzero) == 0:
            return 0.0
        return float(self.dose_bin_edges_gy[nonzero[0]])

    @property
    def max_dose_gy(self) -> float:
        """Maximum dose in the DVH (upper edge of highest occupied bin)."""
        nonzero = np.nonzero(self.differential_volume_cc)[0]
        if len(nonzero) == 0:
            return 0.0
        return float(self.dose_bin_edges_gy[nonzero[-1] + 1])

    @property
    def mean_dose_gy(self) -> float:
        """Volume-weighted mean dose, computed from bin centres."""
        bin_centres = (
            self.dose_bin_edges_gy[:-1] + self.dose_bin_edges_gy[1:]
        ) / 2.0
        return float(
            np.sum(bin_centres * self.differential_volume_cc)
            / self.total_volume_cc
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DVHBins):
            return NotImplemented
        return (
            np.array_equal(self.dose_bin_edges_gy, other.dose_bin_edges_gy)
            and np.array_equal(self.differential_volume_cc, other.differential_volume_cc)
            and self.total_volume_cc == other.total_volume_cc
        )

    def __hash__(self) -> int:
        return hash(self.dose_bin_edges_gy.tobytes())

@dataclass(frozen=True, slots=True)
class MetricResult:
    """Result for a single computed metric.

    Self-describing: carries its own MetricSpec so the result is
    interpretable without parent context.

    Issues at this level are specific to this metric only.
    """
    spec: MetricSpec
    value: Optional[float]  # None if metric could not be computed
    unit: str
    convergence_estimate: Optional[float] = None
    issues: tuple[Issue, ...] = ()

@dataclass(frozen=True, slots=True)
class ROIDiagnostics:
    """Per-ROI computation diagnostics."""
    effective_supersampling: Optional[int] = None
    boundary_voxel_count: Optional[int] = None
    interior_voxel_count: Optional[int] = None
    mean_boundary_gradient_gy_per_mm: Optional[float] = None
    contour_slice_count: int = 0
    endcap_volume_fraction: Optional[float] = None
    computation_time_s: Optional[float] = None

@dataclass(frozen=True, slots=True)
class ROIResult:
    """Complete result for a single ROI.

    Self-describing: carries its own ROIRef and explicit status.
    Callers can distinguish "ok", "skipped" (invalid ROI, skipped
    per policy), and "failed" (computation error).

    Issues at this level affect this ROI as a whole.
    """
    roi: ROIRef
    status: Literal["ok", "skipped", "failed"]
    volume_cc: Optional[float] = None
    metrics: tuple[MetricResult, ...] = ()
    dvh: Optional[DVHBins] = None
    diagnostics: Optional[ROIDiagnostics] = None
    issues: tuple[Issue, ...] = ()

@dataclass(frozen=True, slots=True)
class InputMetadata:
    """Metadata about the computation inputs, for provenance."""
    rtstruct_file_sha256: Optional[str] = None
    rtdose_file_sha256: Optional[str] = None
    dose_grid_frame: Optional[GridFrame] = None

@dataclass(frozen=True, slots=True)
class PlatformInfo:
    """Platform and dependency version info, for reproducibility."""
    python_version: str
    numpy_version: str
    numba_version: str
    os: str

@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    """Complete provenance for a computation run."""
    pymedphys_version: str
    timestamp_utc: str
    config: DVHConfig
    input_metadata: InputMetadata
    platform: PlatformInfo

@dataclass(frozen=True, slots=True)
class DVHResultSet:
    """Top-level result object. Immutable, JSON-serialisable, self-documenting.

    Results are stored as a tuple of ROIResult (not a name-keyed dict),
    since ROIRef is the primary identity and names may duplicate.
    Convenience methods provide name-based lookup with ambiguity checks.

    Issues at this level are global (not ROI- or metric-specific).
    """
    schema_version: str
    results: tuple[ROIResult, ...]
    provenance: ProvenanceRecord
    computation_time_s: float
    dose_refs: Optional[DoseReferenceSet] = None
    issues: tuple[Issue, ...] = ()

    def by_name(self, name: str) -> ROIResult:
        """Look up an ROIResult by name. Raises ValueError on ambiguity."""
        matches = [r for r in self.results if r.roi.name == name]
        if not matches:
            raise KeyError(f"No ROI named '{name}'")
        if len(matches) > 1:
            raise ValueError(
                f"Ambiguous ROI name '{name}' — {len(matches)} ROIs match. "
                f"Use by_ref() with an ROIRef including roi_number."
            )
        return matches[0]

    def by_ref(self, ref: ROIRef) -> ROIResult:
        """Look up an ROIResult by ROIRef (matches by number then name)."""
        for r in self.results:
            if r.roi.matches(ref):
                return r
        raise KeyError(f"No ROI matching {ref}")

    def __getitem__(self, key: str) -> ROIResult:
        """Convenience: result["PTV"] — delegates to by_name."""
        return self.by_name(key)

    @property
    def roi_names(self) -> FrozenSet[str]:
        return frozenset(r.roi.name for r in self.results)

    def all_issues(self) -> tuple[Issue, ...]:
        """Collect all issues across all levels: global, ROI, and metric.

        Returns issues in order: global, then per-ROI, then per-metric
        within each ROI.
        """
        all_i: list[Issue] = list(self.issues)
        for roi_result in self.results:
            all_i.extend(roi_result.issues)
            for metric_result in roi_result.metrics:
                all_i.extend(metric_result.issues)
        return tuple(all_i)
```

### 6.10 Public API

`DVHInputs` is a typed input bundle with named constructors, eliminating invalid states from mutually exclusive optional arguments.

```python
@dataclass(frozen=True, slots=True)
class DVHInputs:
    """Typed input bundle for DVH computation.

    Use the named constructors to build inputs from DICOM paths
    or raw NumPy arrays. This eliminates the invalid-state space
    of mutually exclusive optional arguments.
    """
    dose: DoseGrid
    structures: tuple[ContourROI, ...]
    # Raw DICOM paths for provenance (optional)
    rtstruct_path: Optional[str] = None
    rtdose_path: Optional[str] = None

    @classmethod
    def from_dicom(
        cls,
        rtstruct_path: str,
        rtdose_path: str,
        roi_names: Optional[list[str]] = None,
        policy: Optional[PipelinePolicy] = None,
    ) -> DVHInputs:
        """Load from DICOM RTSTRUCT + RTDOSE files.

        Args:
            rtstruct_path: Path to DICOM RTSTRUCT file.
            rtdose_path: Path to DICOM RTDOSE file.
            roi_names: If provided, only load these ROIs. If None, load all.
            policy: Pipeline policy for import (z-tolerance, invalid ROI handling).

        Returns:
            DVHInputs ready for compute_dvh().
        """
        # Implementation delegates to _io module
        ...

    @classmethod
    def from_arrays(
        cls,
        dose_gy: npt.NDArray,
        structures: dict[str, npt.NDArray],
        frame: GridFrame,
    ) -> DVHInputs:
        """Build from raw NumPy arrays.

        Args:
            dose_gy: 3D dose array in Gy, shape (nz, ny, nx).
            structures: Dict mapping ROI name to 3D mask array
                (bool for binary, float [0,1] for fractional occupancy).
            frame: Grid frame defining the spatial coordinates.

        Returns:
            DVHInputs ready for compute_dvh().

        Notes:
            When masks are provided as pre-computed float [0,1] arrays,
            the contour-stage pipeline is bypassed entirely: no contour
            validation, interpolation, or end-capping is performed.
            The mask is used directly as an OccupancyField. In this
            case, the following provenance and diagnostic implications
            apply:

            - ROIDiagnostics fields that derive from contour data
              (contour_slice_count, endcap_volume_fraction) will be
              None, since no contour stack exists.

            - The ProvenanceRecord will record that the input pathway
              was 'from_arrays' (not 'from_dicom'), and the
              AlgorithmConfig fields for interpolation_method and
              endcap_policy will be recorded but noted as inapplicable.

            - An Issue with code CONTOUR_STAGE_BYPASSED (level INFO)
              will be attached to each ROIResult whose input was a
              pre-voxelised mask, so downstream consumers can
              distinguish contour-derived from mask-derived results.

            - Boolean masks (dtype bool) are converted to float
              occupancy (0.0/1.0) and proceed through the standard
              supersampling pathway only if the user explicitly sets
              occupancy_method to a supersampling variant; otherwise
              they are treated as final binary occupancy.
        """
            DVHInputs ready for compute_dvh().
        """
        dose = DoseGrid(dose_gy=dose_gy, frame=frame)
        contour_rois = []
        for name, mask in structures.items():
            # Convert mask to ContourROI via marching squares or
            # directly to OccupancyField (bypass contour stage)
            ...
        return cls(dose=dose, structures=tuple(contour_rois))

def compute_dvh(
    inputs: DVHInputs,
    request: MetricRequestSet,
    config: Optional[DVHConfig] = None,
) -> DVHResultSet:
    """Compute DVH and extract metrics.

    This is the single public entry point. All input validation,
    coordinate handling, geometry reconstruction, dose sampling,
    histogram construction, metric extraction, and provenance
    recording are handled internally.

    Args:
        inputs: What to compute on (DICOM or arrays).
        request: What metrics to compute.
        config: How to compute. Defaults to DVHConfig().

    Returns:
        DVHResultSet with all requested metrics, DVH curves,
        diagnostics, and provenance.
    """
    ...
```

**Usage examples:**

```python
from pymedphys._dvh import (
    compute_dvh, DVHInputs, MetricRequestSet,
    DoseReferenceSet, DVHConfig,
)

# DICOM workflow
inputs = DVHInputs.from_dicom("RS.dcm", "RD.dcm")
request = MetricRequestSet.from_toml("metrics.toml")
result = compute_dvh(inputs, request, DVHConfig.reference())

# Print results
for roi_result in result.results:
    print(f"{roi_result.roi}: {roi_result.status}")
    if roi_result.status == "ok":
        for m in roi_result.metrics:
            print(f"  {m.spec.raw} = {m.value:.2f} {m.unit}")

# Raw array workflow
import numpy as np
frame = GridFrame.from_uniform(
    shape_zyx=(100, 256, 256),
    spacing_xyz_mm=(2.5, 2.5, 2.5),
    origin_xyz_mm=(-320.0, -320.0, -125.0),
)
inputs = DVHInputs.from_arrays(
    dose_gy=my_dose_array,
    structures={"PTV": my_ptv_mask, "Cord": my_cord_mask},
    frame=frame,
)
request = MetricRequestSet.from_dict({
    "dose_ref_gy": 42.0,
    "dose_ref_source": "prescription: 3 fx × 14 Gy",
    "metrics": {
        "PTV": ["D95%", "D99%", "mean", "HI"],
        "Cord": ["D0.03cc", "max"],
    }
})
result = compute_dvh(inputs, request)
```

### 6.11 Strategy Protocols (Private/Internal)

Strategy protocols are extension points for algorithmic choices, explicitly private. Their signatures use typed geometry models rather than ambiguous unions. The internal architecture builds a continuous `StructureModel` from contours, then samples it onto a grid — separating geometry construction from grid rasterisation.

These protocols are documented here for implementor reference but are not part of the stable public API. They may change between minor versions.

```python
from typing import Protocol, runtime_checkable

@dataclass(frozen=True, slots=True, eq=False)
class SDFField:
    """A 3D signed distance field on a regular grid.

    Values represent the signed distance to the structure boundary:
    negative inside, positive outside, zero on the boundary.
    The gradient magnitude is approximately 1 everywhere for an
    exact distance field.

    Shape is (nz, ny, nx) matching frame.shape_zyx.

    Invariants:

        - data shape matches frame.shape_zyx
        - all values are finite
    """
    data: npt.NDArray[np.float64]  # (nz, ny, nx)
    frame: GridFrame
    roi: ROIRef

    def __post_init__(self) -> None:
        expected = self.frame.shape_zyx
        if self.data.shape != expected:
            raise ValueError(
                f"SDF shape {self.data.shape} != frame shape {expected}"
            )
        d = np.array(self.data, dtype=np.float64)
        d.flags.writeable = False
        object.__setattr__(self, 'data', d)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SDFField):
            return NotImplemented
        return (
            self.frame == other.frame
            and self.roi == other.roi
            and np.array_equal(self.data, other.data)
        )

    def __hash__(self) -> int:
        return hash((self.frame, self.roi.name, self.data.tobytes()))

# StructureModel is a union of the two first-class structure representation types.
# SDFBuilder produces SDFField; RightPrismBuilder produces RightPrismModel.
# OccupancyComputer dispatches on the runtime type of the StructureModel it receives.
StructureModel = SDFField | RightPrismModel

@runtime_checkable
class StructureModelBuilder(Protocol):
    """Builds a continuous 3D structure model from a ContourROI.

    The structure model is an internal representation that can be sampled
    at arbitrary resolution. This separates geometry construction
    (right-prism vs SDF interpolation) from grid rasterisation
    (supersampling, occupancy computation).

    Two first-class implementations are supported (both fully validated):

    - **SDFBuilder** (reference mode default): produces an `SDFField` — a 3D
      signed-distance-field volume on a fine internal grid. Negative values =
      inside, positive = outside, zero = boundary.

    - **RightPrismBuilder** (practical/fast mode default): produces a
      `RightPrismModel` — a stack of 2D contour polygons with z-extents.
      This is NOT an SDF and does not return an `SDFField`.

    The return type is `StructureModel = SDFField | RightPrismModel`. The
    `OccupancyComputer` receives the `StructureModel` and dispatches to the
    appropriate occupancy algorithm based on its runtime type.
    """
    def build(
        self,
        contour_roi: ContourROI,
        config: AlgorithmConfig,
    ) -> StructureModel:
        """Return a continuous 3D structure model.

        The concrete return type depends on the builder implementation:
        - `SDFBuilder.build(...)` returns `SDFField`
        - `RightPrismBuilder.build(...)` returns `RightPrismModel`

        Both are variants of `StructureModel = SDFField | RightPrismModel`.
        """
        ...

@runtime_checkable
class OccupancyComputer(Protocol):
    """Computes fractional voxel occupancy from a structure model."""
    def compute(
        self,
        structure_sdf: SDFField,
        target_frame: GridFrame,
        config: AlgorithmConfig,
    ) -> OccupancyField:
        ...

@runtime_checkable
class DoseInterpolator(Protocol):
    """Interpolates dose at arbitrary points."""
    def evaluate(
        self,
        dose: DoseGrid,
        points_xyz: npt.NDArray[np.float64],  # (N, 3)
    ) -> npt.NDArray[np.float64]:  # (N,)
        ...
```

---

## 7. Algorithmic Design: Detailed Specification

This section specifies every algorithm in the DVH computation pipeline with full mathematical detail. Each subsection states the problem, defines the mathematics, describes candidate algorithms, analyses complexity and accuracy, cites the literature, and recommends a default with explicit justification.

### 7.0 Contour Area, Winding Order, and Geometric Validation

Before any DVH computation, imported contour data must be validated. Two fundamental geometric operations underpin this: signed area computation (which determines winding order) and self-intersection detection.

#### 7.0.1 Signed Area via the Shoelace Formula

Given a 2D polygon with $n$ vertices $(x_1, y_1), (x_2, y_2), \ldots, (x_n, y_n)$ listed in order (with the convention that $(x_{n+1}, y_{n+1}) \equiv (x_1, y_1)$), the **signed area** is:

$$A_{\text{signed}} = \frac{1}{2} \sum_{i=1}^{n} (x_i y_{i+1} - x_{i+1} y_i)$$

If $A_{\text{signed}} > 0$, the vertices are ordered counter-clockwise (CCW). If $A_{\text{signed}} < 0$, they are clockwise (CW). The absolute area is $|A_{\text{signed}}|$.

**Numerical stability:** For contours with coordinates far from the origin (as is common in DICOM patient coordinates where $x, y$ can be hundreds of mm), the products $x_i y_{i+1}$ can be large while the differences are small. This can cause catastrophic cancellation in float64. To mitigate this, translate the contour to its centroid before computing area:

$$\bar{x} = \frac{1}{n}\sum_{i=1}^{n} x_i, \quad \bar{y} = \frac{1}{n}\sum_{i=1}^{n} y_i$$

$$A_{\text{signed}} = \frac{1}{2} \sum_{i=1}^{n} ((x_i - \bar{x})(y_{i+1} - \bar{y}) - (x_{i+1} - \bar{x})(y_i - \bar{y}))$$

This is algebraically equivalent but numerically superior. *[Engineering inference]*

**Usage in validation:**

- Contour with $|A_{\text{signed}}| < \epsilon$ (configurable, e.g. $10^{-6}$ $\text{mm}^2$) is flagged as degenerate (zero-area slice)
- Winding order sign determines whether a contour is an outer boundary (CCW by convention) or a hole (CW)
- Inconsistent winding within a slice may indicate data corruption

#### 7.0.2 Self-Intersection Detection

A simple polygon should have no edge-edge crossings other than at consecutive-edge shared vertices. Self-intersection detection is $O(n^2)$ by brute-force (test all edge pairs) or $O(n \log n)$ via the Bentley-Ottmann sweep-line algorithm.

For v1, the brute-force approach is acceptable since clinical contours rarely have more than a few hundred vertices. For each pair of non-adjacent edges $(e_i, e_j)$ where $|i - j| > 1 \mod n$, test for intersection using the standard cross-product orientation test.

**Segment intersection test:** Two line segments $\mathbf{P}_1\mathbf{P}_2$ and $\mathbf{P}_3\mathbf{P}_4$ intersect if and only if both of the following hold:

1. $\mathbf{P}_3$ and $\mathbf{P}_4$ lie on opposite sides of the line through $\mathbf{P}_1\mathbf{P}_2$
2. $\mathbf{P}_1$ and $\mathbf{P}_2$ lie on opposite sides of the line through $\mathbf{P}_3\mathbf{P}_4$

using the 2D cross product for the sidedness test. Collinear/degenerate cases (where any cross product is exactly zero) require additional overlap checks. *[Engineering inference — standard computational geometry]*

### 7.1 Point-in-Polygon Algorithms

**Problem:** Given a 2D point $\mathbf{p} = (p_x, p_y)$ and a closed polygon $P$ with vertices $\{(x_i, y_i)\}_{i=1}^{n}$, determine whether $\mathbf{p}$ lies inside $P$. This is the innermost operation in voxelisation and is called millions of times per structure. Performance and correctness under edge cases are both critical.

#### 7.1.1 Ray Casting (Even-Odd Rule)

Cast a semi-infinite ray from $\mathbf{p}$ in any fixed direction (conventionally $+x$). Count the number of intersections with polygon edges. If odd, $\mathbf{p}$ is inside; if even, outside.

**Algorithm:** For each edge $(x_i, y_i) \to (x_{i+1}, y_{i+1})$:

1. Skip if both $y_i$ and $y_{i+1}$ are on the same side of $p_y$ (no crossing possible)
2. Compute the $x$-coordinate of the intersection: $x_{\text{int}} = x_i + (p_y - y_i) \cdot \frac{x_{i+1} - x_i}{y_{i+1} - y_i}$
3. If $x_{\text{int}} > p_x$, the ray crosses this edge; toggle inside/outside

**Vertex handling (the "half-plane" convention):** When the ray passes exactly through a vertex, the vertex is treated as belonging to the upper half-plane only. Concretely, an edge is crossed only if $\min(y_i, y_{i+1}) \leq p_y < \max(y_i, y_{i+1})$ — note the strict inequality on the upper bound. This ensures that a shared vertex between two edges is counted exactly once. This convention was described by Drzymala et al. [^1] as the scanline even-odd crossing rule.

**Complexity:** $O(n)$ per query. No preprocessing.

**Strengths:** Simple, fast, well-understood. Works for all simple (non-self-intersecting) polygons. The default method in most radiotherapy software.

**Weaknesses:** For self-intersecting polygons, the even-odd rule gives different results from the winding number rule. The method requires careful handling of degenerate cases (horizontal edges, point exactly on an edge).

#### 7.1.2 Winding Number Algorithm

The winding number $w(\mathbf{p}, P)$ counts how many times the polygon $P$ winds around point $\mathbf{p}$ in the counter-clockwise direction. If $w \neq 0$, $\mathbf{p}$ is inside $P$.

**Efficient implementation (per Sunday [^27]):** Rather than computing angles (which requires expensive $\arctan$ calls), the winding number can be computed using the same edge-crossing framework as ray casting, but tracking direction.

**Complexity:** $O(n)$ per query. Same as ray casting — no trigonometry needed.

**Strengths:** Correctly handles self-intersecting polygons and multiply-wound contours. More robust for points very close to the polygon boundary.

**Weaknesses:** Slightly more complex to implement. Sensitive to polygon orientation convention.

#### 7.1.3 Handling Multi-Component Contours (Holes)

A single DICOM RTSTRUCT slice may contain multiple contours, representing disconnected islands or structures with holes. With the `PlanarRegion` type, holes are explicitly typed rather than inferred from winding order at query time. For the even-odd rule, holes work automatically via the crossing count. For the winding number, the outer boundary contributes $w = +1$ and the hole contributes $w = -1$.

**Recommendation for v1:** Support both ray casting and winding number, with winding number as the default for reference mode due to its superior robustness for pathological contours. Ray casting is the default for practical mode. *[Design proposal]*

### 7.2 Contour Interpolation / Structure Reconstruction

**Problem:** DICOM RTSTRUCT encodes anatomy as a stack of 2D contour polygons, one per CT slice. Between slices, the 3D shape is undefined. The reconstruction method determines the 3D volume.

#### 7.2.1 Right-Prism Extrusion

**Right-prism is a first-class method, not an emulation of SDF.** The `RightPrismBuilder` protocol implementation produces a `RightPrismModel` — a stack of 2D contour polygons with z-extents. This is architecturally distinct from the SDF representation and is not emulated via SDF approximation. Both methods are fully supported and independently validated:

- **`RightPrismBuilder` → `RightPrismModel`**: default for practical/fast mode. Uses point-in-polygon directly for occupancy (no SDF needed).
- **`SDFBuilder` → `SDFField`**: default for reference mode. Full 3D signed-distance field computation.

The `OccupancyComputer` dispatches on the runtime type of the `StructureModel` it receives (`isinstance` check on `SDFField` vs `RightPrismModel`).

Each contour is extruded perpendicular to its slice plane. For adjacent slices at $z_i$ and $z_{i+1}$, the midpoint $z_m = (z_i + z_{i+1})/2$ defines the transition.

**Matches:** Mobius3D v3.1, MIM Maestro v6.9.6, ProKnow DS v1.22 [^18].

#### 7.2.2 Shape-Based Interpolation (Signed Distance Field)

Originally described by Herman et al. [^24]. The modern form uses continuous Euclidean signed distance fields (SDFs) with linear interpolation between slices.

**Step 1:** Compute 2D SDF on each contour slice. For multi-component contours (exterior + holes via `PlanarRegion`), the sign convention uses the winding number: $\phi < 0$ where the winding number is non-zero.

**Step 2:** Linearly interpolate SDFs between slices in z.

**Step 3:** The 3D structure boundary is the zero-level isosurface $\phi(x, y, z) = 0$. Points with $\phi < 0$ are inside.

**Matches:** Eclipse v15.5, RayStation v9A [^18].

**Note on inter-slice default:** Vertex-blending approaches (linear vertex loft) are not suitable as a default due to the vertex-correspondence problem. SDF-based shape interpolation is the reference-mode default and right-prism is the fast-mode default. Linear vertex loft is deferred to future work.

##### SDF Computation Methods

**Method A: Brute-force nearest-edge distance.** $O(M \cdot n)$, exact, numba-friendly. Recommended for v1.

**Method B: Rasterise-then-EDT.** $O(M)$ via scipy `distance_transform_edt` (Maurer et al. [^26]). Fast but introduces grid-alignment error up to $h\sqrt{2}/2$.

**Method C: AABB-tree accelerated.** $O(M \cdot \log n)$. Deferred to future work.

**Recommendation:** Method A for v1 with numba acceleration. Method B as a fast alternative. *[Design proposal]*

### 7.3 End-Capping

**Problem:** The terminal contour slices define the structure's in-plane extent but not how far it extends beyond them in $z$.

#### 7.3.1 No End-Cap (`none`)

The structure terminates exactly at terminal slice z-coordinates.

#### 7.3.2 Half-Slice Extension (`half_slice`)

The structure extends by $\Delta z / 2$ beyond each terminal contour. Matches: Mobius3D, MIM, RayStation [^18].

#### 7.3.3 Half-Slice Capped (`half_slice_capped`)

Same as half-slice but capped at a configurable maximum. Matches: ProKnow DS v1.22 at 1.5 mm [^18].

#### 7.3.4 Rounded End-Cap (`rounded`)

SDF extrapolated beyond terminal slices produces a dome-shaped cap. Matches: Eclipse v15.5 [^18].

**Critical invariant (the "Pinnacle constraint"):** The dose tally MUST include dose samples from the end-capped region. Nelms et al. [^14] documented that Pinnacle v9.8 included end-cap volume in the structure volume but excluded end-cap voxels from dose sampling, causing Dmin errors up to 60%. Our implementation enforces geometric identity: the occupancy field used for volume computation and dose sampling is the same `OccupancyField` instance.

### 7.4 Voxelisation and Partial-Volume Occupancy

**Problem:** Map the 3D geometric model onto the dose grid to determine the fractional occupancy $\omega_{ijk} \in [0, 1]$ of each voxel.

#### 7.4.1 Binary Centre-Inclusion

$\omega_{ijk} = 1$ if centre is inside, 0 otherwise.

#### 7.4.2 Fractional Occupancy via Supersampling

Each voxel subdivided into $N^3$ sub-voxels. Error converges as $O(1/N)$.

#### 7.4.3 Adaptive Supersampling with Gradient-Aware Refinement

Step 1: Classify voxels via 8-corner testing. Step 2: Supersample boundary voxels with convergence checking. Step 3: Increase supersampling at high-gradient boundaries.

#### 7.4.4 SDF-Derived Fractional Occupancy

> See also: [SDF Explainer](./sdf_explainer.md) — a self-contained derivation of the 2D signed-distance-field computation, vectorised pseudocode, accuracy analysis, and worked examples.

For boundary voxels, $\omega \approx \frac{1}{2} - \frac{\phi(\mathbf{p})}{2h}$ clamped to $[0, 1]$. Exact for planar boundaries, $O(h/R)$ for curved boundaries with radius $R$. *[Engineering inference]*

**Volume-of-Fluid box-plane intersection (closed form, Scardovelli & Zaleski 1999 [^ScZ1999]):**

For a voxel box $\mathcal{B}$ with half-width $h$ centred at grid point $\mathbf{p}$, and a planar boundary defined by the linearised SDF $\phi(\mathbf{x}) \approx \phi(\mathbf{p}) + \nabla\phi \cdot (\mathbf{x} - \mathbf{p})$, the exact fractional volume inside the boundary is:

$$\omega = F(\phi(\mathbf{p}), \hat{n}, h)$$

where $F$ is the clipped-box/plane volume function given in closed form by Scardovelli & Zaleski (1999), parameterised by the signed distance at the voxel centre and the unit normal $\hat{n} = \nabla\phi / \|\nabla\phi\|$. This is exact for planar boundaries (no approximation beyond floating-point precision).

**Curvature correction:**

For curved boundaries (radius $R$ from the SDF zero-crossing), the first-order correction to $\omega$ is:

$$\Delta\omega = -\frac{\kappa_1 \Delta x^2 + \kappa_2 \Delta y^2}{24}$$

where $\kappa_1, \kappa_2$ are the principal curvatures of the structure boundary and $\Delta x, \Delta y$ are the in-plane voxel spacings. This correction is $O(h^2/R)$ and becomes relevant for small structures (radius $R \lesssim 5h$). *[Engineering inference from curvature-corrected SDF literature]*

### 7.5 Dose Interpolation

#### 7.5.1 Trilinear Interpolation

Standard trilinear interpolation with $O(h^2)$ error for smooth dose fields.

#### 7.5.2 Surface-Point Dose Sampling

After standard DVH computation, additionally sample dose at every original contour vertex by trilinear interpolation for extrema/near-extrema metrics. Used by PlanIQ v2.1 [^14].

#### 7.5.3 Dose-Grid-Point Preservation

Construct the sampling lattice to include every original dose-grid centre exactly. Used by PlanIQ v2.1 [^14].

### 7.6 Histogram Construction

The canonical storage is `DVHBins` (dose bin edges + differential volume). Cumulative DVH is derived, not stored independently.

#### 7.6.0 Binning Strategy Specification

DVH bin edges are fully configurable via `DVHBins.BinningConfig` (part of `AlgorithmConfig`). Three strategies are supported:

1. **`UNIFORM_GY`** (default for practical mode): Uniform-width bins from 0 to `max_dose_gy * (1 + margin_fraction)`. Default bin width: 0.5 Gy (per Drzymala et al. recommendation). Bin edges are NOT forced to align with dose grid values.

2. **`DOSE_GRID_ALIGNED`** (default for reference mode): Bin edges coincide with dose grid values present in the sampled set. Eliminates interpolation artefacts in cumulative DVH.

3. **`CUSTOM`**: User supplies explicit `dose_bin_edges_gy` array. Must be strictly monotonically increasing.

**Axis range:** By default, the lower bound is 0 Gy and the upper bound is `ceil(max_sampled_dose / bin_width) * bin_width`, ensuring the maximum sampled dose falls within the last bin.

**Bin width guidance:** Drzymala et al. [^1] recommend ≤0.5 Gy for cumulative DVH. Pepin et al. note that bin width affects the precision band width — narrower bins increase precision-band sensitivity to histogram noise. 0.5 Gy is the default; research users may want to adjust via the `BinningConfig`. *[Design proposal]*

#### 7.6.1 Differential Histogram

For bin boundaries $D_0 < D_1 < \cdots < D_B$ with spacing $\delta$:

$$h_j = \sum_{k : D_j \leq d_k < D_{j+1}} w_k$$

**Numerical stability:** Kahan (compensated) summation [^28] for accumulation. For deterministic reproducibility, accumulation order is fixed to index order when `runtime.deterministic=True`. *[Design proposal]*

#### 7.6.2 Cumulative DVH (derived)

$$V(D_j) = \sum_{m=j}^{B-1} h_m$$

computed by reverse cumulative summation from the differential histogram.

### 7.7 Metric Extraction

#### 7.7.1 Dose-at-Volume Metrics (Dx%, Dxcc)

$D_{x\%} = \inf \{ D : V(D) \leq x/100 \cdot V_{\text{total}} \}$ — inverse lookup on cumulative DVH with linear interpolation.

#### 7.7.2 Volume-at-Dose Metrics (VxGy, Vx%)

$V_{x\text{Gy}} = V(x)$ — direct lookup. $V_{x\%}$ requires a dose reference: $V_{x\%} = V(x/100 \cdot D_{\text{ref}})$.

#### 7.7.3 Stereotactic Indices

**Paddick Conformity Index [^22]:** $\text{PCI} = (\text{TV}_{\text{PIV}})^2 / (\text{TV} \times \text{PIV})$

**Paddick Gradient Index [^23]:** $\text{GI} = V_{50\%\text{Rx}} / V_{100\%\text{Rx}}$

**Homogeneity Index (ICRU 83):** $\text{HI} = (D_{2\%} - D_{98\%}) / D_{50\%}$

Note: HI does NOT require a dose reference. It depends only on volume-percentage dose queries (D2%, D98%, D50%), not on percent-of-reference-dose queries.

### 7.8 Extrema and Near-Extrema Handling

Dmin, Dmax, and near-extremum metrics (D0.03cc) are computed from the union of all dose-volume samples and all surface-point dose samples. The combined list is sorted by dose for metric extraction.

### 7.9 Invalid-ROI Handling

The `repair_if_safe` mode attempts: (1) close open contours, (2) remove zero-area slices, (3) fix reversed winding, (4) remove minor self-intersections (< 5% of contour area). All repairs are recorded as `Issue` objects with full context. — Repairs convert raw `Contour` objects into validated `PlanarRegion` objects, making the two-layer distinction (raw import vs canonical validated) explicit.

---

## 8. Validation and Benchmark Strategy

The validation strategy is a first-class deliverable, split into five tiers.

**Literature-validated methodological principle:** The literature consistently demonstrates that analytical ground truth is essential but insufficient alone [^14], [^17], [^18], [^20], [^21]. Simple convex shapes in smooth gradients are excellent for diagnosing algorithmic failure modes, but they do not reproduce the full complexity of clinical anatomy: concavities, thin shells, multiply connected structures, heterogeneous media, and modulated dose fields remain untested by analytical benchmarks. A robust validation strategy therefore requires both analytical phantoms for algorithm verification and clinical datasets for real-world stress testing. The five-tier structure below operationalises this principle.

### 8.1 Tier 1: Analytical Ground-Truth Tests

#### 8.1.1 Available Analytical Benchmark Datasets

**Nelms et al. [^14]:** Sphere (7.3 cc), cylinder (10.86 cc), cone (3.62 cc) with linear gradients at multiple contour spacings. Closed-form analytical cumulative DVHs.

**Pepin et al. [^18]:** Reuses Nelms shapes with precision-band analysis methodology and vendor-algorithm survey.

**Stanley et al. [^17]:** Spheres 3–20 mm diameter, 50 random placements per size. Best for small-volume SRS and phase-sensitivity.

**Grammatikou et al. [^20]:** Spheres 2–9 mm radius, Mendeley Data CC BY 4.0.

**Walker and Byrne [^21]:** Spherical/Gaussian with analytical PCI and GI truth at very small volumes.

**Gossman et al. [^10]:** Rectangular parallelepiped with depth-dose profile.

**Corbett et al. [^5]:** Brachytherapy benchmarks (stress test only for v1).

**Drzymala et al. [^1]:** Nested concentric cubes, notched cube, cylinder (must be recreated).

**Decision:** All are included. Each targets different failure modes.

#### 8.1.2 Novel Analytical Benchmarks (Project-Specific)

| Test case | Purpose | Ground truth |
| --- | --- | --- |
| Rotated ellipsoid (oblique axes) | Non-axis-aligned geometry | Analytical volume and DVH in linear gradient |
| Torus (axis perpendicular to slice direction) | Branching/reconverging topology, hole stress test | Analytical volume; DVH in uniform and gradient fields |
| Thin cylindrical shell (wall thickness 1–4 mm) | Rosewall-type slender-OAR test [^13] | Analytical volume and DVH in sigmoid gradient |
| Disconnected islands (two separated spheres) | Multi-component ROI | Sum of individual analytical DVHs |
| Nested concentric spheres with different dose | Boundary logic and dose-volume assignment | Analytical per-shell DVH |
| Structure at dose-grid edge | Incomplete dose coverage | Analytical with explicit zero-dose region |
| Phase-shift sweep (structure translated 0–1 voxels) | Grid-phase sensitivity [^6], [^17] | Analytical DVH should be phase-independent for large structures |
| Anisotropic dose grid (e.g. $1 \times 1 \times 3$ mm) | Non-isotropic grid handling | Analytical adjustment |
| Adversarial contours: near-zero-area slices, reversed winding, duplicate slices | Robustness | Expected failures and repairs |

### 8.2 Tier 2: Numerical Convergence Tests

- Supersampling convergence (1x through 11x, odd only)
- Dose-grid refinement (0.1 to 3.0 mm)
- Bin-width refinement (0.005 to 1.0 Gy)
- Interpolation method comparison (right_prism vs shape_based)

### 8.3 Tier 3: Cross-Tool Comparisons

#### 8.3.1 Open-Source Comparators

| Tool | Status | Notes |
| --- | --- | --- |
| dicompyler-core | Active | TODO: infer DVH algorithms from source code |
| SlicerRT (3D Slicer) | Active | Binary centre-inclusion [^15] |
| CERR | Active | MATLAB-based |

#### 8.3.2 Commercial Comparator Matrix

The following table synthesises vendor DVH construction behaviour from two key multi-system studies. Where both studies tested the same product family, entries are listed separately by version to avoid conflation; algorithmic behaviour may differ between versions. Private-communication-sourced details are noted.

**From Pepin et al. [^18] (five systems, synthetic analytical benchmarks):**

| System | Version | Interpolation | End-capping | Supersampling | Source |
| --- | --- | --- | --- | --- | --- |
| Eclipse | v15.5 | Shape-based | Rounded | 100,000 points | [^18] |
| RayStation | v9A | Shape-based | Half-slice | 3x axial | [^18] |
| Mobius3D | v3.1 | Right-prism | Half-slice | None | [^18] |
| MIM Maestro | v6.9.6 | Right-prism | Half-slice | $\sim$1 $\text{mm}^3$ subvoxels | [^18] |
| ProKnow DS | v1.22 | Right-prism | Half-slice capped 1.5 mm | >10,000 points | [^18] |

**From Nelms et al. [^14] (two systems, analytical benchmarks):**

| System | Version | End-capping | Supersampling | Source |
| --- | --- | --- | --- | --- |
| Pinnacle | v9.8 | Half-slice auto | Regular on dose grid | [^14] |
| PlanIQ | v2.1 | Half-slice | Odd-factor adaptive $\geq$40,000 voxels + surface-point sampling | [^14] |

**From Penoncello et al. [^19] (eight systems, clinical DICOM imports — selected details from their Table 1, some sourced from vendor private communication):**

| System | Version | Interpolation | End-capping | Voxel inclusion | Source |
| --- | --- | --- | --- | --- | --- |
| Eclipse | v16.1 | Shape-based | Rounded | 100,000 structure points | [^19] |
| RayStation | v9B | Shape-based | Half-slice | Sub-voxel (3x axial) | [^19] |
| Pinnacle | v16.2 | Right-prism | "Coarse" inclusion (any touched voxel) | Native grid | [^19] |
| MIM | v7.0.4 | Right-prism | Half-slice | $\sim$1 $\text{mm}^3$ subvoxels | [^19] |
| Mobius3D | v3.0 | Right-prism | Half-slice | Native grid | [^19] |
| ProKnow | v1.22.2 | Right-prism | Half-slice capped 1.5 mm | >10,000 points | [^19] |
| Elements | v3.0.0.4 | Contours in 3D (no classical end-capping) | N/A | 0.5 mm subvoxels | [^19] |
| Velocity | v4.1 | Not reported | Not reported | Not reported | [^19] |

**Notes:**

- Penoncello et al. [^19] compiled the most detailed published table of vendor DVH construction behaviour; many details were obtained through vendor private communication rather than public documentation.
- Elements' approach of allowing contours to exist in 3D space effectively avoids classical end-capping entirely [^19].
- Pinnacle v16.2 used a coarse inclusion rule counting any voxel touched by the structure, producing the largest volume ratios (mean 1.101 relative to Eclipse) [^19].
- Across all eight systems in Penoncello et al., dosimetric medians were all 1.000, confirming that central tendency for dose metrics was essentially identical while volume reporting differed materially [^19].

### 8.4 Tier 4: Clinical-Case Benchmarking

Case library targets: large-volume conventional (prostate), small-volume SRS (3–20 mm), spine SBRT, H&N IMRT, lung SBRT, slender/hollow OARs (bladder wall).

### 8.5 Tier 5: Sensitivity Analysis

Systematic single-variable sensitivity analysis for every configurable parameter: interpolation method, end-cap policy, supersampling factor, adaptive refinement, bin width, dose-grid resolution, grid phase, surface sampling.

---

## 9. Development Plan

### Development Practices (applies to all phases)

- **Test-driven development (TDD).** Write the test first. See it fail. Implement the feature. See it pass. Never merge code without a covering test.
- **Property-based testing** (via Hypothesis) for all dataclass invariants, metric grammar round-trips, and numerical monotonicity/bound properties.
- **Golden-data regression tests** gate every merge.
- **Strict typing** throughout. `mypy --strict` on all source files.
- **AI-assisted workflow.** Each task is a self-contained specification with clear inputs, outputs, and acceptance criteria.
- **Benchmark gating.** After Phase 3, every PR to core computation code must pass the full Tier 1 suite.
- **Documentation as deliverable.** Every module and public function has complete docstrings.
- **Conventional commits.** `type(scope): description` format.
- **Branch strategy.** One feature branch per task. PRs < 500 lines when possible.

---

### Phase 0: Scaffolding, Core Types, and Test Infrastructure

**Objectives:** Establish the module skeleton, all core data types, metric grammar parser, serialisation, and test harness. No computation logic.

The type system includes: `GridFrame`, `DoseReferenceSet`, `ROIRef`, `MetricSpec` (metric AST), `PlanarRegion`, `ContourROI`, `SDFField`, `DVHBins`, `Issue`, `ROIResult` with status, `DVHInputs`, and the separated config types (`AlgorithmConfig`, `RuntimeConfig`, `PipelinePolicy`, `DVHConfig`).

#### Task 0.1: Module skeleton and packaging

**Files to create:**

```plaintext
lib/pymedphys/_dvh/
    __init__.py
    _types/
        __init__.py
        _grid_frame.py       # GridFrame
        _dose_ref.py         # DoseReference, DoseReferenceSet
        _roi_ref.py          # ROIRef
        _metrics.py          # MetricSpec, MetricFamily, ThresholdUnit, OutputUnit, ROIMetricRequest, MetricRequestSet
        _config.py           # AlgorithmConfig, RuntimeConfig, PipelinePolicy, DVHConfig, all enums, SupersamplingConfig
        _contour.py          # Contour (raw), PlanarRegion, ContourROI
        _occupancy.py        # OccupancyField
        _sdf.py              # SDFField
        _dose.py             # DoseGrid
        _results.py          # MetricResult, ROIResult, DVHResultSet, DVHBins
        _issues.py           # IssueLevel, IssueCode, Issue
        _provenance.py       # ProvenanceRecord, InputMetadata, PlatformInfo
        _inputs.py           # DVHInputs
    _protocols.py            # StructureModelBuilder, OccupancyComputer, DoseInterpolator (private)
    _serialisation.py        # to_json(), from_json(), to_toml(), from_toml()
    _grammar.py              # MetricSpec.parse() implementation

tests/dvh/
    __init__.py
    conftest.py
    test_types/
        test_grid_frame.py
        test_dose_ref.py
        test_roi_ref.py
        test_metrics.py
        test_config.py
        test_contour.py
        test_results.py
        test_issues.py
    test_grammar.py
    test_serialisation.py
    test_profiles.py
```

**Key Phase 0 tests (selected):**

- `GridFrame.from_uniform()` constructs with correct affine; `spacing_mm` returns correct values
- `GridFrame` rejects non-positive shape or spacing
- `DoseReferenceSet.single()` creates a single-ref set; `.get()` resolves correctly
- `DoseReferenceSet` rejects empty refs; rejects invalid default_id
- `DoseReference` rejects empty `source` string (`from_dict` requires explicit source documentation)
- `ROIRef.matches()` compares by roi_number when both have one, else by name
- `MetricSpec.parse("HI").requires_dose_ref` is **False** (HI uses volume-percentage queries only)
- `MetricSpec.parse("V95%").requires_dose_ref` is True
- `MetricSpec` deduplication uses `canonical_key`, not `raw` string
- `PlanarRegion` stores exterior and holes with explicit types
- `ContourROI` rejects duplicate z values, unsorted slices
- `DVHBins.cumulative_volume_cc` is derived correctly from differential
- `ROIResult.status` distinguishes "ok", "skipped", "failed"
- `DVHResultSet.by_name()` raises on ambiguous name; `by_ref()` resolves by number
- `Issue` carries path tuple identifying source ROI/metric
- `DVHConfig.reference()` and `.fast()` return expected settings
- All frozen dataclasses with `slots=True`; array-bearing types have `eq=False` and read-only arrays
- Full JSON/TOML round-trip for all types

### Phase 1: Synthetic Benchmark Generation

**Objectives:** Build the analytical benchmark corpus that will be used to validate all subsequent computation. This phase produces no DVH computation code — only test fixtures and ground-truth data.

#### Task 1.1: Analytical geometry library

**Files:**

```plaintext
lib/pymedphys/_dvh/_benchmarks/
    __init__.py
    _geometry.py          # Analytical volume formulas for all shapes
    _dose_fields.py       # Analytical dose field generators
    _dvh_analytical.py    # Closed-form cumulative DVH formulas
    _dicom_generator.py   # DICOM RTSTRUCT/RTDOSE generator
```

**Implement analytical volume formulas for:**

- Sphere: $V = \frac{4}{3}\pi r^3$
- Cylinder: $V = \pi r^2 h$
- Cone: $V = \frac{1}{3}\pi r^2 h$
- Ellipsoid: $V = \frac{4}{3}\pi abc$
- Torus: $V = 2\pi^2 R r^2$
- Thin cylindrical shell: $V = \pi(r_{\text{outer}}^2 - r_{\text{inner}}^2)h$
- Rectangular parallelepiped: $V = lwh$

**Tests (unit):**

- Each formula verified against at least 3 hand-calculated values
- Sphere ($r = 10$ mm): $V = 4188.79$ $\text{mm}^3$ $= 4.189$ cc
- Cylinder ($r = 12$ mm, $h = 24$ mm): $V = 10857.34$ $\text{mm}^3$ $= 10.857$ cc (matches Nelms [^14])
- Cone ($r = 12$ mm, $h = 24$ mm): $V = 3619.11$ $\text{mm}^3$ $= 3.619$ cc (matches Nelms [^14])

#### Task 1.2: Analytical DVH formulas

**Implement closed-form cumulative DVH V(D) for each geometry under specific dose distributions:**

- **Sphere in linear gradient** $D(z) = D_0 + gz$:
  - $V(D)$ = volume of the spherical cap where dose $\geq D$
  - Closed form: $V(D) = \frac{\pi}{3}(2r^3 - 3r^2 h + h^3)$ where $h = r - (D - D_0)/g$
  - Clamping: $h$ is clamped to $[0,\, 2r]$. When $h \leq 0$ (i.e. $D \leq D_0 + g \cdot (\text{centre}_z - r)$), $V(D) = V_{\text{total}}$. When $h \geq 2r$ (i.e. $D \geq D_0 + g \cdot (\text{centre}_z + r)$), $V(D) = 0$.

- **Cylinder in linear gradient** $D(z) = D_0 + gz$ (gradient along cylinder axis):
  - $V(D) = \pi r^2 \cdot \max(0,\; (D_{\max} - D)/g)$ where $D_{\max} = D_0 + g \cdot h$

- **Cone in linear gradient** (gradient along cone axis):
  - Tapered cross-section requires integration; closed form derived from cone radius as a function of z

- **Sphere in radial Gaussian** $D(r) = A \exp(-r^2 / (2\sigma^2))$:
  - $V(D) = \frac{4\pi}{3} r(D)^3$ where $r(D) = \sigma\sqrt{2 \ln(A/D)}$, capped at sphere radius
  - This is the Stanley [^17] / Walker [^21] benchmark model

**Tests (unit):**

- For sphere in uniform dose: $V(D \leq D_{\text{uniform}})$ = full volume, $V(D > D_{\text{uniform}}) = 0$
- For cylinder in linear gradient: V at midpoint dose = half volume
- Each formula agrees with numerical integration (scipy.integrate) to < 0.01% for 5 representative parameter sets

**Tests (property-based):**

- $V(D_{\min})$ = total volume
- $V(D_{\max}) = 0$ (or near-zero for continuous distributions)
- $V$ is monotonically non-increasing in $D$
- $0 \leq V(D) \leq$ total volume for all $D$

#### Task 1.3: DICOM RTSTRUCT generator

**Implement:** Generate synthetic DICOM RTSTRUCT files from analytical geometry definitions.

**Specific capabilities:**

- Generate contour points for: sphere, cylinder, cone, ellipsoid, torus, shell, parallelepiped
- Configurable slice spacing (0.2, 0.5, 1.0, 2.0, 3.0 mm)
- Configurable in-plane point density
- Configurable centre position (for phase-shift testing)
- Output valid DICOM RTSTRUCT that passes pydicom validation
- Support for on-slice and between-slice sphere positioning (per Walker [^21])

**Tests:**

- Generated RTSTRUCT is valid DICOM (pydicom.dcmread succeeds, no warnings)
- Generated sphere contours have correct radius at each slice (within discretisation tolerance)
- Generated structures can be imported by dicompyler-core without error
- Contour point count matches expected density
- Structure volume from contour integration matches analytical volume within discretisation tolerance

#### Task 1.4: DICOM RTDOSE generator

**Implement:** Generate synthetic DICOM RTDOSE files with known dose distributions.

**Supported dose fields:**

- Uniform: $D(x,y,z) = D_0$
- Linear gradient (any axis): $D = D_0 + g \cdot \{x,y,z\}$
- Radial Gaussian: $D(r) = A \exp(-r^2 / (2\sigma^2))$
- Sigmoid: $D(z) = D_{\max} / (1 + \exp(-k(z - z_0)))$

**Configurable parameters:**

- Grid spacing (0.1 to 5 mm)
- Grid extent
- Gradient magnitude and direction
- Gaussian peak and width
- Grid origin (for phase-shift testing)

**Tests:**

- Generated RTDOSE is valid DICOM
- Dose values at known points match analytical formula to machine precision
- Grid geometry in DICOM headers matches specified parameters
- Generated dose imports correctly in pydicom

#### Task 1.5: Benchmark manifest and published dataset integration

**Implement:**

- JSON manifest format for each test case
- Integration scripts for downloading/importing published datasets:
  - Nelms et al. [^14] supplementary DICOM
  - Stanley et al. [^17] downloadable DICOM
  - Grammatikou et al. [^20] Mendeley Data (DOI 10.17632/pb55hjf5y3.1)
  - Walker and Byrne [^21] Mendeley Data

**Tests:**

- All manifests validate against a JSON schema
- All integrated published datasets load without error
- Published dataset volumes match reported values within stated tolerance

#### Task 1.6: Phase-shift sweep generator

**Implement:** Given a geometry and dose field, generate a sweep of $N$ test cases where the structure is translated by $[0,\, 1/N,\, 2/N,\, \ldots,\, (N{-}1)/N] \times \text{voxel\_size}$ in each axis, keeping the dose field fixed.

**Purpose:** Directly tests grid-phase sensitivity [^6], [^17].

**Tests:**

- Sweep generates exactly N cases
- Each case has the correct translation offset in its manifest
- Analytical DVH is identical across all phase shifts (since the analytical formula is continuous)

#### Task 1.7: Novel benchmark case generation

**Implement the project-specific novel benchmarks from Section 8.1.2.**

**Tests:**

- Each novel case has a validated analytical ground truth
- Each case generates valid DICOM
- Adversarial cases trigger appropriate validation errors in contour types

**Phase 1 exit criteria:**

- Complete benchmark corpus with $\geq$ 30 distinct test cases
- All test cases have JSON manifests with analytical ground truth
- All generated DICOM files import correctly in pydicom and dicompyler-core
- All analytical DVH formulas validated against numerical integration
- Published dataset integration scripts work end-to-end
- Full documentation of every analytical formula with derivation

---

### Phase 2a: Core Geometry Engine — Basic Methods

**Objectives:** Implement contour import, validation, right-prism interpolation, basic end-capping, and binary/fixed-supersampling occupancy. Establish the `numba` compilation and caching pattern. Validate volume accuracy against the Phase 1 benchmark corpus using these basic methods.

#### Task 2a.0: `numba` compilation strategy and infrastructure

**Files:**

```plaintext
lib/pymedphys/_dvh/_numba_utils.py
tests/dvh/test_numba_utils.py
```

**Implement:** Establish the project-wide `numba` JIT compilation pattern that all subsequent phases will follow.

**Specific deliverables:**

- Module `_numba_utils.py` with: project-wide `@njit` decorator wrapper that handles `cache=True`, `nogil=True`, `error_model="numpy"` defaults
- Ahead-of-time (AOT) compilation support: a script or entry point that pre-compiles all `@njit` functions
- Cache directory configuration: respect `PYMEDPHYS_NUMBA_CACHE_DIR` environment variable, defaulting to a package-local `__pycache__/numba` directory
- A simple "warm-up" function that can be called once at import time to trigger compilation of all critical inner loops, with timing diagnostics
- Documentation of the pattern: how to write a new numba-accelerated function, how to test it, how to benchmark it

**Tests:**

- `@njit`-decorated function compiles and runs correctly
- Cached compilation produces identical results to uncached
- Warm-up function completes without error and reports timing
- Pure-Python fallback works when numba is not installed (via a `try/except` import pattern)

**Acceptance criteria:**

- All subsequent phases use this pattern exclusively for numba acceleration
- No direct `@numba.njit` decorators outside `_numba_utils.py`

#### Task 2a.1: DICOM RTSTRUCT importer

**Files:**

```plaintext
lib/pymedphys/_dvh/_io/
    __init__.py
    _rtstruct.py          # DICOM RTSTRUCT → ContourROI
```

**Implement:** Parse DICOM RTSTRUCT into `ContourROI` objects.

**Specific requirements:**

- Extract ROI name, ROI number, contour data, referenced frame of reference UID
- Construct `ROIRef` with both name and roi_number from DICOM
- Handle multiple contours per slice (disconnected islands)
- Handle ROIs with holes (inner contour with opposite winding)
- Convert DICOM 3D contour data (flat x,y,z,x,y,z,...) into raw `Contour` objects
- Group raw contours by z-coordinate using `PipelinePolicy.z_tolerance_mm` for normalisation
- Validate that all contours in an ROI share the same referenced frame
- Log and handle gracefully: empty ROIs, single-point contours, open contours

**Tests:**

- Import the Phase 1 generated DICOM: resulting `ContourROI` has correct `num_slices`, z values, and point counts
- Import a real DICOM RTSTRUCT from the Nelms [^14] published data (if available)
- ROI names and ROI numbers match DICOM ROI sequence
- Disconnected-island ROIs produce multiple `PlanarRegion` objects per slice
- Invalid/pathological structures handled per `invalid_roi_policy`

#### Task 2a.2: Contour validation and repair

**Implement:** Validation and optional repair logic, converting raw `Contour` objects into validated `PlanarRegion` / `ContourROI` objects.

**Validation checks:**

- Contour closure (first point == last point, or auto-close)
- Winding orientation consistency (all outer contours CCW, all holes CW)
- Self-intersection detection (per §7.0.2 orientation test)
- Zero-area slice detection
- Duplicate slice detection (after z-tolerance normalisation)

**Repair actions (for `repair_if_safe` mode):**

- Auto-close open contours (connect first and last point)
- Remove zero-area slices with issue
- Fix reversed winding order
- Remove minor self-intersections (< 5% of contour area) *[Design proposal]*

**Tests:**

- Valid contour passes validation silently
- Open contour: strict mode raises, repair mode closes and logs an `Issue`
- Reversed winding: detected and repaired with `Issue`
- Self-intersecting contour: detected; minor intersection repaired, major intersection rejected
- Zero-area slice: detected and removed with `Issue`
- All repairs are logged as `Issue` objects with `IssueCode.CONTOUR_REPAIRED`

#### Task 2a.3: Right-prism interpolation

**Implement:** Right-prism extrusion between contour slices.

**Tests:**

- For a cylinder (constant cross-section), right-prism produces identical contours at all z
- For a cone (tapering cross-section), right-prism produces step-like transitions at midpoints
- Volume of right-prism-interpolated cylinder matches analytical cylinder volume within 1 slice-thickness $\times$ area
- Volume of right-prism-interpolated sphere is systematically biased (expected: overestimate due to stair-stepping); quantify against analytical

#### Task 2a.4: End-capping — none and half-slice

**Implement:** `none` and `half_slice` end-cap policies.

**Tests:**

- `none` produces strictly less volume than `half_slice` for all structures
- For a cylinder with uniform slice spacing dz, `half_slice` adds approximately $\text{terminal\_area} \times dz/2 \times 2$ (one cap at each end)
- Volume with `half_slice` is closer to analytical sphere volume than `none`

#### Task 2a.5: Scanline point-in-polygon (even-odd rule)

**Implement:** Scanline even-odd crossing rule for 2D point-in-polygon testing [^1].

**Specific edge-case handling (per Drzymala [^1]):**

- Tangency: a contour vertex that touches the scanline without crossing → not a crossing
- Reversal: two consecutive edges that approach and recede from the scanline → not a crossing
- Collinear: contour edge that lies exactly on the scanline → handled by perturbation or explicit rule

**Implementation in numba:** The inner loop must use the project `@njit` pattern (Task 2a.0). Input: 2D point, contour vertices. Output: bool.

**Tests:**

- Square contour: centre is inside, corners are inside, points outside are outside
- Triangle: standard test points
- L-shaped (concave) contour: points in the concavity are correctly outside
- Tangency test: point exactly on a horizontal contour edge
- Collinear test: scanline passes through a vertex shared by two edges
- Performance: $\geq$ 1M point-in-polygon tests per second on a single core

#### Task 2a.5b: Winding number point-in-polygon

**Implement:** Winding number algorithm for 2D point-in-polygon testing, per Sunday [^27].

**Algorithm:** As specified in §7.1.2 — edge-crossing framework tracking upward/downward crossings with left-of-edge cross-product test.

**Implementation in numba:** Same `@njit` pattern as Task 2a.5.

**Tests:**

- All tests from Task 2a.5 must also pass with winding number (both algorithms agree on simple polygons)
- Self-intersecting polygon: even-odd and winding number produce different results (verify both are correct per their respective semantics)
- Multi-wound polygon (figure-8): winding number correctly identifies enclosed regions
- Performance: $\geq$ 1M point-in-polygon tests per second on a single core (comparable to even-odd)

#### Task 2a.6: Binary centre-inclusion occupancy

**Implement:** For each voxel in the dose grid, test whether its centre is inside the structure. Support both even-odd and winding number via the `point_in_polygon` config setting. The output is an `OccupancyField` on the target `GridFrame`.

**Tests:**

- For a large sphere on a fine grid, volume matches analytical to within 5%
- For a small sphere on a coarse grid, volume can deviate by > 20% (expected; this validates the known limitation)
- All occupancy values are exactly 0 or 1
- Even-odd and winding number produce identical results for all non-self-intersecting contours

#### Task 2a.7: Fractional occupancy via fixed supersampling

**Implement:** For each boundary voxel, subdivide into $N \times N \times N$ sub-voxels and compute occupancy fraction.

**Tests:**

- At supersampling factor 1, result matches binary centre-inclusion exactly
- At increasing factors (3, 5, 7, 9), volume converges monotonically toward analytical
- For a known sphere, volume at factor 7 is within 1% of analytical
- Interior voxels (all corners inside) have occupancy exactly 1.0
- Exterior voxels (all corners outside) have occupancy exactly 0.0
- Boundary voxels have 0 < occupancy < 1

**Performance tests:**

- Numba-accelerated supersampling is $\geq 10\times$ faster than pure Python
- 100 cc structure on 2.5 mm grid at $5\times$ supersampling completes in < 5 seconds

#### Task 2a.8: Volume computation golden-data tests

**Implement:** Compute volume for all Phase 1 benchmark geometries using every combination of: [right_prism] $\times$ [none, half_slice] $\times$ [binary, fractional_3x, fractional_5x, fractional_7x].

**Store results as golden data:** JSON files with computed volumes, analytical volumes, and percentage errors.

**Tests:**

- Every golden-data file is generated and stored in the test fixtures
- No volume error exceeds the expected bound for the method/geometry combination
- Volume error decreases with increasing supersampling factor

**Phase 2a exit criteria:**

- DICOM RTSTRUCT import works for generated and published datasets
- Right-prism + half-slice + fractional-7x achieves $\leq$ 2% volume error on Nelms [^14] analytical geometries
- Both even-odd and winding number PIP algorithms functional and tested
- All golden-data tests pass
- numba acceleration verified via the project pattern from Task 2a.0
- mypy strict passes

---

### Phase 2b: Core Geometry Engine — Advanced Methods

**Objectives:** Implement shape-based (SDF) interpolation, advanced end-capping, and adaptive supersampling.

#### Task 2b.1: 2D signed distance field computation

**Implement:** Given a `PlanarRegion` (validated 2D polygon with explicit exterior and holes), compute the signed distance at every pixel of a 2D grid. Negative inside, positive outside, zero on the boundary.

**Implementation options (evaluate both, select based on accuracy/speed):**

- Option A: Brute-force nearest-edge distance ($O(M \times N)$, simple, exact, numba-friendly)
- Option B: Rasterise + exact Euclidean distance transform via Maurer et al. [^26] ($O(M)$ via scipy.ndimage.distance_transform_edt, fast but approximate for non-grid-aligned contours)

**Tests:**

- For a circular contour of radius $r$ centred at origin: SDF at $(0,0) = -r$, SDF at $(r,0) = 0$, SDF at $(2r,0) = +r$
- SDF is negative inside, positive outside, zero on boundary
- SDF gradient magnitude $\approx 1$ everywhere (property of exact distance fields)
- Performance: < 1 second for a $500 \times 500$ grid from a 100-point contour

#### Task 2b.2: Shape-based interpolation (SDF lofting)

**Implement:** For each contour slice, compute 2D SDF. Linearly interpolate SDFs between slices in z. Extract the 3D structure as the zero-level set of the interpolated SDF. The output is a 3D SDF array on the target `GridFrame`, which the `OccupancyComputer` protocol implementations then rasterise to an `OccupancyField`.

**Tests:**

- For a cylinder (constant radius), SDF interpolation produces a smooth cylinder (occupancy nearly identical to right-prism)
- For a cone (linearly tapering radius), SDF interpolation produces a smooth taper (not a stair-step)
- Cone volume with SDF interpolation is closer to analytical than right-prism
- Sphere volume with SDF interpolation is closer to analytical than right-prism
- SDF-interpolated structure occupancy transitions smoothly across slice boundaries

#### Task 2b.3: Rounded and half-slice-capped end-caps

**Implement:**

- `half_slice_capped`: same as half_slice but capped at configurable max mm (default: 1.5 mm per ProKnow [^18])
- `rounded`: extrapolate SDF beyond terminal slices to produce smooth dome-shaped cap

**Tests:**

- `half_slice_capped(max_mm=1.5)` with 3mm slice spacing produces 1.5mm cap (not 1.5mm)
- `half_slice_capped(max_mm=10)` with 3mm slice spacing produces 1.5mm cap (same as half_slice, since 1.5 < 10)
- `rounded` cap volume is between `none` and `half_slice` for most geometries
- **Critical test:** Dose sampling includes end-capped regions (verifying the Pinnacle [^14] inconsistency is not reproduced)

#### Task 2b.4: Adaptive supersampling with gradient-aware refinement

**Implement:**

1. First pass: classify each voxel as interior / exterior / boundary (by corner testing)
2. Boundary voxels: start at base factor (e.g. 5x), increase until convergence
3. Gradient-aware: compute $|\nabla D|$ at each boundary voxel; increase supersampling where $|\nabla D| \times \text{voxel\_size}$ exceeds threshold

**Tests:**

- Adaptive produces volume within convergence_tol of fine fixed-factor result
- Adaptive uses fewer total sub-voxel evaluations than uniform supersampling at the same accuracy
- Gradient-aware refinement concentrates effort at high-gradient boundaries
- Convergence diagnostics (iterations per voxel, final effective factor) are recorded in `ROIDiagnostics`

#### Task 2b.5: Comprehensive volume golden-data expansion

**Extend golden data:** Compute volume for all benchmark geometries using all methods $\times$ all end-caps $\times$ adaptive supersampling.

**Key comparisons:**

- Shape-based + rounded + adaptive vs analytical → target < 0.5% for all convex geometries
- Right-prism + half_slice + binary vs analytical → quantify the baseline degradation
- Shape-based vs right-prism difference, as a function of slice spacing (0.2 to 3 mm) and structure taper

**Phase 2b exit criteria:**

- Shape-based interpolation produces volumes within 0.5% of analytical for Nelms [^14] geometries at 0.2 mm slice spacing
- Adaptive supersampling converges to within specified tolerance for all benchmark cases
- Golden-data tests pass for all method combinations
- Performance: reference-mode volume computation for a 10 cc structure on 1 mm dose grid completes in < 30 seconds

---

### Phase 3: DVH Computation Engine

**Objectives:** Implement DICOM RTDOSE import, dose sampling, histogram construction, metric extraction, the raw-array compute pathway, and the complete reference/practical mode pipelines. Validate against the full Phase 1 analytical benchmark corpus.

#### Task 3.1: DICOM RTDOSE importer

**Files:**

```plaintext
lib/pymedphys/_dvh/_io/_rtdose.py
tests/dvh/test_io/test_rtdose.py
```

**Implement:** Parse DICOM RTDOSE into a `DoseGrid` object.

**Specific requirements:**

- Extract 3D dose array from Pixel Data (7FE0,0010) via pydicom
- Apply Dose Grid Scaling (3004,000E) to convert stored integers to physical dose in Gy
- Build a `GridFrame` from Image Position Patient (0020,0032), Pixel Spacing (0028,0030), Grid Frame Offset Vector (3004,000C), Rows (0028,0010), Columns (0028,0011)
- Detect dose units from Dose Units (3004,0002): "GY" or "CGY" — convert cGy to Gy on import
- Detect dose summation type from Dose Summation Type (3004,000A): PLAN, FRACTION, BEAM, etc.
- Validate Frame of Reference UID (0020,0052) consistency with RTSTRUCT
- Handle both float32 and float64 pixel data
- Handle missing or malformed optional tags gracefully

**Tests:**

- Import Phase 1 generated RTDOSE: dose values at grid centres match analytical formula to float64 precision
- Import published Nelms [^14] RTDOSE: loads without error, grid geometry matches published parameters
- `GridFrame` constructed from DICOM headers matches expected affine and shape
- Dose units correctly detected and converted to Gy
- Frame of Reference UID mismatch between RTSTRUCT and RTDOSE raises `IncompatibleGrids` error
- Missing Dose Grid Scaling tag handled (default = 1.0 with `Issue`)

#### Task 3.2: Trilinear dose interpolation

**Evaluate `pymedphys._interp` for reuse.** If it meets requirements (correct trilinear, numba-accelerated, handles boundary conditions), use it. Otherwise implement standalone.

**Tests:**

- At grid centres, interpolated value equals the grid value exactly
- For a linear dose field, interpolation is exact everywhere
- For a quadratic dose field, interpolation error is bounded by $O(h^2)$ where $h$ is grid spacing
- Performance: $\geq$ 10M interpolations per second

#### Task 3.3: Surface-point dose sampling

**Implement:** After standard occupancy-based DVH computation, additionally sample dose at every original contour vertex (3D) for extrema/near-extrema computation.

**Tests:**

- Surface samples capture dose values that voxel-centre sampling misses
- For a sphere in a linear SI gradient: surface-sampled Dmin is at the inferior pole (correct), not at the closest voxel centre
- Dmin/Dmax from surface sampling are at least as extreme as from voxel-centre sampling

#### Task 3.4: Histogram construction

**Implement:** Build `DVHBins` (dose bin edges + differential volume) from (dose, volume_weight) pairs. Cumulative DVH and percentage views are derived from `DVHBins` properties.

**Tests (property-based):**

- `DVHBins.cumulative_volume_cc` is monotonically non-increasing
- Cumulative DVH starts at total volume (at dose = 0)
- Cumulative DVH ends at 0 (at dose > max_dose)
- Sum of all `differential_volume_cc` $\times$ `bin_width_gy` = `total_volume_cc` (to machine precision)
- Mean dose from histogram = weighted mean of bin centres (to bin-width tolerance)

#### Task 3.5: Metric extraction

**Implement:** All v1 metrics: Dx%, Dxcc, VxGy, Vx%, mean, median, min, max, HI, CI, PCI [^22], GI [^23]. Each metric is extracted from a `DVHBins` object and returns a `MetricResult` carrying its own `MetricSpec`.

**Tests (unit, one per metric type):**

- D50% of a uniform-dose structure = the uniform dose value
- Mean of a uniform-dose structure = the uniform dose value
- V(dose = uniform_dose) of a uniform structure = total volume
- HI of a perfectly uniform structure = 0
- PCI of a perfectly conformal plan = 1.0
- GI of a known Gaussian sphere matches Walker [^21] analytical value

**Tests (property-based):**

- $D_{\min} \leq D_{99\%} \leq D_{95\%} \leq D_{50\%} \leq D_{5\%} \leq D_{1\%} \leq D_{\max}$ (monotonicity)
- $D_{\min} \leq \text{mean} \leq D_{\max}$
- $0 \leq V(\text{any dose}) \leq$ total volume
- D0% = Dmax (by definition)
- D100% = Dmin (by definition)

#### Task 3.6: Issue system integration

**Implement:** Trigger `Issue` objects based on computed diagnostics.

**Tests:**

- Small structure (< 1 cc) triggers `STRUCTURE_VOLUME_SMALL`
- Coarse dose grid (> 2.5 mm) with SRS metrics triggers `DOSE_GRID_COARSE`
- Few contour slices (< 5) triggers `SPARSE_CONTOUR_STACK`
- Adaptive non-convergence triggers `CONVERGENCE_NOT_REACHED`
- Issues are structured `Issue` objects with `IssueLevel` and `IssueCode`, not strings
- Issues are placed at the correct scope level (metric, ROI, or global) with appropriate `path` tuples

#### Task 3.7: Raw-array `compute_dvh()` orchestrator

**Files:**

```plaintext
lib/pymedphys/_dvh/_compute.py
tests/dvh/test_compute.py
```

**Implement:** The `compute_dvh()` function for raw NumPy array inputs via `DVHInputs.from_arrays()`. This is the core computation pathway used by all Phase 1/2/3 benchmarks.

**Specific requirements:**

- Accept `DVHInputs` built from 3D boolean or float [0,1] structure masks, 3D float dose array, and `GridFrame`
- Construct internal `OccupancyField` and `DoseGrid` from raw arrays
- Run the full pipeline: occupancy → dose sampling → histogram → metrics
- Return `DVHResultSet` with full provenance, with each `ROIResult` carrying its `ROIRef` and explicit status

**Tests:**

- Sphere mask + uniform dose → correct volume, mean, and DVH
- Sphere mask + linear gradient → DVH matches analytical formula from Phase 1
- Multiple ROIs (separate masks) → correct independent `ROIResult` per ROI
- Invalid inputs (shape mismatch, negative dose) produce clear errors

#### Task 3.8: Full analytical benchmark validation

**Run the complete Tier 1 benchmark suite:**

- All Nelms [^14] geometries at all slice spacings and gradient directions
- All Pepin [^18] tests (precision-band analysis)
- All Stanley [^17] small-sphere tests
- All Walker [^21] PCI and GI analytical values
- All novel project-specific benchmarks

**Generate comparison report:**

- Per-test: computed vs analytical for volume, Dmean, Dmin, Dmax, D95%, D0.03cc
- Per-test: full-curve comparison at $\geq$ 301 points (CurveCompare methodology [^14])
- Aggregate: summary statistics by geometry type, method, and slice spacing

**Exit criteria:** Reference mode achieves < 1% whole-curve volume error on all Nelms [^14] geometries at 0.2 mm slice spacing. < 2% at 1 mm slice spacing. All property-based metric tests pass.

#### Task 3.9: Convergence study (Tier 2 benchmarks)

**Run and document:**

- Supersampling convergence curves (1x to 11x)
- Bin-width convergence (0.005 to 1.0 Gy)
- Dose-grid refinement convergence (0.1 to 3.0 mm)
- Interpolation method comparison (right_prism vs shape_based)

**Phase 3 exit criteria:**

- All Tier 1 and Tier 2 benchmarks pass
- Full-curve analytical agreement characterised and documented
- Reference mode and practical mode both functional
- Raw-array input pathway functional
- Performance benchmarks documented

---

### Phase 4a: DICOM Integration and Pipeline

**Objectives:** Complete the DICOM-to-result pipeline, coordinate handling, and end-to-end integration.

#### Task 4a.1: DICOM coordinate system handling

**Files:**

```plaintext
lib/pymedphys/_dvh/_io/_coordinates.py
tests/dvh/test_io/test_coordinates.py
```

**Implement:**

- Parse Patient Position (0018,5100): HFS, HFP, FFS, FFP, HFDR, HFDL, FFDR, FFDL
- Parse Image Orientation Patient (0020,0037) to validate axis alignment
- Build the `GridFrame` affine transform from DICOM spatial tags
- Validate that RTSTRUCT contour coordinates are in the same Frame of Reference as RTDOSE
- Handle the common case: HFS with standard axial acquisition

**Tests:**

- HFS: DICOM x increases to patient left, y increases to patient posterior, z increases to patient superior — all preserved correctly in `GridFrame`
- FFS: z-axis direction is reversed relative to HFS — transform handles this
- Contour points from RTSTRUCT and dose grid from RTDOSE are correctly aligned after coordinate handling
- Image Orientation Patient with non-standard oblique orientation raises `NotImplementedError` with clear message (v1 supports axial only)
- Mismatched Frame of Reference UIDs raise `IncompatibleGrids`

#### Task 4a.2: End-to-end DICOM pipeline

**Files:**

```plaintext
lib/pymedphys/_dvh/_pipeline.py
tests/dvh/test_pipeline.py
```

**Implement:** Wire together RTSTRUCT importer, RTDOSE importer, coordinate validation, geometry engine, DVH computation, and metric extraction into the `DVHInputs.from_dicom()` pathway, feeding into `compute_dvh(inputs, request, config)`.

**Tests:**

- End-to-end: Phase 1 generated DICOM → `DVHInputs.from_dicom()` → `compute_dvh()` → `DVHResultSet` with correct metrics
- End-to-end: published Nelms [^14] DICOM → `compute_dvh()` → metrics within documented tolerance of published PlanIQ values
- Multiple ROIs in a single RTSTRUCT processed correctly (one `ROIResult` per ROI)
- `ROIRef` objects in `DVHResultSet` contain both name and roi_number from DICOM
- Invalid ROI handling: `strict` mode halts, `skip_invalid` skips and continues, `repair_if_safe` attempts repair
- Missing ROI (requested but not in RTSTRUCT) raises `ROINotFound`
- Partial dose coverage (ROI extends beyond dose grid) triggers `DOSE_COVERAGE_INCOMPLETE` issue
- Skipped and failed ROIs have explicit `ROIResult.status` ("skipped" / "failed") distinguishable from "not requested"

#### Task 4a.3: Invalid-ROI policy framework

**Implement:** Per-ROI error isolation using the `PipelinePolicy.invalid_roi_policy` setting.

**Behaviour per policy:**

- `strict`: Any invalid contour → raise `InvalidContour` immediately, halt all computation
- `repair_if_safe`: Attempt repair → if successful, proceed with `Issue`; if repair fails, mark ROI as `status="failed"`, continue with remaining ROIs
- `skip_invalid`: Skip the invalid ROI (mark as `status="skipped"`), record an `Issue` with code and details, continue with remaining ROIs

**Critical invariant:** One bad ROI never silently corrupts results for other ROIs. Each ROI is processed independently with its own error handling.

**Tests:**

- `strict` mode: one invalid ROI among three valid ROIs → computation halts, no results returned
- `repair_if_safe` mode: one repairable ROI (open contour) → repaired, results for all three ROIs returned, `Issue` attached to repaired ROI
- `repair_if_safe` mode: one unrepairable ROI (catastrophically self-intersecting) → two `ROIResult` with `status="ok"`, third with `status="failed"`
- `skip_invalid` mode: one invalid ROI → two `ROIResult` with `status="ok"`, one with `status="skipped"`
- Valid ROIs produce identical results regardless of what happens to invalid ROIs in the same computation

**Phase 4a exit criteria:**

- DICOM end-to-end pipeline functional
- Coordinate system handling correct for HFS and FFS
- Invalid-ROI policy correctly isolates errors
- `ROIRef` flows correctly from DICOM through to `DVHResultSet`

---

### Phase 4b: DVH Export, CLI, and Provenance

**Objectives:** DICOM DVH export, CLI, provenance, and anonymisation.

#### Task 4b.1: DICOM RTDOSE DVH export

**Implement:** Write computed DVH curves into a valid DICOM RTDOSE object conforming to the DVH Module (C.8.8.1) of the DICOM standard. DVH data is derived from the canonical `DVHBins` representation.

**Tests:**

- Exported DICOM is valid: `pydicom.dcmread()` succeeds, no warnings
- Round-trip: compute DVH → export → re-import → compare dose/volume arrays to float64 precision
- DVH Type correctly written as CUMULATIVE or DIFFERENTIAL
- Referenced Structure Set Sequence correctly links to the source RTSTRUCT SOP Instance UID
- DVH for each ROI correctly references the ROI Number from the original RTSTRUCT (via `ROIRef`)
- Dmin, Dmax, Dmean optional tags are populated when available

#### Task 4b.2: CLI implementation

**Implement three CLI commands:**

**`pymedphys dvh compute`:**

```bash
pymedphys dvh compute \
    --rtstruct RS.dcm \
    --rtdose RD.dcm \
    --metrics-toml metrics.toml \
    --profile reference \
    --output results.json \
    --csv-summary summary.csv
```

**`pymedphys dvh export-dicom`:**

```bash
pymedphys dvh export-dicom --results results.json --rtstruct RS.dcm --output dvh_dose.dcm
```

**`pymedphys dvh benchmark`:**

```bash
pymedphys dvh benchmark --test-suite all --output benchmark_report.json
```

**Tests (subprocess-based):**

- `pymedphys dvh compute --help` exits 0 and prints usage
- `pymedphys dvh compute` with Phase 1 generated DICOM produces correct JSON output
- JSON output matches expected schema
- CSV summary has correct columns and values
- `pymedphys dvh export-dicom` produces valid DICOM
- `pymedphys dvh benchmark --test-suite nelms` runs and produces a report
- Missing required arguments produce clear error messages

#### Task 4b.3: Provenance implementation and anonymisation

**Implement:**

- `ProvenanceRecord` construction: automatically capture pymedphys version, timestamp, platform info, config, input metadata
- Input metadata: SHA-256 hashes of input DICOM files, `GridFrame` of the dose grid
- `verify_provenance(result: DVHResultSet, rtstruct_path, rtdose_path) -> bool`: re-run computation with stored config, compare outputs bit-for-bit
- `anonymise(result: DVHResultSet) -> DVHResultSet`: produce a new `DVHResultSet` with patient-identifying data removed

**Tests:**

- `ProvenanceRecord` contains correct pymedphys version
- `ProvenanceRecord` timestamp is a valid ISO 8601 string
- `verify_provenance` returns True for an unmodified result
- `verify_provenance` returns False after manually altering a metric value
- Anonymised result contains no DICOM UIDs
- Anonymised result retains file hashes, grid geometry, config, and platform info

**Phase 4b exit criteria:**

- CLI produces correct results for all three commands
- DICOM DVH export round-trips correctly
- Provenance-based recomputation produces bit-identical results
- Anonymisation completely removes all patient-identifying data

---

### Phase 5: Cross-Tool Comparison, Clinical Validation, and Performance

#### Task 5.1: dicompyler-core algorithm documentation

- Read dicompyler-core source code
- Document: interpolation method, end-capping, voxelisation, dose interpolation, supersampling, binning, extrema handling
- Write comparison report

#### Task 5.2: Automated cross-tool comparison framework

- Scripts to compute DVH with pymedphys._dvh and dicompyler-core on same inputs
- Full-curve comparison with statistical summary
- Per-metric comparison tables

#### Task 5.3: Clinical case library

- Curate representative cases per Section 8.4
- Compute reference-mode and practical-mode DVHs
- Compare against available cross-tool results

#### Task 5.4: Full sensitivity analysis (Tier 5)

- Single-variable sweeps per Section 8.5
- Generate publication-quality figures
- Calibrate issue thresholds from sensitivity data

#### Task 5.5: Performance benchmarking

- Timing benchmarks: small SRS target (< 1 cc), medium prostate PTV (~50 cc), large lung (~1000 cc), full clinical plan (20+ ROIs)
- Memory profiling for each case
- Thread scaling (1, 2, 4, 8 threads)
- numba cold-start vs warm timing
- Document all results in a performance report

### Phase 6: Documentation and Release Preparation

**Objectives:** Prepare comprehensive documentation and the package for public release.

#### Task 6.1: API documentation

**Deliverables:**

- Complete API reference auto-generated from docstrings (Sphinx autodoc)
- Types reference: every dataclass, enum, and protocol with examples
- Metric grammar reference: every metric form with parsing examples and edge cases
- Configuration guide: every parameter, its effect, its default, its tentative status, and the evidence informing it
- Profile rationale: why `reference()` and `fast()` have the settings they do, with citations

**Acceptance criteria:**

- `sphinx-build` completes without errors or warnings
- Every public function, class, and method has a docstring
- Every docstring includes Args, Returns, Raises, and at least one Example
- Documentation renders correctly in HTML

#### Task 6.2: CLI documentation

**Deliverables:**

- Complete CLI reference for all three commands
- Worked examples with sample commands and expected output
- TOML configuration file examples (including nested sub-config format)
- Error message reference

#### Task 6.3: Benchmark report

**Deliverables:**

- Full Tier 1 results: per-test computed vs analytical for volume, Dmean, Dmin, Dmax, D95%, D0.03cc
- Full-curve comparison plots (computed vs analytical DVH overlays)
- Precision-band analysis per Pepin [^18] methodology
- Tier 2 convergence curves (supersampling, bin-width, dose-grid refinement)
- Tier 3 cross-tool comparison tables (vs dicompyler-core)
- Tier 5 sensitivity analysis results with figures
- Honest reporting of all failures, limitations, and open questions
- Not just pass/fail: full numerical results with context

#### Task 6.4: Algorithm reference document

**Deliverables:**

- Detailed description of every algorithmic choice, matching Section 7 of this RFC
- Mathematical formulas with derivations
- Diagrams illustrating each method (right-prism vs SDF, end-capping policies, supersampling geometry)
- Complexity analysis for each algorithm
- Literature citations for each approach

#### Task 6.5: Migration guide from dicompyler-core

**Deliverables:**

- Side-by-side API comparison: dicompyler-core → pymedphys._dvh
- Algorithmic differences explained (what dicompyler-core does vs what pymedphys._dvh does)
- Expected numerical differences and why they occur
- Code examples showing equivalent operations in both libraries
- FAQ: "Why are my results different from dicompyler-core?"

#### Task 6.6: Contributing guide

**Deliverables:**

- How to add a new benchmark test case to the corpus
- How to add a new interpolation method (implement the Protocol, register, test)
- How to add a new metric type to the grammar
- How to run the benchmark suite locally
- How to interpret benchmark results
- Code style and testing requirements

#### Task 6.7: Gallery and demo outputs

**Deliverables:**

- Publication-quality DVH curve plots for representative cases
- Side-by-side comparison visualisations (reference vs practical mode, pymedphys vs dicompyler-core)
- Sensitivity analysis heatmaps (parameter vs metric impact)
- Interactive Jupyter notebook demonstrating the full workflow: load DICOM → configure → compute → extract metrics → plot → export

#### Task 6.8: Release preparation

**Deliverables:**

- CHANGELOG entry with complete feature list
- Release notes with known limitations
- Version bump in `pyproject.toml`
- Package installs cleanly from source and from wheel
- `pymedphys dvh benchmark --test-suite all` runs to completion
- All tests pass on Linux, macOS, and Windows (CI matrix)
- README.md updated with DVH module description and quickstart link

**Phase 6 exit criteria:**

- Documentation complete and builds without errors
- All tests pass on all CI platforms
- Package installs cleanly via `pip install pymedphys[dvh]`
- Full benchmark suite runs via CLI
- Demo notebook executes without error
- CHANGELOG and release notes written

---

## 10. Risk Register and Open Technical Questions

### 10.1 Technical Risks

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Shape-based interpolation artefacts for complex topology | Medium | High | Extensive testing with adversarial geometries; right-prism fallback |
| Analytical formula errors for novel geometries | Medium | High | Independent numerical verification at very high resolution |
| Performance inadequate for clinical workflows | High | Medium | `numba` acceleration; batched processing; reference mode is explicitly slow |
| DICOM RTSTRUCT encoding inconsistencies across vendors | High | Medium | Robust parser; multi-vendor test set |
| Floating-point non-reproducibility across platforms | Low | High | Fixed accumulation order; Kahan summation [^28]; CI on multiple platforms |
| `numba` compilation overhead for small jobs | Medium | Low | Ahead-of-time compilation option; caching |
| `numba` thread-safety for histogram accumulation | Medium | High | `numba.prange` with `nogil=True` and shared mutable accumulation buffers (e.g. histogram bins) requires careful design to avoid race conditions. Mitigation: use per-thread accumulation buffers with a final reduction step; verify determinism by comparing single-threaded and multi-threaded outputs bit-for-bit; gate all parallel accumulation paths with explicit `deterministic` flag checks |
| Type system too rigid for unforeseen clinical edge cases | Medium | Medium | Private protocol layer allows internal flexibility without breaking public API |

### 10.2 Open Technical Questions

1. **Optimal adaptive supersampling termination.** Volume-dependent, gradient-dependent, or metric-dependent? Needs empirical characterisation. *[Open question]*
2. **Shape-based interpolation algorithm selection.** Multiple SDF methods exist. Which gives best accuracy for clinical contour stacks? *[Open question]*
3. **Sufficient supersampling factor.** Is adaptive 7x–9x sufficient for all clinically relevant geometries? *[Open question]*
4. **Non-planar contour slices.** Some DICOM encodings allow non-axial contours. v1 requirement or future? *[Open question]*
5. **Warning threshold calibration.** Exact thresholds for all warnings to be derived from benchmark data. *[Open question]*
6. **Cross-platform reproducibility limits.** Empirical characterisation needed. *[Open question]*

---

## 11. Research Agenda

### 11.1 Key Gaps in the Literature

1. **Irregular geometry validation.** Nearly all validation uses spheres, cylinders, and cones [^14], [^17], [^18], [^20], [^21]. Concave, branching, multi-component, and topologically complex structures are unvalidated.
2. **Quantitative algorithm-to-impact mapping.** No complete, controlled mapping from each algorithmic choice to its quantitative impact on each metric for each anatomy class.
3. **Phase-sensitivity beyond spheres.** Stanley [^17] characterised phase-sensitivity for spheres; extension to irregular anatomies is needed.
4. **Uncertainty-predictive models.** Can DVH uncertainty be predicted from geometry, dose field, and parameters without computing at multiple settings? *[Open question]*
5. **Clinical outcome impact.** No study has demonstrated actual outcome differences attributable to DVH computation method.
6. **Inter-fraction and intra-fraction motion effects on DVH computation.** Zhang [^12] addresses the motion-weighted concept; no study validates DVH accuracy for moving targets.

### 11.2 Key Experiments This Tool Enables

1. **Controlled single-variable sensitivity analysis** of every DVH parameter across comprehensive geometries and dose fields.
2. **Open benchmark corpus** for evaluating any DVH system against known truth.
3. **Cross-mode validation** using the reference mode.
4. **Uncertainty quantification research** toward uncertainty-predictive configuration profiles.
5. **Evidence base for DVH computation standardisation proposals.**

---

## 12. Appendices

### Appendix A: Glossary of Metric Semantics

| Metric | Definition | Unit | Source |
| --- | --- | --- | --- |
| Dx% | Minimum dose received by the hottest x% of the structure volume | Gy | Standard |
| Dxcc | Minimum dose received by the hottest x cc of the structure | Gy | Standard |
| VxGy | Absolute volume receiving at least x Gy | cc | Standard |
| Vx% | Absolute volume receiving at least x% of the dose reference | cc | Standard |
| Dmean | Arithmetic mean dose across the structure volume, weighted by voxel occupancy | Gy | Standard |
| Dmedian | Dose at which the cumulative DVH crosses 50% of the structure volume; equivalent to D50% | Gy | Standard |
| HI | $(D_{2\%} - D_{98\%}) / D_{50\%}$ | dimensionless | ICRU 83 |
| CI | $V_{\text{Rx}} / \text{TV}$ (RTOG conformity index) | dimensionless | RTOG |
| PCI | $(\text{TV}_{\text{PIV}})^2 / (\text{TV} \times \text{PIV})$ | dimensionless | Paddick [^22] |
| GI | $V_{50\%\text{Rx}} / V_{100\%\text{Rx}}$ (Paddick gradient index) | dimensionless | Paddick & Lippitz [^23] |

**Terminological note:** Walker and Byrne [^21] use "Modified Gradient Index (MGI)" for the same quantity defined as GI above. This RFC uses "GI" throughout for consistency with Paddick's original terminology [^23].

### Appendix B: Implementation Design Decisions

This appendix records design decisions made during implementation that diverge from or extend the original RFC specification. Each decision includes its rationale and the phase in which it was made.

#### B.1 ROIRef enriched with `colour_rgb` (Phase 0)

**RFC §6.4 originally specified:** `ROIRef(name, roi_number)` — a minimal identity token.

**Decision:** Add `colour_rgb: Optional[tuple[int, int, int]] = None` to `ROIRef`.

**Rationale:** Colour is DICOM ROI identity metadata (tag 3006,002A), not just display data. Without it on `ROIRef`, downstream code that wants to plot DVH curves in the ROI's DICOM-specified colour would need to look up the original structure data — breaking the self-describing property of result objects. Since `ROIRef` travels through `OccupancyField`, `SDFField`, `MetricResult`, and `ROIResult`, adding colour here makes it available everywhere it's needed for display.

**What changed:** RFC §6.4 code block updated to include `colour_rgb` with validation (values in 0–255).

#### B.2 ContourROI carries geometry-interpretation fields (Phase 0)

**RFC §6.7 originally specified:** `ContourROI(roi, slices)` — geometry only.

**Decision:** Add `combination_mode: str = "auto"` and `coordinate_frame: str = "DICOM_PATIENT"` to `ContourROI`.

**Rationale:** These fields govern how contours are combined during voxelisation (e.g., XOR vs union for overlapping contours on the same slice) and which coordinate frame applies. They are geometry-interpretation concerns, not identity concerns, so they belong on `ContourROI` rather than `ROIRef`. The prior flat `Structure` type carried these fields; splitting them between `ROIRef` (identity + display) and `ContourROI` (geometry + interpretation) preserves the information while maintaining clean separation.

**What changed:** RFC §6.7 code block updated to include both fields on `ContourROI`.

#### B.3 `cached_property` incompatibility with `slots=True` — precompute in `__post_init__` (Phase 0)

**Rule:** `functools.cached_property` does not work with `slots=True` dataclasses because `slots=True` eliminates `__dict__`. For `slots=True` dataclasses, precompute derived values in `__post_init__` and store them as private fields (using `field(init=False, repr=False)`), then expose via regular `@property`. Only use `cached_property` on classes that intentionally carry a `__dict__` (i.e., non-slots classes).

**Applied to DVHBins:** `cumulative_volume_cc` and `cumulative_volume_pct` are computed eagerly in `__post_init__` and stored as `_cumulative_volume_cc` / `_cumulative_volume_pct`, exposed via regular `@property`. Example:

```python
@dataclass(frozen=True, slots=True)
class DVHBins:
    dose_bin_edges_gy: np.ndarray

    # Precompute derived values in __post_init__
    _cumulative_volume_cc: np.ndarray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        # ... validation ...
        cumulative = np.cumsum(...)
        object.__setattr__(self, '_cumulative_volume_cc', cumulative)

    @property
    def cumulative_volume_cc(self) -> np.ndarray:
        return self._cumulative_volume_cc
```

**Rationale:** `functools.cached_property` requires `__dict__` on the instance, which is unavailable when `slots=True` is set. Since the RFC specifies `slots=True` for all dataclasses, these two requirements are incompatible. Computing cumulative values eagerly in `__post_init__` and storing them as private fields preserves the frozen/slots contract while still providing the derived values. The fields are excluded from `__init__` (via `field(init=False)`) and `__repr__`.

#### B.4 `_types/` subdirectory structure (Phase 0)

**Decision:** Place all domain types in `_dvh/_types/` with one file per type group (13 files), rather than a single flat `types.py`.

**Rationale:** The RFC §9 Task 0.1 explicitly specifies this structure. A single `types.py` file (as in the prior attempt) would grow to 2000+ lines and make it difficult to navigate or review changes to individual types. The subdirectory structure keeps each file focused (<150 lines typically), makes imports explicit, and allows test files to mirror the production structure.

#### B.5 Serialisation format split: TOML input, JSON output (Phase 0)

**Decision:** Use TOML for human-edited inputs (metric requests, configuration). Use JSON for machine-generated outputs (computation results).

**Rationale:**

*TOML for inputs:*

- Physicists write metric request files by hand. TOML supports comments (documenting why specific metrics were chosen), has clean syntax without excessive punctuation, and is the standard format for Python config files.
- DVH configuration (algorithm settings, runtime config) is similarly human-edited and benefits from comments and readability.
- `tomlkit` is already a pymedphys dependency and supports read/write with comment preservation.

*JSON for results:*

- Computation results (`DVHResultSet`) are machine-generated and machine-consumed. No one edits them by hand.
- JSON handles arrays natively (DVH bin edges, differential volumes), supports deeply nested structures (results → metrics → spec), and is universally readable by every language and tool.
- TOML's array-of-tables syntax (`[[results]]`) becomes awkward with nested sub-objects and long 1D arrays (hundreds of DVH bin values).

*Not YAML:*

- YAML has no role in DVH. PyYAML is in pyproject.toml for other pymedphys modules but is whitespace-sensitive, has security concerns with arbitrary object loading, and offers no advantage over TOML (for config) or JSON (for data interchange).

*Not HDF5/npz (Phase 0):*

- Large 3D arrays (DoseGrid, OccupancyField, SDFField) are internal computation intermediates. Text formats are inappropriate for millions of voxels. Binary serialisation (HDF5, numpy `.npz`, or DICOM) is deferred to Phase 1+.

#### B.6 `to_dict()`/`from_dict()` on each type (Phase 0)

**Decision:** Each serialisable type gets `to_dict() -> dict` and `from_dict(cls, d: dict) -> Self` methods. The top-level `_serialisation.py` provides thin wrappers (`to_json`, `from_json`, `to_toml`, `from_toml`) that dispatch to these.

**Rationale:** Keeping serialisation logic on the type itself (rather than in a central serialiser) means:

- Each type's round-trip can be tested independently
- Adding a new type doesn't require modifying a central dispatch table
- The serialisation contract is visible in the same file as the type definition
- `MetricRequestSet.from_dict()` already follows this pattern (implemented in Task 0.1)

**Conventions:**

- Enums serialise as their `.value` string (e.g., `"dvh_dose"` not `"MetricFamily.DVH_DOSE"`)
- Numpy arrays serialise via `.tolist()` and reconstruct with `np.array(..., dtype=np.float64)`
- `Optional` fields serialise as `null` (JSON) or are omitted (TOML)
- DVHBins cumulative fields are NOT serialised — they're derived from differential volume and recomputed in `__post_init__`

---

## 13. Future Research Directions: Computer Graphics Algorithms for DVH Computation

This section summarises a systematic survey of algorithms from computer graphics, gaming, and computational geometry that could transform DVH computation in future versions. These techniques are not part of the v1 implementation but represent the most promising avenues for improving accuracy, performance, and capability in subsequent releases. The architecture in Section 6 is designed to accommodate these extensions without breaking the public API.

### 13.1 SDF-First Architecture

The most impactful medium-term architectural evolution would be replacing the current contour-centric pipeline with a **signed distance field (SDF)-first architecture**. In game engines (Unreal Engine 5, Unity), every mesh has a precomputed SDF volume that drives global illumination, collision detection, and boolean modelling. The properties that make SDFs valuable in games translate directly to DVH:

**Point-in-structure becomes $O(1)$.** Once an SDF is computed on the dose grid, $\text{SDF}(\mathbf{p}) < 0$ means inside. Compare this to $O(\log F)$ ray-casting with a BVH or $O(F)$ brute-force winding number computation.

**Boolean operations reduce to scalar min/max.** Union is $\min(\text{SDF}_A, \text{SDF}_B)$, intersection is $\max(\text{SDF}_A, \text{SDF}_B)$, difference is $\max(\text{SDF}_A, -\text{SDF}_B)$. The clinically ubiquitous "PTV minus heart" becomes a single NumPy broadcast. Note (Sellán et al., SIGGRAPH 2023): min/max produces correct zero level sets but the result is a pseudo-SDF whose interior distance values are not exact — fine for point-in-structure testing.

**Margin expansion is trivial subtraction.** To expand by margin $m$: $\text{SDF}(\mathbf{p}) - m$. No mesh offset computation, no self-intersection handling.

**Partial-volume estimation comes free.** For boundary voxels, a linear model $\text{fraction} \approx 0.5 + d / \Delta x$ provides a good planar approximation, already specified in §7.4.4.

**Key libraries:** scikit-fmm (fast marching), fastsweep (CUDA fast sweeping), pysdf and mesh2sdf (mesh-to-SDF conversion).

**Integration path:** v8's `StructureModelBuilder` protocol already returns an `SDFField`. A full SDF-first architecture would compute 2D SDFs per contour slice, interpolate in z, perform boolean operations as array arithmetic, and derive occupancy from the SDF — replacing the chain of mesh construction → ray-casting → binary inclusion with robust, composable, GPU-friendly array operations.

### 13.2 Exact Analytical Partial-Volume Computation

Current open-source DVH tools use binary centre-point testing with no partial-volume correction. Graphics offers a spectrum of approaches beyond the supersampling already specified in §7.4:

**Toblerone** (Kirk et al., IEEE TMI 2020): A surface-based partial-volume estimator achieving per-voxel errors with standard deviation < 0.03 across 1–3.8 mm resolutions. Available as `pip install toblerone`. Adaptable from NIfTI to DICOM-RT coordinates.

**r3d library** (Powell & Abel, J. Comp. Physics 2015): Exact analytical computation of polyhedron–voxel intersection volumes via Sutherland-Hodgman clipping. Machine-precision accuracy ($\sim 10^{-14}$ errors). The gold standard for a reference-quality engine. C library wrappable via pybind11 or ctypes.

**Supersampled density maps** (Eisemann & Décoret 2008): A $4\times$ oversampled binary voxelisation downsampled to the dose grid yields 64 sub-voxel samples per output voxel — mathematically identical to the supersampling in §7.4.2 but implementable on GPU in milliseconds.

**Integration path:** Toblerone and r3d would serve as independent verification backends for the reference mode, not replacements for the v1 adaptive supersampling. The tiered architecture (classify → assign 1.0/0.0 to interior/exterior → apply expensive methods to boundary voxels only) ensures tractability since boundary voxels scale as $O(\text{surface area} / \text{voxel area})$.

### 13.3 GPU-Accelerated DVH Computation

Five Python-accessible GPU libraries stand out for future DVH acceleration:

**NVIDIA Warp** (`pip install warp-lang`): Purpose-built for spatial computing. JIT-compiles Python to CUDA. Built-in mesh BVH with `wp.mesh_query_point()`. Apache 2.0.

**cubvh** (GitHub: ashawkey): CUDA BVH with PyTorch bindings. `BVH.signed_distance(points)` queries 134M points on GPU in a single call.

**Open3D RaycastingScene**: Embree-backed CPU parallelism. `compute_occupancy(query_points)` accepts grid-shaped tensors.

**trimesh + embreex**: Embree acceleration provides $50$–$100\times$ speedup over pure Python.

**Taichi Lang**: Python-embedded DSL compiling to CUDA/Vulkan/Metal. Supports AMD GPUs via Vulkan.

**Performance target:** For a $256 \times 256 \times 100$ dose grid with 20 structures ($\sim$130M queries), BVH-accelerated GPU computation should achieve sub-second total DVH computation — $100$–$1000\times$ over naive CPU. Wald et al. (HPG 2019) demonstrated that NVIDIA RT cores can be repurposed for point-in-mesh queries via infinitesimally short rays, faster than pure CUDA BVH.

**Integration path:** v8's array-oriented architecture (NumPy arrays, GridFrame, OccupancyField) is directly amenable to CuPy drop-in replacement. A GPU backend would implement the `OccupancyComputer` protocol.

### 13.4 Sparse Volumetric Storage

**OpenVDB** (Museth 2013, Apache 2.0): Hierarchical $B^+$-tree architecture storing uniform regions as compressed tiles — ideal for structure masks where interior voxels are uniformly 1.0 and exterior 0.0. The `meshToLevelSet` function converts triangle meshes to narrow-band SDFs. Python bindings via `pyopenvdb`.

**NanoVDB** (Museth, SIGGRAPH 2021): Read-only, GPU-friendly serialisation with built-in per-node statistics (min/max/avg) that could enable hierarchical DVH approximation.

**Integration path:** For very large structures or very fine grids, OpenVDB could replace dense NumPy arrays as the storage backend for `OccupancyField`, dramatically reducing memory usage.

### 13.5 Neural Implicit Structure Representations

Neural implicit representations — where a small neural network encodes a continuous function mapping 3D coordinates to occupancy or signed distance — offer resolution independence, compact storage, differentiability, and natural interpolation between slices.

**DeepSDF** (Park et al. 2019): Continuous SDF via auto-decoder. **IOSNet** (Khan & Fang, MICCAI 2022): Implicit neural representations for organ segmentation. **ImplMORe** (Zarin et al., ShapeMI 2025): End-to-end multi-organ implicit surface reconstruction. **Shape-Aware Organ Segmentation** (Xue et al., AAAI 2020): Predicts signed distance maps directly from images.

For DVH, a neural SDF trained on a structure's contour stack would provide: (a) continuous boundary queries at arbitrary resolution; (b) analytical differentiability enabling gradient-based DVH optimisation; (c) compact storage. Hash-grid neural representations (Instant NGP / tiny-cuda-nn) could encode organ SDFs in milliseconds.

**3D Gaussian Splatting** has been applied to CT reconstruction (R2-Gaussian, NeurIPS 2024) but not yet to RT structure representation — a clear research gap.

**Integration path:** A neural SDF would implement the `StructureModelBuilder` protocol, producing continuous structure queries. This would enable fully differentiable DVH computation when combined with differentiable dose engines (PDRT, Simkó et al. 2025) and differentiable DVH loss functions — the pieces all exist but the integration gap is the opportunity.

### 13.6 Advanced Surface Reconstruction

**Screened Poisson reconstruction** (Kazhdan & Hoppe 2013): Produces guaranteed-watertight surfaces from oriented point clouds. One-line Python via Open3D.

**Manifold library** (`pip install manifold3d`): First algorithm to guarantee manifold output from manifold input for mesh booleans. Interactive rates on meshes up to 200K triangles.

**Constrained Delaunay triangulation** for end-capping: CDT via Shewchuk's `triangle` library maximises minimum angles while respecting boundary edges. Handles holes from nested contours naturally.

**Integration path:** These would be used for mesh-based operations when needed (e.g., export to surface formats, exact analytical partial-volume via r3d) but the SDF-first architecture makes mesh-level operations largely unnecessary for the core DVH pipeline.

### 13.7 Recommended Research Priorities

Ordered by estimated impact-to-effort ratio:

1. **SDF-first occupancy** — Replace supersampled point-in-polygon with SDF-derived occupancy for reference mode. Estimated 2–4 weeks. High accuracy improvement, moderate implementation effort.
2. **r3d exact partial volume** — Integrate as a reference-quality verification backend. Estimated 2–3 weeks. Provides gold-standard accuracy for validation.
3. **Toblerone integration** — Adapt for DICOM-RT coordinates. Estimated 1–2 weeks. Independent verification of partial-volume estimates.
4. **GPU occupancy via Warp or CuPy** — $10$–$100\times$ speedup for practical mode. Estimated 3–5 weeks.
5. **OpenVDB sparse storage** — Memory reduction for large-structure batch processing. Estimated 2–3 weeks.
6. **Neural implicit structures** — Research prototype. Estimated 8–12 weeks. High long-term potential but furthest from production readiness.

---

## Bibliography

[^1]: Drzymala RE, Mohan R, Brewster L, Chu J, Goitein M, Harms W, Urie M. Dose-volume histograms. *Int J Radiat Oncol Biol Phys*. 1991;21(1):71-78. doi:10.1016/0360-3016(91)90168-4.

[^2]: Kooy HM, Nedzi LA, Alexander E III, Loeffler JS, Ledoux RJ. Dose-volume histogram computations for small intracranial volumes. *Med Phys*. 1993;20(3):755-760. doi:10.1118/1.597029.

[^3]: Fraass B, Doppke K, Hunt M, Kutcher G, Starkschall G, Stern R, Van Dyke J. AAPM TG-53: Quality assurance for clinical radiotherapy treatment planning. *Med Phys*. 1998;25(10):1773-1829. doi:10.1118/1.598373.

[^4]: Panitsa E, Rosenwald JC, Kappas C. Quality control of dose volume histogram computation characteristics of 3D treatment planning systems. *Phys Med Biol*. 1998;43(10):2807-2816. doi:10.1088/0031-9155/43/10/010.

[^5]: Corbett JF, Jezioranski JJ, Crook J, Yeung I. The effect of voxel size on the accuracy of dose-volume histograms of prostate 125I seed implants. *Med Phys*. 2002;29(5):848-853. doi:10.1118/1.1477417.

[^6]: Chung H, Jin H, Palta J, Suh TS, Kim S. Dose variations with varying calculation grid size in head and neck IMRT. *Phys Med Biol*. 2006;51(19):4841-4856. doi:10.1088/0031-9155/51/19/008.

[^7]: Kirisits C, Siebert FA, Baltas D, De Brabandere M, Hellebust TP, Berger D, Venselaar J. Accuracy of volume and DVH parameters determined with different brachytherapy treatment planning systems. *Radiother Oncol*. 2007;84(3):290-297. doi:10.1016/j.radonc.2007.06.010.

[^8]: Henriquez FC, Castrillon SV. A novel method for the evaluation of uncertainty in dose-volume histogram computation. *Int J Radiat Oncol Biol Phys*. 2008;70(4):1263-1271. doi:10.1016/j.ijrobp.2007.11.038.

[^9]: Ebert MA, Haworth A, Kearvell R, Hooton B, Hug B, Spry NA, Bydder SA, Joseph DJ. Comparison of DVH data from multiple radiotherapy treatment planning systems. *Phys Med Biol*. 2010;55(11):N337-N346. doi:10.1088/0031-9155/55/11/N04.

[^10]: Gossman MS, Bank MI, Barthel JS, Sorrells JE. Dose-volume histogram quality assurance for linac-based treatment planning systems. *J Appl Clin Med Phys*. 2010;11(4):3255. doi:10.1120/jacmp.v11i4.3255.

[^11]: Grimm J, LaCouture T, Croce R, Yeo I, Zhu Y, Xue J. Dose tolerance limits and dose volume histogram evaluation for stereotactic body radiotherapy. *J Appl Clin Med Phys*. 2011;12(2):3368. doi:10.1120/jacmp.v12i2.3368.

[^12]: Zhang M, Hallman JE, Brame RS, Yin FF, Siebers JV, Barker JL, Kim RY, Brezovich IA. Motion-weighted target volume and dose-volume histogram. *Radiother Oncol*. 2011;99(Suppl 1):S305.

[^13]: Rosewall T, Kong V, Heaton R, Currie G, Milosevic M, Wheat J. The effect of dose grid resolution on dose volume histograms for slender organs at risk during pelvic IMRT. *J Med Imaging Radiat Sci*. 2014;45(3):204-209. doi:10.1016/j.jmir.2014.01.006.

[^14]: Nelms B, Stambaugh C, Hunt D, Tonner B, Zhang G, Feygelman V. Methods, software and datasets to verify DVH calculations against analytical values: twenty years late(r). *Med Phys*. 2015;42(8):4435-4443. doi:10.1118/1.4923175.

[^15]: Sunderland K, Pinter C, Engel C, Engel K, Fichtinger G. Effects of voxelization on dose volume histogram accuracy. *Proc SPIE Medical Imaging*. 2016;9786:97862E. doi:10.1117/12.2216837.

[^16]: Snyder KC, Liu M, Zhao B, Huang Y, Wen N, Chetty IJ, Siddiqui MS. Investigating the dosimetric effects of grid size on dose calculation accuracy using VMAT in spine stereotactic radiosurgery. *J Radiosurgery SBRT*. 2017;4(4):303-313. PMCID:PMC5658825.

[^17]: Stanley DN, Covington EL, Liu H, Alexandrian AN, Cardan RA, Bridges DS, Thomas EM, Fiveash JB, Popple RA. Accuracy of dose-volume metric calculation for small-volume radiosurgery targets. *Med Phys*. 2021;48(5):2694-2709. doi:10.1002/mp.14645.

[^18]: Pepin MD, Penoncello GP, Brom KM, Gustafson JM, Long KM, Rong Y, Fong de los Santos LE, Shiraishi S. Assessment of dose-volume histogram precision for five clinical systems. *Med Phys*. 2022;49(12):7532-7542. doi:10.1002/mp.15916.

[^19]: Penoncello GP, Voss MM, Gao Y, Sensoy L, Cao M, Pepin MD, Herchko SM, Benedict SH, DeWees TA, Rong Y. Multicenter multivendor evaluation of DVH creation consistencies for 8 commercial radiation therapy dosimetric systems. *Pract Radiat Oncol*. 2024;14(1):e47-e57. doi:10.1016/j.prro.2023.09.009.

[^20]: Grammatikou I, Drakopoulou A, Alexiou A, Pissakas G, Karaiskos P, Peppa V. Validation of dose-volume calculation accuracy for intracranial SRS with VMAT using analytical and clinical treatment plans. *J Appl Clin Med Phys*. 2025;26(3):e70235. doi:10.1002/acm2.70235. Mendeley Data DOI: 10.17632/pb55hjf5y3.1.

[^21]: Walker LS, Byrne JP. Clinical impact of DVH uncertainties. *Med Dosim*. 2025;50(1):1-7. doi:10.1016/j.meddos.2024.06.002.

[^22]: Paddick I. A simple scoring ratio to index the conformity of radiosurgical treatment plans. *J Neurosurg*. 2000;93(Suppl 3):219-222. doi:10.3171/jns.2000.93.supplement_3.0219.

[^23]: Paddick I, Lippitz B. A simple dose gradient measurement tool to complement the conformity index. *J Neurosurg*. 2006;105(Suppl):194-201. doi:10.3171/sup.2006.105.7.194.

[^24]: Herman GT, Zheng J, Bucholtz CA. Shape-based interpolation. *IEEE Comput Graph Appl*. 1992;12(3):69-79. doi:10.1109/38.135915.

[^25]: International Atomic Energy Agency. Commissioning and quality assurance of computerized planning systems for radiation treatment of cancer. *IAEA Technical Reports Series No. 430*. Vienna: IAEA; 2004.

[^26]: Maurer CR, Qi R, Raghavan V. A linear time algorithm for computing exact Euclidean distance transforms of binary images in arbitrary dimensions. *IEEE Trans Pattern Anal Mach Intell*. 2003;25(2):265-270. doi:10.1109/TPAMI.2003.1177156.

[^27]: Sunday D. Inclusion of a point in a polygon. *Geometry Algorithms*. 2001. Available [here](https://web.archive.org/web/2021*/https://geomalgorithms.com/a03-_inclusion.html).

[^28]: Kahan W. Pracniques: Further remarks on reducing truncation errors. *Commun ACM*. 1965;8(1):40. doi:10.1145/363707.363723.

[^ScZ1999]: Scardovelli R, Zaleski S. Direct numerical simulation of free-surface and interfacial flow. *Annual Review of Fluid Mechanics*. 1999;31(1):567–603. doi:10.1146/annurev.fluid.31.1.567. (Source of the closed-form Volume-of-Fluid box-plane intersection formula used in §7.4.4.)

[^Powell2015]: Powell D, Abel T. An exact general remeshing scheme applied to physically conservative voxelization. *Journal of Computational Physics*. 2015;297:340–356. doi:10.1016/j.jcp.2015.05.022. (Source of the `r3d` exact polyhedron–voxel intersection algorithm referenced in the accuracy comparison table.)
