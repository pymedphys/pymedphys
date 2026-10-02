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

"""The release report's record of the method and the runtime environment.

Each de-identification run is to write a release report: a record of what
was done that can be distributed with the output, so it contains no source
attribute value, original path, or key. This module gives the parts of it
that do not depend on the instances of a run:

- ``policy``: the PS3.15 edition, the preset (None for a custom option set),
  the selected options, and whether the policy can claim conformance;
- ``method``: the method digest that each instance records in
  De-identification Method (0012,0063), with the components it is computed
  from, so that two digests can be compared component by component
  (:class:`~pymedphys._dicom.deidentify.method_digest.MethodDigestComponents`);
- ``runtime``: the PyMedPhys, Python, pydicom, and tomlkit versions that ran,
  the same values that Software Versions (0018,1020) of the de-identifying
  equipment records
  (:class:`~pymedphys._dicom.deidentify.runtime.RuntimeEnvironment`).

:func:`report_document` gives a report as JSON values, and :func:`to_json`
as text; each first checks that every field has the form of a digest, a
version, a known edition, preset, or option, or a file name or path within
the engine's package. Every field is built from the policy, the engine's own
files, and the versions that run it, never from DICOM data, and the check is
a backstop: a field of another form, which could be a source value or a path
outside the package, is refused. A field that fails is named, never quoted.

Two sections describe a run's instances, by attribute tags and reason codes
that the engine defines, never by a value or a path:

- ``sequestered``: each instance that was sequestered, by a label that
  :func:`sequestration_labels` gives at random for the run, with each
  reason (D-026). A sequestered instance has no output name, and the label
  holds nothing of the instance or its place in the run; only the
  confidential QC pack maps labels to sources (D-016).
- ``search_coverage``: how many source values of each attribute the
  residual search did not search, in full or in part, by reason (D-027),
  from :func:`search_coverage`. The QC pack lists each by instance and
  place.

The residual search's findings, and the stage that sequesters an instance
for them, are to follow.
"""

from __future__ import annotations

import collections
import dataclasses
import json
import random
import re
import secrets
from collections.abc import Iterable, Mapping

from pymedphys._nomenclature import tg263

from . import method_digest
from .method_digest import MethodDigestComponents
from .file_layout import TAG_PATTERN, ElementPath
from .policy import PRESETS, Policy
from .reference_graph import FindingKind
from .residuals import NotSearched, Omission, Unsearched, UnsearchedReason
from .runtime import RuntimeEnvironment, runtime_environment
from .scope import Disposition
from .source import SourceReason
from .standard import OPTIONS, VRS
from .walker import Sequestration, SequesterReason

# The format of the report document. A change to its fields takes a new label.
FORMAT = "pymedphys-deid-release-report/2"

_DIGEST = re.compile(r"[0-9a-f]{64}")
_EDITION = re.compile(r"[0-9]{4}[a-z]")
# A version, or a Python implementation's name: no space, separator, or
# other character that a path or a person's name would need.
_VERSION = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+!_-]{0,63}")
# A file name within the package, which never starts with "." (so is never
# ".." or a cache), and a table, which is a JSON file of the tables' folder.
_NAME = re.compile(r"[0-9A-Za-z_][0-9A-Za-z_.-]*")
_TABLE = re.compile(r"[0-9A-Za-z_][0-9A-Za-z_.-]*\.json")
# The form of a sequestered instance's label, which the QC pack maps.
LABEL_PATTERN = re.compile(r"S-[0-9]{4,}")
_ATTRIBUTE = re.compile(rf"{TAG_PATTERN.pattern}( > {TAG_PATTERN.pattern})*")
_ACTIONS = frozenset({"K", "X", "Z", "D", "U", "C"})

# The reason codes of each stage that sequesters an instance.
_SEQUESTERING = {
    "scope": frozenset(d.value for d in Disposition) - {Disposition.SUPPORTED.value},
    "admission": frozenset(r.value for r in SourceReason),
    "references": frozenset(
        {
            FindingKind.CONFLICTING_INSTANCE.value,
            FindingKind.SERIES_IN_SEVERAL_STUDIES.value,
        }
    ),
    "walker": frozenset(r.value for r in SequesterReason),
}


