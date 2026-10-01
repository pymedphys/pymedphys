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

"""The de-identification markers that every de-identified instance carries.

DICOM PS3.15 E.1.1 has a de-identifier record what it did in each instance,
and E.2 and E.3.6 say how the instance's dates were treated.
:func:`markers_for` gives the markers of one instance from its validated
policy, the policy digest, and the options that the instance's validated
result satisfies, and :func:`apply_markers` adds them to a copy of a data set
and changes nothing else in it:

- Patient Identity Removed (0012,0062) is YES under every policy, and never
  NO, replacing any value already present.
- De-identification Method (0012,0063) keeps the values already present and
  gains two: the policy digest as 64 lowercase hexadecimal digits, then a
  readable value, unless that pair is already present as two consecutive
  values, when it gains neither. The readable value is
  ``PyMedPhys <version>; PS3.15 <edition>; <preset>`` for a policy that can
  claim conformance, with ``custom option set`` in place of the preset for a
  custom option set, and ``PyMedPhys <version>; no PS3.15 claim; tps-import``
  for ``tps-import``, which claims none.
- De-identification Method Code Sequence (0012,0064) keeps the items already
  present and, for a policy that can claim conformance, gains the CID 7050
  codes of the Basic Profile and of each satisfied option, in Table E.1-1's
  order of options. Every selected option must be satisfied except Clean
  Descriptors, which is satisfied only by output whose retained descriptors
  have passed pooled human review, and otherwise goes unsatisfied because
  the Basic Profile's actions apply to the descriptors instead.
  A code is not added where an item already present has the same Code
  Value and Coding Scheme Designator, and the same Coding Scheme Version
  where either has one. ``tps-import`` adds no code, and the sequence is left
  out where it would have no item, since a present Type 1C sequence needs
  one.
- Longitudinal Temporal Information Modified (0028,0303) is MODIFIED where
  the policy applies Retain Longitudinal Temporal Information with Modified
  Dates, and otherwise REMOVED, or the value already present where that is
  stricter, in the order UNMODIFIED, MODIFIED, REMOVED. A value already
  present that is not one of these is refused.
- Contributing Equipment Sequence (0018,A001) keeps the items already present
  and, unless one of them has the same Manufacturer, Software Versions in the
  same order, and purpose of reference, gains one that names PyMedPhys as its
  Manufacturer (0008,0070), gives
  in Software Versions (0018,1020) PyMedPhys's full version and then the
  environment that the policy digest covers, and has DCM 109104
  "De-identifying Equipment" from CID 7005 as its Purpose of Reference Code
  Sequence (0040,A170). The environment is taken from
  :func:`~pymedphys._dicom.deidentify.policy_digest.environment` when the
  markers are computed, in its order: the Python implementation and version
  as one value, such as ``CPython 3.14.0``, then each library's name and
  version, ``pydicom <version>`` and ``tomlkit <version>``.

So output de-identified twice by the same release, policy, and environment
carries the markers of one run, and a run with another digest adds its own
pair of De-identification Method values.

Each value is checked against its VR and VM in the pinned data dictionary,
Patient Identity Removed is checked to be YES, and the first
De-identification Method value to be 64 lowercase hexadecimal digits, both
when :func:`markers_for` gives the markers and again when
:func:`apply_markers` writes them, so that markers changed in between, such
as with :func:`dataclasses.replace`, are refused before anything is written.
A value that does not fit is refused rather than shortened, and never written
without the version.

An attribute whose values have an odd length in all is padded with a
trailing space after its last value. PS3.5 Section 6.4 allows the last value
to exceed its VR's maximum length by that space, but pydicom checks each
value's length before it removes the padding, so it reads a last value of
the maximum length as too long: with a warning, or with an error under its
strict reading. The digest, which has the 64 characters that LO allows,
therefore comes before the readable value, and the readable value may have
at most 63 characters, so that output reads cleanly. With edition 2026d,
every version of up to 14 characters fits every preset's readable value.
For the same reason, the markers are refused wherever an attribute that
:func:`apply_markers` writes would end in a value of its VR's maximum length
and have an odd length in all, as Software Versions could, or
De-identification Method where another tool's value of that length follows a
pair already present.

The markers depend only on the policy, the digest, the satisfied options,
PyMedPhys's version, and the environment, never on the data set, so they
never quote a source value.
"""

