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

"""Clean Pixel Data's blackout of the text found in native Pixel Data (D-037).

Every file is synthetic, and every finder is a stand-in that gives fixed
regions, so no model is downloaded and no network is reached.
"""

import io
import json

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import (
    conformance,
    conformance_markdown,
    pixel_cleaning,
    policy,
    release_report,
    run,
)
from pymedphys._dicom.deidentify.instance_transform import (
    HeldEvidence,
    InstanceTransform,
    ReleaseGate,
)
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.pixel_cleaning import (
    PixelDataRefused,
    black_out,
    redaction_problem,
)
from pymedphys._dicom.deidentify.policy import PolicyError
from pymedphys._dicom.deidentify.reasons import (
    HeldPixelData,
    PixelDataReason,
    TransformReason,
)
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.run_report import RELEASE_REPORT
from pymedphys._dicom.deidentify.source import read_source
from pymedphys._dicom.deidentify.text_detection import TextBox

from . import _synthetic_compressed as compressed
from . import _synthetic_references as synthetic

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
CLEAN_PIXEL_DATA = policy.CLEAN_PIXEL_DATA
BASIC_PROFILE_CODE = "113100"
CLEAN_PIXEL_DATA_CODE = "113101"
IMPLICIT_VR_LITTLE_ENDIAN = "1.2.840.10008.1.2"
BOX = TextBox(1, 2, 3, 5)


class Finder:
    """Gives fixed regions in the frames it names, and records each frame."""

    def __init__(self, boxes=(BOX,), frames=None):
        self.boxes = tuple(boxes)
        self.frames = frames
        self.seen = []

    def find(self, frame):
        self.seen.append(np.array(frame))
        index = len(self.seen) - 1
        if self.frames is not None and index not in self.frames:
            return ()
        return self.boxes


def _ct(frames, *, bits_stored=12, signed=False, photometric="MONOCHROME2"):
    """A CT slice whose native Pixel Data holds ``frames`` of stored words."""
    words = np.asarray(frames)
    if words.ndim == 2:
        words = words[np.newaxis]
    dataset = synthetic.ct_slice(0)
    dataset.SamplesPerPixel = 1
    dataset.PhotometricInterpretation = photometric
    dataset.Rows, dataset.Columns = words.shape[1:]
    dataset.BitsAllocated, dataset.BitsStored = 16, bits_stored
    dataset.HighBit = bits_stored - 1
    dataset.PixelRepresentation = int(signed)
    if words.shape[0] > 1:
        dataset.NumberOfFrames = words.shape[0]
    dataset.PixelData = words.astype("<u2").tobytes()
    return dataset


def _rgb(frame, planar):
    """A CT slice whose native Pixel Data holds one 8-bit RGB frame."""
    dataset = synthetic.ct_slice(0)
    dataset.SamplesPerPixel = 3
    dataset.PhotometricInterpretation = "RGB"
    dataset.PlanarConfiguration = planar
    dataset.Rows, dataset.Columns = frame.shape[:2]
    dataset.BitsAllocated = dataset.BitsStored = 8
    dataset.HighBit = 7
    dataset.PixelRepresentation = 0
    stored = np.moveaxis(frame, -1, 0) if planar else frame
    dataset.PixelData = stored.astype(np.uint8).tobytes()
    return dataset


def _frame(rows=6, columns=8, start=100):
    return (np.arange(rows * columns).reshape(rows, columns) + start) % 4096


def _source(dataset, transfer_syntax=synthetic.EXPLICIT_VR_LITTLE_ENDIAN):
    return read_source(synthetic.written(dataset, transfer_syntax))


def _blacked_out(dataset, finder=None, **written):
    source = _source(dataset, **written)
    return source, black_out(source, source.dataset(), finder or Finder())


def _replaced(source, redaction):
    """The source's file with its Pixel Data replaced by the redaction's."""
    dataset = source.dataset()
    dataset.PixelData = redaction.value
    return read_source(synthetic.written(dataset, source.transfer_syntax))


def _pixels(source):
    return pydicom.pixels.pixel_array(source.dataset())


def _inside(shape, box=BOX):
    mask = np.zeros(shape, dtype=bool)
    mask[box.top : box.bottom, box.left : box.right] = True
    return mask


