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

Every input is changed by monkeypatching or by injecting synthetic inputs, so
no test edits the package's own files. The engine's files and tables are read
once per process, so each test starts with them unread, and a test that
edits a synthetic engine or tables reads them again, as a new process would.
"""

import ast
import dataclasses
import hashlib
import importlib
import json
import pathlib
import pkgutil
import platform
import re
import shutil
import sys
import types
import uuid

from pymedphys._imports import pytest

from pymedphys import _version
from pymedphys._dicom.deidentify import (
    actions,
    dates,
    dummy_values,
    keys,
    policy,
    policy_digest,
    pseudonyms,
    standard,
    supplementary_actions,
    temporal_roles,
    uid_roles,
    uids,
    values,
)
from pymedphys._dicom.deidentify.temporal_roles import TemporalRole
from pymedphys._nomenclature import tg263

HEX_DIGEST = re.compile(r"[0-9a-f]{64}")
WEDGE_ID = "(300A,00D4)"  # K under Retain Device Identity, which basic omits
CALIBRATION_DATE = "(0018,1200)"  # a device date, which only Modified Dates uses
SOP_INSTANCE_UID = "(0008,0018)"

# A small synthetic input, and its canonical form written out by hand from
# the documented encoding. Its SHA-256 was computed from these bytes with
# `printf '%s' '<bytes>' | sha256sum`, independently of the code under test.
SYNTHETIC_POLICY = policy.Policy(
    preset="basic",
    edition="2026d",
    options=(),
    actions=types.MappingProxyType({"(0010,0010)": "Z"}),
    resolved=(),
    supplementary_actions=types.MappingProxyType({"(300A,00C2)": "X/Z/D"}),
)
SYNTHETIC_INPUTS = policy_digest.DigestInputs(
    engine_version="0.42.0.dev1",
    tables={"e1_1.json": "0" * 64},
    l2_rules={
        "uid_roles.toml": {
            "acknowledgement": "DICOM PS3.6 2026d, © NEMA",
            "note": 'Kept "as is".\t\x01',
            "rules": {SOP_INSTANCE_UID: uid_roles.UIDRole.INSTANCE},
        }
    },
    vocabulary=None,
    generated_values={
        "uids.UID_ROOT": "2.25.",
        "uids.UID_NAMESPACE": uuid.UUID("6f71d76c-0573-58b6-bfda-7c5b4ee304f1"),
        "keys.DOMAINS": frozenset({"uid", "patient"}),
        "keys.DERIVATION_VERSION": b"pymedphys-deid/1",
        "dummy_values.CONSTANTS": {"FL": (0.0, 1.0)},
        "dates.MIN_OFFSET_WEEKS": 52,
    },
    files={"policy.py": "f" * 64},
    environment={
        "pydicom.__version__": "3.0.2",
        "platform.python_version": "3.14.0",
        "platform.python_implementation": "CPython",
    },
)
SYNTHETIC_CANONICAL_BYTES = (
    '{"engine_version":"0.42.0.dev1",'
    '"environment":{'
    '"platform.python_implementation":["str","CPython"],'
    '"platform.python_version":["str","3.14.0"],'
    '"pydicom.__version__":["str","3.0.2"]},'
    '"files":{"policy.py":"' + "f" * 64 + '"},'
    '"format":"pymedphys-deid-policy-digest/1",'
    '"generated_values":{'
    '"dates.MIN_OFFSET_WEEKS":["int",52],'
    '"dummy_values.CONSTANTS":["map",{"FL":["list",'
    '[["float","0x0.0p+0"],["float","0x1.0000000000000p+0"]]]}],'
    '"keys.DERIVATION_VERSION":["bytes","70796d6564706879732d646569642f31"],'
    '"keys.DOMAINS":["set",[["str","patient"],["str","uid"]]],'
    '"uids.UID_NAMESPACE":["uuid","6f71d76c-0573-58b6-bfda-7c5b4ee304f1"],'
    '"uids.UID_ROOT":["str","2.25."]},'
    '"l2_rules":{"uid_roles.toml":{'
    '"acknowledgement":"DICOM PS3.6 2026d, © NEMA",'
    '"note":"Kept \\"as is\\".\\t\\u0001",'
    '"rules":{"(0008,0018)":"instance"}}},'
    '"l3_rules":null,'
    '"policy":{"actions":{"(0010,0010)":"Z"},"edition":"2026d","enabled":false,'
    '"options":[],"preset":"basic","resolved":[],'
    '"supplementary_actions":{"(300A,00C2)":"X/Z/D"}},'
    '"tables":{"e1_1.json":"' + "0" * 64 + '"},'
    '"vocabulary":null}'
).encode("utf-8")
SYNTHETIC_SHA256 = "4657ba6f07dc332a9cfd7eddc7f1b13bc954d4587dbf342f802d5e1e1b27f315"

# Each parameter of generated values, and another value for it.
GENERATED_VALUE_CHANGES = {
    "keys.DERIVATION_VERSION": (keys, b"pymedphys-deid/2"),
    "keys.DOMAINS": (keys, keys.DOMAINS | {"birth-date"}),
    "uids.UID_ROOT": (uids, "2.25.0."),
    "uids.UID_NAMESPACE": (uids, uuid.UUID(int=1)),
    "pseudonyms.PATIENT_ID_PREFIX": (pseudonyms, "DEID_"),
    "pseudonyms.FAMILY_NAME": (pseudonyms, "DE-IDENTIFIED"),
    "pseudonyms.CODE_BYTES": (pseudonyms, 12),
    "dates.MIN_OFFSET_WEEKS": (dates, 53),
    "dates.MAX_OFFSET_WEEKS": (dates, 521),
    "dates.NOMINAL_UTC_OFFSET": (dates, "-0000"),
    "dummy_values.CONSTANTS": (
        dummy_values,
        types.MappingProxyType(
            {**dummy_values.CONSTANTS, "DA": ("19000101", "19000103")}
        ),
    ),
}

# Each value of the environment: where it comes from, and another value for it.
ENVIRONMENT_CHANGES = {
    "platform.python_implementation": (platform, "python_implementation", "PyPy"),
    "platform.python_version": (platform, "python_version", "3.14.1"),
    "pydicom.__version__": ("pydicom", "__version__", "3.0.3"),
    "tomlkit.__version__": ("tomlkit", "__version__", "0.15.2"),
}

ENGINE_FILES = {
    "__init__.py": b'"""A package."""\n',
    "policy_digest.py": b'FORMAT = "digest/1"\n',
    "policy.py": b"ACTION = 'X'\n\n\ndef action():\n    return ACTION\n",
    "rules.toml": b'schema = "rules/1"\n\n[[attribute]]\ntag = "(0008,0018)"\n',
    "_standard/table.json": b'{\n "rows": [\n  {"tag": "(0010,0010)"}\n ]\n}\n',
}


@pytest.fixture(name="basic", scope="module")
def _basic():
    return policy.compose_policy("basic")


def _forget_reads():
    """Forget the engine's files and tables, which are read once per process."""
    # pylint: disable = protected-access
    policy_digest._file_digests.cache_clear()
    policy_digest._table_digests.cache_clear()


