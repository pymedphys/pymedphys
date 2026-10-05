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
that the report holds none of it. Ordinary tests share the engine's files
and tables, which are read once per process. Each synthetic engine uses its
own directory, and cached reads are cleared at each module boundary.
"""

import dataclasses
import json
import pathlib
import random
import shutil
import types

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    method_digest,
    policy,
    reference_graph,
    release_report,
    residuals,
    runtime,
    scope,
    source,
    standard,
    walker,
)
from pymedphys._dicom.deidentify.file_layout import ElementPath
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


@pytest.fixture(autouse=True, scope="module")
def _read_again():
    """Start and end this module with the engine's files and tables unread."""
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
    report = release_report.release_report(basic, vocabulary=None)

    assert report.policy == release_report.PolicyRecord(
        preset="basic", edition=basic.edition, options=(), claims_conformance=True
    )
    assert report.method == method_digest.method_digest_components(
        basic, vocabulary=None
    )
    assert report.runtime == runtime.runtime_environment()


@pytest.mark.parametrize("preset", list(policy.PRESETS))
def test_the_policy_section_names_the_edition_preset_and_options(preset):
    composed = policy.compose_policy(preset)

    document = release_report.report_document(
        release_report.release_report(composed, vocabulary=None)
    )

    assert document["policy"] == {
        "preset": preset,
        "edition": composed.edition,
        "options": list(policy.PRESETS[preset]),
        "claims_conformance": preset != "tps-import",
    }


def test_a_custom_option_set_has_no_preset():
    custom = policy.compose_custom_policy(("clean_descriptors",))

    report = release_report.release_report(custom, vocabulary=None)

    assert report.policy.preset is None
    assert report.policy.options == ("clean_descriptors",)


def test_the_document_has_the_sections_and_fields_the_design_lists(basic):
    document = release_report.report_document(
        release_report.release_report(basic, vocabulary=None)
    )

    assert list(document) == [
        "format",
        "policy",
        "method",
        "runtime",
        "sequestered",
        "search_coverage",
    ]
    assert document["format"] == "pymedphys-deid-release-report/2"
    assert list(document["policy"]) == POLICY_FIELDS
    assert list(document["method"]) == METHOD_FIELDS
    assert list(document["runtime"]) == RUNTIME_FIELDS


def test_the_method_section_holds_the_digest_and_its_components(basic):
    vocabulary = _vocabulary("Heart", "Lung_L")
    components = method_digest.method_digest_components(basic, vocabulary=vocabulary)

    document = release_report.report_document(
        release_report.release_report(basic, vocabulary=vocabulary)
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
        basic, vocabulary=vocabulary
    )
    assert document["method"]["l3_rules"] is None


def test_the_runtime_section_holds_the_values_of_software_versions(basic):
    environment = runtime.runtime_environment()

    section = release_report.report_document(
        release_report.release_report(basic, vocabulary=None)
    )["runtime"]

    assert section == dataclasses.asdict(environment)
    assert (
        section["pymedphys_version"],
        f"{section['python_implementation']} {section['python_version']}",
        f"pydicom {section['pydicom_version']}",
        f"tomlkit {section['tomlkit_version']}",
    ) == environment.software_versions


def test_the_json_is_the_document_and_the_same_report_gives_the_same_text(basic):
    report = release_report.release_report(basic, vocabulary=None)

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

    text = release_report.to_json(release_report.release_report(basic, vocabulary=None))

    assert SENTINEL not in text and "SENTINEL" not in text
    assert str(tmp_path) not in text and tmp_path.as_posix() not in text
    assert set(json.loads(text)["method"]["engine_files"]) == {
        *ENGINE_FILES,
        *(f"_standard/{path.name}" for path in (engine / "_standard").glob("*.json")),
    }


def test_the_report_holds_no_path_of_the_running_engine_or_home(basic):
    text = release_report.to_json(release_report.release_report(basic, vocabulary=None))

    for directory in (method_digest.PACKAGE_DIR, pathlib.Path.home()):
        assert str(directory) not in text and directory.as_posix() not in text


