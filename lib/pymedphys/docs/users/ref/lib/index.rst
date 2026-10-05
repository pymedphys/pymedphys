===================
Library Reference
===================

Use these pages for signatures, arguments, return values, and supported
interfaces. The :doc:`user guide <../../tasks/index>` connects them to worked
examples and interpretation. Import public interfaces from ``pymedphys`` or
its public modules; private modules beginning with ``_`` are implementation
details.

.. toctree::
    :maxdepth: 2

    ../../../genindex
    delivery
    data
    dicom
    gamma
    interp
    mosaiq
    metersetmap
    trf
    electronfactors
    pinnacle
    experimental/index

Version attributes
------------------

``pymedphys.__version__`` is the installed version string.
``pymedphys.version_info`` contains its parsed components. Record the version
with your calculation settings and dependency environment; it does not imply
that a particular workflow has been validated for your data.

Compatibility names
-------------------

``pymedphys.read_trf`` is deprecated in favour of
:func:`pymedphys.trf.read`. The ``pymedphys.mudensity`` functions
``calculate``, ``grid``, and ``display`` are deprecated aliases of the matching
:doc:`metersetmap` functions. ``pymedphys.mudensity.WARNING_MESSAGE`` contains
the same limitations notice as ``pymedphys.metersetmap.WARNING_MESSAGE``.
Use current names in new code. The :doc:`delivery` reference also covers the
deprecated ``Delivery.from_logfile`` and ``Delivery.mudensity`` methods.
