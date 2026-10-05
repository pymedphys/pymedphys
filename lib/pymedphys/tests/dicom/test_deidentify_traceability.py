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

"""The requirements-to-tests matrix generated from the requirements register."""

import re

from pymedphys._imports import pytest, tomlkit

from pymedphys._dicom.deidentify import requirements, traceability
from pymedphys.cli import define_parser

URL = (
    "https://dicom.nema.org/medical/dicom/current/output/chtml/part15/"
    "chapter_E.html#para_{}-0000-0000-0000-000000000000"
)

PLAIN = "tests/dicom/test_a.py::test_plain"
CASES = "tests/dicom/test_a.py::test_cases"
METHOD = "tests/dicom/test_b.py::TestGroup::test_method"
UNRUN = "tests/dicom/test_b.py::test_unrun"

REGISTER = {
    "schema": "pymedphys-deid-requirements/2",
    "edition": "2026d",
    "acknowledgement": "DICOM PS3.15 2026d, © NEMA",
    "midi_report": "Clunie DA et al., MIDI Task Group report",
    "requirement": [
        {
            "id": "PS3.15-E.1.1-01",
            "url": URL.format("00000001"),
            "text": "Each Attribute shall be retained:\n\n- in ```fences```;\n- or not.",
            "status": "partial",
            "milestone": "M3",
            "decisions": ["D-001", "D-011"],
            "implementation": ["_dicom/deidentify/actions.py"],
            "note": "Remaining: the walker,\nwhich applies `X | Z` (M3).",
        },
        {
            "id": "PS3.15-E.3.9-01",
            "url": URL.format("00000002"),
            "text": "UIDs shall be retained.",
            "status": "out-of-scope",
            "decisions": ["D-003"],
            "note": "Retain UIDs is not supported.",
        },
        {
            "id": "MIDI-BP-06",
            "text": "Use the current edition.",
            "status": "implemented",
            "decisions": ["D-001"],
            "implementation": ["_dicom/deidentify/standard.py"],
        },
        {
            "id": "MIDI-BP-09",
            "text": "Re-identify nobody.",
            "status": "not-applicable",
            "note": "PyMedPhys does not re-identify.",
        },
        {
            "id": "MIDI-BP-10",
            "text": "Plan ahead.",
            "status": "planned",
            "milestone": "M6",
        },
    ],
}


# The tests that cite the register's requirements: PLAIN and CASES cite
# PS3.15-E.1.1-01, and METHOD and UNRUN cite MIDI-BP-06.
CITING_TESTS = {
    "tests/dicom/test_a.py": """
import pytest


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
def test_plain():
    pass


@pytest.mark.deid_requirement("PS3.15-E.1.1-01")
@pytest.mark.parametrize("value", [1, 2])
def test_cases(value):
    pass
""",
    "tests/dicom/test_b.py": """
import pytest


@pytest.mark.deid_requirement("MIDI-BP-06")
class TestGroup:
    def test_method(self):
        pass


@pytest.mark.deid_requirement("MIDI-BP-06")
def test_unrun():
    pass
""",
}


@pytest.fixture(name="register")
def _register(tmp_path):
    for name, source in CITING_TESTS.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(source, encoding="utf-8")
    path = tmp_path / "requirements.toml"
    path.write_text(tomlkit.dumps(REGISTER), encoding="utf-8")
    return requirements.load_requirements(path, requirements.cited_tests(tmp_path))


def _junit(path, *cases):
    """Write a pytest JUnit report of ``(classname, name, child)`` test cases."""
    body = "".join(
        f'<testcase classname="{classname}" name="{name}" time="0.1">{child}</testcase>'
        for classname, name, child in cases
    )
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?><testsuites name="pytest tests">'
        f'<testsuite name="pytest">{body}</testsuite></testsuites>',
        encoding="utf-8",
    )
    return path


FAILURE = '<failure message="assert False">trace</failure>'
ERROR = '<error message="fixture failed">trace</error>'
SKIPPED = '<skipped type="pytest.skip" message="no data">reason</skipped>'