class ReleaseReportError(ValueError):
    """A release report has a field that could hold a value or a path.

    The message names the field, never its value.
    """


@dataclasses.dataclass(frozen=True)
class PolicyRecord:
    """The policy that a release report records.

    Attributes
    ----------
    preset : str or None
        The preset, such as ``"basic"``, or None for a custom option set.
    edition : str
        The edition of PS3.15 Table E.1-1, such as ``"2026d"``.
    options : tuple of str
        The selected options, in the table's order.
    claims_conformance : bool
        Whether the policy can claim PS3.15 conformance, which it cannot
        when it leaves a selected option's action unapplied, as
        ``tps-import`` does.
    """

    preset: str | None
    edition: str
    options: tuple[str, ...]
    claims_conformance: bool


@dataclasses.dataclass(frozen=True)
class SequestrationReason:
    """Why an instance was sequestered, by codes that the engine defines.

    Attributes
    ----------
    stage : str
        What sequestered it: ``"scope"``, ``"admission"`` (a source file
        refused, which is set aside like any sequestered instance),
        ``"references"`` (the first pass's reference graph), or
        ``"walker"``.
    code : str
        The stage's reason code, such as ``"conflicting-instance"``.
    attribute : str or None
        For the walker, and only for it, the attribute's tags from the
        outermost sequence, without items, such as
        ``"(0010,1002) > (0010,0020)"``.
    action : str or None
        For the walker, and only for it, the action at that place, such as
        ``"D"``.
    vr : str or None
        For the walker, the VR that the action met, if known; None for every
        other stage.
    """

    stage: str
    code: str
    attribute: str | None = None
    action: str | None = None
    vr: str | None = None


@dataclasses.dataclass(frozen=True)
class SequesteredInstance:
    """An instance that was sequestered, as a release report names it (D-026).

    Attributes
    ----------
    label : str
        Its label for the run, from :func:`sequestration_labels`.
    reasons : tuple of SequestrationReason
    """

    label: str
    reasons: tuple[SequestrationReason, ...]


@dataclasses.dataclass(frozen=True)
class SearchCoverage:
    """How many source values of an attribute were not searched, and why.

    Attributes
    ----------
    attribute : str
        The attribute's tags from the outermost sequence, without items.
    reason : str
        An :class:`~pymedphys._dicom.deidentify.residuals.Omission` or an
        :class:`~pymedphys._dicom.deidentify.residuals.UnsearchedReason`, as
        its value, such as ``"too-short"``.
    count : int
    """

    attribute: str
    reason: str
    count: int


@dataclasses.dataclass(frozen=True)
class ReleaseReport:
    """A release report's record of the method, the runtime, and the run.

    Attributes
    ----------
    policy : PolicyRecord
    method : ~pymedphys._dicom.deidentify.method_digest.MethodDigestComponents
    runtime : ~pymedphys._dicom.deidentify.runtime.RuntimeEnvironment
    sequestered : tuple of SequesteredInstance
    search_coverage : tuple of SearchCoverage
    """

    policy: PolicyRecord
    method: MethodDigestComponents
    runtime: RuntimeEnvironment
    sequestered: tuple[SequesteredInstance, ...] = ()
    search_coverage: tuple[SearchCoverage, ...] = ()


def attribute_tags(path: ElementPath) -> str:
    """Return an element's tags from the outermost sequence, without items.

    >>> attribute_tags(ElementPath((("(0010,1002)", 3),), "(0010,0020)"))
    '(0010,1002) > (0010,0020)'
    """
    return " > ".join([*(tag for tag, _ in path.items), path.tag])


def sequestration_reason(
    cause: Disposition | SourceReason | FindingKind | Sequestration,
) -> SequestrationReason:
    """Return the reason that a stage gives for sequestering an instance.

    Raises
    ------
    ValueError
        For a disposition or finding that does not sequester an instance:
        :attr:`~.scope.Disposition.SUPPORTED`; a dangling reference or an
        identical duplicate, which are reported only; a missing identifier,
        whose handling is not yet decided; or a study with several patients,
        which stops the run instead.
    TypeError
        For anything else.
    """
    if isinstance(cause, Sequestration):
        return SequestrationReason(
            "walker",
            cause.reason.value,
            attribute_tags(cause.path),
            cause.action,
            cause.vr,
        )
    stages = {
        Disposition: "scope",
        SourceReason: "admission",
        FindingKind: "references",
    }
    stage = stages.get(type(cause))  # type: ignore[arg-type]
    if stage is None:
        raise TypeError("a reason must come from a stage that sequesters instances")
    if cause.value not in _SEQUESTERING[stage]:
        raise ValueError(f"{type(cause).__name__}.{cause.name} does not sequester")
    return SequestrationReason(stage, cause.value)


