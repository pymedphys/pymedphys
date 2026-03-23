# What PyMedPhys can do

PyMedPhys is a toolkit for common medical physics data and workflow problems.
You can use it through three main interfaces:

- the Python library
- the command line interface (CLI)
- the app layer for point-and-click workflows

You do not need to know the module name before you start. This page is
intentionally task-first and not exhaustive.

```{important}
PyMedPhys is still in beta. Interfaces and workflows can change between
releases. If you depend on a local script or automation, read the release notes
before upgrading.
```

## If you want to compare dose or fluence-like data

Gamma calculations are one of the most visible parts of PyMedPhys.
Start with the {doc}`Gamma how-to guides <../howto/gamma/index>` if you want
worked examples.
If you already know that you need the API, see the
{doc}`Gamma library reference <../ref/lib/gamma>`.

For fast interpolation on rectilinear grids, see the
{doc}`Interpolation how-to guide <../howto/interp/index>` and the
{doc}`Interpolation reference <../ref/lib/interp>`.

MetersetMap is also available for field or delivery-style comparisons.
See the {doc}`MetersetMap reference <../ref/lib/metersetmap>`.

## If you want to work with DICOM

PyMedPhys includes DICOM-related library and CLI functionality.
Start with the {doc}`DICOM library reference <../ref/lib/dicom>` if you are
scripting in Python.
Start with the {doc}`DICOM CLI reference <../ref/cli/dicom>` if you want a
shell-based workflow.

If your goal is to share data outside the clinic, also see the
{doc}`pseudonymisation library reference <../ref/lib/experimental/pseudonymisation>`
and the
{doc}`pseudonymisation CLI reference <../ref/cli/pseudonymisation>`.

## If you want to work with delivery or machine log data

PyMedPhys contains tooling around Elekta logfile and related workflows.
Start with the
{doc}`Elekta logfile background page <../background/elekta-logfiles>` for
context.
Then use the {doc}`TRF library reference <../ref/lib/trf>` or the
{doc}`TRF CLI reference <../ref/cli/trf>` depending on whether you want Python
or CLI automation.

For iCom-oriented command line workflows, see the
{doc}`iCom CLI reference <../ref/cli/icom>`.

## If you want to query or integrate with Mosaiq

PyMedPhys exposes Mosaiq functionality in the library.
Start with the {doc}`Mosaiq library reference <../ref/lib/mosaiq>`.
This path is especially useful when you need a local report, an integration
script, or a clinic-specific workflow.

## If you want point-and-click tools

PyMedPhys also includes a Streamlit-based app layer for selected workflows.
The current stable app registry includes MetersetMap and pseudonymisation, and
there are additional experimental apps.
If you want a graphical workflow rather than code, continue to
{doc}`Choose your path <choose-your-path>`.

## If you want electron cutout factor tools

See the
{doc}`electron cutout factor reference <../ref/lib/electronfactors>`.

## There is more than this

The pages above are the most obvious current entry points for end users.
The {doc}`Technical Reference <../ref/index>` lists the library and CLI areas
that are already surfaced in the documentation.
Some specialised or experimental areas are also present in the project, but
this page focuses on the capabilities most users are likely to look for first.

## Where to go next

If you know the kind of task you want to solve but not the interface, continue
to {doc}`Choose your path <choose-your-path>`.

If you already know you need PyMedPhys on a workstation, continue to
{doc}`Installation options <installation-options>`.

If you already know the exact module or command you want, jump straight to the
{doc}`Technical Reference <../ref/index>`.