MODULE_A = "lib.pymedphys.tests.dicom.test_a"
MODULE_B = "lib.pymedphys.tests.dicom.test_b"


def _passing(path):
    return _junit(
        path,
        (MODULE_A, "test_plain", ""),
        (MODULE_A, "test_cases[1]", ""),
        (MODULE_A, "test_cases[2]", ""),
        (f"{MODULE_B}.TestGroup", "test_method", ""),
        (MODULE_B, "test_unrun", ""),
    )


def _outcomes(matrix):
    return {
        test.node_id: (test.result.outcome, test.result.counts)
        for row in matrix.rows
        for test in row.tests
    }


def test_the_matrix_follows_the_register(register):
    matrix = traceability.build_matrix(register)
    assert [row.requirement for row in matrix.rows] == list(register.requirements)
    assert [[test.node_id for test in row.tests] for row in matrix.rows] == [
        [PLAIN, CASES],
        [],
        [METHOD, UNRUN],
        [],
        [],
    ]
    assert not matrix.reports
    assert all(test.result is None for row in matrix.rows for test in row.tests)
    assert all(row.verdict is None for row in matrix.rows)
    assert not matrix.problems()


def test_exclusions_are_the_out_of_scope_and_not_applicable_requirements(register):
    assert [entry.id for entry in traceability.exclusions(register)] == [
        "PS3.15-E.3.9-01",
        "MIDI-BP-09",
    ]


def test_each_test_case_is_matched_to_its_node_id(register, tmp_path):
    report = _junit(
        tmp_path / "junit.xml",
        (MODULE_A, "test_plain", ""),
        (MODULE_A, "test_cases[1]", ""),
        (MODULE_A, "test_cases[2]", SKIPPED),
        (MODULE_A, "test_cases_other", FAILURE),
        (f"{MODULE_B}.TestGroup", "test_method", ERROR),
        # Neither the method of another class nor a module-level test of the
        # same name is the traced method.
        (f"{MODULE_B}.TestOther", "test_method", ""),
        (MODULE_B, "test_method", ""),
    )
    matrix = traceability.build_matrix(register, [report])
    assert matrix.reports == ("junit.xml",)
    assert _outcomes(matrix) == {
        PLAIN: ("passed", (1, 0, 0, 0)),
        CASES: ("skipped", (1, 0, 1, 0)),
        METHOD: ("failed", (0, 1, 0, 0)),
        UNRUN: ("not run", (0, 0, 0, 0)),
    }


@pytest.mark.parametrize(
    "classname",
    [
        "tests.dicom.test_a",
        "pymedphys.tests.dicom.test_a",
        "lib.pymedphys.tests.dicom.test_a",
    ],
)
def test_a_module_matches_whatever_the_rootdir(register, tmp_path, classname):
    report = _junit(tmp_path / "junit.xml", (classname, "test_plain", ""))
    matrix = traceability.build_matrix(register, [report])
    assert _outcomes(matrix)[PLAIN] == ("passed", (1, 0, 0, 0))


@pytest.mark.parametrize(
    "classname, name",
    [
        ("lib.pymedphys.tests.dicom.test_ab", "test_plain"),
        ("lib.pymedphys.tests.dicom.xtest_a", "test_plain"),
        ("lib.pymedphys.xtests.dicom.test_a", "test_plain"),
        ("lib.pymedphys.tests.test_a", "test_plain"),
        ("lib.pymedphys.tests.dicom.test_a.TestGroup", "test_plain"),
        (MODULE_A, "test_plain_more"),
        (MODULE_A, "test_plai"),
    ],
)
def test_only_the_whole_node_id_matches(register, tmp_path, classname, name):
    report = _junit(tmp_path / "junit.xml", (classname, name, ""))
    matrix = traceability.build_matrix(register, [report])
    assert _outcomes(matrix)[PLAIN] == ("not run", (0, 0, 0, 0))