def test_the_report_holds_the_vocabulary_digest_not_its_entries(basic):
    vocabulary = _vocabulary("Heart", SENTINEL_ROI)

    text = release_report.to_json(
        release_report.release_report(basic, vocabulary=vocabulary)
    )

    assert SENTINEL_ROI not in text and "Sentinel" not in text
    assert json.loads(text)["method"]["vocabulary_digest"] == (
        method_digest.digest_inputs(vocabulary=vocabulary).vocabulary
    )


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
    report = change(release_report.release_report(basic, vocabulary=None))

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
        release_report.release_report({"preset": "basic"}, vocabulary=None)


# D-026, as the maintainer decided on 2 October 2026: a sequestered instance
# is named by a random per-run label, which only the QC pack maps to its
# source.
def _sequestered(label="S-0001"):
    rule = walker.Sequestration(
        ElementPath((("(0010,1002)", 3),), "(0010,0020)"),
        "D",
        "SQ",
        walker.SequesterReason.NO_DUMMY_VALUE,
    )
    return release_report.SequesteredInstance(
        label,
        (
            release_report.sequestration_reason(
                reference_graph.FindingKind.CONFLICTING_INSTANCE
            ),
            release_report.sequestration_reason(rule),
        ),
    )


def test_sequestered_instances_are_listed_by_label_with_their_reasons(basic):
    report = release_report.release_report(
        basic,
        vocabulary=None,
        sequestered=(_sequestered("S-0002"), _sequestered("S-0001")),
    )
    document = release_report.report_document(report)

    assert [entry["label"] for entry in document["sequestered"]] == [
        "S-0001",
        "S-0002",
    ]
    assert document["sequestered"][0]["reasons"] == [
        # Only the walker names a place.
        {"stage": "references", "code": "conflicting-instance"},
        {
            # The attribute's tags, without the item that held it.
            "stage": "walker",
            "code": "no-dummy-value",
            "attribute": "(0010,1002) > (0010,0020)",
            "action": "D",
            "vr": "SQ",
        },
    ]


def test_a_reason_given_twice_is_listed_once(basic):
    instance = _sequestered()
    twice = dataclasses.replace(instance, reasons=instance.reasons * 2)
    report = release_report.release_report(basic, vocabulary=None, sequestered=(twice,))

    (entry,) = release_report.report_document(report)["sequestered"]
    assert len(entry["reasons"]) == 2


_SEQUESTERING = [
    *(
        (each, "scope")
        for each in scope.Disposition
        if each is not scope.Disposition.SUPPORTED
    ),
    *((each, "admission") for each in source.SourceReason),
    (reference_graph.FindingKind.MISSING_IDENTIFIER, "references"),
    (reference_graph.FindingKind.CONFLICTING_INSTANCE, "references"),
    (reference_graph.FindingKind.SERIES_IN_SEVERAL_STUDIES, "references"),
]


@pytest.mark.parametrize(
    "cause, stage", _SEQUESTERING, ids=[str(each) for each, _ in _SEQUESTERING]
)
def test_each_stage_that_sequesters_gives_its_reason_code(basic, cause, stage):
    reason = release_report.sequestration_reason(cause)

    assert (reason.stage, reason.code) == (stage, cause.value)
    assert (reason.attribute, reason.action, reason.vr) == (None, None, None)
    report = release_report.release_report(
        basic,
        vocabulary=None,
        sequestered=(release_report.SequesteredInstance("S-0001", (reason,)),),
    )
    assert release_report.report_document(report)["sequestered"][0]["reasons"] == [
        {"stage": stage, "code": cause.value}
    ]


@pytest.mark.parametrize("reason", list(walker.SequesterReason))
def test_each_walker_reason_is_written(basic, reason):
    cause = walker.Sequestration(ElementPath((), "(0010,0020)"), "X", None, reason)
    report = release_report.release_report(
        basic,
        vocabulary=None,
        sequestered=(
            release_report.SequesteredInstance(
                "S-0001", (release_report.sequestration_reason(cause),)
            ),
        ),
    )

    assert release_report.report_document(report)["sequestered"][0]["reasons"] == [
        {
            "stage": "walker",
            "code": reason.value,
            "attribute": "(0010,0020)",
            "action": "X",
            "vr": None,
        }
    ]


