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

"""The de-identification requirements register and its loader."""

import collections
import copy
import os
import re
import subprocess
import sys

from pymedphys._imports import pytest, tomlkit

from pymedphys import conftest
from pymedphys._dicom.deidentify import requirements, standard
from pymedphys._root import LIBRARY_ROOT

DESIGN = LIBRARY_ROOT / "docs" / "contrib" / "info" / "deidentification-design.md"

URL = (
    "https://dicom.nema.org/medical/dicom/current/output/chtml/part15/"
    "chapter_E.html#para_{}-0000-0000-0000-000000000000"
)

VALID = {
    "schema": "pymedphys-deid-requirements/2",
    "edition": "2026d",
    "acknowledgement": "DICOM PS3.15 2026d, © NEMA",
    "midi_report": "Clunie DA et al., MIDI Task Group report",
    "requirement": [
        {
            "id": "PS3.15-E.1.1-01",
            "url": URL.format("00000001"),
            "text": "Each Attribute shall be retained.",
            "status": "planned",
            "milestone": "M3",
            "decisions": ["D-001", "D-011"],
        },
        {
            "id": "PS3.15-E.3.9-01",
            "url": URL.format("00000002"),
            "text": "UIDs shall be retained.",
            "status": "out-of-scope",
            "note": "Not supported.",
        },
        {
            "id": "MIDI-BP-06",
            "text": "Use the current edition.",
            "status": "partial",
            "milestone": "M1",
            "implementation": ["_dicom/deidentify/standard.py"],
            "tests": ["tests/dicom/test_deidentify_standard.py::test_x"],
        },
    ],
}


def _write(path, document):
    path.write_text(tomlkit.dumps(document), encoding="utf-8")
    return path


def _load(tmp_path, document):
    """Load ``document``, taking each entry's ``tests`` as the tests that cite it.

    The register holds no tests: they cite its requirements with a marker.
    """
    document = copy.deepcopy(document)
    tests = {}
    for entry in (
        document["requirement"] if isinstance(document.get("requirement"), list) else []
    ):
        if isinstance(entry, dict) and "tests" in entry:
            tests[entry.get("id")] = entry.pop("tests")
    return requirements.load_requirements(_write(tmp_path / "r.toml", document), tests)


def _changed(entry, **fields):
    document = copy.deepcopy(VALID)
    target = document["requirement"][entry]
    for field, value in fields.items():
        if value is None:
            target.pop(field, None)
        else:
            target[field] = value
    return document


@pytest.fixture(name="register")
def _register():
    return requirements.load_requirements()


def test_the_register_records_each_normative_paragraph_of_annex_e(register):
    dicom = [entry for entry in register.requirements if entry.source == "PS3.15"]
    # The paragraphs of PS3.15 2026d Annex E, outside Notes and tables, that
    # contain "shall".
    assert collections.Counter(entry.section for entry in dicom) == {
        "E.1.1": 9,
        "E.1.2": 3,
        "E.1.3": 1,
        "E.2": 1,
        "E.3.1": 2,
        "E.3.2": 2,
        "E.3.3": 1,
        "E.3.4": 1,
        "E.3.5": 2,
        "E.3.6": 4,
        "E.3.7": 2,
        "E.3.8": 1,
        "E.3.9": 1,
        "E.3.10": 4,
        "E.3.11": 1,
    }
    # A paragraph that introduces a list keeps the list.
    (conformance,) = (entry for entry in dicom if entry.section == "E.1.3")
    assert conformance.text.startswith(
        "The Conformance Statement of an application that claims conformance "
        "to the Basic Application Level Confidentiality Profile shall describe:"
    )
    assert "\n- which Options are supported;\n" in conformance.text
    assert conformance.text.endswith("(e. g. key sizes for public keys).")


def test_the_register_records_each_midi_best_practice(register):
    midi = [entry.id for entry in register.requirements if entry.source == "MIDI"]
    assert midi == [f"MIDI-BP-{number:02d}" for number in range(1, 19)]
    assert {
        entry.section for entry in register.requirements if entry.source == "MIDI"
    } == {"1.6"}