from __future__ import annotations

import copy
import dataclasses
import functools
import re
import types
from collections.abc import Iterable, Iterator, MutableSequence, Sequence

from pymedphys import _version
from pymedphys._imports import pydicom

from . import policy_digest
from .codes import CodedConcept, load_context_group
from .policy import MODIFIED_DATES, Policy
from .standard import DictionaryAttribute, StandardTableError, load_data_dictionary
from .values import values_problem

MANUFACTURER = "PyMedPhys"
# The readable value's name for a policy without a preset. No preset's name
# contains a space, so it cannot be mistaken for one.
CUSTOM_OPTION_SET = "custom option set"
# Where a policy claims no conformance, its readable value says so in place of
# the edition.
NO_CONFORMANCE_CLAIM = "no PS3.15 claim"
# The Coding Scheme Designator of every code that the markers write.
DCM = "DCM"
# The CID 7050 code of the Basic Application Level Confidentiality Profile,
# and of each option that the design document's Scope targets.
PROFILE_CODE = "113100"
OPTION_CODES = types.MappingProxyType(
    {
        "retain_safe_private": "113111",
        "retain_device_identity": "113109",
        "retain_patient_characteristics": "113108",
        "retain_longitudinal_modified_dates": "113107",
        "clean_descriptors": "113105",
    }
)
# The CID 7005 code of De-identifying Equipment.
DEIDENTIFYING_EQUIPMENT = "109104"
# The values of Longitudinal Temporal Information Modified, from the least
# strict to the strictest.
TEMPORAL_VALUES = ("UNMODIFIED", "MODIFIED", "REMOVED")
# The one selected option that a policy claiming conformance can leave
# unsatisfied: the Basic Profile's actions then apply to the descriptors.
_CLEAN_DESCRIPTORS = "clean_descriptors"

_PATIENT_IDENTITY_REMOVED = "(0012,0062)"
_DEIDENTIFICATION_METHOD = "(0012,0063)"
_DEIDENTIFICATION_METHOD_CODES = "(0012,0064)"
_TEMPORAL_INFORMATION_MODIFIED = "(0028,0303)"
_CONTRIBUTING_EQUIPMENT = "(0018,A001)"
_MANUFACTURER = "(0008,0070)"
_SOFTWARE_VERSIONS = "(0018,1020)"
_PURPOSE_OF_REFERENCE = "(0040,A170)"
_CODE_VALUE = "(0008,0100)"
_CODING_SCHEME_DESIGNATOR = "(0008,0102)"
_CODE_MEANING = "(0008,0104)"
_CODING_SCHEME_VERSION = "(0008,0103)"

_DIGEST = re.compile(r"[0-9a-f]{64}")
# The maximum length of a value of each VR that the markers write, in
# characters (PS3.5 Table 6.2-1). Each is even, so padding can follow a value
# of the maximum length only in an attribute of more than one value.
_MAXIMUM_LENGTHS = types.MappingProxyType({"CS": 16, "LO": 64, "SH": 16})
# The readable value is the last of the two De-identification Method values
# that the markers add, so it leaves room for the padding that can follow it.
_READABLE_LENGTH = _MAXIMUM_LENGTHS["LO"] - 1

# The names that policy_digest.environment gives the Python implementation and
# version, which Software Versions records as one value, and the end of the
# name it gives each library's version.
_PYTHON_IMPLEMENTATION = "platform.python_implementation"
_PYTHON_VERSION = "platform.python_version"
_LIBRARY_VERSION = ".__version__"


class MarkerError(ValueError):
    """The markers cannot be written as valid values.

    For example, PyMedPhys's version may make the readable value of
    De-identification Method longer than LO allows. The message names each
    attribute and what is wrong, without quoting a value.
    """


