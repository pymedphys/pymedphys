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

"""The Visible Human face block check (D-057), on the analytic head written
as IDC keeps the Visible Human's CT: one series whose stacks differ in
field of view and pixel spacing."""

from __future__ import annotations

import hashlib
import io
import json
import pathlib

import pytest

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from pymedphys._dicom.deidentify import defacing, face_validation_command
from pymedphys._dicom.deidentify import face_validation_vhp as vhp
from pymedphys._dicom.deidentify.face_validation import FaceValidationRefused
from pymedphys._dicom.deidentify.face_validation_vhp_markdown import markdown

from . import _synthetic_head as head
from . import _synthetic_head_dicom as files

UUID = "00000000-0000-4000-8000-000000000001"
GLOBES = (
    (-head.GLOBE_X, head.GLOBE_Y, head.GLOBE_Z),
    (head.GLOBE_X, head.GLOBE_Y, head.GLOBE_Z),
)
# The head's stack, at the finer spacing, above the body's.
HEAD_SCAN = head.axial(
    spacing=1.0, thickness=2.5, extent=((-100, 100), (-130, 110), (-40, 120))
)
BODY_SCAN = head.axial(
    spacing=2.0, thickness=2.5, extent=((-120, 120), (-140, 120), (-110, -42.5))
)


def _written(folder: pathlib.Path) -> None:
    """The two stacks as one CT series, as IDC keeps a Visible Human scan."""
    folder.mkdir(parents=True)
    head_files = files.ct_files(HEAD_SCAN)
    body_files = files.ct_files(BODY_SCAN, series=files.ROOT + ".9")
    for number, data in enumerate([*head_files, *body_files], start=1):
        dataset = pydicom.dcmread(io.BytesIO(data))
        dataset.SeriesInstanceUID = files.SERIES
        dataset.SOPInstanceUID = f"{files.ROOT}.7.{number}"
        dataset.file_meta.MediaStorageSOPInstanceUID = dataset.SOPInstanceUID
        (folder / f"{number:04d}.dcm").write_bytes(files.written(dataset))


@pytest.fixture(name="data", scope="module")
def _data(tmp_path_factory):
    root = tmp_path_factory.mktemp("vhp")
    _written(root / UUID)
    count, digest = vhp.manifest_digest(root / UUID)
    pinned = vhp.VhpSeries(
        UUID, "VHP-F", "analytic head, two stacks", count, digest, GLOBES, True
    )
    return root, pinned


@pytest.fixture(name="summary", scope="module")
def _summary(data, tmp_path_factory):
    root, pinned = data
    renders = tmp_path_factory.mktemp("renders") / "renders"
    return vhp.check_visible_human(root, renders, (pinned,)), renders


def _series(summary):
    return summary[0]["series"][0]


def test_the_digest_is_that_of_sha256sum_sorted_by_name(tmp_path):
    (tmp_path / "b").write_bytes(b"second")
    (tmp_path / "a").write_bytes(b"first")
    lines = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n"
        for name, data in (("a", b"first"), ("b", b"second"))
    )
    assert vhp.manifest_digest(tmp_path) == (
        2,
        hashlib.sha256(lines.encode()).hexdigest(),
    )


def test_the_pinned_series_are_the_collections_ct_series():
    assert len(vhp.SERIES) == 11
    assert len({each.uuid for each in vhp.SERIES}) == 11
    assert {each.subject for each in vhp.SERIES} == {"VHP-F", "VHP-M"}
    assert sum(each.globes is not None for each in vhp.SERIES) == 3
    # Only the female cadaver's face is rendered.
    assert [each.subject for each in vhp.SERIES if each.rendered] == ["VHP-F"]
    for each in vhp.SERIES:
        assert len(each.sha256) == 64
        if each.globes is not None:
            right, left = each.globes
            # The patient's right is towards lower x.
            assert right[0] < left[0]


def test_a_run_refuses_the_series_whole_as_not_one_stack(summary):
    assert _series(summary)["engine"] == {"outcome": "not-one-stack"}


def test_each_stack_is_given_to_the_finder_as_a_series_of_its_own(summary):
    series = _series(summary)
    assert [stack["pixel_spacing_mm"] for stack in series["stacks"]] == [
        [2.0, 2.0],
        [1.0, 1.0],
    ]
    body, found = series["by_stack"]
    assert body["outcome"] in {"no-eyes", "cranium-not-above-eyes"}
    assert found["outcome"] == "block"
    assert found["swapped"] is False
    assert max(found["globe_error_mm"]) < 2.0
    assert found["inspection"]["pairs_passing"] == 1
    for side in ("right", "left"):
        ball = found["at_reference"][side]["nearest_tested"]
        assert ball["kept"] is True
        assert ball["distance_mm"] < 2.0
    assert found["at_reference"]["pair"]["passes"] is True


def test_the_resampled_slices_give_the_heads_block(summary):
    resampled = _series(summary)["resampled"]
    # The body's stack has the larger field of view, so its grid is taken.
    assert resampled["grid"]["pixel_spacing_mm"] == [2.0, 2.0]
    assert resampled["outcome"] == "block"
    assert max(resampled["globe_error_mm"]) < 3.0


def test_each_block_is_given_to_the_defacer_and_measured(summary):
    defaced = _series(summary)["defacing"]
    assert set(defaced) == {"stack 2", "resampled", "reference"}
    for label, measures in defaced.items():
        assert measures["pixels_written_outside_block"] == 0, label
        assert measures["written_ml"] > measures["tissue_written_ml"] > 0, label
        for globe in measures["reference_globes"]:
            assert globe["anterior_pole_written"] is True, label
            # The plane lies behind the globes' centres, so more than half
            # of each globe is written.
            assert globe["share_written"] > 0.5, label
    against = defaced["stack 2"]["against_reference"]
    assert abs(against["plane_ahead_mm"]) < 2.0
    assert against["angle_degrees"] < 3.0