def test_the_register_follows_the_edition_of_the_generated_tables(register):
    assert register.edition == standard.load_table_e1_1().edition
    assert register.edition == standard.load_table_e1_1a().edition
    assert register.edition == standard.load_table_e3_10_1().edition
    assert register.acknowledgement == f"DICOM PS3.15 {register.edition}, © NEMA"


def test_unsupported_options_and_re_identification_are_excluded(register):
    by_section = collections.defaultdict(set)
    for entry in register.requirements:
        by_section[entry.section].add(entry.status)
    # The design document's Scope excludes these Options.
    for section in ("E.3.1", "E.3.2", "E.3.3", "E.3.4", "E.3.9", "E.3.11"):
        assert by_section[section] == {"out-of-scope"}, section
    # PyMedPhys never claims conformance as a re-identifier.
    assert by_section["E.1.2"] == {"not-applicable"}


def test_each_cited_decision_is_in_the_design_document(register):
    decisions = set(
        re.findall(r"^### (D-[0-9]{3}):", DESIGN.read_text("utf-8"), re.MULTILINE)
    )
    cited = {
        decision for entry in register.requirements for decision in entry.decisions
    }
    assert cited
    assert cited <= decisions, sorted(cited - decisions)


def test_each_implementation_path_exists(register):
    paths = {path for entry in register.requirements for path in entry.implementation}
    assert paths
    assert not [path for path in sorted(paths) if not (LIBRARY_ROOT / path).is_file()]


SAMPLE_TESTS = """\
import pytest


def _helper():
    pass


@pytest.fixture
def test_data():
    return 1


def test_plain():
    pass


@pytest.mark.parametrize("value", [1, 2])
def test_parametrised(value):
    pass


class TestGroup:
    def test_method(self):
        pass


class Helper:
    def test_method(self):
        pass
"""


def _uncollected(node_ids, root, *, collected=None):
    """Return the node ids under ``root`` that pytest does not collect as tests.

    Exact matches in the session's collection need no second collection.
    Missing references collect their modules whole: pytest stops at the first
    explicit node id it cannot find. An id for a parametrised function covers
    each of its cases. Collection errors cannot count as successful evidence.
    """
    collected = set(collected or ())
    paths = {node_id.split("::")[0] for node_id in node_ids if node_id not in collected}
    modules = sorted(path for path in paths if (root / path).is_file())
    if modules:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "--collect-only",
                "-q",
                "-p",
                "no:cacheprovider",
                f"--rootdir={root}",
                *modules,
            ],
            cwd=root,
            env={**os.environ, "PYTEST_ADDOPTS": ""},
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        if result.returncode:
            raise AssertionError(
                "pytest could not collect the traced modules "
                f"(exit {result.returncode}):\n{result.stdout}{result.stderr}"
            )
        collected.update(line.split("[")[0] for line in result.stdout.splitlines())
    return [node_id for node_id in node_ids if node_id not in collected]


