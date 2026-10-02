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

"""The de-identification method digest of a policy and the engine that applies it.

Every input of the method is changed by monkeypatching or by injecting
synthetic inputs, so no test edits the package's own files, and each change
must change the digest. The runtime environment (Python and the libraries
that run the engine) is not part of the method, so changing it must leave
the digest unchanged. The engine's files and tables are read once per
process, so each test starts with them unread, and a test that edits a
synthetic engine or tables reads them again, as a new process would.
"""

# The tests share the synthetic inputs and engine below, so they stay in one
# module.
# pylint: disable = too-many-lines

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
    method_digest,
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
# `printf '%s' '<bytes>' | sha256sum`, and checked with `openssl dgst -sha256`,
# independently of the code under test.
SYNTHETIC_POLICY = policy.Policy(
    preset="basic",
    edition="2026d",
    options=(),
    actions=types.MappingProxyType({"(0010,0010)": "Z"}),
    resolved=(),
    supplementary_actions=types.MappingProxyType({"(300A,00C2)": "X/Z/D"}),
)
SYNTHETIC_INPUTS = method_digest.MethodDigestInputs(
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
    reviewed_roi_names=None,
    generated_values={
        "uids.UID_ROOT": "2.25.",
        "uids.UID_NAMESPACE": uuid.UUID("6f71d76c-0573-58b6-bfda-7c5b4ee304f1"),
        "keys.DOMAINS": frozenset({"uid", "patient"}),
        "keys.DERIVATION_VERSION": b"pymedphys-deid/1",
        "dummy_values.CONSTANTS": {"FL": (0.0, 1.0)},
        "dates.MIN_OFFSET_WEEKS": 52,
    },
    files={"policy.py": "f" * 64},
)
SYNTHETIC_CANONICAL_BYTES = (
    '{"engine_version":"0.42.0.dev1",'
    '"files":{"policy.py":"' + "f" * 64 + '"},'
    '"format":"pymedphys-deid-method-digest/2",'
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
    '"reviewed_roi_names":null,'
    '"tables":{"e1_1.json":"' + "0" * 64 + '"},'
    '"vocabulary":null}'
).encode("utf-8")
SYNTHETIC_SHA256 = "1df94ac28b2f41430e85c3e1115196e88bdcfbeb2ab27b9cc17c4e36208a33fa"

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

# The members of the canonical form: the inputs of the method, and no others.
CANONICAL_MEMBERS = {
    "format",
    "engine_version",
    "policy",
    "tables",
    "l2_rules",
    "l3_rules",
    "vocabulary",
    "reviewed_roi_names",
    "generated_values",
    "files",
}


def _next_patch_release():
    major, minor, micro = sys.version_info[:3]
    return f"{major}.{minor}.{micro + 1}"


# The runtime environment, which runs the method but is not part of it: where
# each value comes from, and the values it can take instead, as an upgrade
# or another interpreter would give. A test takes the first that differs from
# the value now.
RUNTIME_CHANGES = {
    "python-implementation": (platform, "python_implementation", ("PyPy", "CPython")),
    "python-version": (platform, "python_version", (_next_patch_release(),)),
    "pydicom-version": ("pydicom", "__version__", ("3.0.3", "3.0.4")),
    "tomlkit-version": ("tomlkit", "__version__", ("0.15.2", "0.15.3")),
}