def sequestration_labels(
    count: int, *, rng: random.Random | None = None
) -> tuple[str, ...]:
    """Return a label for each of ``count`` sequestered instances, at random.

    The labels are ``S-0001`` to ``S-n``, all with the same number of
    digits, at least four, given in an order drawn from ``rng``, by default the
    operating system's source of randomness, so that a label says nothing
    of an instance or of its place in the run (D-026). Only the QC pack maps
    labels to sources.
    """
    labels = _labels(count)
    (rng or secrets.SystemRandom()).shuffle(labels)
    return tuple(labels)


def _labels(count: int) -> list[str]:
    width = max(4, len(str(count)))
    return [f"S-{number:0{width}d}" for number in range(1, count + 1)]


def search_coverage(
    instances: Iterable[Iterable[NotSearched | Unsearched]],
) -> tuple[SearchCoverage, ...]:
    """Count the values not searched by attribute and reason (D-027).

    ``instances`` holds, for each instance, its records of what the
    residual search did not search. A source value counts once for each
    reason, however many of its forms or spellings that reason left out,
    since a :class:`~pymedphys._dicom.deidentify.residuals.NotSearched`
    names one form of a value at its place, and an
    :class:`~pymedphys._dicom.deidentify.residuals.Unsearched` a whole
    value. Values at the same place in different instances count apart.
    The counts are in the order of their attributes and reasons.

    >>> from pymedphys._dicom.deidentify.residuals import (
    ...     Unsearched, UnsearchedReason)
    >>> place = ElementPath((), "(0010,0020)")
    >>> retained = Unsearched(place, UnsearchedReason.RETAINED)
    >>> search_coverage([[retained, retained], [retained]])
    (SearchCoverage(attribute='(0010,0020)', reason='retained', count=2),)
    """
    counts: collections.Counter[tuple[str, str]] = collections.Counter()
    for records in instances:
        if isinstance(records, (NotSearched, Unsearched)):
            raise TypeError("records must be given for each instance")
        places = set()
        for record in records:
            if not isinstance(record, (NotSearched, Unsearched)):
                raise TypeError("a record must be NotSearched or Unsearched")
            places.add((record.source, record.reason.value))
        for source, reason in places:
            counts[attribute_tags(source), reason] += 1
    return tuple(
        SearchCoverage(attribute, reason, count)
        for (attribute, reason), count in sorted(counts.items())
    )


def release_report(
    policy: Policy,
    *,
    vocabulary: tg263.Nomenclature | None,
    sequestered: Iterable[SequesteredInstance] = (),
    coverage: Iterable[SearchCoverage] = (),
) -> ReleaseReport:
    """Return the release report of a policy, its method, the runtime, and a run.

    Parameters
    ----------
    policy : Policy
        A validated policy, such as one from
        :func:`~pymedphys._dicom.deidentify.policy.compose_policy`.
    vocabulary : ~pymedphys._nomenclature.tg263.Nomenclature or None
        The TG-263 vocabulary that descriptor cleaning matches ROI Names
        against, or None without one. It must be given by name, and has no
        default, so that every caller states whether there is one. The
        report records only its content digest.
    sequestered : iterable of SequesteredInstance, optional
        The run's sequestered instances.
    coverage : iterable of SearchCoverage, optional
        How many values the run's residual search did not search, from
        :func:`search_coverage`.

    Returns
    -------
    ReleaseReport

    Raises
    ------
    TypeError, ValueError
        For any reason
        :func:`~pymedphys._dicom.deidentify.method_digest.method_digest_components`
        gives.

    Examples
    --------
    >>> from pymedphys._dicom.deidentify.policy import compose_policy
    >>> report = release_report(compose_policy("basic"), vocabulary=None)
    >>> report.policy.preset, report.policy.options
    ('basic', ())
    >>> list(report_document(report))
    ['format', 'policy', 'method', 'runtime', 'sequestered', 'search_coverage']
    """
    if not isinstance(policy, Policy):
        raise TypeError("policy must be a Policy")
    return ReleaseReport(
        policy=PolicyRecord(
            preset=policy.preset,
            edition=policy.edition,
            options=tuple(policy.options),
            claims_conformance=policy.claims_conformance,
        ),
        method=method_digest.method_digest_components(policy, vocabulary=vocabulary),
        runtime=runtime_environment(),
        sequestered=tuple(sequestered),
        search_coverage=tuple(coverage),
    )