def test_only_node_ids_that_pytest_collects_count_as_tests(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_sample.py").write_text(SAMPLE_TESTS, encoding="utf-8")
    module = "tests/test_sample.py"
    collected = [
        f"{module}::test_plain",
        f"{module}::test_parametrised",
        f"{module}::TestGroup::test_method",
    ]
    not_tests = [
        f"{module}::_helper",
        f"{module}::test_data",
        f"{module}::Helper::test_method",
        f"{module}::test_missing",
        "tests/test_missing.py::test_plain",
    ]
    assert _uncollected(collected + not_tests, tmp_path) == not_tests


def test_exact_session_matches_need_no_second_collection(tmp_path, monkeypatch):
    module = tmp_path / "test_sample.py"
    module.write_text(SAMPLE_TESTS, encoding="utf-8")
    node_id = "test_sample.py::test_parametrised"

    def unexpected_collection(*_args, **_kwargs):
        raise AssertionError("an already collected test was collected again")

    monkeypatch.setattr(subprocess, "run", unexpected_collection)

    assert _uncollected([node_id], tmp_path, collected={node_id}) == []


def test_missing_references_collect_whole_modules_without_inherited_selection(
    tmp_path, monkeypatch
):
    for name in ("test_first.py", "test_second.py"):
        (tmp_path / name).write_text(SAMPLE_TESTS, encoding="utf-8")
    known = "test_first.py::test_plain"
    found = "test_second.py::test_parametrised"
    missing = "test_first.py::test_plain_missing"
    monkeypatch.setenv("PYTEST_ADDOPTS", "-m pydicom -k absent -n 2")
    calls = []

    def collect(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return subprocess.CompletedProcess(
            arguments, 0, stdout=f"{found}[1]\n{found}[2]\n", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", collect)

    assert _uncollected([known, found, missing], tmp_path, collected={known}) == [
        missing
    ]
    ((arguments, kwargs),) = calls
    assert arguments[-2:] == ["test_first.py", "test_second.py"]
    assert not any("::" in argument for argument in arguments)
    assert kwargs["env"]["PYTEST_ADDOPTS"] == ""
    assert kwargs["cwd"] == tmp_path


def test_failed_collection_cannot_validate_names_it_printed(tmp_path, monkeypatch):
    (tmp_path / "test_sample.py").write_text(SAMPLE_TESTS, encoding="utf-8")
    node_id = "test_sample.py::test_plain"
    result = subprocess.CompletedProcess(
        [], 2, stdout=f"{node_id}\n", stderr="another collector failed"
    )
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: result)

    with pytest.raises(AssertionError, match="could not collect.*exit 2"):
        _uncollected([node_id], tmp_path)


class _CollectedItem(pytest.Item):
    """A real pytest Item whose collection never executes a test body."""

    def runtest(self):
        raise AssertionError("a collection fixture must not be executed")


def test_collected_items_use_their_library_relative_path(
    tmp_path, monkeypatch, request
):
    monkeypatch.setattr(conftest, "LIBRARY_ROOT", tmp_path)
    monkeypatch.setattr(request.session, "stash", pytest.Stash())
    for name in ("test_value[1]", "test_value[2]", "TestGroup::test_method[other]"):
        item = _CollectedItem.from_parent(
            request.session,
            name=name,
            path=tmp_path / "tests" / "test_sample.py",
            nodeid=f"parent/path/tests/test_sample.py::{name}",
        )
        conftest.pytest_itemcollected(item)
    outside = _CollectedItem.from_parent(
        request.session,
        name="test_outside",
        path=tmp_path.parent / "test_outside.py",
        nodeid="test_outside.py::test_outside",
    )
    conftest.pytest_itemcollected(outside)

    # pylint: disable = protected-access
    assert request.session.stash[conftest._COLLECTED_TEST_IDS] == {
        "tests/test_sample.py::test_value",
        "tests/test_sample.py::TestGroup::test_method",
    }


def test_the_session_snapshot_preserves_collected_parameter_ids(
    request, collected_test_ids
):
    if any("::" in argument for argument in request.config.args):
        assert collected_test_ids is None
    else:
        module = "tests/dicom/test_deidentify_requirements.py"
        assert (
            f"{module}::test_a_malformed_requirement_is_rejected" in collected_test_ids
        )
        assert not any(
            "[" in node_id or "\\" in node_id for node_id in collected_test_ids
        )


def test_pytest_collects_each_traced_test(register, collected_test_ids):
    tests = sorted({test for entry in register.requirements for test in entry.tests})
    assert tests
    assert not _uncollected(tests, LIBRARY_ROOT, collected=collected_test_ids)


def test_a_valid_register_loads(tmp_path):
    register = _load(tmp_path, VALID)
    assert register.edition == "2026d"
    assert register.midi_report == "Clunie DA et al., MIDI Task Group report"
    first, excluded, practice = register.requirements
    assert first == requirements.Requirement(
        id="PS3.15-E.1.1-01",
        source="PS3.15",
        section="E.1.1",
        url=URL.format("00000001"),
        text="Each Attribute shall be retained.",
        status="planned",
        milestone="M3",
        decisions=("D-001", "D-011"),
        implementation=(),
        tests=(),
        note=None,
    )
    assert (excluded.section, excluded.note, excluded.milestone) == (
        "E.3.9",
        "Not supported.",
        None,
    )
    assert (practice.source, practice.section, practice.url) == ("MIDI", "1.6", None)
    assert practice.tests == ("tests/dicom/test_deidentify_standard.py::test_x",)
    assert hash(practice)


def test_function_and_class_node_ids_are_accepted(tmp_path):
    tests = ["tests/a/test_b.py::test_c", "tests/a/test_b.py::TestD::test_e"]
    register = _load(tmp_path, _changed(2, tests=tests))
    assert register.requirements[2].tests == tuple(tests)


def test_text_keeps_its_lines_without_surrounding_whitespace(tmp_path):
    document = copy.deepcopy(VALID)
    tests = {"MIDI-BP-06": document["requirement"][2].pop("tests")}
    path = tmp_path / "r.toml"
    path.write_text(
        tomlkit.dumps(document).replace(
            '"Each Attribute shall be retained."',
            "'''\nEach Attribute shall be:\n\n- retained\n'''",
        ),
        encoding="utf-8",
    )
    first = requirements.load_requirements(path, tests).requirements[0]
    assert first.text == "Each Attribute shall be:\n\n- retained"


@pytest.mark.parametrize(
    "change, message",
    [
        ({"schema": "other/1"}, "is not a pymedphys-deid-requirements/2 file"),
        ({"edition": ""}, "does not name its edition as text"),
        ({"edition": 2026}, "does not name its edition as text"),
        ({"acknowledgement": "© NEMA"}, "lacks the copyright acknowledgement"),
        ({"midi_report": ""}, "does not cite the MIDI report"),
        ({"requirement": []}, "has no requirements"),
        ({"requirement": "none"}, "has no requirements"),
    ],
)
def test_a_malformed_register_is_rejected(tmp_path, change, message):
    document = copy.deepcopy(VALID)
    document.update(change)
    with pytest.raises(requirements.RequirementsError, match=message):
        _load(tmp_path, document)


@pytest.mark.parametrize(
    "entry, fields, message",
    [
        (0, {"colour": "red"}, "PS3.15-E.1.1-01 does not have only the fields"),
        (0, {"status": None}, "PS3.15-E.1.1-01 lacks id, text, or status"),
        (0, {"id": "E.1.1-01"}, "#1 has an id that is not of the form"),
        (0, {"id": "PS3.15-E.1.1-1"}, "#1 has an id that is not of the form"),
        (2, {"id": "MIDI-BP-19"}, "#3 has an id that is not of the form"),
        (2, {"id": "MIDI-BP-00"}, "#3 has an id that is not of the form"),
        (1, {"id": "PS3.15-E.1.1-01"}, "PS3.15-E.1.1-01 repeats an id"),
        (0, {"url": None}, "PS3.15-E.1.1-01 lacks a url to its paragraph"),
        (0, {"url": "https://example.com/#para_1"}, "has a url that is not"),
        (1, {"url": URL.format("00000001")}, "PS3.15-E.3.9-01 repeats a url"),
        (2, {"url": URL.format("00000003")}, "MIDI-BP-06 has a url"),
        (0, {"text": ""}, "PS3.15-E.1.1-01 has text that is not non-empty"),
        (0, {"text": ["a"]}, "PS3.15-E.1.1-01 has text that is not non-empty"),
        (0, {"text": "Each Attribute is retained."}, "does not contain 'shall'"),
        (0, {"status": "done"}, "PS3.15-E.1.1-01 has a status that is not one of"),
        (0, {"milestone": None}, "PS3.15-E.1.1-01 is planned without a milestone"),
        (0, {"milestone": "M9"}, "PS3.15-E.1.1-01 has a milestone that is not"),
        (1, {"milestone": "M3"}, "PS3.15-E.3.9-01 is out-of-scope with a milestone"),
        (0, {"decisions": ["D-1"]}, "has decisions that are not distinct D-NNN"),
        (0, {"decisions": ["D-001", "D-001"]}, "that are not distinct D-NNN"),
        (0, {"decisions": "D-001"}, "has decisions that are not distinct D-NNN"),
        (2, {"tests": None}, "MIDI-BP-06 is partial without implementation"),
        (2, {"implementation": []}, "MIDI-BP-06 is partial without implementation"),
        (0, {"tests": ["tests/a/test_b.py::test_c"]}, "is planned with implementation"),
        (1, {"implementation": ["x.py"]}, "is out-of-scope with implementation"),
        (1, {"note": None}, "PS3.15-E.3.9-01 is out-of-scope without a note"),
        (0, {"note": ""}, "PS3.15-E.1.1-01 has a note that is not non-empty"),
        (2, {"implementation": ["/abs/x.py"]}, "has implementation that is not"),
        (2, {"implementation": ["../x.py"]}, "has implementation that is not"),
        (2, {"implementation": ["_dicom\\x.py"]}, "has implementation that is not"),
        (2, {"implementation": [1]}, "has implementation that is not"),
        (2, {"tests": ["tests/x.py"]}, "has tests that are not pytest node ids"),
        (2, {"tests": ["tests/x.py::test_y[1]"]}, "has tests that are not pytest"),
        (2, {"tests": ["x.py::test_y"]}, "has tests that are not pytest node ids"),
        (2, {"tests": ["tests/a/test_b.py::_write"]}, "has tests that are not pytest"),
        (2, {"tests": ["tests/a/test_b.py::Helper::test_c"]}, "has tests that are not"),
    ],
)
def test_a_malformed_requirement_is_rejected(tmp_path, entry, fields, message):
    with pytest.raises(requirements.RequirementsError, match=re.escape(message)):
        _load(tmp_path, _changed(entry, **fields))


def test_a_requirement_that_is_not_a_table_is_rejected(tmp_path):
    document = copy.deepcopy(VALID)
    document["requirement"] = ["PS3.15-E.1.1-01"]
    with pytest.raises(requirements.RequirementsError, match="#1 is not a table"):
        _load(tmp_path, document)


@pytest.mark.parametrize("text", ["schema = ", "[[requirement]\n", "\udcff"])
def test_an_unreadable_register_is_rejected(tmp_path, text):
    path = tmp_path / "r.toml"
    path.write_bytes(text.encode("utf-8", "surrogateescape"))
    with pytest.raises(requirements.RequirementsError, match="could not be read"):
        requirements.load_requirements(path)


def test_a_missing_register_is_rejected(tmp_path):
    with pytest.raises(requirements.RequirementsError, match="could not be read"):
        requirements.load_requirements(tmp_path / "missing.toml")


def test_a_register_that_lists_tests_is_rejected(tmp_path):
    # Tests cite requirements with the marker; the register does not list them.
    path = _write(tmp_path / "r.toml", VALID)
    with pytest.raises(
        requirements.RequirementsError, match="MIDI-BP-06 does not have only the fields"
    ):
        requirements.load_requirements(path, {})


def test_a_test_citing_a_requirement_the_register_lacks_is_rejected(tmp_path):
    document = _changed(2, tests=None)
    document["requirement"][2].update(status="planned", implementation=None)
    del document["requirement"][2]["implementation"]
    path = _write(tmp_path / "r.toml", document)
    with pytest.raises(
        requirements.RequirementsError,
        match="a test cites MIDI-BP-07, which r.toml does not record",
    ):
        requirements.load_requirements(
            path, {"MIDI-BP-07": ["tests/a/test_b.py::test_c"]}
        )


def test_a_note_written_one_sentence_per_line_is_joined(tmp_path):
    document = _changed(1, note="\n  First sentence.\nSecond (D-001).\n\n")
    excluded = _load(tmp_path, document).requirements[1]
    assert excluded.note == "First sentence. Second (D-001)."


def _tests_tree(root, files):
    for name, source in files.items():
        path = root / "tests" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    return root


CITING = """
import pytest


def helper():
    pass


@pytest.mark.deid_requirement("MIDI-BP-02", "MIDI-BP-01")
def test_first():
    pass


@pytest.mark.parametrize("value", [1, 2])
@pytest.mark.deid_requirement("MIDI-BP-01")
async def test_second(value):
    pass


@pytest.mark.deid_requirement("MIDI-BP-03")
class TestGroup:
    @pytest.mark.deid_requirement("MIDI-BP-01")
    def test_method(self):
        pass

    def test_other(self):
        pass

    def helper(self):
        pass


def test_uncited():
    pass
"""


def test_cited_tests_reads_markers_on_test_functions_and_classes(tmp_path):
    root = _tests_tree(
        tmp_path,
        {
            "b/test_later.py": CITING,
            "a/test_earlier.py": (
                "import pytest\n\n\n"
                "@pytest.mark.deid_requirement('MIDI-BP-01')\n"
                "def test_only():\n    pass\n"
            ),
            # Only test_*.py files are read.
            "b/helpers.py": "@pytest.mark.deid_requirement(1)\ndef test_x(): pass\n",
            "b/conftest.py": "@pytest.mark.deid_requirement(1)\ndef test_x(): pass\n",
        },
    )
    later = "tests/b/test_later.py"
    assert requirements.cited_tests(root) == {
        # By file, then by line.
        "MIDI-BP-01": (
            "tests/a/test_earlier.py::test_only",
            f"{later}::test_first",
            f"{later}::test_second",
            f"{later}::TestGroup::test_method",
        ),
        "MIDI-BP-02": (f"{later}::test_first",),
        "MIDI-BP-03": (
            f"{later}::TestGroup::test_method",
            f"{later}::TestGroup::test_other",
        ),
    }


def test_no_tests_directory_cites_nothing(tmp_path):
    assert requirements.cited_tests(tmp_path) == {}


@pytest.mark.parametrize(
    "source, message",
    [
        ("@pytest.mark.deid_requirement\ndef test_x(): pass\n", "string literals"),
        ("@pytest.mark.deid_requirement()\ndef test_x(): pass\n", "string literals"),
        (
            "ID = 'MIDI-BP-01'\n@pytest.mark.deid_requirement(ID)\ndef test_x(): pass\n",
            "string literals",
        ),
        (
            "@pytest.mark.deid_requirement('MIDI-BP-01', reason='x')\ndef test_x(): pass\n",
            "string literals",
        ),
        (
            "@pytest.mark.deid_requirement(b'MIDI-BP-01')\ndef test_x(): pass\n",
            "string literals",
        ),
        (
            "pytestmark = pytest.mark.deid_requirement('MIDI-BP-01')\n",
            "other than to decorate",
        ),
        (
            "@pytest.mark.deid_requirement('MIDI-BP-01')\ndef helper(): pass\n",
            "other than to decorate",
        ),
        (
            "@pytest.mark.deid_requirement('MIDI-BP-01')\nclass Group:\n    def test_x(self): pass\n",
            "other than to decorate",
        ),
        (
            "class TestGroup:\n    @pytest.mark.deid_requirement('MIDI-BP-01')\n    def helper(self): pass\n",
            "other than to decorate",
        ),
        (
            "def test_x():\n    @pytest.mark.deid_requirement('MIDI-BP-01')\n    def test_y(): pass\n",
            "other than to decorate",
        ),
        (
            "@pytest.mark.parametrize('a', [pytest.param(1, marks=pytest.mark.deid_requirement('MIDI-BP-01'))])\ndef test_x(a): pass\n",
            "other than to decorate",
        ),
        (
            "@pytest.mark.deid_requirement('MIDI-BP-01', 'MIDI-BP-01')\ndef test_x(): pass\n",
            "cites a requirement more than once",
        ),
        (
            "@pytest.mark.deid_requirement('MIDI-BP-01')\nclass TestGroup:\n    @pytest.mark.deid_requirement('MIDI-BP-01')\n    def test_x(self): pass\n",
            "TestGroup::test_x cites a requirement more than once",
        ),
        ("def test_x(:\n", "could not be read"),
    ],
)
def test_a_citation_that_cannot_be_read_from_the_source_is_rejected(
    tmp_path, source, message
):
    root = _tests_tree(tmp_path, {"test_bad.py": "import pytest\n" + source})
    with pytest.raises(requirements.RequirementsError, match=re.escape(message)):
        requirements.cited_tests(root)


def test_the_shipped_register_takes_its_tests_from_the_markers(register):
    cited = requirements.cited_tests()
    assert {
        entry.id: entry.tests for entry in register.requirements if entry.tests
    } == cited


def test_pytest_sees_the_citations_read_from_the_source(
    collected_test_ids, collected_citations
):
    """The source reading and pytest's own markers agree on every collected test."""
    if collected_test_ids is None or collected_citations is None:
        pytest.skip("needs a session that collects whole modules")
    from_source = collections.defaultdict(set)
    for identifier, node_ids in requirements.cited_tests().items():
        for node_id in node_ids:
            from_source[node_id].add(identifier)
    assert collected_citations.keys() <= collected_test_ids
    for node_id in collected_test_ids:
        assert collected_citations.get(node_id, frozenset()) == from_source.get(
            node_id, set()
        ), node_id
