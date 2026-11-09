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

"""The PDDCA face block check (D-054), on the analytic head stored as
PDDCA's Zenodo re-host stores its cases. Every value here is invented."""

from __future__ import annotations

import json
import zipfile
from collections.abc import Mapping, Sequence

from pymedphys._imports import numpy as np
from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import (
    defacing,
    face_validation,
    face_validation_command,
)
from pymedphys._dicom.deidentify import face_validation_pddca as pddca
from pymedphys._dicom.deidentify.face_validation import CaseMeasures, CaseNotMeasured
from pymedphys._dicom.deidentify.face_validation_pddca_markdown import markdown

from . import _synthetic_head as head
from . import _synthetic_nrrd as files

_GRID = files.grid_of(files.SCAN)
_SECRET = "SYNTHETIC-PATIENT-NAME"
# Each optic nerve, as a rod of this radius from just behind its globe back
# to the orbit's apex, so that its anterior tip lies this far behind the
# globe's centre.
_NERVE_RADIUS = 2.0
_TIP_BEHIND = head.GLOBE_RADIUS + 1.0
# The cases of the module's ZIP files, in order, by what each holds; the
# first two in the first file, the rest in the second.
_CASES = ("head", "nerves-swapped", "no-eyes", "no-nerves", "no-ct")


def _nerves(grid=_GRID) -> dict[str, np.ndarray]:
    points = grid.points()
    masks = {}
    for side, name in ((-1, "R"), (1, "L")):
        x = side * head.GLOBE_X
        across = np.hypot(points[..., 0] - x, points[..., 2] - head.GLOBE_Z)
        along = (points[..., 1] >= head.GLOBE_Y + _TIP_BEHIND) & (
            points[..., 1] <= head.APEX[1]
        )
        masks[f"OpticNerve_{name}"] = (across <= _NERVE_RADIUS) & along
    return masks


def _case(ct, organs: Mapping[str, np.ndarray]) -> dict[str, bytes]:
    case = {} if ct is None else {"img.nrrd": files.nrrd_file(ct, _GRID)}
    case["Landmarks_0001.fcsv"] = f"# {_SECRET}\n".encode()
    for name, mask in organs.items():
        case[f"structures/{name}.nrrd"] = files.nrrd_file(mask.astype(np.uint8), _GRID)
    return case


def _cases(ct: np.ndarray) -> dict[str, dict[str, bytes]]:
    nerves = _nerves()
    brainstem = files.organ_masks(_GRID)["Brainstem"]
    no_eyes = files.ct_values(files.SCAN, head.Head(eyes=(False, False), noise=0.0))
    swapped = {
        "OpticNerve_R": nerves["OpticNerve_L"],
        "OpticNerve_L": nerves["OpticNerve_R"],
    }
    cases = {
        "head": _case(ct, {**nerves, "BrainStem": brainstem}),
        "nerves-swapped": _case(ct, swapped),
        "no-eyes": _case(no_eyes, nerves),
        "no-nerves": _case(ct, {"BrainStem": brainstem}),
        "no-ct": _case(None, nerves),
    }
    assert tuple(cases) == _CASES
    return cases


def _zip(path, cases: Mapping[str, Mapping[str, bytes]]) -> None:
    """A ZIP file laid out as one of PDDCA's parts: each case's files under
    a directory named for the case, and empty directory entries."""
    with zipfile.ZipFile(path, "w") as archive:
        for case, members in cases.items():
            archive.writestr(f"{case}/", b"")
            archive.writestr(f"{case}/structures/", b"")
            for name, data in members.items():
                archive.writestr(f"{case}/{name}", data)


def _parts(paths: Sequence) -> tuple[pddca.Part, ...]:
    parts = []
    for number, path in enumerate(paths, start=1):
        digest = face_validation.file_digest(path)
        parts.append(
            pddca.Part(
                f"10.5281/zenodo.{number}",
                path.name,
                digest["size"],
                digest["md5"],
                digest["sha256"],
            )
        )
    return tuple(parts)


@pytest.fixture(scope="module", name="ct")
def _ct() -> np.ndarray:
    return files.ct_values(files.SCAN, head.Head(noise=0.0))