@dataclasses.dataclass(frozen=True)
class Markers:
    """The markers that one de-identified instance carries.

    Attributes
    ----------
    patient_identity_removed : str
        Patient Identity Removed (0012,0062): ``"YES"``.
    method : tuple of str
        The two values added to De-identification Method (0012,0063): the
        policy digest, then the readable value.
    method_codes : tuple of CodedConcept
        The items added to De-identification Method Code Sequence
        (0012,0064): the Basic Profile's code and each satisfied option's,
        or none for a policy that claims no conformance.
    temporal_information_modified : str
        Longitudinal Temporal Information Modified (0028,0303):
        ``"MODIFIED"`` or ``"REMOVED"``.
    manufacturer : str
        Manufacturer (0008,0070) in the Contributing Equipment Sequence item:
        ``"PyMedPhys"``.
    software_versions : tuple of str
        The values of Software Versions (0018,1020) in that item: PyMedPhys's
        full version, then the environment that the policy digest covers, the
        Python implementation and version as one value, such as
        ``"CPython 3.14.0"``, then ``"pydicom <version>"`` and
        ``"tomlkit <version>"``.
    purpose_of_reference : CodedConcept
        The item's Purpose of Reference Code Sequence (0040,A170) item: DCM
        109104 "De-identifying Equipment".
    """

    patient_identity_removed: str
    method: tuple[str, str]
    method_codes: tuple[CodedConcept, ...]
    temporal_information_modified: str
    manufacturer: str
    software_versions: tuple[str, ...]
    purpose_of_reference: CodedConcept


@functools.cache
def _dictionary() -> dict[str, DictionaryAttribute]:
    return {entry.tag: entry for entry in load_data_dictionary().attributes}


def _code(cid: int, value: str) -> CodedConcept:
    """Return a DCM code from the pinned context group, as published."""
    for row in load_context_group(cid).rows:
        if row.scheme_designator == DCM and row.code_value == value:
            return row
    raise StandardTableError(f"CID {cid} has no code {DCM} {value}")


def _environment_versions() -> tuple[str, ...]:
    """Return the environment that the policy digest covers, as Software Versions.

    The Python implementation and version make one value, such as
    ``"CPython 3.14.0"``, followed by each library's name and version, such
    as ``"pydicom 3.0.2"``, in the order that the environment gives them.
    """
    covered = dict(policy_digest.environment())
    implementation = covered.pop(_PYTHON_IMPLEMENTATION, None)
    python = covered.pop(_PYTHON_VERSION, None)
    unknown = [name for name in covered if not name.endswith(_LIBRARY_VERSION)]
    problems = []
    if implementation is None or python is None:
        problems.append("it gives no Python implementation and version")
    if unknown:
        problems.append(
            f"it gives {', '.join(unknown)}, which is neither the Python "
            "implementation or version nor a library's version"
        )
    if problems:
        raise MarkerError(
            f"Software Versions {_SOFTWARE_VERSIONS} cannot record the "
            "environment that the policy digest covers: " + "; ".join(problems)
        )
    libraries = (
        f"{name.removesuffix(_LIBRARY_VERSION)} {version}"
        for name, version in covered.items()
    )
    return (f"{implementation} {python}", *libraries)


def _satisfied(policy: Policy, satisfied: Iterable[str]) -> tuple[str, ...]:
    """Return the satisfied options in the policy's order, after checking them.

    Under a policy that can claim conformance, every selected option but
    Clean Descriptors must be satisfied, so that the codes name each option
    whose actions the instance carries. An option that the policy records as
    unmet is never required.
    """
    if isinstance(satisfied, str):
        raise TypeError(
            "satisfied must be a collection of option names, not a single string"
        )
    chosen = set(satisfied)
    unselected = sorted(chosen.difference(policy.options))
    if unselected:
        raise ValueError(
            f"the policy does not select {', '.join(unselected)}, "
            "so no instance can satisfy it"
        )
    unmet = {option for resolution in policy.resolved for option in resolution.unmet}
    missing = [
        option
        for option in policy.options
        if option not in chosen and option != _CLEAN_DESCRIPTORS and option not in unmet
    ]
    if policy.claims_conformance and missing:
        raise ValueError(
            f"satisfied leaves out {', '.join(missing)}, which the policy "
            f"selects; only {_CLEAN_DESCRIPTORS} can go unsatisfied, since the "
            "Basic Profile's actions then apply to the descriptors"
        )
    return tuple(option for option in policy.options if option in chosen)


def _code_elements(code: CodedConcept) -> Iterator[tuple[str, Sequence[str]]]:
    yield _CODE_VALUE, [code.code_value]
    yield _CODING_SCHEME_DESIGNATOR, [code.scheme_designator]
    yield _CODE_MEANING, [code.code_meaning]


