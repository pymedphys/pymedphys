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

The sentinel tests put recognisable text where a report could leak it, in
the path of the installed engine and in the vocabulary's entries, and check
that the report holds none of it. The engine's files and tables are read once
per process, so each test starts and ends with them unread.
"""

import dataclasses
import json
import pathlib
import shutil
import types

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    method_digest,
    policy,
    release_report,
    runtime,
    standard,
)
from pymedphys._nomenclature import tg263

# The method section's fields, as the design's method digest decision lists
# them, and the runtime section's, as its runtime environments decision does.
METHOD_FIELDS = [
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
]
RUNTIME_FIELDS = [
    "pymedphys_version",
    "python_implementation",
    "python_version",
    "pydicom_version",
    "tomlkit_version",
]
POLICY_FIELDS = ["preset", "edition", "options", "claims_conformance"]

# Text that must never reach a report: a person name and an ROI name of the
# kind a site's vocabulary or an installation path could hold.
SENTINEL = "SENTINEL^Margaret"
SENTINEL_ROI = "SentinelTumourMcAllister"

ENGINE_FILES = {
    "__init__.py": b'"""A package."""\n',
    "method_digest.py": b'FORMAT = "digest/1"\n',
    "policy.py": b"ACTION = 'X'\n",
}


@pytest.fixture(name="basic", scope="module")
def _basic():
    return policy.compose_policy("basic")


@pytest.fixture(autouse=True)
def _read_again():
    """Start and end each test with the engine's files and tables unread."""
    # pylint: disable = protected-access
    method_digest._file_digests.cache_clear()
    method_digest._table_digests.cache_clear()
    yield
    method_digest._file_digests.cache_clear()
    method_digest._table_digests.cache_clear()


def _vocabulary(*names):
    structures = tuple(
        tg263.Structure(
            target_type="Anatomic",
            major_category="Thorax",
            minor_category="",
            anatomic_group="",
            primary_name=name,
            reverse_order_name=name,
            description="",
            fma_id=None,
        )
        for name in names
    )
    return tg263.Nomenclature(
        source=tg263.Source(file="invented.xls", sha256="0" * 64, sheet="Invented"),
        attribution=tg263.ATTRIBUTION,
        structures=structures,
    )


def test_the_report_records_the_policy_the_method_and_the_runtime(basic):
    report = release_report.release_report(
        basic, vocabulary=None, reviewed_roi_names=None
    )

    assert report.policy == release_report.PolicyRecord(
        preset="basic", edition=basic.edition, options=(), claims_conformance=True
    )
    assert report.method == method_digest.method_digest_components(
        basic, vocabulary=None, reviewed_roi_names=None
    )
    assert report.runtime == runtime.runtime_environment()


@pytest.mark.parametrize("preset", list(policy.PRESETS))
def test_the_policy_section_names_the_edition_preset_and_options(preset):
    composed = policy.compose_policy(preset)

    document = release_report.report_document(
        release_report.release_report(
            composed, vocabulary=None, reviewed_roi_names=None
        )
    )

    assert document["policy"] == {
        "preset": preset,
        "edition": composed.edition,
        "options": list(policy.PRESETS[preset]),
        "claims_conformance": preset != "tps-import",
    }


def test_a_custom_option_set_has_no_preset():
    custom = policy.compose_custom_policy(("clean_descriptors",))

    report = release_report.release_report(
        custom, vocabulary=None, reviewed_roi_names=None
    )

    assert report.policy.preset is None
    assert report.policy.options == ("clean_descriptors",)


def test_the_document_has_the_sections_and_fields_the_design_lists(basic):
    document = release_report.report_document(
        release_report.release_report(basic, vocabulary=None, reviewed_roi_names=None)
    )

    assert list(document) == ["format", "policy", "method", "runtime"]
    assert document["format"] == "pymedphys-deid-release-report/2"
    assert list(document["policy"]) == POLICY_FIELDS
    assert list(document["method"]) == METHOD_FIELDS
    assert list(document["runtime"]) == RUNTIME_FIELDS


