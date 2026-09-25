# pylint: disable = unused-import
# ruff: noqa: F401

# The functions are deprecated here, at the public interface, so that the
# private implementation can call them without repeating the warning.

from pymedphys._experimental import pseudonymisation as _pseudonymisation
from pymedphys._experimental.pseudonymisation.strategy import pseudonymisation_dispatch
from pymedphys._vendor.deprecated import deprecated as _deprecated

_deprecate = _deprecated(_pseudonymisation.DEPRECATION_REASON)

pseudonymise = _deprecate(_pseudonymisation.pseudonymise)
get_default_pseudonymisation_keywords = _deprecate(
    _pseudonymisation.get_default_pseudonymisation_keywords
)
is_valid_strategy_for_keywords = _deprecate(
    _pseudonymisation.is_valid_strategy_for_keywords
)
