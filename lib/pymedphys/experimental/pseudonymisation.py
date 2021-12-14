def _stub(*_args, **_kwargs):
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

pseudonymisation_dispatch = dict(
    {
        "AE": _stub,
        "AS": _stub,
        "CS": _stub,
        "DA": _stub,
        "DS": _stub,
        "DT": _stub,
        "LO": _stub,
        "LT": _stub,
        "OB": _stub,
        "OB or OW": _stub,
        "OW": _stub,
        "PN": _stub,
        "SH": _stub,
        "ST": _stub,
        "SQ": _stub,
        "TM": _stub,
        "UI": _stub,
        "US": _stub,
    }
)
