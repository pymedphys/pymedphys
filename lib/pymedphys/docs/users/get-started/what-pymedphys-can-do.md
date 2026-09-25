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
Start with the [Gamma how-to guides](../howto/gamma/index.rst) if you want
worked examples.
If you already know that you need the API, see the
[Gamma library reference](../ref/lib/gamma.rst).

For fast interpolation on rectilinear grids, see the
[Interpolation how-to guide](../howto/interp/index.rst) and the
[Interpolation reference](../ref/lib/interp.rst).

MetersetMap is also available for field or delivery-style comparisons.
See the [MetersetMap reference](../ref/lib/metersetmap.rst).

## If you want to work with DICOM

PyMedPhys includes DICOM-related library and CLI functionality.
Start with the [DICOM library reference](../ref/lib/dicom.rst) if you are
scripting in Python.
Start with the [DICOM CLI reference](../ref/cli/dicom.rst) if you want a
shell-based workflow.

If your goal is to share data outside the clinic, first read
[DICOM de-identification](../background/dicom-deidentification.md), which
explains the terms and the known limitations of the current anonymisation and
pseudonymisation tools. Their references are the
[pseudonymisation library reference](../ref/lib/experimental/pseudonymisation.rst)
and the
[pseudonymisation CLI reference](../ref/cli/pseudonymisation.rst).

## If you want to work with delivery or machine log data

PyMedPhys contains tooling around Elekta logfile and related workflows.
Start with the
[Elekta logfile background page](../background/elekta-logfiles.rst) for
context.
Then use the [TRF library reference](../ref/lib/trf.rst) or the
[TRF CLI reference](../ref/cli/trf.rst) depending on whether you want Python
or CLI automation.

For iCom-oriented command line workflows, see the
[iCom CLI reference](../ref/cli/icom.rst).

## If you want to query or integrate with Mosaiq

PyMedPhys exposes Mosaiq functionality in the library.
Start with the [Mosaiq library reference](../ref/lib/mosaiq.rst).
This path is especially useful when you need a local report, an integration
script, or a clinic-specific workflow.

## If you want point-and-click tools

PyMedPhys also includes a Streamlit-based app layer for selected workflows.
The current stable app registry includes MetersetMap and pseudonymisation, and
there are additional experimental apps.
If you want a graphical workflow rather than code, continue to
[Choose your path](choose-your-path.md).

## If you want electron cutout factor tools

See the
[electron cutout factor reference](../ref/lib/electronfactors.rst).

## There is more than this

The pages above are the most obvious current entry points for end users.
The [Technical Reference](../ref/index.md) lists the library and CLI areas
that are already surfaced in the documentation.
Some specialised or experimental areas are also present in the project, but
this page focuses on the capabilities most users are likely to look for first.

## Where to go next

If you know the kind of task you want to solve but not the interface, continue
to [Choose your path](choose-your-path.md).

If you already know you need PyMedPhys on a workstation, continue to
[Installation options](installation-options.md).

If you already know the exact module or command you want, jump straight to the
[Technical Reference](../ref/index.md).