@pytest.fixture(scope="module", name="block")
def _block(ct) -> defacing.FaceBlock:
    """The block that the finder finds in the head's CT, given its slices
    directly."""
    scan = files.SCAN
    finder = defacing.FaceFinder(
        scan.orientation, scan.positions, scan.spacing, scan.shape
    )
    for frame in ct:
        finder.add(frame.astype(float))
    return finder.block()


@pytest.fixture(scope="module", name="archives")
def _archives(tmp_path_factory, ct):
    root = tmp_path_factory.mktemp("pddca")
    cases = _cases(ct)
    # Named for the cases' directories, as PDDCA's are.
    names = {name: f"0522c{index:04d}" for index, name in enumerate(_CASES, 1)}
    first, second = root / "part1.zip", root / "part2.zip"
    _zip(first, {names[name]: cases[name] for name in _CASES[:2]})
    _zip(second, {names[name]: cases[name] for name in _CASES[2:]})
    return [first, second]


@pytest.fixture(scope="module", name="measured")
def _measured(archives) -> dict[str, CaseMeasures | CaseNotMeasured]:
    cases = [case for path in archives for case in pddca.measure_pddca(path)]
    return dict(zip(_CASES, cases, strict=True))


@pytest.fixture(scope="module", name="summary")
def _summary(archives):
    return pddca.check_pddca(archives, _parts(archives))


def test_the_parts_are_the_three_zenodo_records():
    assert [part.file for part in pddca.PARTS] == [
        f"PDDCA-1.4.1_part{number}.zip" for number in (1, 2, 3)
    ]
    assert len({part.doi for part in pddca.PARTS}) == 3
    for part in pddca.PARTS:
        assert part.doi.startswith("10.5281/zenodo.")
        assert len(part.md5) == 32
        assert len(part.sha256) == 64
    assert pddca.NERVES == ("OpticNerve_R", "OpticNerve_L")


def test_a_head_is_defaced_and_its_globes_measured_against_the_nerve_tips(
    measured, block
):
    case = measured["head"]
    assert isinstance(case, CaseMeasures)
    assert case.outcome == "defaced"
    # PDDCA has no eye masks.
    assert case.eyes == "no-reference-eyes"
    assert case.globe_errors == ()
    assert case.finder is None
    assert case.nerve_sides_swapped is False
    points = _GRID.points()
    for globe, name, found, behind in zip(
        block.globes,
        pddca.NERVES,
        case.nerve_tips,
        case.nerve_tips_behind,
        strict=True,
    ):
        nerve = points[_nerves()[name]]
        tip = nerve[nerve[:, 1] == nerve[:, 1].min()].mean(axis=0)
        assert found == pytest.approx(float(np.linalg.norm(np.asarray(globe) - tip)))
        assert behind == pytest.approx(
            float((np.asarray(globe) - tip) @ np.asarray(block.anterior))
        )
        # The rod's front lies just behind each globe.
        assert behind == pytest.approx(_TIP_BEHIND, abs=2.5)
    # The brainstem lies behind the block.
    assert case.written == {
        "BrainStem": 0.0,
        "OpticNerve_L": 0.0,
        "OpticNerve_R": 0.0,
    }


def test_nerves_named_for_the_other_side_are_counted_as_swapped(measured):
    case = measured["nerves-swapped"]
    assert isinstance(case, CaseMeasures)
    assert case.nerve_sides_swapped is True
    assert min(case.nerve_tips) > 2 * head.GLOBE_X


def test_a_case_without_both_nerves_or_a_block_has_no_nerve_measures(measured):
    no_nerves = measured["no-nerves"]
    no_eyes = measured["no-eyes"]
    assert isinstance(no_nerves, CaseMeasures)
    assert isinstance(no_eyes, CaseMeasures)
    assert no_nerves.outcome == "defaced"
    assert no_eyes.outcome == "no-eyes"
    for case in (no_nerves, no_eyes):
        assert case.nerve_tips == ()
        assert case.nerve_tips_behind == ()
        assert case.nerve_sides_swapped is None
    assert measured["no-ct"] == CaseNotMeasured("ct-missing")