def _check_digest(digest: object) -> None:
    """Check the policy digest's form, without quoting it."""
    if not isinstance(digest, str):
        raise TypeError("the policy digest must be text")
    if not _DIGEST.fullmatch(digest):
        raise ValueError("the policy digest must be 64 lowercase hexadecimal digits")


def _padding_problem(vr: str, given: Sequence[str]) -> str | None:
    """Return what is wrong if the padding would make the last value too long.

    Values whose length in all, counting the backslash between each two, is
    odd are padded with a trailing space after the last value (PS3.5 Section
    6.4). pydicom checks each value's length before it removes the padding,
    so it reads a last value of the VR's maximum length as too long. Lengths
    are counted in characters, which in the Default Character Repertoire are
    also bytes.
    """
    length = sum(len(value) for value in given) + len(given) - 1
    if given and length % 2 and len(given[-1]) == _MAXIMUM_LENGTHS[vr]:
        return (
            "would have an odd length and end in a value of as many characters "
            f"as VR {vr} allows, which pydicom reads with the padding as too long"
        )
    return None


def _check(found: Markers) -> None:
    """Check the markers as they are to be written, and report each problem.

    De-identification Method must gain two values, the first a policy
    digest and the second a readable value of at most 63 characters;
    Patient Identity Removed must be YES; every value must fit its VR and
    VM; and no attribute may end in a value that the padding would make
    too long.
    """
    if len(found.method) != 2:
        raise MarkerError(
            "the de-identification markers cannot be written: "
            f"De-identification Method {_DEIDENTIFICATION_METHOD} must gain two "
            "values, the policy digest and the readable value"
        )
    digest, readable = found.method
    _check_digest(digest)
    problems = []
    if found.patient_identity_removed != "YES":
        name = _dictionary()[_PATIENT_IDENTITY_REMOVED].name
        problems.append(f"{name} {_PATIENT_IDENTITY_REMOVED} is not YES")
    if found.temporal_information_modified not in TEMPORAL_VALUES:
        name = _dictionary()[_TEMPORAL_INFORMATION_MODIFIED].name
        problems.append(
            f"{name} {_TEMPORAL_INFORMATION_MODIFIED} is not "
            f"{', '.join(TEMPORAL_VALUES[:-1])}, or {TEMPORAL_VALUES[-1]}"
        )
    elements = [
        (_PATIENT_IDENTITY_REMOVED, [found.patient_identity_removed]),
        (_DEIDENTIFICATION_METHOD, found.method),
        (_TEMPORAL_INFORMATION_MODIFIED, [found.temporal_information_modified]),
        (_MANUFACTURER, [found.manufacturer]),
        (_SOFTWARE_VERSIONS, found.software_versions),
    ]
    for code in (*found.method_codes, found.purpose_of_reference):
        elements.extend(_code_elements(code))
    for tag, given in elements:
        attribute = _dictionary()[tag]
        problem = values_problem(attribute.vr, attribute.vm, given)
        if (
            not problem
            and tag == _DEIDENTIFICATION_METHOD
            and len(readable) > _READABLE_LENGTH
        ):
            problem = (
                f"has a readable value longer than {_READABLE_LENGTH} characters, "
                "which leaves no room for the padding that can follow it"
            )
        problem = problem or _padding_problem(attribute.vr, given)
        if problem:
            problems.append(f"{attribute.name} {tag} {problem}")
    if problems:
        raise MarkerError(
            "the de-identification markers cannot be written: " + "; ".join(problems)
        )