def test_reports_are_combined(register, tmp_path):
    first = _passing(tmp_path / "linux.xml")
    second = _junit(
        tmp_path / "windows.xml",
        (MODULE_A, "test_plain", FAILURE),
        (MODULE_A, "test_cases[1]", ""),
    )
    matrix = traceability.build_matrix(register, [first, second])
    assert matrix.reports == ("linux.xml", "windows.xml")
    outcomes = _outcomes(matrix)
    assert outcomes[PLAIN] == ("failed", (1, 1, 0, 0))
    # The Windows report lacks a case that the Linux report ran.
    assert outcomes[CASES] == ("partly run", (3, 0, 0, 1))


def test_a_test_missing_from_one_report_is_partly_run(register, tmp_path):
    linux = _passing(tmp_path / "linux.xml")
    windows = _junit(tmp_path / "windows.xml", (MODULE_A, "test_other", ""))
    matrix = traceability.build_matrix(register, [linux, windows])
    outcomes = _outcomes(matrix)
    assert outcomes[PLAIN] == ("partly run", (1, 0, 0, 1))
    assert outcomes[CASES] == ("partly run", (2, 0, 0, 2))
    assert matrix.rows[0].verdict == "incomplete"
    assert matrix.problems()[:2] == (
        f"PS3.15-E.1.1-01: {PLAIN} partly run",
        f"PS3.15-E.1.1-01: {CASES} partly run",
    )
    markdown = traceability.render_markdown(matrix)
    assert f"- `{CASES}`: partly run (2 passed, 2 missing)\n" in markdown


def test_a_case_missing_from_one_report_is_partly_run(register, tmp_path):
    linux = _passing(tmp_path / "linux.xml")
    windows = _passing(tmp_path / "windows.xml")
    text = windows.read_text(encoding="utf-8")
    windows.write_text(
        re.sub(r'<testcase[^>]*name="test_cases\[2\]"[^>]*></testcase>', "", text),
        encoding="utf-8",
    )
    matrix = traceability.build_matrix(register, [linux, windows])
    assert _outcomes(matrix)[CASES] == ("partly run", (3, 0, 0, 1))
    assert matrix.rows[0].verdict == "incomplete"


def test_the_same_cases_in_every_report_pass(register, tmp_path):
    reports = [_passing(tmp_path / "linux.xml"), _passing(tmp_path / "windows.xml")]
    matrix = traceability.build_matrix(register, reports)
    assert _outcomes(matrix)[CASES] == ("passed", (4, 0, 0, 0))
    assert not matrix.problems()


def test_reports_with_the_same_name_are_named_by_their_paths(register, tmp_path):
    (tmp_path / "linux").mkdir()
    (tmp_path / "windows").mkdir()
    first = _passing(tmp_path / "linux" / "junit.xml")
    second = _passing(tmp_path / "windows" / "junit.xml")
    other = _passing(tmp_path / "macos.xml")
    matrix = traceability.build_matrix(register, [first, second, other])
    assert matrix.reports == (str(first), str(second), "macos.xml")


def test_a_requirement_passes_only_when_each_traced_test_passed(register, tmp_path):
    passing = traceability.build_matrix(register, [_passing(tmp_path / "a.xml")])
    assert [row.verdict for row in passing.rows] == [
        "passed",
        None,
        "passed",
        None,
        None,
    ]
    assert not passing.problems()

    report = _junit(
        tmp_path / "b.xml",
        (MODULE_A, "test_plain", ""),
        (MODULE_A, "test_cases[1]", FAILURE),
        (f"{MODULE_B}.TestGroup", "test_method", SKIPPED),
    )
    matrix = traceability.build_matrix(register, [report])
    assert [row.verdict for row in matrix.rows] == [
        "failed",
        None,
        "incomplete",
        None,
        None,
    ]
    assert matrix.problems() == (
        f"PS3.15-E.1.1-01: {CASES} failed",
        f"MIDI-BP-06: {METHOD} skipped",
        f"MIDI-BP-06: {UNRUN} not run",
    )

    # A skipped case leaves a requirement incomplete, even when every test ran.
    report = _junit(
        tmp_path / "c.xml",
        (MODULE_A, "test_plain", ""),
        (MODULE_A, "test_cases[1]", ""),
        (MODULE_A, "test_cases[2]", SKIPPED),
    )
    matrix = traceability.build_matrix(register, [report])
    assert matrix.rows[0].verdict == "incomplete"
    assert matrix.problems()[0] == f"PS3.15-E.1.1-01: {CASES} skipped"


