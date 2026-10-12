# Copyright (C) 2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""The runtime environment that runs the de-identification engine.

Each run records the environment that ran it as provenance, apart from the
method digest, which the environment does not change: the PyMedPhys version,
the Python implementation and version, and the versions of pydicom and
tomlkit. The release report holds them as structured fields, and the
Software Versions of the de-identifying equipment's Contributing Equipment
Sequence item holds the same values as four LO values
(:attr:`RuntimeEnvironment.software_versions`), so that both sources agree.
Neither holds a key, a path, or a source value.
"""

from __future__ import annotations

import dataclasses
import platform

from pymedphys import _version
from pymedphys._imports import pydicom, tomlkit


@dataclasses.dataclass(frozen=True)
class RuntimeEnvironment:
    """The software that runs the engine.

    Attributes
    ----------
    pymedphys_version : str
        PyMedPhys's full version, such as ``"0.42.0"``.
    python_implementation : str
        As :func:`platform.python_implementation` gives it, such as
        ``"CPython"``.
    python_version : str
        As :func:`platform.python_version` gives it, such as ``"3.14.0"``.
    pydicom_version : str
        pydicom's version, such as ``"3.0.2"``.
    tomlkit_version : str
        tomlkit's version, such as ``"0.15.1"``.
    """

    pymedphys_version: str
    python_implementation: str
    python_version: str
    pydicom_version: str
    tomlkit_version: str

    @property
    def software_versions(self) -> tuple[str, str, str, str]:
        """The four values of Software Versions (0018,1020), in order.

        PyMedPhys's version; the Python implementation, a space, and the
        Python version, such as ``"CPython 3.14.0"``; ``"pydicom <version>"``;
        and ``"tomlkit <version>"``.
        """
        return (
            self.pymedphys_version,
            f"{self.python_implementation} {self.python_version}",
            f"pydicom {self.pydicom_version}",
            f"tomlkit {self.tomlkit_version}",
        )


def runtime_environment() -> RuntimeEnvironment:
    """Return the runtime environment of the running process.

    The values are read at each call rather than once at import, so that
    they are those of the process that records them.

    Returns
    -------
    RuntimeEnvironment

    Examples
    --------
    >>> import platform
    >>> environment = runtime_environment()
    >>> environment.python_version == platform.python_version()
    True
    >>> environment.software_versions[2].startswith("pydicom ")
    True
    """
    return RuntimeEnvironment(
        pymedphys_version=_version.__version__,
        python_implementation=platform.python_implementation(),
        python_version=platform.python_version(),
        pydicom_version=pydicom.__version__,
        tomlkit_version=tomlkit.__version__,
    )