def markers_for(policy: Policy, digest: str, *, satisfied: Iterable[str]) -> Markers:
    """Return the markers of one instance de-identified under a policy.

    The environment in Software Versions is taken from
    :func:`~pymedphys._dicom.deidentify.policy_digest.environment` at this
    call, so it is the environment that the policy digest covers when both
    are computed in the same process.

    Parameters
    ----------
    policy : Policy
        The instance's validated policy, such as one from
        :func:`~pymedphys._dicom.deidentify.policy.compose_policy`.
    digest : str
        The policy digest,
        :func:`~pymedphys._dicom.deidentify.policy_digest.policy_digest` of
        the policy and the vocabulary that descriptor cleaning used.
    satisfied : iterable of str
        The policy's options that the instance's validated result satisfies,
        whose codes a policy that can claim conformance adds. Such a policy
        must have every selected option satisfied except Clean Descriptors,
        which is satisfied only by output whose retained descriptors have
        passed pooled human review; an instance that applies the Basic
        Profile's actions to its descriptors instead does not satisfy it.
        ``tps-import``, which claims no conformance and adds no codes, needs
        none satisfied, and never the Retain Device Identity that it records
        as unmet.

    Returns
    -------
    Markers

    Raises
    ------
    TypeError
        If ``policy`` is not a
        :class:`~pymedphys._dicom.deidentify.policy.Policy`, ``digest`` is
        not text, or ``satisfied`` is a single string rather than a
        collection of names.
    ValueError
        If ``digest`` is not 64 lowercase hexadecimal digits; if
        ``satisfied`` names an option that the policy does not select, or,
        under a policy that can claim conformance, leaves out a selected
        option other than Clean Descriptors, in which case the message names
        each option left out; or if the policy selects an option without a
        CID 7050 code here, which a validated policy never does. The message
        does not quote the digest.
    MarkerError
        If the policy resolves a conflict between options by keeping the
        value, so that Patient Identity Removed could be neither YES nor NO;
        if a value does not fit its VR or VM, such as a library version too
        long for a Software Versions value; if the readable value is longer
        than 63 characters; if an attribute would have an odd length and end
        in a value of its VR's maximum length, which pydicom reads with the
        padding as too long; or if the environment that the policy digest
        covers lacks the Python implementation and version, or gives
        anything else that is not a library's version.
    ~pymedphys._dicom.deidentify.standard.StandardTableError
        If a pinned context group lacks a code that the markers write.

    Examples
    --------
    >>> from pymedphys._dicom.deidentify.policy import compose_policy
    >>> from pymedphys._dicom.deidentify.policy_digest import policy_digest
    >>> policy = compose_policy("basic-clean-descriptors")
    >>> digest = policy_digest(policy, vocabulary=None)
    >>> found = markers_for(policy, digest, satisfied=["clean_descriptors"])
    >>> found.method[0] == digest
    True
    >>> found.method[1].split("; ")[1:]
    ['PS3.15 2026d', 'basic-clean-descriptors']
    >>> [(code.code_value, code.code_meaning) for code in found.method_codes]
    [('113100', 'Basic Application Confidentiality Profile'), ('113105', 'Clean Descriptors Option')]
    """
    if not isinstance(policy, Policy):
        raise TypeError("policy must be a Policy")
    _check_digest(digest)
    uncoded = [option for option in policy.options if option not in OPTION_CODES]
    if uncoded:
        raise ValueError(
            f"the options {', '.join(uncoded)} have no code here; "
            f"the options with codes are {', '.join(OPTION_CODES)}"
        )
    if any(resolution.action == "K" for resolution in policy.resolved):
        raise MarkerError(
            "the policy keeps a value that a selected option modifies, so "
            "Patient Identity Removed can be set to neither YES nor NO"
        )
    options = _satisfied(policy, satisfied)

    version = _version.__version__
    name = CUSTOM_OPTION_SET if policy.preset is None else policy.preset
    if policy.claims_conformance:
        claim = f"PS3.15 {policy.edition}"
        method_codes = tuple(
            _code(7050, code)
            for code in (PROFILE_CODE, *(OPTION_CODES[o] for o in options))
        )
    else:
        claim, method_codes = NO_CONFORMANCE_CLAIM, ()
    found = Markers(
        patient_identity_removed="YES",
        method=(digest, f"{MANUFACTURER} {version}; {claim}; {name}"),
        method_codes=method_codes,
        temporal_information_modified=(
            "MODIFIED" if MODIFIED_DATES in policy.options else "REMOVED"
        ),
        manufacturer=MANUFACTURER,
        software_versions=(version, *_environment_versions()),
        purpose_of_reference=_code(7005, DEIDENTIFYING_EQUIPMENT),
    )
    _check(found)
    return found


def _int_tag(tag: str) -> int:
    return int(tag[1:5] + tag[6:10], 16)