def _refuse(field: str, problem: str) -> ReleaseReportError:
    return ReleaseReportError(f"the release report's {field} {problem}")


def _matches(pattern: re.Pattern, value: object) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _digest(field: str, value: object) -> str:
    if not _matches(_DIGEST, value):
        raise _refuse(field, "is not 64 lowercase hexadecimal digits")
    return str(value)


def _optional_digest(field: str, value: object) -> str | None:
    return None if value is None else _digest(field, value)


def _version(field: str, value: object) -> str:
    if not _matches(_VERSION, value):
        raise _refuse(field, "is not a version")
    return str(value)


def _package_path(value: object) -> bool:
    return isinstance(value, str) and all(
        _NAME.fullmatch(part) for part in value.split("/")
    )


def _digests(field: str, value: object, name: re.Pattern | None) -> dict[str, str]:
    """Return a mapping of names or package paths to digests, sorted by name."""
    if not isinstance(value, Mapping):
        raise _refuse(field, "is not a mapping")
    for key in value:
        if not (_matches(name, key) if name else _package_path(key)):
            raise _refuse(field, "has a name that is not within the package")
    return {key: _digest(field, value[key]) for key in sorted(value)}


def _policy_section(record: PolicyRecord) -> dict:
    if record.preset is not None and not (
        isinstance(record.preset, str) and record.preset in PRESETS
    ):
        raise _refuse("preset", "is not a preset")
    if not _matches(_EDITION, record.edition):
        raise _refuse("edition", "is not an edition")
    if not isinstance(record.options, tuple) or any(
        option not in OPTIONS for option in record.options
    ):
        raise _refuse("options", "are not PS3.15 options")
    if not isinstance(record.claims_conformance, bool):
        raise _refuse("claims_conformance", "is not true or false")
    return {
        "preset": record.preset,
        "edition": record.edition,
        "options": list(record.options),
        "claims_conformance": record.claims_conformance,
    }


def _method_section(method: MethodDigestComponents) -> dict:
    if method.method_digest_format != method_digest.FORMAT:
        raise _refuse("method_digest_format", "is not the method digest's format")
    return {
        "method_digest": _digest("method_digest", method.method_digest),
        "method_digest_format": method.method_digest_format,
        "engine_version": _version("engine_version", method.engine_version),
        "table_digests": _digests("table_digests", method.table_digests, _TABLE),
        "l2_rules_digest": _digest("l2_rules_digest", method.l2_rules_digest),
        "l3_rules": _optional_digest("l3_rules", method.l3_rules),
        "vocabulary_digest": _optional_digest(
            "vocabulary_digest", method.vocabulary_digest
        ),
        "generated_values_digest": _digest(
            "generated_values_digest", method.generated_values_digest
        ),
        "engine_files": _digests("engine_files", method.engine_files, None),
    }


def _runtime_section(environment: RuntimeEnvironment) -> dict:
    return {
        field.name: _version(field.name, getattr(environment, field.name))
        for field in dataclasses.fields(environment)
    }


def _string(value: object) -> str | None:
    # A str subclass could carry anything in its methods or attributes, so
    # only a str itself is written, as the value that was checked.
    return value if type(value) is str else None  # pylint: disable=unidiomatic-typecheck


def _code(field: str, value: object, codes: Iterable[str]) -> str:
    text = _string(value)
    if text is None or text not in frozenset(codes):
        raise _refuse(field, "is not a code that the engine defines")
    return text


def _attribute(field: str, value: object) -> str:
    text = _string(value)
    if text is None or _ATTRIBUTE.fullmatch(text) is None:
        raise _refuse(field, "is not a path of tags")
    return text