def test_the_reference_block_is_placed_as_the_finder_places_one():
    headers = [
        vhp._Header(  # pylint: disable = protected-access
            pathlib.Path("x"),
            (0.0, 0.0, float(z)),
            (1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
            (1.0, 1.0),
            (4, 4),
            (1.0, 0.0),
        )
        for z in np.arange(-20.0, 60.0, 2.5)
    ]
    block = vhp.reference_block(GLOBES, headers)
    assert block.anterior == pytest.approx((0.0, -1.0, 0.0))
    assert block.origin[1] == pytest.approx(head.GLOBE_Y + defacing.MARGIN)
    # Lowered by the 2.5 mm gap, which is larger than the least voxel.
    assert block.inferior_limit == pytest.approx(
        head.GLOBE_Z - vhp.REFERENCE_RADIUS - 2.5
    )


def test_the_tissue_about_the_reference_globes_is_measured(summary):
    for tissue in _series(summary)["reference_tissue"]:
        assert tissue["core"]["soft_tissue_share"] > 0.9
        assert tissue["core"]["median_hu"] == pytest.approx(head.VITREOUS, abs=10)
        assert tissue["shell"]["pixels"] > tissue["core"]["pixels"]


def test_the_rendered_series_face_is_rendered_with_the_attribution(summary):
    series = _series(summary)
    renders = summary[1]
    assert set(series["renders"]) == {
        "VHP-F-surface-as-received.png",
        "VHP-F-surface-stack-2.png",
        "VHP-F-surface-resampled.png",
        "VHP-F-surface-reference.png",
        "VHP-F-globes.png",
        "NOTICE.txt",
    }
    for name in series["renders"]:
        data = (renders / name).read_bytes()
        if name.endswith(".png"):
            assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert vhp.ATTRIBUTION in (renders / "NOTICE.txt").read_text()


def test_an_unrendered_series_writes_no_render(data, tmp_path):
    root, pinned = data
    plain = vhp.VhpSeries(
        pinned.uuid, "VHP-M", pinned.description, pinned.files, pinned.sha256
    )
    summary = vhp.check_visible_human(root, tmp_path / "renders", (plain,))
    assert "renders" not in summary["series"][0]
    assert "reference_block" not in summary["series"][0]
    assert not (tmp_path / "renders").exists()


def test_the_summary_carries_the_source_terms_and_attribution(summary):
    whole = summary[0]
    assert whole["format"] == vhp.FORMAT
    assert whole["source"]["attribution"] == (
        "Courtesy of the U.S. National Library of Medicine."
    )
    assert "may not reflect the most current" in whole["source"]["notice"]
    assert "not endorsed" in whole["source"]["notice"]
    assert whole["source"]["licence"] == vhp.LICENCE
    assert whole["held_out"] == vhp.HELD_OUT
    json.dumps(whole)


@pytest.mark.parametrize("change", ["missing", "changed"])
def test_a_series_that_is_not_the_one_pinned_is_refused_before_any_render(
    data, tmp_path, change
):
    root, pinned = data
    other = tmp_path / "data"
    if change == "changed":
        (other / UUID).mkdir(parents=True)
        for path in (root / UUID).iterdir():
            (other / UUID / path.name).write_bytes(path.read_bytes())
        first = sorted((other / UUID).iterdir())[0]
        first.write_bytes(first.read_bytes() + b"\0\0")
    else:
        other.mkdir()
    with pytest.raises(FaceValidationRefused, match=UUID):
        vhp.check_visible_human(other, tmp_path / "renders", (pinned,))
    assert not (tmp_path / "renders").exists()


def test_the_page_shows_the_measures_as_commonmark(summary):
    page = markdown(summary[0])
    assert page.startswith("# Face block check on the NLM Visible Human Project\n")
    assert page.count(vhp.ATTRIBUTION) == 2
    assert "| VHP-F | `" + UUID + "` |" in page
    assert "`not-one-stack`" in page
    assert "### Defacing" in page
    assert "\t" not in page
    assert page.endswith("\n")


def test_the_command_writes_the_summary_page_and_renders(
    data, tmp_path, monkeypatch, capsys
):
    root, pinned = data
    monkeypatch.setattr(vhp, "SERIES", (pinned,))
    out = tmp_path / "out"
    assert (
        face_validation_command.main(["visible-human", str(root), "--out", str(out)])
        == 0
    )
    summary = json.loads((out / vhp.JSON_NAME).read_text())
    assert summary["series"][0]["engine"]["outcome"] == "not-one-stack"
    page = (out / vhp.MARKDOWN_NAME).read_text()
    assert capsys.readouterr().out == page
    assert (out / vhp.RENDERS / "VHP-F-globes.png").is_file()
    with pytest.raises(SystemExit, match="must not exist"):
        face_validation_command.main(["visible-human", str(root), "--out", str(out)])


def test_the_command_refuses_a_series_that_is_missing(tmp_path, monkeypatch, data):
    _, pinned = data
    monkeypatch.setattr(vhp, "SERIES", (pinned,))
    with pytest.raises(SystemExit, match="is missing"):
        face_validation_command.main(
            ["visible-human", str(tmp_path), "--out", str(tmp_path / "out")]
        )
    assert not (tmp_path / "out").exists()