@pytest.mark.parametrize(
    "photometric, fill", [("MONOCHROME2", np.min), ("MONOCHROME1", np.max)]
)
@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_text_is_set_to_the_frames_stored_fill(photometric, fill):
    frame = _frame()
    source, redaction = _blacked_out(_ct(frame, photometric=photometric))

    output = _replaced(source, redaction)
    pixels = _pixels(output)
    inside = _inside(frame.shape)
    assert np.all(pixels[inside] == fill(frame))
    assert np.array_equal(pixels[~inside], frame[~inside])
    assert redaction.reason is PixelDataReason.TEXT_BLACKED_OUT
    assert not redaction_problem(source, output, redaction)


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_signed_values_keep_their_sign_in_the_unused_bits():
    frame = _frame() - 2048
    words = frame % 65536  # sign-extended two's complement
    source, redaction = _blacked_out(_ct(words, signed=True))

    output = _replaced(source, redaction)
    pixels = _pixels(output)
    inside = _inside(frame.shape)
    assert np.all(pixels[inside] == frame.min())
    assert np.array_equal(pixels[~inside], frame[~inside])
    written = np.frombuffer(redaction.value, "<u2").reshape(frame.shape)
    assert np.all(written[inside] == frame.min() % 65536)
    assert not redaction_problem(source, output, redaction)


@pytest.mark.parametrize("planar", [0, 1])
@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_rgb_text_is_set_to_black_in_either_planar_configuration(planar):
    rng = np.random.default_rng(0)
    frame = rng.integers(1, 256, size=(6, 8, 3))
    finder = Finder()
    source, redaction = _blacked_out(_rgb(frame, planar), finder)

    output = _replaced(source, redaction)
    pixels = _pixels(output)
    inside = _inside(frame.shape[:2])
    assert np.all(pixels[inside] == 0)
    assert np.array_equal(pixels[~inside], frame[~inside])
    (seen,) = finder.seen
    assert np.array_equal(seen, frame)
    assert not redaction_problem(source, output, redaction)


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_each_frame_is_searched_and_blacked_out_with_its_own_fill():
    frames = np.stack([_frame(start=100), _frame(start=900), _frame(start=50)])
    finder = Finder(frames={1})
    source, redaction = _blacked_out(_ct(frames), finder)

    assert [np.array_equal(seen, f) for seen, f in zip(finder.seen, frames)] == [
        True
    ] * 3
    (regions,) = redaction.regions
    assert (regions.frame, regions.boxes) == (1, (BOX,))
    output = _replaced(source, redaction)
    pixels = _pixels(output)
    inside = _inside(frames.shape[1:])
    assert np.array_equal(pixels[[0, 2]], frames[[0, 2]])
    assert np.all(pixels[1][inside] == frames[1].min())
    assert np.array_equal(pixels[1][~inside], frames[1][~inside])
    assert not redaction_problem(source, output, redaction)


def test_regions_beyond_the_frame_are_clipped_to_it():
    frame = _frame(rows=4, columns=4)
    finder = Finder(boxes=(TextBox(2, 3, 40, 40), TextBox(9, 9, 12, 12)))
    _, redaction = _blacked_out(_ct(frame), finder)

    (regions,) = redaction.regions
    assert regions.boxes == (TextBox(2, 3, 4, 4),)


def test_a_frame_without_text_is_left_as_it_is_and_still_held():
    frame = _frame()
    source, redaction = _blacked_out(_ct(frame), Finder(boxes=()))

    assert not redaction.regions
    assert redaction.value == source.value_field(pixel_cleaning.PIXEL_DATA)
    assert redaction.reason is PixelDataReason.NO_TEXT_FOUND


def test_implicit_vr_little_endian_is_cleaned_in_its_own_transfer_syntax():
    frame = _frame()
    source, redaction = _blacked_out(
        _ct(frame), transfer_syntax=IMPLICIT_VR_LITTLE_ENDIAN
    )

    output = _replaced(source, redaction)
    assert output.transfer_syntax == IMPLICIT_VR_LITTLE_ENDIAN
    assert not redaction_problem(source, output, redaction)


def test_an_instance_without_pixel_data_has_nothing_to_clean():
    source = _source(synthetic.rt_plan())
    finder = Finder()

    assert black_out(source, source.dataset(), finder) is None
    assert not finder.seen


