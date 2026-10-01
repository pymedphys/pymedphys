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

"""The policy digest, which identifies a policy and the engine that applies it.

Every preset will add the digest to De-identification Method (0012,0063) of
each instance it de-identifies, as exactly 64 lowercase hexadecimal digits, so
that a file can be traced to the policy and the engine that produced it.
:func:`policy_digest` gives the SHA-256 of a canonical form
(:func:`canonical_bytes`) of the policy, of everything the engine could
apply, whether or not the policy's options use it, and of the versions of
Python and of the libraries that the engine imports:

- PyMedPhys's version;
- the content digest of every generated table in ``_standard/``, which must
  match the digest the table records;
- every supplementary (L2) rule: the UID roles, the temporal roles, the
  supplementary actions, and the action for a text attribute that no rule
  covers;
- every validated user (L3) rule. There are none yet, so the canonical form
  records their absence, and adding them will change every digest;
- the content digest of the entries of the TG-263 vocabulary that descriptor
  cleaning matches ROI Names against, which the vocabulary file also records,
  or the absence of a vocabulary;
- the parameters of generated values: the derivation version and domains of
  keyed values, the root and namespace of replacement UIDs, the prefix, family
  name, and code length of patient pseudonyms, the range of date offsets and
  the nominal UTC offset, and the constants of dummy values;
- the engine's source and rule files: every ``.py``, ``.toml``, and ``.json``
  file of this package, at any depth. These are its modules; its rule files,
  and the requirements register beside them; and its generated tables. Each
  is read as bytes, with CRLF line endings normalised to LF, so a Windows
  checkout gives each file the same digest. ``__pycache__`` and names that
  start with ``.``, such as the caches that tools write, are left out.
  Development builds and editable installs share a version across commits,
  so these files identify their code where the version cannot. They and the
  generated tables are read once per process, when the first digest is
  computed, and stand for the engine as first read in the process: every
  instance of a run carries the same digest, and an edit to an editable
  install after that is not seen until the process restarts;
- the Python implementation and version, such as ``CPython`` and
  ``3.14.0``, and the version of each third-party library that this package
  imports: pydicom, which will read and write every DICOM file, and tomlkit,
  which reads the rule files.

The digest therefore also changes when something the policy does not use
changes, which is harmless; it never stays the same when one of these inputs
changes, with the files and tables as first read in the process. It does not
cover the operating system, compiled libraries, third-party libraries that
this package does not import itself, or the code of a development install of
pydicom, which keeps its version across commits.
"""

from __future__ import annotations

import dataclasses
import enum
import functools
import hashlib
import json
import pathlib
import platform
import types
import uuid
from collections.abc import Callable, Mapping
from typing import Any

from pymedphys._imports import pydicom, tomlkit

from pymedphys import _version
from pymedphys._nomenclature import tg263

from . import (
    dates,
    dummy_values,
    keys,
    pseudonyms,
    standard,
    supplementary_actions,
    temporal_roles,
    uid_roles,
    uids,
)
from .policy import Policy

# The format of the canonical form. A change to the form takes a new label.
FORMAT = "pymedphys-deid-policy-digest/1"
# The engine's package, whose source and rule files the digest covers.
PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
COVERED_SUFFIXES = frozenset({".py", ".toml", ".json"})
# The parameters of generated values, by module, which the digest names as
# "<module>.<name>", such as "dates.MIN_OFFSET_WEEKS".
GENERATED_VALUE_PARAMETERS: tuple[tuple[types.ModuleType, tuple[str, ...]], ...] = (
    (keys, ("DERIVATION_VERSION", "DOMAINS")),
    (uids, ("UID_ROOT", "UID_NAMESPACE")),
    (pseudonyms, ("PATIENT_ID_PREFIX", "FAMILY_NAME", "CODE_BYTES")),
    (dates, ("MIN_OFFSET_WEEKS", "MAX_OFFSET_WEEKS", "NOMINAL_UTC_OFFSET")),
    (dummy_values, ("CONSTANTS",)),
)

