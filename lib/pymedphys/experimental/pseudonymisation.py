# pylint: disable = unused-import
# ruff: noqa: F401

# The limitation warning is emitted here, at the public interface, so that the
# private implementation can call these functions without repeating it.
# pseudonymisation_dispatch is a dictionary of strategy functions, not a call,
# so it is re-exported without a warning; the functions that apply it warn.

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

    # functools.wraps copies the private module and name. Point them at this
    # module instead, so that pickle resolves the public name to the wrapper.
    wrapper.__module__ = __name__
    wrapper.__qualname__ = func.__name__
    return wrapper


pseudonymise = _warn_about_limitations(_pseudonymisation.pseudonymise)
get_default_pseudonymisation_keywords = _warn_about_limitations(
    _pseudonymisation.get_default_pseudonymisation_keywords
)
is_valid_strategy_for_keywords = _warn_about_limitations(
    _pseudonymisation.is_valid_strategy_for_keywords
)