@pytest.mark.parametrize(
    "content",
    [
        "not xml",
        "<testsuites><testsuite><testcase name='test_x'/></testsuite></testsuites>",
        "<testsuites><testsuite><testcase classname='x'/></testsuite></testsuites>",
        "<testsuites><testsuite></testsuites>",
        "<results/>",
    ],
)
def test_a_malformed_report_is_rejected(register, tmp_path, content):
    report = tmp_path / "junit.xml"
    report.write_text(content, encoding="utf-8")
    with pytest.raises(traceability.TraceabilityError, match="junit.xml"):
        traceability.build_matrix(register, [report])


def test_a_missing_report_is_rejected(register, tmp_path):
    with pytest.raises(traceability.TraceabilityError, match="missing.xml"):
        traceability.build_matrix(register, [tmp_path / "missing.xml"])


def test_the_markdown_lists_each_requirement_with_its_tests(register):
    markdown = traceability.render_markdown(traceability.build_matrix(register))
    assert markdown.startswith(
        "# DICOM de-identification requirements-to-tests matrix\n"
    )
    assert "DICOM PS3.15 2026d, © NEMA" in markdown
    assert "Clunie DA et al., MIDI Task Group report" in markdown
    assert "No test results were given" in markdown
    for entry in register.requirements:
        assert f"\n### {entry.id}\n" in markdown
    assert f"[PS3.15-E.1.1-01]({URL.format('00000001')})" in markdown
    assert f"- `{PLAIN}`\n" in markdown
    assert "| partial | 1 | 0 | 1 |" in markdown
    assert "| Total | 2 | 3 | 5 |" in markdown


def test_the_markdown_lists_each_exclusion_with_its_reason(register):
    markdown = traceability.render_markdown(traceability.build_matrix(register))
    exclusions = markdown.split("\n## Exclusions\n")[1].split("\n## ")[0]
    assert (
        "| [PS3.15-E.3.9-01]({}) | out-of-scope | Retain UIDs is not supported. |".format(
            URL.format("00000002")
        )
        in exclusions
    )
    assert "| MIDI-BP-09 | not-applicable | PyMedPhys does not re-identify. |" in (
        exclusions
    )
    assert "MIDI-BP-10" not in exclusions


def test_table_cells_keep_to_one_line_and_escape_pipes(register):
    markdown = traceability.render_markdown(traceability.build_matrix(register))
    assert "| Remaining: the walker, which applies `X \\| Z` (M3). |" in markdown


def test_requirement_text_is_fenced_verbatim(register):
    markdown = traceability.render_markdown(traceability.build_matrix(register))
    text = REGISTER["requirement"][0]["text"]
    assert f"\n````text\n{text}\n````\n" in markdown


def test_the_markdown_gives_each_outcome(register, tmp_path):
    report = _junit(
        tmp_path / "junit.xml",
        (MODULE_A, "test_plain", ""),
        (MODULE_A, "test_cases[1]", ""),
        (MODULE_A, "test_cases[2]", FAILURE),
        (f"{MODULE_B}.TestGroup", "test_method", SKIPPED),
    )
    markdown = traceability.render_markdown(
        traceability.build_matrix(register, [report])
    )
    assert "Test results are from `junit.xml`." in markdown
    assert f"- `{PLAIN}`: passed (1 passed)\n" in markdown
    assert f"- `{CASES}`: failed (1 passed, 1 failed)\n" in markdown
    assert f"- `{METHOD}`: skipped (1 skipped)\n" in markdown
    assert f"- `{UNRUN}`: not run\n" in markdown
    assert "| Traced tests | Requirements |" in markdown
    assert "| failed | 1 |" in markdown
    assert "| incomplete | 1 |" in markdown
    assert "| Decisions | Tests | Traced tests |" in markdown
    # A partial requirement whose tests pass is not thereby met.
    assert "A requirement passes" not in markdown