def _reason_entry(reason: object) -> dict:
    if not isinstance(reason, SequestrationReason):
        raise _refuse("sequestered reasons", "are not a tuple of reasons")
    stage = _code("sequestered stage", reason.stage, _SEQUESTERING)
    code = _code("sequestered code", reason.code, _SEQUESTERING[stage])
    if stage != "walker":
        if (reason.attribute, reason.action, reason.vr) != (None, None, None):
            raise _refuse("sequestered attribute", "is given for another stage")
        return {"stage": stage, "code": code}
    return {
        "stage": stage,
        "code": code,
        "attribute": _attribute("sequestered attribute", reason.attribute),
        "action": _code("sequestered action", reason.action, _ACTIONS),
        "vr": None if reason.vr is None else _code("sequestered vr", reason.vr, VRS),
    }


def _sequestered_section(instances: tuple[SequesteredInstance, ...]) -> list:
    if not all(isinstance(each, SequesteredInstance) for each in instances):
        raise _refuse("sequestered", "is not a tuple of sequestered instances")
    labels = {_string(instance.label) for instance in instances}
    if labels != set(_labels(len(instances))):
        raise _refuse("sequestered label", "are not the labels S-0001 to S-n")
    entries = []
    for instance in sorted(instances, key=lambda each: each.label):
        if not (isinstance(instance.reasons, tuple) and instance.reasons):
            raise _refuse("sequestered reasons", "are not a tuple of reasons")
        reasons: list[dict] = []
        for reason in instance.reasons:
            entry = _reason_entry(reason)
            if entry not in reasons:
                reasons.append(entry)
        entries.append({"label": instance.label, "reasons": reasons})
    return entries


_UNSEARCHED = frozenset(
    {*(o.value for o in Omission), *(r.value for r in UnsearchedReason)}
)


def _coverage_section(coverage: tuple[SearchCoverage, ...]) -> list:
    entries = []
    for each in coverage:
        if not isinstance(each, SearchCoverage):
            raise _refuse("search_coverage", "is not a tuple of coverage counts")
        if not (isinstance(each.count, int) and not isinstance(each.count, bool)):
            raise _refuse("search_coverage count", "is not a whole number")
        if each.count < 1:
            raise _refuse("search_coverage count", "is not positive")
        entries.append(
            {
                "attribute": _attribute("search_coverage attribute", each.attribute),
                "reason": _code("search_coverage reason", each.reason, _UNSEARCHED),
                "count": each.count,
            }
        )
    return sorted(entries, key=lambda entry: (entry["attribute"], entry["reason"]))


def report_document(report: ReleaseReport) -> dict:
    """Return a release report as JSON values, after checking every field.

    The document is an object with the members ``format`` (:data:`FORMAT`),
    ``policy``, ``method``, ``runtime``, ``sequestered``, and
    ``search_coverage``, in that order, each section's fields in the order
    of its class, the digests of tables and files sorted by name, the
    sequestered instances by label, each with its reasons once, in the
    order given, and the coverage by attribute and reason. A reason from a
    stage other than the walker has only its stage and code.

    Parameters
    ----------
    report : ReleaseReport

    Returns
    -------
    dict

    Raises
    ------
    ReleaseReportError
        If a field does not have the form of a digest, a version, a known
        edition, preset, or option, a file name or path within the engine's
        package, one of the labels ``S-0001`` to ``S-n`` for ``n``
        sequestered instances, a path of tags, a code that the engine
        defines, or a positive count, or is not of its class. The message names the field, never its value.
    """
    return {
        "format": FORMAT,
        "policy": _policy_section(report.policy),
        "method": _method_section(report.method),
        "runtime": _runtime_section(report.runtime),
        "sequestered": _sequestered_section(report.sequestered),
        "search_coverage": _coverage_section(report.search_coverage),
    }


def to_json(report: ReleaseReport) -> str:
    """Return a release report as JSON text, after checking every field.

    The text is :func:`report_document` indented by two spaces, with
    characters outside ASCII written as themselves and a final newline, so
    the same report always gives the same text.

    Parameters
    ----------
    report : ReleaseReport

    Returns
    -------
    str

    Raises
    ------
    ReleaseReportError
        For any reason :func:`report_document` gives.
    """
    return json.dumps(report_document(report), indent=2, ensure_ascii=False) + "\n"