@pytest.mark.parametrize(
    "cause",
    [
        scope.Disposition.SUPPORTED,
        reference_graph.FindingKind.DANGLING_REFERENCE,
        reference_graph.FindingKind.DUPLICATE_INSTANCE,
        reference_graph.FindingKind.STUDY_WITH_SEVERAL_PATIENTS,
        "SENTINEL",
    ],
)
def test_what_does_not_sequester_an_instance_is_not_a_reason(cause):
    # A study with several patients stops the run instead.
    with pytest.raises((TypeError, ValueError)) as raised:
        release_report.sequestration_reason(cause)

    assert "SENTINEL" not in str(raised.value)


def test_labels_are_random_and_carry_nothing_from_the_run():
    first = release_report.sequestration_labels(12, rng=random.Random(1))
    second = release_report.sequestration_labels(12, rng=random.Random(2))

    assert sorted(first) == sorted(second) == [f"S-{n:04d}" for n in range(1, 13)]
    assert first != second
    assert first != tuple(sorted(first))
    assert not release_report.sequestration_labels(0)
    assert release_report.sequestration_labels(12345)[0].startswith("S-")
    assert {len(label) for label in release_report.sequestration_labels(12345)} == {7}


def test_labels_are_drawn_from_the_operating_system_by_default(monkeypatch):
    drawn = []

    class Recording(random.Random):
        def shuffle(self, x):  # pylint: disable=arguments-differ
            drawn.append(list(x))
            x.reverse()

    monkeypatch.setattr(release_report.secrets, "SystemRandom", Recording)

    assert release_report.sequestration_labels(3) == ("S-0003", "S-0002", "S-0001")
    assert drawn == [["S-0001", "S-0002", "S-0003"]]


# D-027, as the maintainer decided on 2 October 2026: the report counts what
# the residual search did not search, by attribute and reason, and the QC
# pack lists each by instance and place.
def test_values_not_searched_are_counted_by_attribute_and_reason(basic):
    name = ElementPath((), "(0010,0010)")
    nested = ElementPath((("(0010,1002)", 0),), "(0010,0020)")
    short_word = residuals.NotSearched(
        name, "PN", residuals.Form.NAME_WORD, residuals.Omission.TOO_SHORT
    )
    coverage = release_report.search_coverage(
        [
            [
                # Two forms of one value count as one value.
                short_word,
                residuals.NotSearched(
                    name,
                    "PN",
                    residuals.Form.NAME_COMPONENT,
                    residuals.Omission.TOO_SHORT,
                ),
                residuals.NotSearched(
                    ElementPath((("(0010,1002)", 1),), "(0010,0020)"),
                    "LO",
                    residuals.Form.VALUE,
                    residuals.Omission.TOO_SHORT,
                ),
                residuals.Unsearched(nested, residuals.UnsearchedReason.UNDECODABLE),
                residuals.Unsearched(name, residuals.UnsearchedReason.RETAINED),
            ],
            # The same place in another instance is another value.
            [short_word],
        ]
    )
    report = release_report.release_report(basic, vocabulary=None, coverage=coverage)

    assert release_report.report_document(report)["search_coverage"] == [
        {"attribute": "(0010,0010)", "reason": "retained", "count": 1},
        {"attribute": "(0010,0010)", "reason": "too-short", "count": 2},
        {"attribute": "(0010,1002) > (0010,0020)", "reason": "too-short", "count": 1},
        {"attribute": "(0010,1002) > (0010,0020)", "reason": "undecodable", "count": 1},
    ]


@pytest.mark.parametrize(
    "records",
    [
        residuals.Unsearched(
            ElementPath((), "(0010,0010)"), residuals.UnsearchedReason.RETAINED
        ),
        ["SENTINEL"],
    ],
    ids=["not-by-instance", "not-a-record"],
)
def test_coverage_needs_records_by_instance(records):
    with pytest.raises(TypeError) as raised:
        release_report.search_coverage([records])

    assert "SENTINEL" not in str(raised.value)


class _Text(str):
    pass


def _with(report, **changes):
    return dataclasses.replace(report, **changes)


def _reason(**changes):
    return dataclasses.replace(_sequestered().reasons[1], **changes)


def _instance(*reasons, label="S-0001"):
    return release_report.SequesteredInstance(label, reasons)


