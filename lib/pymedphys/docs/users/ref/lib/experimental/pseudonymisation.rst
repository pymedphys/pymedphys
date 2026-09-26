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
::

    import pymedphys.experimental.pseudonymisation as pseudonymisation_api

    pseudonymisation_api.pseudonymise(ds_input, output_path="/home/myname/pseudo_out/")
    # or
    ds_pseudo = anonymise_dataset(ds_input,
        replacement_strategy=pseudonymisation_api.pseudonymisation_dispatch,
        identifying_keywords=pseudonymisation_api.get_default_pseudonymisation_keywords(),
    )
