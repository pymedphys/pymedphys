def _stub():
    raise NotImplementedError(
        """
        It appears that the pseudonymise function as implemented has some
        identifying components able to be reversible. See
        <https://github.com/pymedphys/pymedphys/issues/1455> for more
        details.

        For the time being, this API is no longer being exposed.
        """
    )


get_default_pseudonymisation_keywords = _stub
is_valid_strategy_for_keywords = _stub
pseudonymise = _stub
pseudonymisation_dispatch = _stub