def _existing(dataset: pydicom.Dataset, tag: str) -> list:
    """Return an attribute's values or items, to be kept before the markers'.

    pydicom can give an attribute added as UN its dictionary VR while leaving
    its value as bytes, so the values themselves are checked too.
    """
    element = dataset.get(_int_tag(tag))
    if element is None or element.VM == 0:
        return []
    attribute = _dictionary()[tag]
    value = element.value
    # A MultiValue or a Sequence; neither text nor bytes is mutable.
    kept = list(value) if isinstance(value, MutableSequence) else [value]
    kind = pydicom.Dataset if attribute.vr == "SQ" else str
    if element.VR != attribute.vr or not all(isinstance(v, kind) for v in kept):
        raise MarkerError(
            f"{attribute.name} {tag} is not read as VR {attribute.vr}, "
            "so its values cannot be kept or compared"
        )
    return kept


def _values_of(item: pydicom.Dataset, tag: str) -> tuple:
    """Return an attribute's values or items in an item, to compare them."""
    element = item.get(_int_tag(tag))
    if element is None or element.VM == 0:
        return ()
    value = element.value
    return tuple(value) if isinstance(value, MutableSequence) else (value,)


def _code_key(item: pydicom.Dataset) -> tuple:
    """Return what makes a code item the same code as another.

    Its Code Value and Coding Scheme Designator, and its Coding Scheme
    Version, which two items share only where neither has one or both have
    the same.
    """
    return tuple(
        _values_of(item, tag)
        for tag in (_CODE_VALUE, _CODING_SCHEME_DESIGNATOR, _CODING_SCHEME_VERSION)
    )


def _equipment_key(item: pydicom.Dataset) -> tuple:
    """Return what makes a Contributing Equipment Sequence item equal another.

    Its Manufacturer, its Software Versions in order, and the Code Value and
    Coding Scheme Designator of each purpose of reference.
    """
    purposes = tuple(
        (_values_of(code, _CODE_VALUE), _values_of(code, _CODING_SCHEME_DESIGNATOR))
        for code in _values_of(item, _PURPOSE_OF_REFERENCE)
    )
    return (
        _values_of(item, _MANUFACTURER),
        _values_of(item, _SOFTWARE_VERSIONS),
        purposes,
    )


def _stricter_temporal(dataset: pydicom.Dataset, given: str) -> str:
    """Return the stricter of the value already present and ``given``."""
    present = _existing(dataset, _TEMPORAL_INFORMATION_MODIFIED)
    if not present:
        return given
    # _existing has checked that each value is text.
    value = str(present[0]).strip(" ") if len(present) == 1 else ""
    if value not in TEMPORAL_VALUES:
        name = _dictionary()[_TEMPORAL_INFORMATION_MODIFIED].name
        raise MarkerError(
            f"{name} {_TEMPORAL_INFORMATION_MODIFIED} already holds something "
            f"other than one of {', '.join(TEMPORAL_VALUES[:-1])}, or "
            f"{TEMPORAL_VALUES[-1]}, so the stricter of it and the markers' "
            "value cannot be told"
        )
    return max(value, given, key=TEMPORAL_VALUES.index)


def _set(dataset: pydicom.Dataset, tag: str, given: list) -> None:
    """Set an attribute to ``given``, with its VR from the pinned dictionary.

    pydicom stores a list of one value as that value.
    """
    dataset.add_new(_int_tag(tag), _dictionary()[tag].vr, given)


def _code_item(code: CodedConcept) -> pydicom.Dataset:
    item = pydicom.Dataset()
    for tag, given in _code_elements(code):
        _set(item, tag, list(given))
    return item