# How a scalar parameter of generated values is written: its type's tag, and
# its value as JSON. A boolean, which Python counts as an integer, has none.
_SCALARS: tuple[tuple[type, str, Callable[[Any], str | int]], ...] = (
    (str, "str", str),
    (int, "int", int),
    (float, "float", float.hex),
    (bytes, "bytes", bytes.hex),
    (uuid.UUID, "uuid", str),
)


@dataclasses.dataclass(frozen=True)
class DigestInputs:
    """Everything the policy digest covers apart from the policy.

    :func:`digest_inputs` gathers them from the engine.

    Attributes
    ----------
    engine_version : str
        PyMedPhys's version, such as ``"0.42.0"``.
    tables : Mapping of str to str
        The content digest of each generated table, by file name, such as
        ``"e1_1.json"``.
    l2_rules : Mapping of str to object
        Each supplementary rule file as loaded, by file name, such as
        ``"uid_roles.toml"``, and the action for a text attribute that no
        rule covers, as ``"supplementary_actions.UNCOVERED_TEXT_ACTION"``.
    vocabulary : str or None
        The content digest of the vocabulary's entries, or None without a
        vocabulary.
    generated_values : Mapping of str to object
        Each parameter of generated values, by module and name, such as
        ``"dates.MIN_OFFSET_WEEKS"``.
    files : Mapping of str to str
        The SHA-256 of each source and rule file, with CRLF line endings read
        as LF, by its path within the package, such as ``"policy.py"`` or
        ``"_standard/e1_1.json"``.
    environment : Mapping of str to object
        The Python implementation and version, and the version of each
        third-party library that the package imports, by where each comes
        from, such as ``"platform.python_version"`` or
        ``"pydicom.__version__"``.
    """

    engine_version: str
    # Mappings are not hashable, so they are left out of the hash.
    tables: Mapping[str, str] = dataclasses.field(hash=False)
    l2_rules: Mapping[str, object] = dataclasses.field(hash=False)
    vocabulary: str | None
    generated_values: Mapping[str, object] = dataclasses.field(hash=False)
    files: Mapping[str, str] = dataclasses.field(hash=False)
    environment: Mapping[str, object] = dataclasses.field(hash=False)


def _encode(value: object) -> bytes:
    """Return ``value`` as canonical JSON, without quoting text it cannot encode."""
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    try:
        return text.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError(
            "an input of the policy digest has text that cannot be encoded as UTF-8"
        ) from None


def _key(key: object) -> str:
    if not isinstance(key, str):
        raise TypeError("a mapping in the policy digest has a key that is not text")
    return key


def _no_form(value: object) -> TypeError:
    return TypeError(f"a {type(value).__name__} has no canonical form")