def test_compressed_pixel_data_is_refused():
    source = read_source(compressed.rle_ct_image(_frame()))

    with pytest.raises(PixelDataRefused) as refused:
        black_out(source, source.dataset(), Finder())
    assert refused.value.reason is TransformReason.COMPRESSED_PIXEL_DATA


def _with(**attributes):
    def change(dataset):
        for keyword, value in attributes.items():
            if value is None:
                delattr(dataset, keyword)
            else:
                setattr(dataset, keyword, value)
        return dataset

    return change


def _overlay_bit(dataset):
    words = np.frombuffer(dataset.PixelData, "<u2").copy()
    words[0] |= 0x8000
    dataset.PixelData = words.tobytes()
    return dataset


def _not_sign_extended(dataset):
    words = np.frombuffer(dataset.PixelData, "<u2").copy()
    words[0] = 0x7800  # a positive 12-bit value with unused bits set
    dataset.PixelData = words.tobytes()
    return dataset


def _short(dataset):
    dataset.PixelData = dataset.PixelData[:-4]
    return dataset


def _float_pixel_data(dataset):
    dataset.FloatPixelData = np.zeros(4, np.float32).tobytes()
    return dataset


@pytest.mark.parametrize(
    "change",
    [
        _with(HighBit=15),
        _with(BitsAllocated=12),
        _with(BitsStored=17),
        _with(PhotometricInterpretation="PALETTE COLOR"),
        _with(PhotometricInterpretation="YBR_FULL", SamplesPerPixel=3),
        _with(Rows=None),
        _with(NumberOfFrames=0),
        _with(PixelRepresentation=2),
        _overlay_bit,
        _short,
        _float_pixel_data,
    ],
    ids=[
        "high-bit",
        "bits-allocated",
        "bits-stored",
        "palette",
        "ybr",
        "no-rows",
        "no-frames",
        "representation",
        "overlay-in-unused-bits",
        "short",
        "float",
    ],
)
def test_pixel_data_that_cannot_be_read_as_frames_is_refused(change):
    source = _source(change(_ct(_frame())))

    with pytest.raises(PixelDataRefused) as refused:
        black_out(source, source.dataset(), Finder())
    assert refused.value.reason is TransformReason.UNCLEANABLE_PIXEL_DATA


def test_signed_unused_bits_that_do_not_give_the_sign_are_refused():
    source = _source(_not_sign_extended(_ct(_frame(), signed=True)))

    with pytest.raises(PixelDataRefused) as refused:
        black_out(source, source.dataset(), Finder())
    assert refused.value.reason is TransformReason.UNCLEANABLE_PIXEL_DATA


def _changed_word(redaction, index):
    words = np.frombuffer(redaction.value, "<u2").copy()
    words[index] ^= 1
    return words.tobytes()


@pytest.mark.parametrize(
    "where", [0, 1 * 8 + 3], ids=["outside-the-region", "inside-the-region"]
)
def test_written_pixel_data_that_differs_from_the_plan_is_found(where):
    source, redaction = _blacked_out(_ct(_frame()))
    dataset = source.dataset()
    dataset.PixelData = _changed_word(redaction, where)
    output = read_source(synthetic.written(dataset))

    assert redaction_problem(source, output, redaction)


@pytest.mark.parametrize(
    "where",
    [48 + 1 * 8 + 3, 2 * 48],
    ids=["inside-the-second-frames-region", "in-the-third-frame"],
)
def test_written_pixel_data_that_differs_in_a_later_frame_is_found(where):
    frames = np.stack([_frame(start=100), _frame(start=900), _frame(start=50)])
    source, redaction = _blacked_out(_ct(frames), Finder(frames={1}))
    dataset = source.dataset()
    dataset.PixelData = _changed_word(redaction, where)
    output = read_source(synthetic.written(dataset))

    assert redaction_problem(source, output, redaction)


def test_written_pixel_data_in_another_transfer_syntax_is_found():
    source, redaction = _blacked_out(_ct(_frame()))
    dataset = source.dataset()
    dataset.PixelData = redaction.value
    output = read_source(synthetic.written(dataset, IMPLICIT_VR_LITTLE_ENDIAN))

    assert redaction_problem(source, output, redaction)