def test_the_method_section_holds_the_digest_and_its_components(basic):
    vocabulary = _vocabulary("Heart", "Lung_L")
    components = method_digest.method_digest_components(
        basic, vocabulary=vocabulary, reviewed_roi_names=None
    )

    document = release_report.report_document(
        release_report.release_report(
            basic, vocabulary=vocabulary, reviewed_roi_names=None
        )
    )

    assert document["method"] == {
        name: (
            dict(getattr(components, name))
            if name in ("table_digests", "engine_files")
            else getattr(components, name)
        )
        for name in METHOD_FIELDS
    }
    assert document["method"]["method_digest"] == method_digest.method_digest(
        basic, vocabulary=vocabulary, reviewed_roi_names=None
    )
    assert document["method"]["l3_rules"] is None


def test_the_runtime_section_holds_the_values_of_software_versions(basic):
    environment = runtime.runtime_environment()

    section = release_report.report_document(
        release_report.release_report(basic, vocabulary=None, reviewed_roi_names=None)
    )["runtime"]

    assert section == dataclasses.asdict(environment)
    assert (
        section["pymedphys_version"],
        f"{section['python_implementation']} {section['python_version']}",
        f"pydicom {section['pydicom_version']}",
        f"tomlkit {section['tomlkit_version']}",
    ) == environment.software_versions


def test_the_json_is_the_document_and_the_same_report_gives_the_same_text(basic):
    report = release_report.release_report(
        basic, vocabulary=None, reviewed_roi_names=None
    )

    text = release_report.to_json(report)

    assert json.loads(text) == release_report.report_document(report)
    assert text == release_report.to_json(report)
    assert text.endswith("}\n")


def _installed_engine(tmp_path, monkeypatch):
    """Install a synthetic engine below a directory named after a person."""
    engine = tmp_path / SENTINEL / "site-packages" / "pymedphys" / "deidentify"
    for name, content in ENGINE_FILES.items():
        path = engine / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    tables = engine / "_standard"
    shutil.copytree(standard.STANDARD_DIR, tables)
    monkeypatch.setattr(method_digest, "PACKAGE_DIR", engine)
    monkeypatch.setattr(standard, "STANDARD_DIR", tables)
    return engine


def test_the_report_holds_no_path_of_the_installed_engine(basic, tmp_path, monkeypatch):
    engine = _installed_engine(tmp_path, monkeypatch)

    text = release_report.to_json(
        release_report.release_report(basic, vocabulary=None, reviewed_roi_names=None)
    )

    assert SENTINEL not in text and "SENTINEL" not in text
    assert str(tmp_path) not in text and tmp_path.as_posix() not in text
    assert set(json.loads(text)["method"]["engine_files"]) == {
        *ENGINE_FILES,
        *(f"_standard/{path.name}" for path in (engine / "_standard").glob("*.json")),
    }


def test_the_report_holds_no_path_of_the_running_engine_or_home(basic):
    text = release_report.to_json(
        release_report.release_report(basic, vocabulary=None, reviewed_roi_names=None)
    )

    for directory in (method_digest.PACKAGE_DIR, pathlib.Path.home()):
        assert str(directory) not in text and directory.as_posix() not in text


def test_the_report_holds_the_vocabulary_digest_not_its_entries(basic):
    vocabulary = _vocabulary("Heart", SENTINEL_ROI)

    text = release_report.to_json(
        release_report.release_report(
            basic, vocabulary=vocabulary, reviewed_roi_names=None
        )
    )

    assert SENTINEL_ROI not in text and "Sentinel" not in text
    assert json.loads(text)["method"]["vocabulary_digest"] == (
        method_digest.digest_inputs(
            vocabulary=vocabulary, reviewed_roi_names=None
        ).vocabulary
    )


# A keyed digest of a reviewed-names list, as ReviewedNames.keyed_digest gives.
REVIEWED_ROI_NAMES = "4247e696d65fef56fae5a25e8b7e2ffc5f81727a0a44395ca29acdc48df4d667"


def test_the_report_holds_the_reviewed_names_digest_it_was_given(basic):
    report = release_report.release_report(
        basic, vocabulary=None, reviewed_roi_names=REVIEWED_ROI_NAMES
    )

    method = release_report.report_document(report)["method"]

    assert method["reviewed_roi_names"] == REVIEWED_ROI_NAMES
    assert method["method_digest"] == method_digest.method_digest(
        basic, vocabulary=None, reviewed_roi_names=REVIEWED_ROI_NAMES
    )
    assert (
        release_report.report_document(
            release_report.release_report(
                basic, vocabulary=None, reviewed_roi_names=None
            )
        )["method"]["reviewed_roi_names"]
        is None
    )