def _plain(value: object) -> object:
    """Return ``value`` as JSON values, rejecting a type without a canonical form.

    A dataclass becomes an object of its fields, a mapping an object, a tuple
    or list an array in its order, and an enumeration member its value. Text,
    integers, booleans, and None are kept.
    """
    if isinstance(value, enum.Enum):
        return _plain(value.value)
    if value is None or isinstance(value, (str, int)):
        return value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: _plain(getattr(value, f.name)) for f in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {_key(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    raise _no_form(value)


def _typed(value: object) -> list:
    """Return a parameter of generated values as a ``[type, value]`` pair.

    Parameters have different types, such as ``"0"``, ``0``, and ``0.0`` for
    the dummy values of DS, US, and FL, so each value carries its type.
    """
    if not isinstance(value, bool):
        for kind, tag, text in _SCALARS:
            if isinstance(value, kind):
                return [tag, text(value)]
    if isinstance(value, Mapping):
        return ["map", {_key(key): _typed(item) for key, item in value.items()}]
    if isinstance(value, (tuple, list)):
        return ["list", [_typed(item) for item in value]]
    if isinstance(value, (set, frozenset)):
        return ["set", sorted((_typed(item) for item in value), key=_encode)]
    raise _no_form(value)


def _check_policy(policy: object) -> None:
    if not isinstance(policy, Policy):
        raise TypeError("policy must be a Policy")


def canonical_bytes(policy: Policy, inputs: DigestInputs) -> bytes:
    """Return the canonical form of a policy and the inputs of its digest.

    The form is one JSON object (RFC 8259), with the members ``format``
    (:data:`FORMAT`), ``engine_version``, ``policy``, ``tables``,
    ``l2_rules``, ``l3_rules``, ``vocabulary``, ``generated_values``,
    ``files``, and ``environment``. ``l3_rules`` is ``null``, since there are
    no user rules yet, and so is ``vocabulary`` without one. It is encoded so
    that the same inputs give the same bytes on every platform and Python
    version:

    - as UTF-8, with every character other than ``"``, ``\\``, and the
      control characters U+0000 to U+001F written as itself; those are
      written as ``\\"``, ``\\\\``, ``\\b``, ``\\f``, ``\\n``, ``\\r``,
      ``\\t``, or ``\\u00xx`` in lowercase hexadecimal;
    - with each object's members sorted by key, compared by code point, and
      no whitespace outside text;
    - with integers in decimal, and ``true``, ``false``, and ``null``.

    A dataclass, such as the policy, is an object of its fields; a mapping
    is an object; a tuple or list is an array in its own order; and an
    enumeration member is its value. Each parameter of generated values, and
    each value of the environment, is a pair ``[type, value]``: ``["str",
    text]``, ``["int", integer]``, ``["float", float.hex()]``, ``["bytes",
    lowercase hexadecimal]``, ``["uuid", hyphenated lowercase
    hexadecimal]``, ``["map", object of pairs]``, ``["list", array of
    pairs]``, or ``["set", array of pairs sorted by their canonical bytes]``.

    Parameters
    ----------
    policy : Policy
        A validated policy, such as one from
        :func:`~pymedphys._dicom.deidentify.policy.compose_policy`.
    inputs : DigestInputs

    Returns
    -------
    bytes

    Raises
    ------
    TypeError
        If ``policy`` is not a :class:`~pymedphys._dicom.deidentify.policy.Policy`,
        or if an input has a type the form does not define, such as a float
        outside the parameters of generated values and the environment, or a
        mapping key that is not text. The message names the type, never the
        value.
    ValueError
        If an input has text that cannot be encoded as UTF-8, such as a lone
        surrogate. The message does not quote it.
    """
    _check_policy(policy)
    generated = {_key(n): _typed(v) for n, v in inputs.generated_values.items()}
    environment = {_key(n): _typed(v) for n, v in inputs.environment.items()}
    document = {
        "format": FORMAT,
        "engine_version": inputs.engine_version,
        "policy": policy,
        "tables": inputs.tables,
        "l2_rules": inputs.l2_rules,
        "l3_rules": None,
        "vocabulary": inputs.vocabulary,
        # Already JSON values, which _plain keeps as they are.
        "generated_values": generated,
        "environment": environment,
        "files": inputs.files,
    }
    return _encode(_plain(document))


@functools.lru_cache(maxsize=None)
def _table_digests(directory: pathlib.Path) -> Mapping[str, str]:
    """Return each generated table's content digest, checked against its record.

    Each directory is read once and cached, keyed by its resolved path.
    """
    digests = {}
    for path in sorted(directory.glob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            digest = standard.content_sha256(document["rows"])
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise standard.StandardTableError(
                f"{path.name} could not be read"
            ) from error
        if digest != document.get("content_sha256"):
            raise standard.StandardTableError(
                f"{path.name} rows do not match their recorded digest; "
                "regenerate the tables with pymedphys dev deid-tables"
            )
        digests[path.name] = digest
    return types.MappingProxyType(digests)


@functools.lru_cache(maxsize=None)
def _file_digests(directory: pathlib.Path) -> Mapping[str, str]:
    """Return the SHA-256 of each source and rule file, with CRLF read as LF.

    Each directory is read once and cached, keyed by its resolved path.
    """
    digests = {}
    for path in directory.rglob("*"):
        relative = path.relative_to(directory)
        cached = any(p == "__pycache__" or p.startswith(".") for p in relative.parts)
        if path.suffix in COVERED_SUFFIXES and not cached and path.is_file():
            data = path.read_bytes().replace(b"\r\n", b"\n")
            digests[relative.as_posix()] = hashlib.sha256(data).hexdigest()
    return types.MappingProxyType(digests)


def _environment() -> dict[str, object]:
    """Return the Python implementation and version, and each library's version."""
    return {
        "platform.python_implementation": platform.python_implementation(),
        "platform.python_version": platform.python_version(),
        "pydicom.__version__": pydicom.__version__,
        "tomlkit.__version__": tomlkit.__version__,
    }


def digest_inputs(vocabulary: tg263.Nomenclature | None = None) -> DigestInputs:
    """Gather everything the policy digest covers apart from the policy.

    Reads the engine's own files once per process, at the first call: the
    generated tables, the supplementary rule files, and the package's source
    and rule files. Takes the Python implementation and version from the
    running interpreter, and each library's version from the library as
    imported.

    Parameters
    ----------
    vocabulary : ~pymedphys._nomenclature.tg263.Nomenclature, optional
        The TG-263 vocabulary that descriptor cleaning matches ROI Names
        against, or None without one.

    Returns
    -------
    DigestInputs

    Raises
    ------
    TypeError
        If ``vocabulary`` is not a TG-263 nomenclature or None.
    ValueError
        If the vocabulary's entries have text that cannot be encoded as
        UTF-8. The message does not quote it.
    ~pymedphys._dicom.deidentify.standard.StandardTableError
        If a generated table cannot be read, or its rows do not match the
        digest it records.
    """
    if vocabulary is not None and not isinstance(vocabulary, tg263.Nomenclature):
        raise TypeError("vocabulary must be a TG-263 Nomenclature or None")
    entries = None
    if vocabulary is not None:
        structures = [dataclasses.asdict(s) for s in vocabulary.structures]
        try:
            entries = tg263.content_sha256(structures)
        except UnicodeEncodeError:
            raise ValueError(
                "the vocabulary has an entry that cannot be encoded as UTF-8"
            ) from None
    return DigestInputs(
        engine_version=_version.__version__,
        tables=_table_digests(standard.STANDARD_DIR.resolve()),
        l2_rules={
            uid_roles.UID_ROLES_PATH.name: uid_roles.load_uid_roles(),
            temporal_roles.TEMPORAL_ROLES_PATH.name: temporal_roles.load_temporal_roles(),
            supplementary_actions.SUPPLEMENTARY_ACTIONS_PATH.name: (
                supplementary_actions.load_supplementary_actions()
            ),
            "supplementary_actions.UNCOVERED_TEXT_ACTION": (
                supplementary_actions.UNCOVERED_TEXT_ACTION
            ),
        },
        vocabulary=entries,
        generated_values={
            f"{module.__name__.rpartition('.')[2]}.{name}": getattr(module, name)
            for module, names in GENERATED_VALUE_PARAMETERS
            for name in names
        },
        files=_file_digests(PACKAGE_DIR.resolve()),
        environment=_environment(),
    )


def policy_digest(
    policy: Policy, *, vocabulary: tg263.Nomenclature | None = None
) -> str:
    """Return the policy digest of a policy, as 64 lowercase hexadecimal digits.

    The digest is the SHA-256 of :func:`canonical_bytes` of the policy and
    :func:`digest_inputs`, so it changes whenever the policy changes, or
    anything the engine could apply, whether or not the policy's options use
    it, or the version of Python or of a library that the engine imports.
    It fits one value of De-identification Method (0012,0063), an LO.

    Parameters
    ----------
    policy : Policy
        A validated policy, such as one from
        :func:`~pymedphys._dicom.deidentify.policy.compose_policy`.
    vocabulary : ~pymedphys._nomenclature.tg263.Nomenclature, optional
        The TG-263 vocabulary that descriptor cleaning matches ROI Names
        against, or None without one.

    Returns
    -------
    str

    Raises
    ------
    TypeError, ValueError, ~pymedphys._dicom.deidentify.standard.StandardTableError
        For any reason :func:`digest_inputs` or :func:`canonical_bytes` gives.

    Examples
    --------
    >>> from pymedphys._dicom.deidentify.policy import compose_policy
    >>> digest = policy_digest(compose_policy("basic"))
    >>> len(digest), digest == digest.lower(), int(digest, 16) >= 0
    (64, True, True)
    """
    _check_policy(policy)
    return hashlib.sha256(
        canonical_bytes(policy, digest_inputs(vocabulary))
    ).hexdigest()