def _transform(finder=None, options=(CLEAN_PIXEL_DATA,)):
    return InstanceTransform(
        policy.compose_custom_policy(options),
        KEY,
        finder=Finder() if finder is None else finder,
        unvalidated_policy=True,
    )


def _transformed(transform, data):
    return transform(data, InstanceRecord.from_file(data))


def _codes(dataset):
    return [item.CodeValue for item in dataset.DeidentificationMethodCodeSequence]


def test_the_engine_applies_clean_pixel_data():
    assert policy.ENGINE_APPLIES[CLEAN_PIXEL_DATA]
    assert CLEAN_PIXEL_DATA in policy.ENGINE_OPTIONS
    assert CLEAN_PIXEL_DATA not in policy.ENABLED_OPTIONS


def test_a_finder_is_given_exactly_with_clean_pixel_data():
    with pytest.raises(PolicyError, match="text finder"):
        InstanceTransform(
            policy.compose_custom_policy((CLEAN_PIXEL_DATA,)),
            KEY,
            unvalidated_policy=True,
        )
    with pytest.raises(PolicyError, match="text finder"):
        InstanceTransform(
            policy.compose_policy("basic"),
            KEY,
            finder=Finder(),
            unvalidated_policy=True,
        )


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_a_ct_image_is_written_blacked_out_and_held_for_review():
    frame = _frame()
    data = synthetic.written(_ct(frame))
    result = _transformed(_transform(), data)

    assert isinstance(result, run.Transformed), result
    evidence = result.evidence
    assert isinstance(evidence, HeldEvidence)
    held = evidence.held  # pylint: disable=no-member
    assert held == (HeldPixelData(PixelDataReason.TEXT_BLACKED_OUT),)
    written = pydicom.dcmread(io.BytesIO(result.data))
    pixels = pydicom.pixels.pixel_array(written)
    inside = _inside(frame.shape)
    assert np.all(pixels[inside] == frame.min())
    assert np.array_equal(pixels[~inside], frame[~inside])
    assert written.file_meta.TransferSyntaxUID == synthetic.EXPLICIT_VR_LITTLE_ENDIAN
    # Burned In Annotation is kept as received until a reviewer's decision.
    assert "BurnedInAnnotation" not in written
    assert _codes(written) == [BASIC_PROFILE_CODE]

    decision = ReleaseGate()(result.data, result.evidence, (result.evidence,))
    assert isinstance(decision, run.HoldForReview)
    assert decision.reasons[0] == HeldPixelData(PixelDataReason.TEXT_BLACKED_OUT)


def test_implicit_vr_pixel_data_is_written_blacked_out_in_implicit_vr():
    frame = _frame()
    data = synthetic.written(_ct(frame), IMPLICIT_VR_LITTLE_ENDIAN)
    result = _transformed(_transform(), data)

    assert isinstance(result, run.Transformed), result
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert written.file_meta.TransferSyntaxUID == IMPLICIT_VR_LITTLE_ENDIAN
    pixels = pydicom.pixels.pixel_array(written)
    inside = _inside(frame.shape)
    assert np.all(pixels[inside] == frame.min())
    assert np.array_equal(pixels[~inside], frame[~inside])


def test_an_image_without_text_found_is_still_held_for_review():
    data = synthetic.written(_ct(_frame()))
    result = _transformed(_transform(Finder(boxes=())), data)

    assert isinstance(result, run.Transformed), result
    evidence = result.evidence
    assert isinstance(evidence, HeldEvidence)
    held = evidence.held  # pylint: disable=no-member
    assert held == (HeldPixelData(PixelDataReason.NO_TEXT_FOUND),)
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert written.PixelData == pydicom.dcmread(io.BytesIO(data)).PixelData


def test_an_instance_without_pixel_data_is_written_without_the_options_code():
    finder = Finder()
    result = _transformed(_transform(finder), synthetic.written(synthetic.rt_plan()))

    assert isinstance(result, run.Transformed), result
    assert not isinstance(result.evidence, HeldEvidence)
    assert not finder.seen
    written = pydicom.dcmread(io.BytesIO(result.data))
    assert CLEAN_PIXEL_DATA_CODE not in _codes(written)


