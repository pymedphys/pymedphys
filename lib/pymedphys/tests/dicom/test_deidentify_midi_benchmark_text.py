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

"""Tests of the MIDI benchmark's counts of what the text detector found (D-018).

Every DICOM file is synthetic, and every region is given by the tests.
"""

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import midi_benchmark_text as text
from pymedphys._dicom.deidentify import pixel_text_validation
from pymedphys._dicom.deidentify.midi_benchmark_shards import combine
from pymedphys._dicom.deidentify.reasons import PixelDataReason
from pymedphys._dicom.deidentify.run_qc import RedactionMaterial
from pymedphys._dicom.deidentify.run_results import Sequestered, Transformed
from pymedphys._dicom.deidentify.text_detection import TextBox

from . import _synthetic_references as synthetic

_BOX = TextBox(0, 0, 1, 1)


def _material(frames, regions):
    """The QC material of a cleaned instance with ``regions`` boxes in each of
    the frames that ``regions`` gives by index."""
    return RedactionMaterial(
        PixelDataReason.TEXT_BLACKED_OUT if regions else PixelDataReason.NO_TEXT_FOUND,
        frames,
        2,
        2,
        tuple((frame, (_BOX,) * count) for frame, count in regions.items()),
        None,
    )


def _ct():
    return synthetic.written(synthetic.collection()[0])


def _rt_dose():
    (dose,) = [
        dataset
        for dataset in synthetic.collection()
        if dataset.SOPClassUID == synthetic.RT_DOSE_STORAGE
    ]
    return synthetic.written(dose)


def _counted(*results):
    """Count ``results``, each a transform's result for its data."""
    counter = text.TextCounter()
    for data, result in results:
        counter.transform(lambda *_, result=result: result)(data, None)
    return counter.counts()


def _bins(**frames):
    counts = dict.fromkeys(text.REGION_BINS, 0)
    for label, number in frames.items():
        counts[label.replace("_", " ")] = number
    return counts


def test_each_cleaned_instance_is_counted_by_frame_and_region():
    counts = _counted(
        (_ct(), Transformed(None, b"", qc=(_material(5, {0: 2, 3: 12}),))),
        (_ct(), Transformed(None, b"", qc=(_material(1, {}),))),
        # A cleaned instance that the transform then sequestered was searched.
        (_ct(), Sequestered((), qc=(_material(2, {1: 1}),))),
        # An instance that it did not clean was not.
        (_ct(), Transformed(None, b"")),
        (_ct(), Sequestered(())),
    )

    assert counts == {
        "CT Image Storage": {
            "instances": 3,
            "instances_with_a_region": 2,
            "frames": 8,
            "frames_with_a_region": 3,
            "regions": 15,
            "frames_by_regions": _bins(
                **{
                    "0_to_under_1": 5,
                    "1_to_under_2": 1,
                    "2_to_under_3": 1,
                    "10_to_under_20": 1,
                }
            ),
        }
    }


def test_the_sop_classes_are_counted_apart_in_order_of_name():
    counts = _counted(
        (_rt_dose(), Transformed(None, b"", qc=(_material(3, {2: 25}),))),
        (_ct(), Transformed(None, b"", qc=(_material(1, {}),))),
    )

    assert list(counts) == ["CT Image Storage", "RT Dose Storage"]
    assert counts["RT Dose Storage"]["frames_by_regions"] == _bins(
        **{"0_to_under_1": 2, "20_or_more": 1}
    )


def test_no_instance_cleaned_is_no_count():
    assert not _counted((_ct(), Transformed(None, b"")))


def test_the_bins_are_the_text_detector_checks():
    assert text.REGION_EDGES == pixel_text_validation.REGIONS_PER_SLICE.edges
    assert text.REGION_BINS == (
        "0 to under 1",
        "1 to under 2",
        "2 to under 3",
        "3 to under 4",
        "4 to under 5",
        "5 to under 10",
        "10 to under 20",
        "20 or more",
    )
    with pytest.raises(ValueError):
        text.region_bin(-1)


class _Prepared:
    """A transform with a prepare method, as the run calls it."""

    def __init__(self):
        self.prepared = None

    def prepare(self, records, read):
        self.prepared = (records, read)

    def __call__(self, data, record):
        return Sequestered(())


def test_a_transform_keeps_its_prepare_method():
    prepared = _Prepared()
    transform = text.TextCounter().transform(prepared)

    getattr(transform, "prepare")({0: None}, len)

    assert prepared.prepared == ({0: None}, len)
    assert not hasattr(text.TextCounter().transform(lambda *_: None), "prepare")


def test_shards_counts_add_up():
    def document(shard, counts):
        return {
            "format": "f",
            "versions": {"shard": shard},
            "coverage": {"text_detection": counts},
        }

    first = _counted((_ct(), Transformed(None, b"", qc=(_material(2, {0: 1}),))))
    second = _counted(
        (_ct(), Transformed(None, b"", qc=(_material(1, {}),))),
        (_rt_dose(), Transformed(None, b"", qc=(_material(1, {0: 4}),))),
    )
    whole = _counted(
        (_ct(), Transformed(None, b"", qc=(_material(2, {0: 1}),))),
        (_ct(), Transformed(None, b"", qc=(_material(1, {}),))),
        (_rt_dose(), Transformed(None, b"", qc=(_material(1, {0: 4}),))),
    )

    for shards in ([first, second], [second, first]):
        combined = combine(
            [document(f"{n}/2", counts) for n, counts in enumerate(shards, 1)]
        )
        assert combined["coverage"]["text_detection"] == whole
