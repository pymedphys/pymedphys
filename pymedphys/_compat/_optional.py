# Code adapted from
# https://github.com/pandas-dev/pandas/blob/6d35836e/pandas/compat/_optional.py

# Original code under the following license:
# ======================================================================================================
# Copyright (c) 2008-2012, AQR Capital Management, LLC, Lambda Foundry, Inc. and PyData Development Team
# Distributed under the terms of the Modified BSD License.
# See https://github.com/pandas-dev/pandas/blob/6d35836e/LICENSE for more details.
# ======================================================================================================

# Modifications under the following license:
# ========================================================================
# Copyright (C) 2019 Simon Biggs

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version (the "AGPL-3.0+").

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License and the additional terms for more
# details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# ADDITIONAL TERMS are also included as allowed by Section 7 of the GNU
# Affero General Public License. These additional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.
# ========================================================================


import importlib
import types
import warnings

import packaging.specifiers
import packaging.version

VERSIONS = {
    "cefpython3": "==66.0",
    "numpy": ">=1.12",
    "pymssql": "<3.0.0",
    "sphinx": ">=1.4,<1.8",
    "sphinx-rtd-theme": ">=0.4.3",
}

message = "Missing optional dependency '{name}'. {extra} " "Use pip to install {name}."
version_message = (
    "PyMedPhys requires version '{specifier_string}' of '{name}' "
    "(version '{actual_version}' currently installed)."
)


def _get_version(module: types.ModuleType) -> packaging.version.Version:
    version = packaging.version.Version(getattr(module, "__version__", None))

    if version is None:
        raise ImportError("Can't determine version for {}".format(module.__name__))

    return version


def import_optional_dependency(
    name: str, extra: str = "", raise_on_missing: bool = True, on_version: str = "raise"
):
    """
    Import an optional dependency.

    By default, if a dependency is missing an ImportError with a nice
    message will be raised. If a dependency is present, but too old,
    we raise.

    Parameters
    ----------
    name : str
        The module name. This should be top-level only, so that the
        version may be checked.
    extra : str
        Additional text to include in the ImportError message.
    raise_on_missing : bool, default True
        Whether to raise if the optional dependency is not found.
        When False and the module is not present, None is returned.
    on_version : str {'raise', 'warn'}
        What to do when a dependency's version is too old.

        * raise : Raise an ImportError
        * warn : Warn that the version is too old. Returns None
        * ignore: Return the module, even if the version is too old.
          It's expected that users validate the version locally when
          using ``on_version="ignore"`` (see. ``io/html.py``)

    Returns
    -------
    maybe_module : Optional[ModuleType]
        The imported module, when found and the version is correct.
        None is returned when the package is not found and `raise_on_missing`
        is False, or when the package's version is too old and `on_version`
        is ``'warn'``.
    """
    try:
        module = importlib.import_module(name)
    except ImportError:
        if raise_on_missing:
            raise ImportError(message.format(name=name, extra=extra)) from None

        return None

    specifier_string = VERSIONS.get(name)

    if specifier_string:
        specifier_set = packaging.specifiers.SpecifierSet(specifier_string)
        version = _get_version(module)

        if not list(specifier_set.filter([version])):
            if not on_version in {"warn", "raise", "ignore"}:
                raise ValueError(
                    "Expected one of 'warn', 'raise', or 'ignore' for `on_version`"
                )
            msg = version_message.format(
                specifier_string=specifier_string, name=name, actual_version=version
            )

            if on_version == "warn":
                warnings.warn(msg, UserWarning)
                return None

            if on_version == "raise":
                raise ImportError(msg)

    return module
