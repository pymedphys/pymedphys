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

"""The strings that an instance's plan retains, for the QC pack's review (D-017).

D-017's human review covers every distinct retained string. A retained
string is a value that the walker's plan keeps as it is: an element planned
K, which is neither a sequence nor removed with one, whose VR is one of
:data:`RETAINED_TEXT_VRS`. Its value is not otherwise read, since keeping it
needs no consumer (:mod:`~pymedphys._dicom.deidentify.walker`), so the
transform reads the values of :func:`retained_paths` for the review only,
and :func:`retained_text` turns them into the QC pack's material
(:class:`~pymedphys._dicom.deidentify.run_qc.RetainedText`).

UI is left out: a UID is kept only where the pinned tables register it,
which names no one, and the residual search already accounts for those
(D-027). A value that the walker cleans (C) or replaces is not retained; a
ROI Name that descriptor cleaning writes is the ROI name material's
(D-009). An element kept with no known VR, as for a private element in
implicit VR, cannot be read as text, and is left to the residual search's
own account.
"""

from __future__ import annotations

from collections.abc import Mapping

from pymedphys._imports import pydicom

from .file_layout import ElementPath
from .qc_pack import QcPackError
from .run_qc import RetainedText
from .walker import InstancePlan

# The VRs whose values are character strings that a reader could take as text.
RETAINED_TEXT_VRS = frozenset(
    {
        "AE",
        "AS",
        "CS",
        "DA",
        "DS",
        "DT",
        "IS",
        "LO",
        "LT",
        "PN",
        "SH",
        "ST",
        "TM",
        "UC",
        "UR",
        "UT",
    }
)


def retained_paths(plan: InstancePlan) -> tuple[ElementPath, ...]:
    """Return the paths of the elements whose values a plan retains, in file order.

    Parameters
    ----------
    plan : ~pymedphys._dicom.deidentify.walker.InstancePlan

    Returns
    -------
    tuple of ElementPath
        Each element planned K, neither a sequence nor removed with one,
        whose VR is in :data:`RETAINED_TEXT_VRS`.
    """
    if not isinstance(plan, InstancePlan):
        raise TypeError("plan must be an InstancePlan")
    return tuple(
        element.path
        for element in plan.elements
        if element.action == "K"
        and element.removed_with is None
        and element.removed_for is None
        and element.vr in RETAINED_TEXT_VRS
    )


def retained_text(
    plan: InstancePlan, values: Mapping[ElementPath, object]
) -> tuple[RetainedText, ...]:
    """Return the QC material of each string that a plan retains.

    Parameters
    ----------
    plan : ~pymedphys._dicom.deidentify.walker.InstancePlan
    values : mapping of ElementPath to object
        The decoded value of every path of :func:`retained_paths`: a string,
        a person name, or a sequence of them for a multi-valued element, or
        ``None`` for an empty one.

    Returns
    -------
    tuple of RetainedText
        One for each value that is not empty, splitting a multi-valued
        element into its values, in file order and then value order.

    Raises
    ------
    QcPackError
        If a path's value is missing, so that a retained string would go
        unreviewed, or is not text. The error names the path, never a value.
    """
    found: list[RetainedText] = []
    for path in retained_paths(plan):
        if path not in values:
            raise QcPackError(f"the retained value of {path} was not read for review")
        for value in _values(values[path], path):
            if value:
                found.append(RetainedText(value, path))
    return tuple(found)


def _values(value: object, path: ElementPath) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple, pydicom.multival.MultiValue)):
        return tuple(text for item in value for text in _values(item, path))
    if isinstance(
        value,
        (
            pydicom.valuerep.PersonName,
            pydicom.valuerep.IS,
            pydicom.valuerep.DSfloat,
            pydicom.valuerep.DSdecimal,
        ),
    ):
        # Each gives the text it was read from by str().
        return (str(value),)
    raise QcPackError(f"the retained value of {path} is not decoded text")
