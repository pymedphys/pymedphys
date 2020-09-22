#####################
Pseudonymisation Tool
#####################

.. contents::
    :local:
    :backlinks: entry


.. automodule:: pymedphys.experimental.pseudonymisation
    :no-members:

*******
Summary
*******

    Pseudonymisation provides a list of identifying keywords that includes UIDs
    and an anonymisation strategy that utilises SHA3_256 to hash text which is then
    encoded as base64, or for UIDs, converted to an integer appended to the PyMedPhys Org Root.  Dates are shifted consistently and ages are jittered.
    The anonymisation strategy is passed in to the (non-experimental) anonymisation module/functions.
    Anonymisation strategies are immutable maps that contain dispatch tables for replacing the values of identifying elements,
    and also contain the identifying keywords that the strategy is intended to address.
    Further, the strategies contain the boolean (or Tri-State) modifiers that control aspects of the anonymisation:

  *  delete_private_tags
  *  delete_unknown_tags

    To modify the behaviour regarding private tags and unknown tags, it is necessary to construct a new dictionary like container,
    potentially another immutable map with the new values for delete_private_tags and/or delete_unknown_tags

    See PEP 603, or the PyPI immutables package for more information

***
API
***

.. autofunction:: pymedphys.experimental.pseudonymisation.get_copy_of_strategy
.. autofunction:: pymedphys.experimental.pseudonymisation.get_default_pseudonymisation_keywords
.. autofunction:: pymedphys.experimental.pseudonymisation.is_valid_strategy_for_keywords
.. autoattribute:: pymedphys.experimental.pseudonymisation.pseudonymisation_dispatch
    :annotation: strategy, i.e. dictionary of VR and function references for anonymisation to achieve pseudonymisation

*******
Example
*******
::

    import pymedphys.experimental.pseudonymisation as pseudonymisation_api

    anonymise_dataset(ds_input,
        replacement_strategy=pseudonymisation_api.get_copy_of_strategy(),
    )
