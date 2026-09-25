#####################
Pseudonymisation Tool
#####################

.. automodule:: pymedphys.experimental.pseudonymisation
    :no-members:

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
