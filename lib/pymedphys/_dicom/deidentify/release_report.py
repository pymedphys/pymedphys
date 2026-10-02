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
files, the versions that run it, and the keyed digest of the reviewed-names
list, never from DICOM data directly, and the check is a backstop: a field of another form, which could be a source value or a path
outside the package, is refused. A field that fails is named, never quoted.

The sections that describe a run's instances, such as residual search
findings and sequestered instances, are to follow.
"""

from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Mapping

from pymedphys._nomenclature import tg263

from . import method_digest
from .method_digest import MethodDigestComponents
from .policy import PRESETS, Policy
from .runtime import RuntimeEnvironment, runtime_environment
from .standard import OPTIONS

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
class ReleaseReport:
    """The parts of a release report that do not depend on a run's instances.

    Attributes
    ----------
    policy : PolicyRecord
    method : ~pymedphys._dicom.deidentify.method_digest.MethodDigestComponents
    runtime : ~pymedphys._dicom.deidentify.runtime.RuntimeEnvironment
    """

    policy: PolicyRecord
    method: MethodDigestComponents
    runtime: RuntimeEnvironment


def release_report(
    policy: Policy,
    *,
    vocabulary: tg263.Nomenclature | None,
    reviewed_roi_names: str | None = None,
) -> ReleaseReport:
    """Return the release report's record of a policy, its method, and the runtime.

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
    reviewed_roi_names : str or None, optional
        The keyed digest of the reviewed-names list whose decisions
        descriptor cleaning applies to ROI Names, or None, the default,
        without a list. It must be given by name. The report records only
        this digest.

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
    ['format', 'policy', 'method', 'runtime']
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
        method=method_digest.method_digest_components(
            policy, vocabulary=vocabulary, reviewed_roi_names=reviewed_roi_names
        ),
        runtime=runtime_environment(),
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
        "reviewed_roi_names": _optional_digest(
            "reviewed_roi_names", method.reviewed_roi_names
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


def report_document(report: ReleaseReport) -> dict:
    """Return a release report as JSON values, after checking every field.

    The document is an object with the members ``format`` (:data:`FORMAT`),
    ``policy``, ``method``, and ``runtime``, in that order, each section's
    fields in the order of its class, and the digests of tables and files
    sorted by name.

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
        edition, preset, or option, or a file name or path within the
        engine's package. The message names the field, never its value.
    """
    return {
        "format": FORMAT,
        "policy": _policy_section(report.policy),
        "method": _method_section(report.method),
        "runtime": _runtime_section(report.runtime),
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
