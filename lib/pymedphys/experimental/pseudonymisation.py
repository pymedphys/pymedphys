# pylint: disable = unused-import
# ruff: noqa: F401

# The limitation warning is emitted here, at the public interface, so that the
# private implementation can call these functions without repeating it.

import functools as _functools
import warnings as _warnings

from pymedphys._experimental import pseudonymisation as _pseudonymisation
from pymedphys._experimental.pseudonymisation import (
    PseudonymisationLimitationWarning,
)
from pymedphys._experimental.pseudonymisation.strategy import pseudonymisation_dispatch


def _warn_about_limitations(func):
    @_functools.wraps(func)
    def wrapper(*args, **kwargs):
        _warnings.warn(
            _pseudonymisation.LIMITATION_NOTICE,
            PseudonymisationLimitationWarning,
            stacklevel=2,
        )
        return func(*args, **kwargs)

    return wrapper


pseudonymise = _warn_about_limitations(_pseudonymisation.pseudonymise)
get_default_pseudonymisation_keywords = _warn_about_limitations(
    _pseudonymisation.get_default_pseudonymisation_keywords
)
is_valid_strategy_for_keywords = _warn_about_limitations(
    _pseudonymisation.is_valid_strategy_for_keywords
)
