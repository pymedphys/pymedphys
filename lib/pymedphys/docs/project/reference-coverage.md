# Public reference coverage

For contributors adding an interface and reviewers checking whether users can
find its contract. This register compares the current source exports and command
parsers with the reference pages and task guides. It is independent of the
navigation inventory: a page existing in a toctree does not establish that every
export is documented.

## Scope and authority

The package root currently exports 17 names, including eight feature modules,
`__version__`, and the deprecated `read_trf` alias. Those eight modules export
39 names, including constants, connection types and deprecated aliases. None of
these files declares `__all__`; inspect their explicit imports, definitions and
assignments when updating this register. The root's deliberate `__version__`
export is included even though its name begins with underscores.

Authoritative sources are
[`pymedphys/__init__.py`](https://github.com/pymedphys/pymedphys/blob/main/lib/pymedphys/__init__.py),
the public facade files named below, and
[`cli.define_parser`](https://github.com/pymedphys/pymedphys/blob/main/lib/pymedphys/cli/__init__.py)
with its registered parser builders. API docstrings own function contracts;
autodoc renders them. Argparse owns command names, defaults and options;
sphinx-argparse renders them. Task guides explain preparation, supported inputs,
observable results and limitations. A rendered signature alone does not establish
scientific validity or complete error documentation.

In the tables, **reference** means the symbol or command has a dedicated
generated reference entry. **Compatibility** means the name remains available
and its replacement is documented. **Scoped** identifies an exported adapter or
constant whose use is explained without presenting a separate application
interface. **Experimental gap** means an experimental export is available but
has no dedicated contract reference; it is not silently counted as covered.
Public beta interfaces remain subject to the
[compatibility policy](compatibility.md).

## Package-root exports

All names in this table are relative to `pymedphys`.

| Namespace | Exported names | Reference and task path | Coverage |
| --- | --- | --- | --- |
| `pymedphys` | `gamma`, `gamma_pass_rate` | [Gamma reference](../users/ref/lib/gamma.rst); [Compare dose](../users/tasks/compare.md) | Reference; conventions, cutoffs and pass-rate denominator belong in the task and docstrings. |
| `pymedphys` | `Delivery` | [Delivery reference](../users/ref/lib/delivery.rst); [Delivery data](../users/tasks/delivery.md) | Reference; include inherited adapters and methods, rather than documenting only the empty assembled class. |
| `pymedphys` | `data_path`, `zip_data_paths`, `zenodo_data_paths` | [Data helper reference](../users/ref/lib/data.rst); [Fixture and data guide](../contrib/validation/data.md) | Reference; download verification, extraction and cache behaviour are part of the contract. |
| `pymedphys` | `__version__`, `version_info` | [Library reference](../users/ref/lib/index.rst); [Compatibility](compatibility.md) | Scoped version metadata; package version and generated version components are described in the library overview. |
| `pymedphys` | `read_trf` | [Library compatibility notes](../users/ref/lib/index.rst); [TRF reference](../users/ref/lib/trf.rst) | Compatibility; use `pymedphys.trf.read`. |
| `pymedphys` | `dicom`, `electronfactors`, `interpolate`, `metersetmap`, `mosaiq`, `pinnacle`, `trf` | [Library reference](../users/ref/lib/index.rst) and the feature entries below | Module entry points; coverage is assessed at their exported names. |
| `pymedphys` | `mudensity` | [Library compatibility notes](../users/ref/lib/index.rst); [MetersetMap reference](../users/ref/lib/metersetmap.rst) | Compatibility module; use `metersetmap`. |

`Delivery` is assembled in
[`_delivery.py`](https://github.com/pymedphys/pymedphys/blob/main/lib/pymedphys/_delivery.py).
Its common representation, `combine` and `merge` come from `DeliveryBase`;
the format mixins supply `from_dicom`, `to_dicom`, `from_trf`, `from_logfile`,
`from_icom`, `from_monaco`, `from_mosaiq`, `metersetmap` and `mudensity`.
The named tuple also supplies its five data fields and ordinary tuple operations.
The task guide explains the representation and adapter limits; the reference
must include inherited public methods. Underscored mixin helpers are implementation
details rather than additional user entry points.

## Public feature exports

Names are relative to the namespace in the first column. Each public facade is
authoritative for the list, even where its implementation lives in an underscored
package.

| Namespace | Exported names | Reference and task path | Coverage |
| --- | --- | --- | --- |
| `pymedphys.dicom` | `anonymise`, `AnonymisationLimitationWarning` | [DICOM reference](../users/ref/lib/dicom.rst); [De-identification scope](../users/background/dicom-deidentification.md) | Reference; the legacy interface and its warnings are distinct from the developing confidentiality-profile engine. |
| `pymedphys.dicom` | `zyx_and_dose_from_dataset`, `depth_dose`, `profile`, `dicom_dose_interpolate` | [DICOM reference](../users/ref/lib/dicom.rst); [Work with DICOM](../users/tasks/dicom.md) | Reference; returned physical axes, dose units and narrower phantom assumptions require explicit limits. |
| `pymedphys.dicom` | `merge_contours` | [DICOM reference](../users/ref/lib/dicom.rst); [Contour workflow](../users/tasks/dicom.md#merge-overlapping-planar-contours) | Reference and worked synthetic geometry; one ROI contour item, mutation and topology limits are documented. |
| `pymedphys.electronfactors` | `parameterise_insert`, `spline_model`, `calculate_deformability`, `spline_model_with_deformability`, `calculate_percent_prediction_differences`, `visual_alignment_of_equivalent_ellipse` | [Electron-factor reference](../users/ref/lib/electronfactors.rst); [Electron factors](../users/tasks/electronfactors.md) | Reference; measured-input and model-validation requirements are in the task guide. |
| `pymedphys.electronfactors` | `convert2_ratio_perim_area`, `create_transformed_mesh`, `plot_model` | [Electron-factor reference](../users/ref/lib/electronfactors.rst); [Electron factors](../users/tasks/electronfactors.md) | Reference; these exported conversion and visualisation helpers are included alongside the main model functions. |
| `pymedphys.interpolate` | `interp`, `interp_linear_1d`, `interp_linear_2d`, `interp_linear_3d`, `plot_interp_comparison_heatmap` | [Interpolation reference](../users/ref/lib/interp.rst); [Interpolation workflow](../users/tasks/interpolation.md) | Reference; the high-level interface, lower-level functions and comparison plot are separate entries. |
| `pymedphys.metersetmap` | `calculate`, `grid`, `display` | [MetersetMap reference](../users/ref/lib/metersetmap.rst); [Delivery data](../users/tasks/delivery.md) | Reference; geometry is supplied separately from delivery control points. |
| `pymedphys.metersetmap` | `WARNING_MESSAGE` | [MetersetMap reference](../users/ref/lib/metersetmap.rst); [Delivery data](../users/tasks/delivery.md) | Scoped constant; the reference explains its relationship to the dosimetric limitations. |
| `pymedphys.mosaiq` | `connect`, `execute`, `Connection`, `Cursor` | [Mosaiq reference](../users/ref/lib/mosaiq.rst); [Mosaiq workflow](../users/tasks/mosaiq.md) | Reference; connection lifetime, credentials and parameterised queries are part of use. |
| `pymedphys.mudensity` | `calculate`, `grid`, `display`, `WARNING_MESSAGE` | [Library compatibility notes](../users/ref/lib/index.rst); [MetersetMap reference](../users/ref/lib/metersetmap.rst) | Compatibility aliases to `metersetmap`; a second independent contract would duplicate the replacement. |
| `pymedphys.pinnacle` | `PinnacleExport`, `PinnaclePlan`, `PinnacleImage` | [Pinnacle reference](../users/ref/lib/pinnacle.rst); [Pinnacle workflow](../users/tasks/pinnacle.md) | Reference with class members; the public namespace does not remove the exporter's research-use limitations. |
| `pymedphys.pinnacle` | `export_cli` | [Pinnacle CLI reference](../users/ref/cli/pinnacle.rst); [Pinnacle workflow](../users/tasks/pinnacle.md) | Scoped parser-namespace adapter; use the classes for Python workflows and `pymedphys pinnacle export` for the CLI. |
| `pymedphys.trf` | `read`, `identify` | [TRF reference](../users/ref/lib/trf.rst); [Logfile workflow](../users/tasks/logfiles.md) | Reference; decoding and Mosaiq-backed identification have different dependency and input requirements. |

The source files are `dicom.py`, `electronfactors.py`, `interpolate.py`,
`metersetmap.py`, `mosaiq.py`, `mudensity.py`, `pinnacle.py` and `trf.py` under
[`lib/pymedphys`](https://github.com/pymedphys/pymedphys/tree/main/lib/pymedphys).
Imports of an underscored implementation into these facades are public exports;
their implementation path does not make them private.

## Experimental and private scope

The experimental subpackage is not imported as a root feature module by
`pymedphys/__init__.py`. It remains an importable namespace with its own explicit
exports. Its reference warning describes its alpha status. The omissions below
are known gaps for that scope, not claims of stable support.

| Namespace | Exported names | Reference and task path | Coverage |
| --- | --- | --- | --- |
| `pymedphys.experimental` | `pseudonymisation` | [Experimental reference](../users/ref/lib/experimental/index.rst); [Pseudonymisation reference](../users/ref/lib/experimental/pseudonymisation.rst) | Experimental module with documented limitations. |
| `pymedphys.experimental` | `fileformats`, `quickcheck` | [Experimental scope](../users/ref/lib/experimental/index.rst) | Experimental gaps; module names are reachable but their contracts are not rendered there. |
| `pymedphys.experimental` | `align_cube_to_structure`, `cubify` | [Experimental scope](../users/ref/lib/experimental/index.rst) | Experimental gaps; document geometry, mutation, accepted structures and independent checks before adding a supported task. |
| `pymedphys.experimental.fileformats` | `read_mapcheck`, `load_mephysto_directory`, `read_prs` | [Experimental scope](../users/ref/lib/experimental/index.rst) | Experimental gaps; supported vendor versions, units, return schemas and failure modes need dedicated references. |
| `pymedphys.experimental.quickcheck` | `QuickCheck` | [Experimental scope](../users/ref/lib/experimental/index.rst) | Experimental gap; the device/network and returned measurement contracts need a dedicated reference. |
| `pymedphys.experimental.pseudonymisation` | `pseudonymise`, `get_default_pseudonymisation_keywords`, `is_valid_strategy_for_keywords`, `pseudonymisation_dispatch`, `PseudonymisationLimitationWarning` | [Pseudonymisation reference](../users/ref/lib/experimental/pseudonymisation.rst); [De-identification scope](../users/background/dicom-deidentification.md) | Experimental reference; hashing and sharing limitations remain explicit. |
| `pymedphys.experimental.pinnacle` | `PinnacleExport`, `PinnaclePlan`, `PinnacleImage`, `export_cli` | [Retained Pinnacle page](../users/ref/lib/experimental/pinnacle.rst); [Current Pinnacle reference](../users/ref/lib/pinnacle.rst) | Compatibility aliases; the module is importable directly but is not imported by `experimental/__init__.py`. |

The underscored packages, vendor code and internal Streamlit helpers are outside
this public-facade contract register. Contributor
[architecture](../contrib/architecture/index.md) and
[design documents](../contrib/design/index.md) explain them. In particular,
`_dicom.deidentify` is a programme under implementation, not an additional
currently exported root DICOM interface. Its requirements and tests belong in the
[design programme](../contrib/design/deidentification/index.md); do not create a
current user contract from planned commands or milestones.

## Command coverage

All command paths below follow `pymedphys`. The root parser registers eight
entry points: `dicom`, `experimental`, `pinnacle`, `trf`, `dev`, `zenodo`,
`icom` and `gui`, with 33 registered leaf paths including aliases. The
[CLI overview](../users/ref/cli/index.rst) renders its
top-level help, including `--verbose`, `--debug` and `--version`. Automatic
`--help` is supplied by argparse. Root help lists command groups; detailed
options require the corresponding reference page.

| Command path | Parser source under `lib/pymedphys/cli/` | Reference and task path | Coverage |
| --- | --- | --- | --- |
| `gui` | `gui.py` | [GUI reference](../users/ref/cli/gui.rst); [Apps](../users/tasks/apps.md) | Generated arguments and serving/configuration explanation. |
| `dicom anonymise` | `dicom.py` | [DICOM CLI](../users/ref/cli/dicom.rst); [De-identification scope](../users/background/dicom-deidentification.md) | Generated arguments; legacy limitations remain visible. |
| `dicom merge-contours`, `dicom adjust-machine-name`, `dicom adjust-RED`, `dicom adjust-RED-by-structure-name` | `dicom.py` | [DICOM CLI](../users/ref/cli/dicom.rst); [DICOM tasks](../users/tasks/dicom.md) | Generated arguments and editing workflows. |
| `dicom listen`, `dicom send` | `dicom.py` | [DICOM CLI](../users/ref/cli/dicom.rst); [DICOM tasks](../users/tasks/dicom.md) | Generated arguments and transfer scope. |
| `trf to-csv`, `trf detect`, `trf orchestrate` | `trf.py` | [TRF CLI](../users/ref/cli/trf.rst); [Logfiles](../users/tasks/logfiles.md) | Generated arguments; orchestration additionally needs site configuration and Mosaiq. |
| `icom listen` | `icom.py` | [iCOM CLI](../users/ref/cli/icom.rst); [Logfiles](../users/tasks/logfiles.md) | Generated arguments and recording/output workflow. |
| `pinnacle export` | `pinnacle.py` | [Pinnacle CLI](../users/ref/cli/pinnacle.rst); [Pinnacle tasks](../users/tasks/pinnacle.md) | Generated arguments and research export scope. |
| `zenodo set-token` | `zenodo.py` | [Zenodo CLI](../users/ref/cli/zenodo.rst); [Fixture and data guide](../contrib/validation/data.md) | Contributor token configuration; no token is required for ordinary public fixture downloads. |
| `experimental dicom pseudonymise` | `experimental/dicom.py` | [Pseudonymisation CLI](../users/ref/cli/pseudonymisation.rst); [De-identification scope](../users/background/dicom-deidentification.md) | Generated arguments and experimental limitations. |
| `experimental dicom anonymise`, `experimental dicom merge-contours`, `experimental dicom adjust-machine-name`, `experimental dicom adjust-RED`, `experimental dicom adjust-RED-by-structure-name`, `experimental dicom listen`, `experimental dicom send` | `experimental/dicom.py` calls `dicom.set_up_dicom_cli` | [DICOM CLI](../users/ref/cli/dicom.rst) | Scoped aliases: this group registers the same seven DICOM parsers before adding `pseudonymise`; use the ordinary `dicom` path for those shared commands. |
| `experimental pinnacle export` | `experimental/pinnacle.py` | [Pinnacle CLI](../users/ref/cli/pinnacle.rst) | Compatibility path to the Pinnacle exporter; prefer the ordinary `pinnacle` path. |

### Developer commands

[`cli/dev.py`](https://github.com/pymedphys/pymedphys/blob/main/lib/pymedphys/cli/dev.py)
registers ten commands. The
[developer command reference](../contrib/guides/dev-reference.rst) renders all
ten from the parser. Additional pytest/Pylint arguments passed through the CLI
belong to those tools and are not separate argparse options.

| Command path | Preparation and result guide | Contract detail to retain |
| --- | --- | --- |
| `dev docs` | [Authoring](../contrib/guides/authoring.md); [Publishing](../contrib/maintainers/publishing.md) | Output, clean/prep/linkcheck modes, generated inputs, execution and warnings. |
| `dev tests` | [Testing](../contrib/validation/testing.md) | Caller-relative paths, forwarded pytest options, markers, skips and reports. |
| `dev doctests` | [Testing](../contrib/validation/testing.md) | Doctest collection and forwarded pytest options. |
| `dev lint` | [Testing](../contrib/validation/testing.md) | Pylint invocation; Ruff is a separate check. |
| `dev propagate` | [Make a change](../contrib/guides/make-a-change.md) | Generated outputs and the intentional dependency upgrade performed by `--update`. |
| `dev imports` | [Lazy import policy](../contrib/info/lazy-imports.md) | Fresh installations, extras, network requirements and failure status. |
| `dev mssql` | [Testing](../contrib/validation/testing.md) | Docker Compose prerequisite and `--daemon`/`--stop`. |
| `dev deid-tables` | [De-identification contribution](../contrib/design/deidentification/contributing.md) | Pinned source checks, output, current-edition comparison and exit statuses. |
| `dev deid-matrix` | [Requirements and evidence](../contrib/design/deidentification/requirements.md); [Contribution](../contrib/design/deidentification/contributing.md) | Register/JUnit inputs, generated output, and `--check` requiring at least one report. |
| `dev tg263-check` | [Maintain CI](../contrib/maintainers/ci.md) | Reviewed resource scope, optional JSON and exit statuses 0/1/3. |

The source tree also contains standalone scripts such as distribution and
migration checks. They are documented with their maintainer procedures; they
are not registered `pymedphys` CLI commands. Streamlit app names likewise belong
to the app selector rather than this argparse command tree.

## Maintain the register

When exports, signatures, parser registrations or optional dependencies change:

1. Enumerate the root and public facade imports, definitions and assignments.
   If a module introduces `__all__`, use its explicit export contract and check
   intentional compatibility names separately. Follow aliases to their public
   names, rather than documenting the private implementation name.
2. Traverse the parser returned by `pymedphys.cli.define_parser()` without
   invoking a command. Inspect subparser registrations, including reused
   groups under `experimental`, and compare every leaf path with these tables.
3. Check that each reference entry renders the current signature/options and
   that class references include the intended inherited public members.
   Confirm that task links explain the relevant input, output, units,
   dependencies, errors and limitations.
4. Classify any omission explicitly as a current gap, compatibility alias,
   scoped adapter or experimental gap. An ordinary public export cannot be
   excluded solely because its implementation is underscored.
5. Build the docs and run the
   [migration checks](documentation.md#check-a-migration). Inspect the affected
   rendered reference and reader path; an export count or navigation check
   does not establish contract quality.

The remaining experimental gaps above need reviewed contracts and examples
before they become supported user workflows. A future change may either
document them within experimental scope or deliberately revise that public
surface under the compatibility policy. Keep this register aligned with that
decision and the source.
