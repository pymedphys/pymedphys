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

"""Write prose for the sections of the conformance statement.

:mod:`~pymedphys._dicom.deidentify.conformance_values` and
:mod:`~pymedphys._dicom.deidentify.conformance_items` join names as prose
and mark actions as code with these, so that every section reads alike.
"""

from __future__ import annotations

from collections.abc import Iterable


def join(values: Iterable[str], conjunction: str = "and") -> str:
    """Join ``values`` as prose: ``"a"``, ``"a and b"``, or ``"a, b, and c"``."""
    values = list(values)
    if len(values) <= 2:
        return f" {conjunction} ".join(values)
    return ", ".join(values[:-1]) + f", {conjunction} " + values[-1]


def code(action: str) -> str:
    """Return ``action`` as inline code."""
    return f"`{action}`"