def test_the_markdown_is_deterministic_and_tidy(register, tmp_path):
    report = _passing(tmp_path / "junit.xml")
    first = traceability.render_markdown(traceability.build_matrix(register, [report]))
    second = traceability.render_markdown(traceability.build_matrix(register, [report]))
    assert first == second
    assert first.endswith("\n") and not first.endswith("\n\n")
    assert not re.search(r"[ \t]$", first, re.MULTILINE)
    assert "\n\n\n" not in first


def test_the_shipped_register_renders():
    register = requirements.load_requirements()
    markdown = traceability.render_markdown(traceability.build_matrix(register))
    for entry in register.requirements:
        assert f"\n### {entry.id}\n" in markdown
    for entry in traceability.exclusions(register):
        assert entry.note is not None


def _run(*options):
    args = define_parser().parse_args(["dev", "deid-matrix", *options])
    args.func(args)


def _run_in(tmp_path, *options):
    """Run the command with the register and citing tests in ``tmp_path``."""
    _run(
        "--register",
        str(tmp_path / "requirements.toml"),
        "--tests",
        str(tmp_path),
        *options,
    )


def test_the_command_writes_the_matrix(register, tmp_path):
    output = tmp_path / "matrix.md"
    register_path = tmp_path / "requirements.toml"
    _run_in(tmp_path, "--output", str(output))
    markdown = output.read_text(encoding="utf-8")
    assert markdown == traceability.render_markdown(
        traceability.build_matrix(register, source=str(register_path))
    )
    # The matrix names the register it was generated from.
    assert f"requirements register `{register_path}`" in markdown


def test_the_matrix_names_the_shipped_register_by_default(register):
    markdown = traceability.render_markdown(traceability.build_matrix(register))
    assert (
        "requirements register `pymedphys/_dicom/deidentify/requirements.toml`"
        in markdown
    )


def test_the_command_prints_the_matrix(register, tmp_path, capsys):
    path = tmp_path / "requirements.toml"
    _run_in(tmp_path)
    assert capsys.readouterr().out == traceability.render_markdown(
        traceability.build_matrix(register, source=str(path))
    )


@pytest.mark.usefixtures("register")
def test_the_check_passes_when_each_traced_test_passed(tmp_path, capsys):
    report = _passing(tmp_path / "junit.xml")
    _run_in(
        tmp_path,
        "--junit",
        str(report),
        "--check",
        "--output",
        str(tmp_path / "matrix.md"),
    )
    assert capsys.readouterr().err == ""


def test_the_check_fails_when_a_traced_test_did_not_pass(register, tmp_path, capsys):
    report = _junit(tmp_path / "junit.xml", (MODULE_A, "test_plain", FAILURE))
    output = tmp_path / "matrix.md"
    with pytest.raises(SystemExit) as raised:
        _run_in(
            tmp_path,
            "--junit",
            str(report),
            "--check",
            "--output",
            str(output),
        )
    assert raised.value.code == 1
    # The matrix is still written, so that the failures can be read in it.
    assert output.read_text(encoding="utf-8") == traceability.render_markdown(
        traceability.build_matrix(
            register, [report], source=str(tmp_path / "requirements.toml")
        )
    )
    err = capsys.readouterr().err
    assert f"PS3.15-E.1.1-01: {PLAIN} failed" in err
    assert f"MIDI-BP-06: {UNRUN} not run" in err


@pytest.mark.usefixtures("register")
def test_the_check_needs_test_results(tmp_path):
    with pytest.raises(SystemExit, match="--check needs at least one --junit"):
        _run_in(tmp_path, "--check")


@pytest.mark.usefixtures("register")
def test_the_command_reports_a_bad_report_without_a_traceback(tmp_path):
    with pytest.raises(SystemExit, match="missing.xml"):
        _run_in(tmp_path, "--junit", str(tmp_path / "missing.xml"))
