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
  gains two: a readable value, and the policy digest as 64 lowercase
  hexadecimal digits. The readable value is
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
  ``tps-import`` adds no code, and the sequence is left out where it would
  have no item, since a present Type 1C sequence needs one.
- Longitudinal Temporal Information Modified (0028,0303) is MODIFIED where
  the policy applies Retain Longitudinal Temporal Information with Modified
  Dates, and otherwise REMOVED, replacing any value already present.
- Contributing Equipment Sequence (0018,A001) keeps the items already present
  and gains one that names PyMedPhys as its Manufacturer (0008,0070), gives
  PyMedPhys's full version in Software Versions (0018,1020), and has DCM
  109104 "De-identifying Equipment" from CID 7005 as its Purpose of Reference
  Code Sequence (0040,A170).

Each value is checked against its VR and VM in the pinned data dictionary
before it is written. A value that does not fit, such as a readable value
longer than the 64 characters of LO, is refused rather than shortened, and
never written without the version. With edition 2026d, every version of up
to 15 characters fits every preset's readable value.

The markers depend only on the policy, the digest, the satisfied options, and
PyMedPhys's version, never on the data set, so they never quote a source
value.
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

_DIGEST = re.compile(r"[0-9a-f]{64}")


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
        readable value, then the policy digest.
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
    software_versions : str
        Software Versions (0018,1020) in that item: PyMedPhys's full version.
    purpose_of_reference : CodedConcept
        The item's Purpose of Reference Code Sequence (0040,A170) item: DCM
        109104 "De-identifying Equipment".
    """

    patient_identity_removed: str
    method: tuple[str, str]
    method_codes: tuple[CodedConcept, ...]
    temporal_information_modified: str
    manufacturer: str
    software_versions: str
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


def _check(found: Markers) -> None:
    """Check every value against its VR and VM, and report each one that fails."""
    elements = [
        (_PATIENT_IDENTITY_REMOVED, [found.patient_identity_removed]),
        (_DEIDENTIFICATION_METHOD, found.method),
        (_TEMPORAL_INFORMATION_MODIFIED, [found.temporal_information_modified]),
        (_MANUFACTURER, [found.manufacturer]),
        (_SOFTWARE_VERSIONS, [found.software_versions]),
    ]
    for code in (*found.method_codes, found.purpose_of_reference):
        elements.extend(_code_elements(code))
    problems = []
    for tag, given in elements:
        attribute = _dictionary()[tag]
        problem = values_problem(attribute.vr, attribute.vm, given)
        if problem:
            problems.append(f"{attribute.name} {tag} {problem}")
    if problems:
        raise MarkerError(
            "the de-identification markers cannot be written: " + "; ".join(problems)
        )


def markers_for(policy: Policy, digest: str, *, satisfied: Iterable[str]) -> Markers:
    """Return the markers of one instance de-identified under a policy.

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
        value, so that Patient Identity Removed could be neither YES nor NO,
        or if a value does not fit its VR or VM, such as a readable value
        longer than 64 characters.
    ~pymedphys._dicom.deidentify.standard.StandardTableError
        If a pinned context group lacks a code that the markers write.

    Examples
    --------
    >>> from pymedphys._dicom.deidentify.policy import compose_policy
    >>> from pymedphys._dicom.deidentify.policy_digest import policy_digest
    >>> policy = compose_policy("basic-clean-descriptors")
    >>> found = markers_for(
    ...     policy, policy_digest(policy), satisfied=["clean_descriptors"]
    ... )
    >>> found.method[0].split("; ")[1:]
    ['PS3.15 2026d', 'basic-clean-descriptors']
    >>> [(code.code_value, code.code_meaning) for code in found.method_codes]
    [('113100', 'Basic Application Confidentiality Profile'), ('113105', 'Clean Descriptors Option')]
    """
    if not isinstance(policy, Policy):
        raise TypeError("policy must be a Policy")
    if not isinstance(digest, str):
        raise TypeError("the policy digest must be text")
    if not _DIGEST.fullmatch(digest):
        raise ValueError("the policy digest must be 64 lowercase hexadecimal digits")
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
        method=(f"{MANUFACTURER} {version}; {claim}; {name}", digest),
        method_codes=method_codes,
        temporal_information_modified=(
            "MODIFIED" if MODIFIED_DATES in policy.options else "REMOVED"
        ),
        manufacturer=MANUFACTURER,
        software_versions=version,
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
            "so its values cannot be kept"
        )
    return kept


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

    Patient Identity Removed and Longitudinal Temporal Information Modified
    replace any value already present. De-identification Method, De-
    identification Method Code Sequence, and Contributing Equipment Sequence
    keep their values and items, and the markers' follow them. A
    De-identification Method Code Sequence that would have no item, as under
    ``tps-import`` where none was present, is left out, since the Patient
    Module makes it Type 1C and so, where present, it needs one.

    Parameters
    ----------
    dataset : pydicom.Dataset
        The data set after every other action of the policy. It is not
        changed.
    markers : Markers
        From :func:`markers_for`.

    Returns
    -------
    pydicom.Dataset
        A deep copy of ``dataset``, with the markers.

    Raises
    ------
    TypeError
        If ``dataset`` is not a :class:`pydicom.Dataset` or ``markers`` is
        not :class:`Markers`.
    MarkerError
        If an attribute whose values are kept has values but another VR than
        the pinned dictionary gives it, such as UN, so that keeping them
        could lose or misread them. The message does not quote them.
    """
    if not isinstance(dataset, pydicom.Dataset):
        raise TypeError("dataset must be a pydicom Dataset")
    if not isinstance(markers, Markers):
        raise TypeError("markers must be Markers, from markers_for")
    marked = copy.deepcopy(dataset)
    method = _existing(marked, _DEIDENTIFICATION_METHOD)
    method_codes = _existing(marked, _DEIDENTIFICATION_METHOD_CODES)
    equipment_items = _existing(marked, _CONTRIBUTING_EQUIPMENT)

    equipment = pydicom.Dataset()
    _set(equipment, _MANUFACTURER, [markers.manufacturer])
    _set(equipment, _SOFTWARE_VERSIONS, [markers.software_versions])
    _set(equipment, _PURPOSE_OF_REFERENCE, [_code_item(markers.purpose_of_reference)])
    _set(marked, _PATIENT_IDENTITY_REMOVED, [markers.patient_identity_removed])
    _set(marked, _DEIDENTIFICATION_METHOD, [*method, *markers.method])
    method_codes.extend(map(_code_item, markers.method_codes))
    if method_codes:
        _set(marked, _DEIDENTIFICATION_METHOD_CODES, method_codes)
    else:
        # Type 1C in the Patient Module, so where present it needs an item.
        marked.pop(_int_tag(_DEIDENTIFICATION_METHOD_CODES), None)
    _set(
        marked, _TEMPORAL_INFORMATION_MODIFIED, [markers.temporal_information_modified]
    )
    _set(marked, _CONTRIBUTING_EQUIPMENT, [*equipment_items, equipment])
    return marked