ENGINE_FILES = {
    "__init__.py": b'"""A package."""\n',
    "method_digest.py": b'FORMAT = "digest/1"\n',
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
    method_digest._file_digests.cache_clear()
    method_digest._table_digests.cache_clear()


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
    digest = method_digest.method_digest(
        policy.compose_policy(preset), vocabulary=vocabulary, reviewed_roi_names=None
    )

    assert HEX_DIGEST.fullmatch(digest)
    assert values.value_problem("LO", digest) is None


def test_the_digest_is_the_sha256_of_the_canonical_form(basic):
    canonical = method_digest.canonical_bytes(
        basic,
        method_digest.digest_inputs(vocabulary=VOCABULARY, reviewed_roi_names=None),
    )

    digest = method_digest.method_digest(
        basic, vocabulary=VOCABULARY, reviewed_roi_names=None
    )

    assert digest == hashlib.sha256(canonical).hexdigest()


def test_a_small_synthetic_input_has_the_canonical_form_written_by_hand():
    canonical = method_digest.canonical_bytes(SYNTHETIC_POLICY, SYNTHETIC_INPUTS)

    assert canonical == SYNTHETIC_CANONICAL_BYTES
    assert hashlib.sha256(canonical).hexdigest() == SYNTHETIC_SHA256


def test_the_same_inputs_always_give_the_same_digest(basic):
    first = method_digest.method_digest(
        basic, vocabulary=VOCABULARY, reviewed_roi_names=None
    )

    assert (
        method_digest.method_digest(
            basic, vocabulary=VOCABULARY, reviewed_roi_names=None
        )
        == first
    )
    assert (
        method_digest.method_digest(
            policy.compose_policy("basic"),
            vocabulary=_vocabulary(*VOCABULARY.structures),
            reviewed_roi_names=None,
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

    assert method_digest.canonical_bytes(
        reordered_policy, reordered_inputs
    ) == method_digest.canonical_bytes(in_order_policy, SYNTHETIC_INPUTS)


def test_the_engine_version_changes_the_digest(basic, monkeypatch):
    before = method_digest.method_digest(
        basic, vocabulary=None, reviewed_roi_names=None
    )
    monkeypatch.setattr(_version, "__version__", _version.__version__ + "+local")

    assert method_digest.digest_inputs(
        vocabulary=None, reviewed_roi_names=None
    ).engine_version.endswith("+local")
    assert (
        method_digest.method_digest(basic, vocabulary=None, reviewed_roi_names=None)
        != before
    )


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
    assert method_digest.method_digest(
        change(basic), vocabulary=None, reviewed_roi_names=None
    ) != method_digest.method_digest(basic, vocabulary=None, reviewed_roi_names=None)


def test_each_preset_has_its_own_digest():
    digests = {
        method_digest.method_digest(
            policy.compose_policy(preset), vocabulary=None, reviewed_roi_names=None
        )
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
    before = method_digest.method_digest(
        basic, vocabulary=None, reviewed_roi_names=None
    )
    copy = _copied_tables(tmp_path)
    rows = json.loads((copy / name).read_text(encoding="utf-8"))["rows"]
    _rewrite(copy / name, rows[::-1])
    monkeypatch.setattr(standard, "STANDARD_DIR", copy)

    assert method_digest.digest_inputs(vocabulary=None, reviewed_roi_names=None).tables[
        name
    ] == standard.content_sha256(rows[::-1])
    assert (
        method_digest.method_digest(basic, vocabulary=None, reviewed_roi_names=None)
        != before
    )


def test_a_reformatted_table_keeps_its_row_digest_but_changes_its_file_digest(
    tmp_path, monkeypatch, read_again
):
    modules = {n: c for n, c in ENGINE_FILES.items() if not n.startswith("_standard/")}
    engine = _engine(tmp_path / "engine", modules)
    tables = _copied_tables(engine)
    monkeypatch.setattr(method_digest, "PACKAGE_DIR", engine)
    monkeypatch.setattr(standard, "STANDARD_DIR", tables)
    before = method_digest.digest_inputs(vocabulary=None, reviewed_roi_names=None)
    path = tables / "e1_1.json"
    layout = path.read_bytes()
    _rewrite(path, json.loads(layout.decode("utf-8"))["rows"], indent=4)
    read_again()
    after = method_digest.digest_inputs(vocabulary=None, reviewed_roi_names=None)

    assert path.read_bytes() != layout
    assert after.tables == before.tables
    assert after.files["_standard/e1_1.json"] != before.files["_standard/e1_1.json"]


def test_a_table_that_does_not_match_its_recorded_digest_is_rejected(
    basic, tmp_path, monkeypatch
):
    copy = _copied_tables(tmp_path)
    path = copy / "e3_10_1.json"
    rows = json.loads(path.read_text(encoding="utf-8"))["rows"]
    _rewrite(path, rows[::-1], recorded=standard.content_sha256(rows))
    monkeypatch.setattr(standard, "STANDARD_DIR", copy)

    with pytest.raises(standard.StandardTableError, match="e3_10_1.json rows do not"):
        method_digest.method_digest(basic, vocabulary=None, reviewed_roi_names=None)


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
    before = method_digest.method_digest(
        basic, vocabulary=None, reviewed_roi_names=None
    )
    rules = changed()
    monkeypatch.setattr(module, name, lambda: rules)

    assert (
        method_digest.method_digest(basic, vocabulary=None, reviewed_roi_names=None)
        != before
    )


def test_the_action_for_text_that_no_rule_covers_changes_the_digest(basic, monkeypatch):
    before = method_digest.method_digest(
        basic, vocabulary=None, reviewed_roi_names=None
    )
    monkeypatch.setattr(supplementary_actions, "UNCOVERED_TEXT_ACTION", "X")

    assert (
        method_digest.method_digest(basic, vocabulary=None, reviewed_roi_names=None)
        != before
    )


def test_the_canonical_form_records_that_there_are_no_user_rules(basic):
    canonical = method_digest.canonical_bytes(
        basic, method_digest.digest_inputs(vocabulary=None, reviewed_roi_names=None)
    )

    assert json.loads(canonical)["l3_rules"] is None


def test_adding_or_removing_a_vocabulary_or_changing_its_entries_changes_the_digest(
    basic,
):
    digests = [
        method_digest.method_digest(
            basic, vocabulary=vocabulary, reviewed_roi_names=None
        )
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

    assert (
        method_digest.digest_inputs(
            vocabulary=VOCABULARY, reviewed_roi_names=None
        ).vocabulary
        == recorded
    )
    assert method_digest.method_digest(
        basic, vocabulary=renamed, reviewed_roi_names=None
    ) == method_digest.method_digest(
        basic, vocabulary=VOCABULARY, reviewed_roi_names=None
    )


def test_the_parameters_of_generated_values_are_those_of_each_generated_value():
    generated = method_digest.digest_inputs(
        vocabulary=None, reviewed_roi_names=None
    ).generated_values

    assert set(generated) == set(GENERATED_VALUE_CHANGES)
    for name, (module, _) in GENERATED_VALUE_CHANGES.items():
        assert generated[name] is getattr(module, name.rpartition(".")[2])


@pytest.mark.parametrize("name", list(GENERATED_VALUE_CHANGES))
def test_any_parameter_of_generated_values_changes_the_digest(basic, monkeypatch, name):
    before = method_digest.method_digest(
        basic, vocabulary=None, reviewed_roi_names=None
    )
    module, value = GENERATED_VALUE_CHANGES[name]
    monkeypatch.setattr(module, name.rpartition(".")[2], value)

    assert (
        method_digest.method_digest(basic, vocabulary=None, reviewed_roi_names=None)
        != before
    )


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

    assert method_digest.canonical_bytes(
        SYNTHETIC_POLICY, changed
    ) != method_digest.canonical_bytes(SYNTHETIC_POLICY, SYNTHETIC_INPUTS)


def test_the_canonical_form_holds_the_inputs_of_the_method_and_nothing_else(basic):
    inputs = method_digest.digest_inputs(vocabulary=None, reviewed_roi_names=None)

    assert set(json.loads(method_digest.canonical_bytes(basic, inputs))) == (
        CANONICAL_MEMBERS
    )
    assert {field.name for field in dataclasses.fields(inputs)} == (
        CANONICAL_MEMBERS - {"format", "policy", "l3_rules"}
    )


def _change_runtime(monkeypatch, name):
    """Change one value of the runtime environment, as an upgrade would."""
    module, attribute, candidates = RUNTIME_CHANGES[name]
    if isinstance(module, str):
        module = importlib.import_module(module)
    current = getattr(module, attribute)
    is_function = callable(current)
    now = current() if is_function else current
    other = next(value for value in candidates if value != now)
    monkeypatch.setattr(module, attribute, (lambda: other) if is_function else other)
    changed = getattr(module, attribute)
    assert (changed() if is_function else changed) == other


@pytest.mark.parametrize(
    "names",
    [[name] for name in RUNTIME_CHANGES] + [list(RUNTIME_CHANGES)],
    ids=[*RUNTIME_CHANGES, "all"],
)
def test_python_and_library_versions_leave_the_digest_unchanged(
    basic, monkeypatch, read_again, names
):
    before = method_digest.method_digest(
        basic, vocabulary=VOCABULARY, reviewed_roi_names=None
    )
    for name in names:
        _change_runtime(monkeypatch, name)
    read_again()

    assert (
        method_digest.method_digest(
            basic, vocabulary=VOCABULARY, reviewed_roi_names=None
        )
        == before
    )


def test_every_module_rule_file_and_table_of_the_engine_is_covered():
    files = method_digest.digest_inputs(vocabulary=None, reviewed_roi_names=None).files
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

    assert {"__init__.py", "method_digest.py"} | rule_files | tables | modules <= set(
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
    monkeypatch.setattr(method_digest, "PACKAGE_DIR", engine)
    before = method_digest.method_digest(
        basic, vocabulary=None, reviewed_roi_names=None
    )
    change(engine)
    read_again()

    assert (
        method_digest.method_digest(basic, vocabulary=None, reviewed_roi_names=None)
        != before
    )


def test_every_file_of_the_engine_other_than_caches_has_a_covered_type():
    package = method_digest.PACKAGE_DIR
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
        if pathlib.PurePosixPath(name).suffix not in method_digest.COVERED_SUFFIXES
    )

    assert not uncovered, "the method digest does not cover these types of file"
    assert (
        set(method_digest.digest_inputs(vocabulary=None, reviewed_roi_names=None).files)
        == expected
    )


def test_every_file_is_covered_when_the_engine_is_installed_below_a_hidden_directory(
    tmp_path, monkeypatch
):
    site_packages = tmp_path / ".venv" / "lib" / "python3.14" / "site-packages"
    engine = _engine(
        site_packages / "pymedphys" / "_dicom" / "deidentify", ENGINE_FILES
    )
    monkeypatch.setattr(method_digest, "PACKAGE_DIR", engine)

    assert set(
        method_digest.digest_inputs(vocabulary=None, reviewed_roi_names=None).files
    ) == set(ENGINE_FILES)


@pytest.mark.parametrize(
    "files, problem",
    [
        (None, "found no source or rule files"),
        ({}, "found no source or rule files"),
        (
            {"notes.txt": b"notes", "__pycache__/method_digest.cpython-313.pyc": b""},
            "found no source or rule files",
        ),
        (
            {n: c for n, c in ENGINE_FILES.items() if n != "method_digest.py"},
            "do not include method_digest.py",
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
    monkeypatch.setattr(method_digest, "PACKAGE_DIR", engine)

    for compute in (
        lambda: method_digest.digest_inputs(vocabulary=None, reviewed_roi_names=None),
        lambda: method_digest.method_digest(
            basic, vocabulary=None, reviewed_roi_names=None
        ),
    ):
        with pytest.raises(method_digest.MethodDigestError, match=problem) as raised:
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
    monkeypatch.setattr(method_digest, "PACKAGE_DIR", engine)
    monkeypatch.setattr(standard, "STANDARD_DIR", tables)
    first = method_digest.method_digest(basic, vocabulary=None, reviewed_roi_names=None)
    edit(engine, tables)

    assert (
        method_digest.method_digest(basic, vocabulary=None, reviewed_roi_names=None)
        == first
    )
    read_again()
    assert (
        method_digest.method_digest(basic, vocabulary=None, reviewed_roi_names=None)
        != first
    )


def test_files_with_crlf_and_lf_line_endings_give_the_same_digest(
    basic, tmp_path, monkeypatch
):
    digests = []
    for newline in (b"\n", b"\r\n"):
        engine = _engine(tmp_path / str(len(newline)), ENGINE_FILES, newline)
        monkeypatch.setattr(method_digest, "PACKAGE_DIR", engine)
        digests.append(
            method_digest.method_digest(basic, vocabulary=None, reviewed_roi_names=None)
        )

    assert (tmp_path / "2" / "policy.py").read_bytes().count(b"\r\n") == 5
    assert digests[0] == digests[1]


def test_caches_and_files_of_other_types_are_not_covered(
    basic, tmp_path, monkeypatch, read_again
):
    engine = _engine(tmp_path, ENGINE_FILES)
    monkeypatch.setattr(method_digest, "PACKAGE_DIR", engine)
    before = method_digest.method_digest(
        basic, vocabulary=None, reviewed_roi_names=None
    )
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

    assert set(
        method_digest.digest_inputs(vocabulary=None, reviewed_roi_names=None).files
    ) == set(ENGINE_FILES)
    assert (
        method_digest.method_digest(basic, vocabulary=None, reviewed_roi_names=None)
        == before
    )


@pytest.mark.parametrize(
    "where, value",
    [
        ("generated_values", 0.5 + 0j),
        ("generated_values", {7: "secret-value"}),
        ("generated_values", True),
        ("l2_rules", 0.5),
        ("l2_rules", b"secret-value"),
        ("l2_rules", {7: "secret-value"}),
    ],
)
def test_a_value_without_a_canonical_form_is_rejected_without_quoting_it(where, value):
    changed = dataclasses.replace(SYNTHETIC_INPUTS, **{where: {"secret-name": value}})

    with pytest.raises(TypeError) as raised:
        method_digest.canonical_bytes(SYNTHETIC_POLICY, changed)

    assert "secret" not in str(raised.value)


def test_text_that_cannot_be_encoded_is_rejected_without_quoting_it():
    changed = dataclasses.replace(SYNTHETIC_INPUTS, engine_version="secret\ud800")

    with pytest.raises(ValueError, match="UTF-8") as raised:
        method_digest.canonical_bytes(SYNTHETIC_POLICY, changed)

    assert "secret" not in str(raised.value)
    assert raised.value.__cause__ is None and raised.value.__suppress_context__


def test_a_vocabulary_whose_entries_cannot_be_encoded_is_rejected_without_quoting_them():
    vocabulary = _vocabulary(_structure("secret\ud800", "Heart"))

    with pytest.raises(ValueError, match="UTF-8") as raised:
        method_digest.digest_inputs(vocabulary=vocabulary, reviewed_roi_names=None)

    assert "secret" not in str(raised.value)


@pytest.mark.parametrize("vocabulary", [(), (None,)], ids=["left-out", "by-position"])
def test_every_call_states_the_vocabulary_by_name(basic, vocabulary):
    with pytest.raises(TypeError, match="vocabulary|positional"):
        method_digest.method_digest(basic, *vocabulary)
    with pytest.raises(TypeError, match="vocabulary|positional"):
        method_digest.digest_inputs(*vocabulary)


def test_only_a_policy_and_a_tg263_vocabulary_are_accepted(basic):
    with pytest.raises(TypeError, match="policy must be"):
        method_digest.method_digest(
            {"preset": "basic"}, vocabulary=None, reviewed_roi_names=None
        )
    with pytest.raises(TypeError, match="policy must be"):
        method_digest.canonical_bytes({"preset": "basic"}, SYNTHETIC_INPUTS)
    with pytest.raises(TypeError, match="vocabulary must be"):
        method_digest.method_digest(
            basic, vocabulary=["Heart"], reviewed_roi_names=None
        )


# The members of the synthetic canonical form whose digests a release report
# records, cut from the bytes above, and their SHA-256, computed with
# `printf '%s' '<bytes>' | sha256sum`, independently of the code under test.
SYNTHETIC_L2_RULES_BYTES = (
    '{"uid_roles.toml":{'
    '"acknowledgement":"DICOM PS3.6 2026d, © NEMA",'
    '"note":"Kept \\"as is\\".\\t\\u0001",'
    '"rules":{"(0008,0018)":"instance"}}}'
).encode("utf-8")
SYNTHETIC_L2_RULES_SHA256 = (
    "35707b0a77e39141f75ab156f70c350ed4259372d79855eb667c520b29426368"
)
SYNTHETIC_GENERATED_VALUES_BYTES = (
    '{"dates.MIN_OFFSET_WEEKS":["int",52],'
    '"dummy_values.CONSTANTS":["map",{"FL":["list",'
    '[["float","0x0.0p+0"],["float","0x1.0000000000000p+0"]]]}],'
    '"keys.DERIVATION_VERSION":["bytes","70796d6564706879732d646569642f31"],'
    '"keys.DOMAINS":["set",[["str","patient"],["str","uid"]]],'
    '"uids.UID_NAMESPACE":["uuid","6f71d76c-0573-58b6-bfda-7c5b4ee304f1"],'
    '"uids.UID_ROOT":["str","2.25."]}'
).encode("utf-8")
SYNTHETIC_GENERATED_VALUES_SHA256 = (
    "28163a075991f6ffd19f67d57699367356fa66935578b4e10ec4d52f26b5e947"
)

# The structured fields of the method digest that a release report records.
COMPONENT_FIELDS = (
    "method_digest",
    "method_digest_format",
    "engine_version",
    "table_digests",
    "l2_rules_digest",
    "l3_rules",
    "vocabulary_digest",
    "reviewed_roi_names",
    "generated_values_digest",
    "engine_files",
)


def test_the_components_hold_the_fields_a_release_report_records_in_order():
    fields = dataclasses.fields(method_digest.MethodDigestComponents)

    assert tuple(field.name for field in fields) == COMPONENT_FIELDS


def test_the_components_of_a_small_synthetic_input_are_digests_of_its_members():
    components = method_digest.digest_components(SYNTHETIC_POLICY, SYNTHETIC_INPUTS)

    assert b'"l2_rules":' + SYNTHETIC_L2_RULES_BYTES in SYNTHETIC_CANONICAL_BYTES
    assert (
        b'"generated_values":' + SYNTHETIC_GENERATED_VALUES_BYTES
        in SYNTHETIC_CANONICAL_BYTES
    )
    assert components == method_digest.MethodDigestComponents(
        method_digest=SYNTHETIC_SHA256,
        method_digest_format="pymedphys-deid-method-digest/2",
        engine_version="0.42.0.dev1",
        table_digests={"e1_1.json": "0" * 64},
        l2_rules_digest=SYNTHETIC_L2_RULES_SHA256,
        l3_rules=None,
        vocabulary_digest=None,
        reviewed_roi_names=None,
        generated_values_digest=SYNTHETIC_GENERATED_VALUES_SHA256,
        engine_files={"policy.py": "f" * 64},
    )


def test_the_components_give_the_method_digest_and_record_its_inputs(basic):
    inputs = method_digest.digest_inputs(vocabulary=VOCABULARY, reviewed_roi_names=None)

    components = method_digest.method_digest_components(
        basic, vocabulary=VOCABULARY, reviewed_roi_names=None
    )

    assert components.method_digest == method_digest.method_digest(
        basic, vocabulary=VOCABULARY, reviewed_roi_names=None
    )
    assert components.method_digest_format == method_digest.FORMAT
    assert components.engine_version == inputs.engine_version == _version.__version__
    assert dict(components.table_digests) == dict(inputs.tables)
    assert components.l3_rules is None
    assert components.vocabulary_digest == inputs.vocabulary
    assert components.reviewed_roi_names is inputs.reviewed_roi_names is None
    assert dict(components.engine_files) == dict(inputs.files)


def test_the_member_digests_are_the_sha256_of_those_members_of_the_canonical_form(
    basic,
):
    document = json.loads(
        method_digest.canonical_bytes(
            basic, method_digest.digest_inputs(vocabulary=None, reviewed_roi_names=None)
        )
    )

    def sha256(member):
        text = json.dumps(
            document[member], sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    components = method_digest.method_digest_components(
        basic, vocabulary=None, reviewed_roi_names=None
    )

    assert components.l2_rules_digest == sha256("l2_rules")
    assert components.generated_values_digest == sha256("generated_values")


def _components_after(basic, monkeypatch, change):
    """Return which components differ after ``change``, besides the digest."""
    before = method_digest.method_digest_components(
        basic, vocabulary=None, reviewed_roi_names=None
    )
    vocabulary = change(monkeypatch)
    _forget_reads()
    after = method_digest.method_digest_components(
        basic, vocabulary=vocabulary, reviewed_roi_names=None
    )
    assert after.method_digest != before.method_digest
    return {
        name
        for name in COMPONENT_FIELDS
        if name != "method_digest" and getattr(after, name) != getattr(before, name)
    }


def _change_engine_version(monkeypatch):
    monkeypatch.setattr(_version, "__version__", _version.__version__ + "+local")


def _change_l2_rule(monkeypatch):
    monkeypatch.setattr(supplementary_actions, "UNCOVERED_TEXT_ACTION", "X")


def _change_generated_value(monkeypatch):
    monkeypatch.setattr(dates, "MIN_OFFSET_WEEKS", dates.MIN_OFFSET_WEEKS + 1)


def _add_vocabulary(_monkeypatch):
    return VOCABULARY


@pytest.mark.parametrize(
    "change, differs",
    [
        (_change_engine_version, {"engine_version"}),
        (_change_l2_rule, {"l2_rules_digest"}),
        (_change_generated_value, {"generated_values_digest"}),
        (_add_vocabulary, {"vocabulary_digest"}),
    ],
    ids=["engine-version", "l2-rule", "generated-value", "vocabulary"],
)
def test_the_components_show_which_input_changed_the_digest(
    basic, monkeypatch, change, differs
):
    assert _components_after(basic, monkeypatch, change) == differs


def test_a_changed_table_shows_in_its_table_digest_and_its_file_digest(
    basic, tmp_path, monkeypatch
):
    modules = {n: c for n, c in ENGINE_FILES.items() if not n.startswith("_standard/")}
    engine = _engine(tmp_path / "engine", modules)
    tables = _copied_tables(engine)
    monkeypatch.setattr(method_digest, "PACKAGE_DIR", engine)
    monkeypatch.setattr(standard, "STANDARD_DIR", tables)

    def reverse_rows(_monkeypatch):
        path = tables / "e1_1.json"
        _rewrite(path, json.loads(path.read_text(encoding="utf-8"))["rows"][::-1])

    assert _components_after(basic, monkeypatch, reverse_rows) == {
        "table_digests",
        "engine_files",
    }


def test_a_changed_engine_file_shows_only_in_the_engine_files(
    basic, tmp_path, monkeypatch
):
    engine = _engine(tmp_path / "engine", ENGINE_FILES)
    monkeypatch.setattr(method_digest, "PACKAGE_DIR", engine)
    before = method_digest.method_digest_components(
        basic, vocabulary=None, reviewed_roi_names=None
    )

    def edit_policy(_monkeypatch):
        (engine / "policy.py").write_bytes(b"ACTION = 'Z'\n")

    assert _components_after(basic, monkeypatch, edit_policy) == {"engine_files"}
    after = method_digest.method_digest_components(
        basic, vocabulary=None, reviewed_roi_names=None
    )
    assert {
        path
        for path in after.engine_files
        if after.engine_files[path] != before.engine_files[path]
    } == {"policy.py"}


def test_the_policy_shows_only_in_the_method_digest(basic):
    custom = policy.compose_custom_policy(("clean_descriptors",))
    before = method_digest.method_digest_components(
        basic, vocabulary=None, reviewed_roi_names=None
    )
    after = method_digest.method_digest_components(
        custom, vocabulary=None, reviewed_roi_names=None
    )

    assert after.method_digest != before.method_digest
    assert dataclasses.replace(after, method_digest=before.method_digest) == before


def test_the_components_are_read_only(basic):
    components = method_digest.method_digest_components(
        basic, vocabulary=None, reviewed_roi_names=None
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        components.method_digest = "0" * 64  # type: ignore[misc]
    with pytest.raises(TypeError):
        components.table_digests["e1_1.json"] = "0" * 64  # type: ignore[index]
    with pytest.raises(TypeError):
        components.engine_files["policy.py"] = "0" * 64  # type: ignore[index]


@pytest.mark.parametrize("vocabulary", [(), (None,)], ids=["left-out", "by-position"])
def test_the_components_take_the_vocabulary_by_name(basic, vocabulary):
    with pytest.raises(TypeError, match="vocabulary|positional"):
        method_digest.method_digest_components(basic, *vocabulary)


def test_the_components_take_only_a_policy():
    with pytest.raises(TypeError, match="policy must be"):
        method_digest.method_digest_components(
            {"preset": "basic"}, vocabulary=None, reviewed_roi_names=None
        )
    with pytest.raises(TypeError, match="policy must be"):
        method_digest.digest_components({"preset": "basic"}, SYNTHETIC_INPUTS)


# A keyed digest of a reviewed-names list, as ReviewedNames.keyed_digest gives.
REVIEWED_ROI_NAMES = "4247e696d65fef56fae5a25e8b7e2ffc5f81727a0a44395ca29acdc48df4d667"


def test_the_reviewed_names_digest_is_an_input_that_shows_only_in_its_component(
    basic,
):
    before = method_digest.method_digest_components(
        basic, vocabulary=None, reviewed_roi_names=None
    )

    after = method_digest.method_digest_components(
        basic, vocabulary=None, reviewed_roi_names=REVIEWED_ROI_NAMES
    )

    assert after.reviewed_roi_names == REVIEWED_ROI_NAMES
    assert after.method_digest != before.method_digest
    assert after.method_digest == method_digest.method_digest(
        basic, vocabulary=None, reviewed_roi_names=REVIEWED_ROI_NAMES
    )
    assert (
        dataclasses.replace(
            after, method_digest=before.method_digest, reviewed_roi_names=None
        )
        == before
    )
    assert before.reviewed_roi_names is None


def test_a_different_reviewed_names_digest_gives_a_different_method_digest(basic):
    digests = {
        method_digest.method_digest(
            basic, vocabulary=None, reviewed_roi_names=reviewed_roi_names
        )
        for reviewed_roi_names in (None, REVIEWED_ROI_NAMES, "0" * 64, "f" * 64)
    }

    assert len(digests) == 4


def test_the_canonical_form_holds_the_reviewed_names_digest_as_given(basic):
    inputs = method_digest.digest_inputs(
        vocabulary=None, reviewed_roi_names=REVIEWED_ROI_NAMES
    )

    document = json.loads(method_digest.canonical_bytes(basic, inputs))

    assert document["reviewed_roi_names"] == REVIEWED_ROI_NAMES
    assert (
        json.loads(
            method_digest.canonical_bytes(
                basic,
                method_digest.digest_inputs(vocabulary=None, reviewed_roi_names=None),
            )
        )["reviewed_roi_names"]
        is None
    )


@pytest.mark.parametrize(
    "reviewed_roi_names",
    ["A" * 64, "0" * 63, "0" * 65, " " + "0" * 63, "SENTINEL" * 8, b"0" * 64, 0],
)
def test_the_reviewed_names_digest_must_be_64_lowercase_hexadecimal_digits(
    basic, reviewed_roi_names
):
    with pytest.raises((TypeError, ValueError), match="reviewed_roi_names") as raised:
        method_digest.digest_inputs(
            vocabulary=None, reviewed_roi_names=reviewed_roi_names
        )
    with pytest.raises((TypeError, ValueError), match="reviewed_roi_names"):
        method_digest.method_digest(
            basic, vocabulary=None, reviewed_roi_names=reviewed_roi_names
        )

    assert "SENTINEL" not in str(raised.value) and "AAAA" not in str(raised.value)


def test_every_call_states_the_reviewed_names_digest_by_name(basic):
    with pytest.raises(TypeError, match="reviewed_roi_names"):
        method_digest.digest_inputs(vocabulary=None)  # type: ignore[call-arg]
    with pytest.raises(TypeError, match="reviewed_roi_names"):
        method_digest.method_digest(basic, vocabulary=None)  # type: ignore[call-arg]
    with pytest.raises(TypeError, match="reviewed_roi_names"):
        method_digest.method_digest_components(  # type: ignore[call-arg]
            basic, vocabulary=None
        )
    with pytest.raises(TypeError, match="positional"):
        method_digest.digest_inputs(None, REVIEWED_ROI_NAMES)  # type: ignore[misc]
    with pytest.raises(TypeError, match="positional"):
        method_digest.method_digest(basic, None, REVIEWED_ROI_NAMES)  # type: ignore[misc]
