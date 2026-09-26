#####################
Pseudonymisation Tool
#####################

This is the legacy experimental interface. Read its limitations in
:doc:`../../../background/dicom-deidentification` before sharing output.

.. automodule:: pymedphys.experimental.pseudonymisation
    :no-members:

.. warning::

    Experimental pseudonymisation hashes UIDs and some numeric values without
    a secret key. Anyone who holds the original UIDs can re-link records, and
    anyone can recover small-range values such as patient weight from the
    output alone by hashing every plausible value. It shifts every patient's
    dates by the same offset. Its output keeps the original file preamble and
    the original SOP Instance UID in the File Meta Information. Its functions
    emit a
    :class:`~pymedphys.experimental.pseudonymisation.PseudonymisationLimitationWarning`
    describing these limitations; this is not a deprecation.
    ``pseudonymisation_dispatch`` is a dictionary, so using it directly with
    ``anonymise_dataset`` does not warn. Review the output before sharing it.

*******
Summary
*******

    Pseudonymisation provides a list of identifying keywords that includes UIDs
    and an anonymisation strategy that utilises SHA3_256 to hash text which is then
    encoded as base64, or for UIDs, converted to an integer appended to the PyMedPhys Org Root.  Dates are shifted consistently and ages are jittered.
    The list of identifying keywords and the anonymisation strategy are passed in to
    the (non-experimental) anonymisation module/functions.



***
API
***

.. autofunction:: pymedphys.experimental.pseudonymisation.pseudonymise
.. autofunction:: pymedphys.experimental.pseudonymisation.get_default_pseudonymisation_keywords
.. autofunction:: pymedphys.experimental.pseudonymisation.is_valid_strategy_for_keywords
.. autoclass:: pymedphys.experimental.pseudonymisation.PseudonymisationLimitationWarning
.. autoattribute:: pymedphys.experimental.pseudonymisation.pseudonymisation_dispatch
    :annotation: strategy, i.e. dictionary of VR and function references for anonymisation to achieve pseudonymisation

*******
Example
*******

For an in-memory dataset, the return value is the pseudonymised dataset;
``output_path`` does not save it. Save the returned dataset explicitly:

.. code-block:: python

    import pydicom
    from pymedphys.experimental import pseudonymisation

    ds_input = pydicom.dcmread("input.dcm")
    ds_pseudo = pseudonymisation.pseudonymise(ds_input)
    ds_pseudo.save_as("output.dcm")

For a file input, pass a file path with a directory component. The parent
directory is used, but the filename is replaced with one generated from the
pseudonymised dataset; use the returned path to locate the file. For a
directory input, ``output_path`` is the destination directory:

.. code-block:: python

    output_file = pseudonymisation.pseudonymise(
        "input.dcm", output_path="output/example.dcm"
    )
    output_files = pseudonymisation.pseudonymise(
        "input_directory", output_path="output_directory"
    )

For finer control, pass this module's replacement strategy and identifying
keywords to :func:`pymedphys.dicom.anonymise`. The following reproduces
``pseudonymise`` for a dataset; adjust the arguments as required:

.. code-block:: python

    import pymedphys.dicom

    ds_pseudo = pymedphys.dicom.anonymise(
        ds_input,
        keywords_to_leave_unchanged=["PatientSex"],
        delete_unknown_tags=True,
        replacement_strategy=pseudonymisation.pseudonymisation_dispatch,
        identifying_keywords=pseudonymisation.get_default_pseudonymisation_keywords(),
    )