@pytest.mark.parametrize(
    "change, field",
    [
        (
            lambda r: _with(r, sequestered=(_sequestered("SENTINEL"),)),
            "label",
        ),
        (
            lambda r: _with(r, sequestered=(_sequestered(), _sequestered())),
            "label",
        ),
        (
            lambda r: _with(
                r,
                sequestered=(
                    release_report.SequesteredInstance(
                        "S-0001", (_reason(code="SENTINEL"),)
                    ),
                ),
            ),
            "code",
        ),
        (
            lambda r: _with(
                r,
                sequestered=(
                    release_report.SequesteredInstance(
                        "S-0001", (_reason(stage="SENTINEL"),)
                    ),
                ),
            ),
            "stage",
        ),
        (
            lambda r: _with(
                r,
                sequestered=(
                    release_report.SequesteredInstance(
                        "S-0001", (_reason(attribute="/SENTINEL/path"),)
                    ),
                ),
            ),
            "attribute",
        ),
        (
            lambda r: _with(
                r,
                sequestered=(
                    release_report.SequesteredInstance(
                        "S-0001", (_reason(action="SENTINEL"),)
                    ),
                ),
            ),
            "action",
        ),
        (
            lambda r: _with(
                r,
                sequestered=(
                    release_report.SequesteredInstance(
                        "S-0001", (_reason(vr="SENTINEL"),)
                    ),
                ),
            ),
            "vr",
        ),
        (
            lambda r: _with(
                r, sequestered=(release_report.SequesteredInstance("S-0001", ()),)
            ),
            "reasons",
        ),
        (lambda r: _with(r, sequestered=(_instance("SENTINEL"),)), "reasons"),
        (lambda r: _with(r, sequestered=("SENTINEL",)), "sequestered"),
        (lambda r: _with(r, sequestered=(_sequestered("S-0002"),)), "label"),
        (lambda r: _with(r, sequestered=(_sequestered("S-001"),)), "label"),
        (lambda r: _with(r, sequestered=(_sequestered(_Text("S-0001")),)), "label"),
        (
            lambda r: _with(
                r, sequestered=(_instance(_reason(code=_Text("no-dummy-value"))),)
            ),
            "code",
        ),
        (
            lambda r: _with(
                r,
                sequestered=(
                    _instance(
                        dataclasses.replace(
                            release_report.sequestration_reason(
                                scope.Disposition.UNSUPPORTED_IOD
                            ),
                            attribute="(0010,0010)",
                        )
                    ),
                ),
            ),
            "attribute",
        ),
        (
            lambda r: _with(r, sequestered=(_instance(_reason(attribute=None)),)),
            "attribute",
        ),
        (lambda r: _with(r, search_coverage=("SENTINEL",)), "search_coverage"),
        (
            lambda r: _with(
                r,
                search_coverage=(
                    release_report.SearchCoverage("SENTINEL^Margaret", "too-short", 1),
                ),
            ),
            "attribute",
        ),
        (
            lambda r: _with(
                r,
                search_coverage=(
                    release_report.SearchCoverage("(0010,0010)", "SENTINEL", 1),
                ),
            ),
            "reason",
        ),
        (
            lambda r: _with(
                r,
                search_coverage=(
                    release_report.SearchCoverage("(0010,0010)", "too-short", 0),
                ),
            ),
            "count",
        ),
        (
            lambda r: _with(
                r,
                search_coverage=(
                    release_report.SearchCoverage("(0010,0010)", "too-short", True),
                ),
            ),
            "count",
        ),
    ],
    ids=[
        "label",
        "repeated-label",
        "code",
        "stage",
        "attribute",
        "action",
        "vr",
        "no-reason",
        "not-a-reason",
        "not-an-instance",
        "label-gap",
        "label-width",
        "label-subclass",
        "code-subclass",
        "place-for-another-stage",
        "walker-without-place",
        "not-coverage",
        "coverage-attribute",
        "coverage-reason",
        "zero-count",
        "boolean-count",
    ],
)
def test_a_run_section_with_a_field_that_could_hold_a_value_is_refused(
    basic, change, field
):
    report = change(release_report.release_report(basic, vocabulary=None))

    for write in (release_report.report_document, release_report.to_json):
        with pytest.raises(release_report.ReleaseReportError, match=field) as raised:
            write(report)
        assert "SENTINEL" not in str(raised.value)
        assert raised.value.__cause__ is None