@pytest.fixture(name="read_again", autouse=True)
def _read_again():
    """Start and end each test with the engine's files and tables unread.

    Gives a function that makes the next digest read them again, as a new
    process would.
    """
    _forget_reads()
    yield _forget_reads
    _forget_reads()


def _engine(directory, files, newline=b"\n"):
    """Write a synthetic engine package, with ``newline`` ending each line."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.replace(b"\n", newline))
    return directory


def _structure(primary_name, reverse_order_name):
    return tg263.Structure(
        target_type="Anatomic",
        major_category="Thorax",
        minor_category="",
        anatomic_group="",
        primary_name=primary_name,
        reverse_order_name=reverse_order_name,
        description="",
        fma_id=None,
    )


def _vocabulary(*structures, file="invented.xls"):
    return tg263.Nomenclature(
        source=tg263.Source(file=file, sha256="0" * 64, sheet="Invented"),
        attribution=tg263.ATTRIBUTION,
        structures=structures,
    )


VOCABULARY = _vocabulary(_structure("Heart", "Heart"), _structure("Lung_L", "L_Lung"))


@pytest.mark.parametrize("preset", list(policy.PRESETS))
@pytest.mark.parametrize("vocabulary", [None, VOCABULARY])
def test_the_digest_is_only_64_lowercase_hexadecimal_digits_and_fits_one_lo_value(
    preset, vocabulary
):
    digest = policy_digest.policy_digest(
        policy.compose_policy(preset), vocabulary=vocabulary
    )

    assert HEX_DIGEST.fullmatch(digest)
    assert values.value_problem("LO", digest) is None


def test_the_digest_is_the_sha256_of_the_canonical_form(basic):
    canonical = policy_digest.canonical_bytes(
        basic, policy_digest.digest_inputs(VOCABULARY)
    )

    digest = policy_digest.policy_digest(basic, vocabulary=VOCABULARY)

    assert digest == hashlib.sha256(canonical).hexdigest()


def test_a_small_synthetic_input_has_the_canonical_form_written_by_hand():
    canonical = policy_digest.canonical_bytes(SYNTHETIC_POLICY, SYNTHETIC_INPUTS)

    assert canonical == SYNTHETIC_CANONICAL_BYTES
    assert hashlib.sha256(canonical).hexdigest() == SYNTHETIC_SHA256


def test_the_same_inputs_always_give_the_same_digest(basic):
    first = policy_digest.policy_digest(basic, vocabulary=VOCABULARY)

    assert policy_digest.policy_digest(basic, vocabulary=VOCABULARY) == first
    assert (
        policy_digest.policy_digest(
            policy.compose_policy("basic"),
            vocabulary=_vocabulary(*VOCABULARY.structures),
        )
        == first
    )


class _Reversed(frozenset):
    """A set that iterates in reverse order."""

    def __iter__(self):
        return iter(sorted(frozenset.__iter__(self), reverse=True))


def test_mappings_and_sets_are_encoded_in_a_defined_order():
    reordered_policy = dataclasses.replace(
        SYNTHETIC_POLICY,
        actions=types.MappingProxyType({"(0010,0020)": "Z", "(0010,0010)": "Z"}),
    )
    in_order_policy = dataclasses.replace(
        SYNTHETIC_POLICY,
        actions=types.MappingProxyType({"(0010,0010)": "Z", "(0010,0020)": "Z"}),
    )
    reordered_inputs = dataclasses.replace(
        SYNTHETIC_INPUTS,
        generated_values={
            **dict(reversed(list(SYNTHETIC_INPUTS.generated_values.items()))),
            "keys.DOMAINS": _Reversed({"uid", "patient"}),
        },
    )

    assert policy_digest.canonical_bytes(
        reordered_policy, reordered_inputs
    ) == policy_digest.canonical_bytes(in_order_policy, SYNTHETIC_INPUTS)


def test_the_engine_version_changes_the_digest(basic, monkeypatch):
    before = policy_digest.policy_digest(basic)
    monkeypatch.setattr(_version, "__version__", _version.__version__ + "+local")

    assert policy_digest.digest_inputs().engine_version.endswith("+local")
    assert policy_digest.policy_digest(basic) != before


def _with_changes(policy_, **changes):
    changed = dataclasses.replace(policy_, **changes)
    object.__setattr__(changed, "enabled", policy_.enabled)
    return changed


def _enabled(policy_):
    changed = dataclasses.replace(policy_)
    object.__setattr__(changed, "enabled", True)
    return changed


def _resolved():
    conflict = actions.OptionConflict(
        name="Date of Last Calibration",
        tag=CALIBRATION_DATE,
        actions=types.MappingProxyType(
            {
                "retain_device_identity": "K",
                "retain_longitudinal_modified_dates": "C",
            }
        ),
    )
    return (
        policy.ResolvedConflict(
            conflict=conflict,
            action="C",
            role=TemporalRole.DEVICE,
            unmet=("retain_device_identity",),
        ),
    )


@pytest.mark.parametrize(
    "change",
    [
        lambda p: _with_changes(p, preset=None),
        lambda p: _with_changes(p, edition="2026c"),
        lambda p: _with_changes(p, options=("clean_descriptors",)),
        lambda p: _with_changes(
            p, actions=types.MappingProxyType({**p.actions, SOP_INSTANCE_UID: "K"})
        ),
        lambda p: _with_changes(p, resolved=_resolved()),
        lambda p: _with_changes(
            p,
            supplementary_actions=types.MappingProxyType(
                {**p.supplementary_actions, WEDGE_ID: "K"}
            ),
        ),
        _enabled,
    ],
    ids=[
        "preset",
        "edition",
        "options",
        "actions",
        "resolved",
        "supplementary_actions",
        "enabled",
    ],
)
def test_any_part_of_the_policy_changes_the_digest(basic, change):
    assert policy_digest.policy_digest(change(basic)) != policy_digest.policy_digest(
        basic
    )


def test_each_preset_has_its_own_digest():
    digests = {
        policy_digest.policy_digest(policy.compose_policy(preset))
        for preset in policy.PRESETS
    }

    assert len(digests) == len(policy.PRESETS)


def _copied_tables(tmp_path):
    copy = tmp_path / "_standard"
    shutil.copytree(standard.STANDARD_DIR, copy)
    return copy


def _rewrite(path, rows, recorded=None, indent=1):
    document = json.loads(path.read_text(encoding="utf-8"))
    document["rows"] = rows
    document["content_sha256"] = recorded or standard.content_sha256(rows)
    path.write_text(json.dumps(document, indent=indent, ensure_ascii=False), "utf-8")


@pytest.mark.parametrize(
    "name", sorted(path.name for path in standard.STANDARD_DIR.glob("*.json"))
)
def test_any_generated_table_changes_the_digest(basic, tmp_path, monkeypatch, name):
    before = policy_digest.policy_digest(basic)
    copy = _copied_tables(tmp_path)
    rows = json.loads((copy / name).read_text(encoding="utf-8"))["rows"]
    _rewrite(copy / name, rows[::-1])
    monkeypatch.setattr(standard, "STANDARD_DIR", copy)

    assert policy_digest.digest_inputs().tables[name] == standard.content_sha256(
        rows[::-1]
    )
    assert policy_digest.policy_digest(basic) != before


def test_the_tables_are_covered_by_their_content_not_their_layout(
    basic, tmp_path, monkeypatch
):
    before = policy_digest.policy_digest(basic)
    copy = _copied_tables(tmp_path)
    path = copy / "e1_1.json"
    rows = json.loads(path.read_text(encoding="utf-8"))["rows"]
    _rewrite(path, rows, indent=4)

    assert path.read_bytes() != (standard.STANDARD_DIR / "e1_1.json").read_bytes()
    monkeypatch.setattr(standard, "STANDARD_DIR", copy)
    assert policy_digest.policy_digest(basic) == before


def test_a_table_that_does_not_match_its_recorded_digest_is_rejected(
    basic, tmp_path, monkeypatch
):
    copy = _copied_tables(tmp_path)
    path = copy / "e3_10_1.json"
    rows = json.loads(path.read_text(encoding="utf-8"))["rows"]
    _rewrite(path, rows[::-1], recorded=standard.content_sha256(rows))
    monkeypatch.setattr(standard, "STANDARD_DIR", copy)

    with pytest.raises(standard.StandardTableError, match="e3_10_1.json rows do not"):
        policy_digest.policy_digest(basic)


def _changed_uid_roles():
    roles = uid_roles.load_uid_roles()
    rule = roles.rules[SOP_INSTANCE_UID]
    changed = dataclasses.replace(rule, role=uid_roles.UIDRole.DEFINITION)
    return dataclasses.replace(
        roles, rules=types.MappingProxyType({**roles.rules, SOP_INSTANCE_UID: changed})
    )


def _changed_temporal_roles():
    roles = temporal_roles.load_temporal_roles()
    rule = roles.rules[CALIBRATION_DATE]
    changed = dataclasses.replace(rule, role=TemporalRole.SUBJECT_EVENT)
    return dataclasses.replace(
        roles, rules=types.MappingProxyType({**roles.rules, CALIBRATION_DATE: changed})
    )


def _changed_supplementary_actions():
    loaded = supplementary_actions.load_supplementary_actions()
    rule = loaded.rules[WEDGE_ID]
    changed = dataclasses.replace(rule, options=types.MappingProxyType({}))
    return dataclasses.replace(
        loaded, rules=types.MappingProxyType({**loaded.rules, WEDGE_ID: changed})
    )


@pytest.mark.parametrize(
    "module, name, changed",
    [
        (uid_roles, "load_uid_roles", _changed_uid_roles),
        (temporal_roles, "load_temporal_roles", _changed_temporal_roles),
        (
            supplementary_actions,
            "load_supplementary_actions",
            _changed_supplementary_actions,
        ),
    ],
    ids=["uid_roles", "temporal_roles", "supplementary_actions"],
)
def test_any_supplementary_rule_changes_the_digest_even_one_the_options_do_not_use(
    basic, monkeypatch, module, name, changed
):
    before = policy_digest.policy_digest(basic)
    rules = changed()
    monkeypatch.setattr(module, name, lambda: rules)

    assert policy_digest.policy_digest(basic) != before


def test_the_action_for_text_that_no_rule_covers_changes_the_digest(basic, monkeypatch):
    before = policy_digest.policy_digest(basic)
    monkeypatch.setattr(supplementary_actions, "UNCOVERED_TEXT_ACTION", "X")

    assert policy_digest.policy_digest(basic) != before


def test_the_canonical_form_records_that_there_are_no_user_rules(basic):
    canonical = policy_digest.canonical_bytes(basic, policy_digest.digest_inputs())

    assert json.loads(canonical)["l3_rules"] is None


def test_adding_or_removing_a_vocabulary_or_changing_its_entries_changes_the_digest(
    basic,
):
    digests = [
        policy_digest.policy_digest(basic, vocabulary=vocabulary)
        for vocabulary in (
            None,
            VOCABULARY,
            _vocabulary(_structure("Heart", "Heart")),
            _vocabulary(_structure("Heart", "Heart"), _structure("Lung_R", "R_Lung")),
        )
    ]

    assert len(set(digests)) == len(digests)


def test_the_vocabulary_is_covered_by_the_digest_its_file_records(basic):
    recorded = json.loads(tg263.to_json(VOCABULARY))["content_sha256"]
    renamed = _vocabulary(*VOCABULARY.structures, file="another-name.xls")

    assert policy_digest.digest_inputs(VOCABULARY).vocabulary == recorded
    assert policy_digest.policy_digest(
        basic, vocabulary=renamed
    ) == policy_digest.policy_digest(basic, vocabulary=VOCABULARY)


def test_the_parameters_of_generated_values_are_those_of_each_generated_value():
    generated = policy_digest.digest_inputs().generated_values

    assert set(generated) == set(GENERATED_VALUE_CHANGES)
    for name, (module, _) in GENERATED_VALUE_CHANGES.items():
        assert generated[name] is getattr(module, name.rpartition(".")[2])


@pytest.mark.parametrize("name", list(GENERATED_VALUE_CHANGES))
def test_any_parameter_of_generated_values_changes_the_digest(basic, monkeypatch, name):
    before = policy_digest.policy_digest(basic)
    module, value = GENERATED_VALUE_CHANGES[name]
    monkeypatch.setattr(module, name.rpartition(".")[2], value)

    assert policy_digest.policy_digest(basic) != before


@pytest.mark.parametrize(
    "name, value",
    [
        ("keys.DERIVATION_VERSION", b"pymedphys-deid/1".hex()),
        ("dummy_values.CONSTANTS", {"FL": ("0x0.0p+0", "0x1.0000000000000p+0")}),
        ("dates.MIN_OFFSET_WEEKS", "52"),
    ],
)
def test_a_parameter_that_changes_only_its_type_changes_the_digest(name, value):
    changed = dataclasses.replace(
        SYNTHETIC_INPUTS,
        generated_values={**SYNTHETIC_INPUTS.generated_values, name: value},
    )

    assert policy_digest.canonical_bytes(
        SYNTHETIC_POLICY, changed
    ) != policy_digest.canonical_bytes(SYNTHETIC_POLICY, SYNTHETIC_INPUTS)


def _third_party_imports(path):
    """Return the top-level names of the third-party modules a module imports.

    A name imported from ``pymedphys._imports``, which imports it lazily, is
    the module it names.
    """
    names = set()
    for node in ast.walk(ast.parse(path.read_bytes())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            if node.module == "pymedphys._imports":
                names.update(alias.name for alias in node.names)
            else:
                names.add(node.module)
    tops = {name.partition(".")[0] for name in names}
    return tops - set(sys.stdlib_module_names) - {"__future__", "pymedphys"}


def test_the_environment_is_python_and_every_library_that_the_engine_imports():
    environment = policy_digest.digest_inputs().environment
    imported = set().union(
        *(
            _third_party_imports(path)
            for path in policy_digest.PACKAGE_DIR.rglob("*.py")
            if "__pycache__" not in path.parts
        )
    )

    assert {"pydicom", "tomlkit"} <= imported
    assert environment == {
        "platform.python_implementation": platform.python_implementation(),
        "platform.python_version": platform.python_version(),
        **{
            f"{name}.__version__": importlib.import_module(name).__version__
            for name in imported
        },
    }


@pytest.mark.parametrize("name", list(ENVIRONMENT_CHANGES))
def test_the_python_implementation_and_version_and_each_library_version_change_the_digest(
    basic, monkeypatch, name
):
    before = policy_digest.policy_digest(basic)
    module, attribute, value = ENVIRONMENT_CHANGES[name]
    if module is platform:
        monkeypatch.setattr(platform, attribute, lambda: value)
    else:
        monkeypatch.setattr(importlib.import_module(module), attribute, value)

    assert policy_digest.digest_inputs().environment[name] == value
    assert policy_digest.policy_digest(basic) != before


def test_every_module_rule_file_and_table_of_the_engine_is_covered():
    files = policy_digest.digest_inputs().files
    package = importlib.import_module("pymedphys._dicom.deidentify")
    modules = {
        f"{module.name}.py"
        for module in pkgutil.iter_modules(package.__path__)
        if not module.ispkg
    }
    tables = {f"_standard/{path.name}" for path in standard.STANDARD_DIR.glob("*.json")}
    rule_files = {
        "uid_roles.toml",
        "temporal_roles.toml",
        "supplementary_actions.toml",
        "requirements.toml",
    }

    assert {"__init__.py", "policy_digest.py"} | rule_files | tables | modules <= set(
        files
    )
    assert all(name.endswith((".py", ".toml", ".json")) for name in files)
    assert not [name for name in files if "__pycache__" in name]


@pytest.mark.parametrize(
    "change",
    [
        lambda d: (d / "policy.py").write_bytes(b"ACTION = 'K'\n"),
        lambda d: (d / "rules.toml").write_bytes(b'schema = "rules/2"\n'),
        lambda d: (d / "_standard" / "table.json").write_bytes(b'{"rows": []}\n'),
        lambda d: (d / "added.py").write_bytes(b""),
        lambda d: (d / "rules.toml").unlink(),
        lambda d: (d / "policy.py").rename(d / "renamed.py"),
    ],
    ids=["module", "rule-file", "table", "added", "removed", "renamed"],
)
def test_changing_adding_or_removing_an_engine_file_changes_the_digest(
    basic, tmp_path, monkeypatch, read_again, change
):
    engine = _engine(tmp_path, ENGINE_FILES)
    monkeypatch.setattr(policy_digest, "PACKAGE_DIR", engine)
    before = policy_digest.policy_digest(basic)
    change(engine)
    read_again()

    assert policy_digest.policy_digest(basic) != before


def test_every_file_of_the_engine_other_than_caches_has_a_covered_type():
    package = policy_digest.PACKAGE_DIR
    expected = set()
    for path in package.rglob("*"):
        relative = path.relative_to(package)
        if path.is_file() and not any(
            part == "__pycache__" or part.startswith(".") for part in relative.parts
        ):
            expected.add(relative.as_posix())
    uncovered = sorted(
        name
        for name in expected
        if pathlib.PurePosixPath(name).suffix not in policy_digest.COVERED_SUFFIXES
    )

    assert not uncovered, "the policy digest does not cover these types of file"
    assert set(policy_digest.digest_inputs().files) == expected


def test_every_file_is_covered_when_the_engine_is_installed_below_a_hidden_directory(
    tmp_path, monkeypatch
):
    site_packages = tmp_path / ".venv" / "lib" / "python3.14" / "site-packages"
    engine = _engine(
        site_packages / "pymedphys" / "_dicom" / "deidentify", ENGINE_FILES
    )
    monkeypatch.setattr(policy_digest, "PACKAGE_DIR", engine)

    assert set(policy_digest.digest_inputs().files) == set(ENGINE_FILES)


@pytest.mark.parametrize(
    "files, problem",
    [
        (None, "found no source or rule files"),
        ({}, "found no source or rule files"),
        (
            {"notes.txt": b"notes", "__pycache__/policy_digest.cpython-313.pyc": b""},
            "found no source or rule files",
        ),
        (
            {n: c for n, c in ENGINE_FILES.items() if n != "policy_digest.py"},
            "do not include policy_digest.py",
        ),
    ],
    ids=["missing", "empty", "no-covered-files", "without-its-own-module"],
)
def test_the_digest_is_refused_without_the_engine_files(
    basic, tmp_path, monkeypatch, files, problem
):
    engine = tmp_path / "engine"
    if files is not None:
        _engine(engine, files)
    monkeypatch.setattr(policy_digest, "PACKAGE_DIR", engine)

    for compute in (
        policy_digest.digest_inputs,
        lambda: policy_digest.policy_digest(basic),
    ):
        with pytest.raises(policy_digest.PolicyDigestError, match=problem) as raised:
            compute()
        assert str(tmp_path) not in str(raised.value)


def _edit_a_file(engine, _tables):
    (engine / "policy.py").write_bytes(b"ACTION = 'K'\n")


def _edit_a_table(_engine_dir, tables):
    rows = json.loads((tables / "e1_1.json").read_text(encoding="utf-8"))["rows"]
    _rewrite(tables / "e1_1.json", rows[::-1])


@pytest.mark.parametrize("edit", [_edit_a_file, _edit_a_table], ids=["file", "table"])
def test_the_engine_files_and_tables_are_read_once_per_process(
    basic, tmp_path, monkeypatch, read_again, edit
):
    engine = _engine(tmp_path / "engine", ENGINE_FILES)
    tables = _copied_tables(tmp_path)
    monkeypatch.setattr(policy_digest, "PACKAGE_DIR", engine)
    monkeypatch.setattr(standard, "STANDARD_DIR", tables)
    first = policy_digest.policy_digest(basic)
    edit(engine, tables)

    assert policy_digest.policy_digest(basic) == first
    read_again()
    assert policy_digest.policy_digest(basic) != first


def test_files_with_crlf_and_lf_line_endings_give_the_same_digest(
    basic, tmp_path, monkeypatch
):
    digests = []
    for newline in (b"\n", b"\r\n"):
        engine = _engine(tmp_path / str(len(newline)), ENGINE_FILES, newline)
        monkeypatch.setattr(policy_digest, "PACKAGE_DIR", engine)
        digests.append(policy_digest.policy_digest(basic))

    assert (tmp_path / "2" / "policy.py").read_bytes().count(b"\r\n") == 5
    assert digests[0] == digests[1]


def test_caches_and_files_of_other_types_are_not_covered(
    basic, tmp_path, monkeypatch, read_again
):
    engine = _engine(tmp_path, ENGINE_FILES)
    monkeypatch.setattr(policy_digest, "PACKAGE_DIR", engine)
    before = policy_digest.policy_digest(basic)
    _engine(
        engine,
        {
            "__pycache__/policy.cpython-313.pyc": b"\x00compiled",
            "__pycache__/stale.py": b"ACTION = 'K'\n",
            ".mypy_cache/3.13/policy.data.json": b"{}",
            ".hidden.py": b"",
            "notes.txt": b"notes",
        },
    )
    read_again()

    assert set(policy_digest.digest_inputs().files) == set(ENGINE_FILES)
    assert policy_digest.policy_digest(basic) == before


@pytest.mark.parametrize(
    "where, value",
    [
        ("generated_values", 0.5 + 0j),
        ("generated_values", {7: "secret-value"}),
        ("generated_values", True),
        ("environment", 0.5 + 0j),
        ("l2_rules", 0.5),
        ("l2_rules", b"secret-value"),
        ("l2_rules", {7: "secret-value"}),
    ],
)
def test_a_value_without_a_canonical_form_is_rejected_without_quoting_it(where, value):
    changed = dataclasses.replace(SYNTHETIC_INPUTS, **{where: {"secret-name": value}})

    with pytest.raises(TypeError) as raised:
        policy_digest.canonical_bytes(SYNTHETIC_POLICY, changed)

    assert "secret" not in str(raised.value)


def test_text_that_cannot_be_encoded_is_rejected_without_quoting_it():
    changed = dataclasses.replace(SYNTHETIC_INPUTS, engine_version="secret\ud800")

    with pytest.raises(ValueError, match="UTF-8") as raised:
        policy_digest.canonical_bytes(SYNTHETIC_POLICY, changed)

    assert "secret" not in str(raised.value)
    assert raised.value.__cause__ is None and raised.value.__suppress_context__


def test_a_vocabulary_whose_entries_cannot_be_encoded_is_rejected_without_quoting_them():
    vocabulary = _vocabulary(_structure("secret\ud800", "Heart"))

    with pytest.raises(ValueError, match="UTF-8") as raised:
        policy_digest.digest_inputs(vocabulary)

    assert "secret" not in str(raised.value)


def test_only_a_policy_and_a_tg263_vocabulary_are_accepted(basic):
    with pytest.raises(TypeError, match="policy must be"):
        policy_digest.policy_digest({"preset": "basic"})
    with pytest.raises(TypeError, match="policy must be"):
        policy_digest.canonical_bytes({"preset": "basic"}, SYNTHETIC_INPUTS)
    with pytest.raises(TypeError, match="vocabulary must be"):
        policy_digest.policy_digest(basic, vocabulary=["Heart"])