def test_the_cases_are_found_by_their_directories_and_landmarks_not_read(archives):
    with zipfile.ZipFile(archives[0]) as archive:
        cases = pddca.pddca_cases(archive)
    assert [case.ct.filename for case in cases if case.ct] == [
        "0522c0001/img.nrrd",
        "0522c0002/img.nrrd",
    ]
    assert list(cases[0].organs) == ["BrainStem", "OpticNerve_L", "OpticNerve_R"]


def test_the_summary_counts_the_globes_against_the_nerve_tips(summary):
    nerves = summary["optic_nerves_of_defaced_series"]
    assert summary["format"] == pddca.FORMAT
    assert summary["held_out"] == pddca.HELD_OUT
    assert summary["cases"]["total"] == 5
    assert summary["series"] == {"defaced": 3, "not_defaced": {"no-eyes": 1}}
    assert summary["eyes_of_defaced_series"] == {"no-reference-eyes": 3}
    assert nerves["series"] == 2
    assert nerves["without_both_nerves"] == 1
    assert nerves["sides_swapped"] == 1
    tips = {
        (each["from"], each["to"]): each["count"]
        for each in nerves["globe_to_nerve_tip"]["bins"]
    }
    assert sum(tips.values()) == 4
    assert tips[(30.0, None)] == 2
    assert sum(each["count"] for each in nerves["nerve_tip_behind_globe"]["bins"]) == 4


def test_the_summary_names_the_files_and_nothing_of_a_case(summary, archives):
    files_named = summary["data"]["files"]
    assert [each["file"] for each in files_named] == [path.name for path in archives]
    assert summary["data"]["licence"] == "CC BY 3.0"
    assert "mp.12197" in summary["data"]["citation"]
    text = json.dumps(summary)
    assert "0522c" not in text
    assert _SECRET not in text
    assert pddca.check_pddca(archives, _parts(archives)) == summary


def test_a_file_that_is_not_the_one_pinned_is_refused(archives, tmp_path):
    parts = _parts(archives)
    with pytest.raises(face_validation.FaceValidationRefused, match="takes 2"):
        pddca.check_pddca(archives[:1], parts)
    changed = tmp_path / archives[1].name
    changed.write_bytes(archives[1].read_bytes() + b"\0")
    with pytest.raises(face_validation.FaceValidationRefused, match="not the one"):
        pddca.check_pddca([archives[0], changed], parts)


def test_the_page_shows_the_counts_as_commonmark(summary):
    page = markdown(summary)
    assert page.startswith("# Face block check on PDDCA\n\n")
    assert page.endswith("|\n")
    assert pddca.HELD_OUT in page
    assert "## Defaced series against the optic nerves\n" in page
    assert "| 30 or more | 2 |\n" in page
    assert "| Defaced | 3 |\n" in page
    lines = page.split("\n")
    assert not any(line != line.rstrip() for line in lines)
    assert "\n\n\n" not in page
    for index, line in enumerate(lines):
        if line.startswith("#"):
            assert index == 0 or lines[index - 1] == ""
            assert lines[index + 1] == ""


def test_the_command_writes_the_counts_and_prints_the_page(
    archives, summary, tmp_path, capsys, monkeypatch
):
    def check(paths):
        assert paths == [*archives, archives[0]]
        return summary

    monkeypatch.setattr(pddca, "check_pddca", check)
    out = tmp_path / "results"
    arguments = ["pddca", *map(str, archives), str(archives[0]), "--out", str(out)]
    assert face_validation_command.main(arguments) == 0
    written = json.loads((out / "face-validation.json").read_text(encoding="utf-8"))
    page = (out / "face-validation.md").read_text(encoding="utf-8")
    assert written == summary
    assert page == markdown(summary)
    assert capsys.readouterr().out == page


def test_the_command_refuses_files_that_are_not_those_pinned(archives, tmp_path):
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as refused:
        face_validation_command.main(
            ["pddca", *map(str, archives), str(archives[0]), "--out", str(out)]
        )
    assert "PDDCA-1.4.1_part1.zip is not the one pinned" in str(refused.value.code)
    assert str(archives[0]) not in str(refused.value.code)
    assert not out.exists()
