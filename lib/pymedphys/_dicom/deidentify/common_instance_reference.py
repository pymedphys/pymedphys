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

"""Decide when the Common Instance Reference Module's sequences lapse.

The Common Instance Reference Module (PS3.3 Section C.12.2) describes "the
hierarchical relationships of any SOP Instances referenced from other
Modules" of the instance. Its two sequences are Type 1C: Referenced Series
Sequence (0008,1115), "Required if this Instance references Instances in
this Study", and Studies Containing Other Referenced Instances Sequence
(0008,1200), "Required if this Instance references Instances in other
Studies". Neither says "May be present otherwise", so PS3.5 Section 7.4.2
does not allow either once its condition fails. Every IOD of the first
supported release includes the module as user-optional.

Table E.1-1 lists neither sequence, so the engine keeps them, with their
UIDs replaced. It can remove every other reference that an instance
holds, such as Referenced Image Sequence (0008,1140) and Source Image
Sequence (0008,2112), whose X/Z/U* removes them where they are Type 3. Where
no reference to an instance remains outside the module, neither condition
holds, so both sequences are removed, with their items. Where one remains,
both are kept: telling a reference to an instance of this study from one to
an instance of another study needs the UIDs' values, and the engine decides
its actions from the data set's structure alone.

A reference to an instance is a Referenced SOP Instance UID (0008,1155) or
Multi-frame Source SOP Instance UID (0008,1167) with a value, in an item of
any sequence but the module's own. Referenced SOP Instance UID in an item of
Referenced Study Sequence (0008,1110) or RT Referenced Study Sequence
(3006,0012) names a study, not an instance, so it is not one
(:data:`~pymedphys._dicom.deidentify.references.STUDY_SEQUENCES`).

This module reads only the paths of elements, never a value.

Examples
--------
>>> from pymedphys._dicom.deidentify.file_layout import ElementPath
>>> plan_reference = ElementPath((("(300C,0060)", 0),), "(0008,1155)")
>>> is_instance_reference(plan_reference)
True
>>> listed = ElementPath(
...     (("(0008,1115)", 0), ("(0008,114A)", 0)), "(0008,1155)"
... )
>>> is_instance_reference(listed)
False
>>> is_common_instance_reference(ElementPath((), "(0008,1115)"))
True
"""

from __future__ import annotations

from .file_layout import ElementPath
from .references import STUDY_SEQUENCES

# Referenced Series Sequence and Studies Containing Other Referenced
# Instances Sequence, at the top level of the data set.
SEQUENCES = frozenset({"(0008,1115)", "(0008,1200)"})
# Referenced SOP Instance UID and Multi-frame Source SOP Instance UID.
INSTANCE_REFERENCE_TAGS = frozenset({"(0008,1155)", "(0008,1167)"})


def is_common_instance_reference(path: ElementPath) -> bool:
    """Return whether ``path`` is one of the module's two sequences.

    Parameters
    ----------
    path : ElementPath
        An element's place in the data set.

    Returns
    -------
    bool
        ``True`` for Referenced Series Sequence (0008,1115) or Studies
        Containing Other Referenced Instances Sequence (0008,1200) at the
        top level of the data set, where the module defines them; the same
        tags within another sequence's items, as in the Hierarchical SOP
        Instance Reference Macro, are not the module's.
    """
    return not path.items and path.tag in SEQUENCES


def is_instance_reference(path: ElementPath) -> bool:
    """Return whether an element at ``path`` would reference an instance.

    Parameters
    ----------
    path : ElementPath
        An element's place in the data set.

    Returns
    -------
    bool
        ``True`` for Referenced SOP Instance UID (0008,1155) or Multi-frame
        Source SOP Instance UID (0008,1167) in an item of a sequence, unless
        the item is within one of the module's two sequences, or the
        innermost sequence is one whose items name a study. Whether the
        element has a value is for the caller to check.
    """
    return (
        path.tag in INSTANCE_REFERENCE_TAGS
        and bool(path.items)
        and path.items[0][0] not in SEQUENCES
        and path.items[-1][0] not in STUDY_SEQUENCES
    )
