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

"""The reviewed cleaners that settle C for the attributes an option names.

Table E.1-1 gives C, "clean, that is replace with values of similar meaning
known not to contain identifying information and consistent with the VR"
(Table E.1-1a), to attributes under several options, and the edits leave
each such attribute pending (D-009). A :class:`Cleaner` settles them for one
option: it names the option, the attributes it cleans by tag, the VRs it
reads them in, and its method, which the conformance statement gives. Each
cleaner's method is in a module of its own, and :data:`CLEANERS` lists every
cleaner, so an option is given a cleaner here, without changing the
transform (D-034):

- Retain Device Identity's eleven attributes of VR AE become keyed tokens
  (:mod:`~pymedphys._dicom.deidentify.ae_titles`).

:class:`~pymedphys._dicom.deidentify.instance_transform.InstanceTransform`
applies the cleaners of the options its policy selects to each instance's
edits, by :func:`apply_cleaners`, before descriptor cleaning. An attribute
given C that no cleaner settles stays pending. Under Clean Descriptors,
descriptor cleaning gives it the action that the policy gives it without
that option, where that action is not C (D-009); otherwise the instance is
sequestered, since writing it with the option's code would claim a retention
that did not happen (D-011), and writing it without the code would claim
that the Basic Profile removed values that the option keeps (D-012).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence

from . import ae_titles
from .edits import EditKind, InstanceEdits
from .file_layout import ElementPath
from .keys import DeidKey
from .policy import DEVICE_IDENTITY, Policy


@dataclasses.dataclass(frozen=True)
class Cleaner:
    """How one option's attributes given C are cleaned.

    Attributes
    ----------
    option : str
        The option whose attributes it cleans, such as
        ``"retain_device_identity"``; it cleans them only under a policy that
        selects the option.
    tags : frozenset of str
        The attributes it cleans, by their tags in Table E.1-1, wherever they
        are in the data set.
    vrs : frozenset of str
        The VRs that it reads them in. A value read in another VR is not
        cleaned.
    method : str
        How it cleans them, as the conformance statement gives it: one or
        more sentences, naming no value.
    clean : callable
        Given an attribute's decoded source values, separated by
        backslashes, and the run's key, returns the values that replace them,
        ``()`` for an attribute written with no value.
    retains : bool
        Whether a value that it writes may be the source's own, so that the
        residual search leaves the source value out (D-027), as it does a
        ROI Name that descriptor cleaning keeps.
    """

    option: str
    tags: frozenset[str]
    vrs: frozenset[str]
    method: str
    clean: Callable[[str, DeidKey], tuple[str, ...]] = dataclasses.field(repr=False)
    retains: bool = False


# Every cleaner, by the order of its option in Table E.1-1. No two clean the
# same attribute.
CLEANERS: tuple[Cleaner, ...] = (
    Cleaner(
        option=DEVICE_IDENTITY,
        tags=ae_titles.TAGS,
        vrs=ae_titles.VRS,
        method=(
            "Each value becomes a token of the run's key, of 16 characters, the "
            "most that VR AE allows: `AE` followed by the first 14 characters "
            "of the base32 encoding of the value's HMAC-SHA256 in a domain of "
            "its own, once its leading and trailing spaces are removed. Within "
            "a run, an application entity therefore has the same token in "
            "every attribute and instance, and different entities have "
            "different tokens; across runs, tokens are unrelated. An empty "
            "value stays empty."
        ),
        clean=ae_titles.ae_tokens,
    ),
)


@dataclasses.dataclass(frozen=True)
class Cleaned:
    """An instance's edits with the attributes that its cleaners clean settled.

    Attributes
    ----------
    edits : InstanceEdits
        The edits, with each attribute that a cleaner cleans replaced, or
        emptied where it has no value, and every other edit as it was.
    retained : frozenset of ElementPath
        The attributes written by a cleaner that may write a value that is
        the source's own, which the residual search leaves out.
    """

    edits: InstanceEdits
    retained: frozenset[ElementPath] = frozenset()


def cleaners_for(policy: Policy) -> tuple[Cleaner, ...]:
    """Return the cleaners of the options that ``policy`` selects."""
    return tuple(cleaner for cleaner in CLEANERS if cleaner.option in policy.options)


def apply_cleaners(
    edits: InstanceEdits, cleaners: Sequence[Cleaner], key: DeidKey
) -> Cleaned:
    """Settle each pending C of one instance that one of ``cleaners`` cleans.

    Parameters
    ----------
    edits : InstanceEdits
        The instance's edits, with none sequestering it.
    cleaners : sequence of Cleaner
        Those of the run's policy, :func:`cleaners_for` it.
    key : DeidKey
        The run's key.

    Returns
    -------
    Cleaned
        With each edit that a cleaner settles replaced. An attribute stays
        pending where its value was not collected for the residual search,
        is bytes, or was read in a VR that its cleaner does not read.
    """
    by_tag = {tag: cleaner for cleaner in cleaners for tag in cleaner.tags}
    if not by_tag:
        return Cleaned(edits)
    sources = {value.source: value for value in edits.source_values}
    settled = {}
    retained = set()
    for edit in edits.edits:
        cleaner = by_tag.get(edit.path.tag)
        if cleaner is None or edit.kind is not EditKind.PENDING or edit.action != "C":
            continue
        source = sources.get(edit.path)
        if (
            source is None
            or source.vr not in cleaner.vrs
            or not isinstance(source.value, str)
        ):
            continue
        values = cleaner.clean(source.value, key)
        kind = EditKind.REPLACE if values else EditKind.EMPTY
        settled[edit.path] = dataclasses.replace(edit, kind=kind, values=values)
        if cleaner.retains:
            retained.add(edit.path)
    return Cleaned(
        dataclasses.replace(
            edits, edits=tuple(settled.get(edit.path, edit) for edit in edits.edits)
        ),
        frozenset(retained),
    )