def test_every_report_states_the_reviewed_names_digest_by_name(basic):
    # This call omits the argument on purpose.
    # pylint: disable = missing-kwoa
    with pytest.raises(TypeError, match="reviewed_roi_names"):
        release_report.release_report(basic, vocabulary=None)  # type: ignore[call-arg]


def _with_method(report, **changes):
    return dataclasses.replace(
        report, method=dataclasses.replace(report.method, **changes)
    )


def _with_runtime(report, **changes):
    return dataclasses.replace(
        report, runtime=dataclasses.replace(report.runtime, **changes)
    )


def _engine_files(report, path):
    files = {**report.method.engine_files, path: "0" * 64}
    return _with_method(report, engine_files=types.MappingProxyType(files))


@pytest.mark.parametrize(
    "change, field",
    [
        (lambda r: _engine_files(r, f"/home/{SENTINEL}/policy.py"), "engine_files"),
        (lambda r: _engine_files(r, f"../{SENTINEL}/policy.py"), "engine_files"),
        (lambda r: _engine_files(r, f"C:\\{SENTINEL}\\policy.py"), "engine_files"),
        (lambda r: _engine_files(r, f".{SENTINEL}/policy.py"), "engine_files"),
        (
            lambda r: _with_method(
                r,
                table_digests={**r.method.table_digests, f"{SENTINEL}.json": "0" * 64},
            ),
            "table_digests",
        ),
        (lambda r: _with_method(r, method_digest=SENTINEL), "method_digest"),
        (lambda r: _with_method(r, vocabulary_digest=SENTINEL), "vocabulary_digest"),
        (lambda r: _with_method(r, l3_rules=SENTINEL), "l3_rules"),
        (
            lambda r: _with_method(r, reviewed_roi_names=SENTINEL),
            "reviewed_roi_names",
        ),
        (
            lambda r: _with_method(r, reviewed_roi_names="A" * 64),
            "reviewed_roi_names",
        ),
        (
            lambda r: _with_method(r, l2_rules_digest="A" * 64),
            "l2_rules_digest",
        ),
        (
            lambda r: _with_method(r, method_digest_format=SENTINEL),
            "method_digest_format",
        ),
        (
            lambda r: _with_method(r, engine_version=f"0.42.0+{SENTINEL}"),
            "engine_version",
        ),
        (
            lambda r: _with_runtime(r, python_version=f"/home/{SENTINEL}"),
            "python_version",
        ),
        (
            lambda r: dataclasses.replace(
                r, policy=dataclasses.replace(r.policy, preset=SENTINEL)
            ),
            "preset",
        ),
        (
            lambda r: dataclasses.replace(
                r, policy=dataclasses.replace(r.policy, preset=[SENTINEL])
            ),
            "preset",
        ),
        (
            lambda r: dataclasses.replace(
                r, policy=dataclasses.replace(r.policy, options=(SENTINEL,))
            ),
            "options",
        ),
        (
            lambda r: dataclasses.replace(
                r, policy=dataclasses.replace(r.policy, edition=SENTINEL)
            ),
            "edition",
        ),
    ],
    ids=[
        "absolute-path",
        "parent-path",
        "windows-path",
        "hidden-path",
        "table-name",
        "digest",
        "vocabulary-digest",
        "l3-rules",
        "reviewed-names-digest",
        "uppercase-reviewed-names-digest",
        "uppercase-digest",
        "format",
        "engine-version",
        "runtime-value",
        "preset",
        "unhashable-preset",
        "options",
        "edition",
    ],
)
def test_a_report_with_a_field_that_could_hold_a_value_or_path_is_refused(
    basic, change, field
):
    report = change(
        release_report.release_report(basic, vocabulary=None, reviewed_roi_names=None)
    )

    for write in (release_report.report_document, release_report.to_json):
        with pytest.raises(release_report.ReleaseReportError, match=field) as raised:
            write(report)
        assert "SENTINEL" not in str(raised.value) and "AAAA" not in str(raised.value)
        assert raised.value.__cause__ is None


@pytest.mark.parametrize("vocabulary", [(), (None,)], ids=["left-out", "by-position"])
def test_every_report_states_the_vocabulary_by_name(basic, vocabulary):
    with pytest.raises(TypeError, match="vocabulary|positional"):
        release_report.release_report(basic, *vocabulary)


def test_only_a_policy_is_accepted():
    with pytest.raises(TypeError, match="policy must be"):
        release_report.release_report(
            {"preset": "basic"}, vocabulary=None, reviewed_roi_names=None
        )
