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

"""The UIDs that a policy keeps, and how the engine names and checks them.

Under the Retain UIDs Option, "UIDs shall be retained, as described in Table
E.1-1" (PS3.15 E.3.9), which gives K to 60 attributes under it: 55 UIDs,
such as SOP Instance UID (0008,0018), Study Instance UID (0020,000D), and
Referenced SOP Instance UID (0008,1155), and five sequences that hold
references, such as Referenced Image Sequence (0008,1140), which are kept as
containers whose items' elements take their own rules. Retain Device
Identity gives K to Device UID (0018,1002) and Manufacturer's Device Class
UID (0018,100B) in the same way. The policy's actions keep each such UID
where it stands, and every other UID is replaced as before, with the run's
key, so a UID that the table does not list under the option, such as
Multi-frame Source SOP Instance UID (0008,1167), or Table E.1-1's own UID
(0040,A124), is still replaced (D-040).

What follows from keeping a UID is decided here, so that the transform
applies it without knowing which option keeps it:

- :func:`retained_uid_tags` gives the tags of the UIDs that a policy keeps:
  each attribute of Table E.1-1 to which it gives K, and which the data
  dictionary gives VR UI, or which the dictionary leaves out but the table
  names as a UID, as it does Media Storage SOP Instance UID (0002,0003),
  Referenced SOP Instance UID in File (0004,1511), and two attributes of the
  command group, which the engine removes from a data set whatever the
  policy gives them.
- :func:`retained_uid_paths` gives each element of an instance that holds
  one of those UIDs and is still collected for the residual search, which
  happens only where the element is removed with an enclosing sequence or by
  the engine's own removals. The search leaves it out (D-027), since the
  option discloses that UID wherever it is kept.
- :func:`output_name_uid` gives the UID that names an output file: a
  replacement UID as it is written, and a kept UID by its keyed replacement,
  so that every file is named as under the Basic Profile, by a ``2.25.`` UID
  of a name-based UUID, with no source UID in its path (D-016).

The reference graph's second pass takes the same tags, and expects an
input's own UID at an identity or reference site whose attribute the policy
keeps
(:func:`~pymedphys._dicom.deidentify.written_references.verify_written_references`).
"""

from __future__ import annotations

from collections.abc import Iterable

from .file_layout import ElementPath
from .keys import DeidKey
from .policy import Policy
from .standard import PRIVATE_ATTRIBUTES_TAG, dictionary_attribute, load_table_e1_1
from .uids import replacement_uid
from .walker import Consumer, ElementPlan

KEEP = "K"
UI = "UI"


def retained_uid_tags(policy: Policy) -> frozenset[str]:
    """Return the tags of the UIDs that ``policy`` keeps where they stand.

    Parameters
    ----------
    policy : Policy
        A policy composed from the pinned Table E.1-1.

    Returns
    -------
    frozenset of str
        The tag of each attribute of Table E.1-1 to which ``policy`` gives K
        and which holds UIDs: one that the pinned data dictionary gives VR
        UI, or, for an attribute of group 0000, 0002, or 0004, which the
        dictionary leaves out, one whose name in the table has ``UID`` as a
        word. Empty for the Basic Profile alone.

    Examples
    --------
    >>> from pymedphys._dicom.deidentify.policy import compose_custom_policy
    >>> tags = retained_uid_tags(compose_custom_policy(["retain_uids"]))
    >>> len(tags), "(0008,0018)" in tags, "(0008,1140)" in tags
    (55, True, False)
    """
    names = {row.tag: row.name for row in load_table_e1_1().attributes}
    return frozenset(
        tag
        for tag, action in policy.actions.items()
        if action == KEEP and tag != PRIVATE_ATTRIBUTES_TAG and _holds_uids(tag, names)
    )


def _holds_uids(tag: str, names: dict[str, str]) -> bool:
    if "x" in tag:  # a masked tag, such as (60xx,4000), which holds no UID
        return False
    attribute = dictionary_attribute(tag)
    if attribute is not None:
        return attribute.vrs == (UI,)
    return tag[1:5] in ("0000", "0002", "0004") and "UID" in names[tag].split()


def retained_uid_paths(
    elements: Iterable[ElementPlan], retained: frozenset[str]
) -> frozenset[ElementPath]:
    """Return each element collected for the residual search that holds a kept UID.

    Parameters
    ----------
    elements : iterable of ElementPlan
        An instance's plan's elements.
    retained : frozenset of str
        The tags of the UIDs that the policy keeps, from
        :func:`retained_uid_tags`.

    Returns
    -------
    frozenset of ElementPath
        Each element read as VR UI, at one of ``retained``, that the plan
        collects for the residual search: one removed with an enclosing
        sequence, or by the engine's own removals, since the policy keeps
        the attribute everywhere else.
    """
    return frozenset(
        element.path
        for element in elements
        if element.path.tag in retained
        and element.vr == UI
        and Consumer.RESIDUAL_COLLECTION in element.consumers
    )


def output_name_uid(key: DeidKey, written: str, retained: bool) -> str:
    """Return the UID that names an output file for one of its identifiers.

    Parameters
    ----------
    key : DeidKey
        The run's key.
    written : str
        The instance's Study, Series, or SOP Instance UID as it is written.
    retained : bool
        Whether the policy keeps that UID.

    Returns
    -------
    str
        ``written`` where it is a replacement, and otherwise its keyed
        replacement, which is the same as the Basic Profile would write and
        name the file by under the same key.
    """
    return replacement_uid(key, written) if retained else written