def test_compressed_pixel_data_sequesters_the_instance():
    data = compressed.rle_ct_image(_frame())
    result = _transformed(_transform(), data)

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (TransformReason.COMPRESSED_PIXEL_DATA,)


def test_a_redaction_that_was_not_written_as_planned_sequesters_the_instance(
    monkeypatch,
):
    monkeypatch.setattr(
        "pymedphys._dicom.deidentify.instance_transform.redaction_problem",
        lambda *_: True,
    )
    result = _transformed(_transform(), synthetic.written(_ct(_frame())))

    assert isinstance(result, run.Sequestered)
    assert result.reasons == (TransformReason.REDACTION_MISMATCH,)


def _statement(monkeypatch, options):
    monkeypatch.setattr(policy, "ENABLED_PRESETS", frozenset({"basic"}))
    monkeypatch.setattr(policy, "ENABLED_OPTIONS", frozenset(options))
    selected = policy.select_policy(options=options) if options else None
    statement = conformance.conformance_statement(
        selected or policy.select_policy("basic"), vocabulary=None
    )
    text = conformance_markdown.render_markdown(statement)
    return statement, " ".join(text.split())


UNCHANGED = "The engine writes Pixel Data (7FE0,0010) unchanged"
BLACKED_OUT = "Under the Clean Pixel Data Option, the engine replaces each region"


@pytest.mark.deid_requirement("PS3.15-E.1.3-01")
def test_the_statement_says_how_pixel_data_are_cleaned_and_claims_no_code(
    monkeypatch,
):
    statement, text = _statement(monkeypatch, [CLEAN_PIXEL_DATA])

    # Pending until the option's claim is described, so the statement claims
    # no conformance; the markers' codes are the policy's.
    assert not statement.claims_conformance
    assert conformance.PENDING_PIXEL_DATA in statement.pending
    assert BASIC_PROFILE_CODE in statement.markers.codes
    assert CLEAN_PIXEL_DATA_CODE not in statement.markers.codes
    assert CLEAN_PIXEL_DATA_CODE not in statement.markers.review_codes
    assert BLACKED_OUT in text
    assert UNCHANGED not in text


def test_the_statement_of_a_policy_without_the_option_keeps_pixel_data(
    monkeypatch,
):
    statement, text = _statement(monkeypatch, [])

    assert conformance.PENDING_PIXEL_DATA not in statement.pending
    assert UNCHANGED in text
    assert BLACKED_OUT not in text


def test_the_release_report_counts_the_held_instances_by_reason():
    counted = release_report.held_for_review(
        [
            (HeldPixelData(PixelDataReason.TEXT_BLACKED_OUT),),
            (HeldPixelData(PixelDataReason.TEXT_BLACKED_OUT),),
            (HeldPixelData(PixelDataReason.NO_TEXT_FOUND),),
        ]
    )

    assert counted == (
        release_report.HeldForReview("pixel-data", "no-text-found", 1),
        release_report.HeldForReview("pixel-data", "text-blacked-out", 2),
    )


def test_a_held_instance_names_its_pixel_data_reason():
    with pytest.raises(TypeError):
        HeldPixelData("text-blacked-out")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        release_report.held_for_review([(PixelDataReason.NO_TEXT_FOUND,)])


@pytest.mark.deid_requirement("PS3.15-E.3.1-01")
def test_a_run_holds_its_images_and_reports_why(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    datasets = [_ct(_frame()), synthetic.structure_set(), synthetic.rt_plan()]
    for position, dataset in enumerate(datasets):
        (source / f"{position}.dcm").write_bytes(synthetic.written(dataset))
    transform = _transform()

    result = run.run(
        run.discover(source),
        tmp_path / "release",
        transform,
        ReleaseGate(),
        qc_destination=tmp_path / "qc",
        reporter=transform.reporter,
    )

    assert [outcome.status for outcome in result.outcomes] == [
        run.Status.HELD_FOR_REVIEW,
        run.Status.RELEASED,
        run.Status.RELEASED,
    ]
    text = (tmp_path / "release" / RELEASE_REPORT).read_text(encoding="utf-8")
    report = json.loads(text)
    assert report["held_for_review"] == [
        {"stage": "pixel-data", "code": "text-blacked-out", "count": 1}
    ]