def apply_markers(dataset: pydicom.Dataset, markers: Markers) -> pydicom.Dataset:
    """Return a copy of a data set with the markers added, and nothing else changed.

    Patient Identity Removed replaces any value already present.
    De-identification Method, De-identification Method Code Sequence, and
    Contributing Equipment Sequence keep their values and items, and the
    markers' follow them, apart from any already present: the digest and
    readable value are added only where that pair is not already present as
    two consecutive values; a code only where no item already present has the
    same Code Value and Coding Scheme Designator, and the same Coding Scheme
    Version where either has one; and the equipment item only where no item
    already present has the same Manufacturer, the same Software Versions in
    the same order, and the same purpose of reference, by its Code Value and
    Coding Scheme Designator. Longitudinal Temporal Information Modified
    becomes the stricter of the value already present and the markers', in
    the order of :data:`TEMPORAL_VALUES`, so that it never returns towards a
    less strict state; an empty value counts as absent. A De-identification
    Method Code Sequence that would have no item, as under ``tps-import``
    where none was present, is left out, since the Patient Module makes it
    Type 1C and so, where present, it needs one.

    Parameters
    ----------
    dataset : pydicom.Dataset
        The data set after every other action of the policy. It is not
        changed.
    markers : Markers
        From :func:`markers_for`. They are checked again as
        :func:`markers_for` checks them, before anything is written, since
        they can be changed after it gives them, such as with
        :func:`dataclasses.replace`.

    Returns
    -------
    pydicom.Dataset
        A deep copy of ``dataset``, with the markers.

    Raises
    ------
    TypeError
        If ``dataset`` is not a :class:`pydicom.Dataset`, ``markers`` is not
        :class:`Markers`, or the policy digest in ``markers`` is not text.
    ValueError
        If the policy digest in ``markers`` is not 64 lowercase hexadecimal
        digits. The message does not quote it.
    MarkerError
        If ``markers`` sets Patient Identity Removed to anything but YES or
        Longitudinal Temporal Information Modified to anything but one of
        :data:`TEMPORAL_VALUES`, does not add exactly two De-identification
        Method values, has a value that does not fit its VR or VM, or has a
        readable value longer than 63 characters; if an attribute it writes
        would have an odd length and end in a value of its VR's maximum
        length, which pydicom reads with the padding as too long, as
        De-identification Method would where a value as long as LO allows
        follows a pair already present; if an attribute whose values are
        kept or compared has values but another VR than the pinned
        dictionary gives it, such as UN, so that keeping them could lose or
        misread them; or if Longitudinal Temporal Information Modified
        already holds something other than one of :data:`TEMPORAL_VALUES`,
        so that the stricter value cannot be told. The message does not
        quote the values.
    """
    if not isinstance(dataset, pydicom.Dataset):
        raise TypeError("dataset must be a pydicom Dataset")
    if not isinstance(markers, Markers):
        raise TypeError("markers must be Markers, from markers_for")
    _check(markers)
    marked = copy.deepcopy(dataset)
    method = _existing(marked, _DEIDENTIFICATION_METHOD)
    method_codes = _existing(marked, _DEIDENTIFICATION_METHOD_CODES)
    equipment_items = _existing(marked, _CONTRIBUTING_EQUIPMENT)
    temporal = _stricter_temporal(marked, markers.temporal_information_modified)

    pair = list(markers.method)
    if not any(method[i : i + 2] == pair for i in range(len(method) - 1)):
        method.extend(pair)
    # _check has checked the markers' own values, but a value already present
    # can end De-identification Method, after a pair already present.
    attribute = _dictionary()[_DEIDENTIFICATION_METHOD]
    problem = _padding_problem(attribute.vr, method)
    if problem:
        raise MarkerError(
            "the de-identification markers cannot be written: "
            f"{attribute.name} {_DEIDENTIFICATION_METHOD} {problem}"
        )
    present_codes = [_code_key(item) for item in method_codes]
    for item in map(_code_item, markers.method_codes):
        if _code_key(item) not in present_codes:
            method_codes.append(item)
            present_codes.append(_code_key(item))
    equipment = pydicom.Dataset()
    _set(equipment, _MANUFACTURER, [markers.manufacturer])
    _set(equipment, _SOFTWARE_VERSIONS, list(markers.software_versions))
    _set(equipment, _PURPOSE_OF_REFERENCE, [_code_item(markers.purpose_of_reference)])
    if all(
        _equipment_key(item) != _equipment_key(equipment) for item in equipment_items
    ):
        equipment_items.append(equipment)

    _set(marked, _PATIENT_IDENTITY_REMOVED, [markers.patient_identity_removed])
    _set(marked, _DEIDENTIFICATION_METHOD, method)
    if method_codes:
        _set(marked, _DEIDENTIFICATION_METHOD_CODES, method_codes)
    else:
        # Type 1C in the Patient Module, so where present it needs an item.
        marked.pop(_int_tag(_DEIDENTIFICATION_METHOD_CODES), None)
    _set(marked, _TEMPORAL_INFORMATION_MODIFIED, [temporal])
    _set(marked, _CONTRIBUTING_EQUIPMENT, equipment_items)
    return marked
