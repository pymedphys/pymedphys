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

"""Tests of the MIDI benchmark's counts of what Clean Graphics removes (D-018).

Every DICOM file is synthetic.
"""

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import midi_benchmark_graphics as graphics
from pymedphys._dicom.deidentify.midi_benchmark_shards import combine
from pymedphys._dicom.deidentify.run_results import Sequestered, Transformed

from . import _synthetic_references as synthetic


def add_curve(dataset, group=0x5000):
    """Give a data set a curve group: Curve Dimensions and Curve Data."""
    dataset.add_new(group << 16 | 0x0005, "US", 2)
    dataset.add_new(group << 16 | 0x3000, "OW", b"\x00\x00\x01\x00")


def add_overlay(dataset, group=0x6000, comments=False):
    """Give a data set a 2 by 2 overlay with Overlay Data, and comments."""
    dataset.add_new(group << 16 | 0x0010, "US", 2)
    dataset.add_new(group << 16 | 0x0011, "US", 2)
    dataset.add_new(group << 16 | 0x0040, "CS", "G")
    dataset.add_new(group << 16 | 0x0050, "SS", [1, 1])
    dataset.add_new(group << 16 | 0x0100, "US", 1)
    dataset.add_new(group << 16 | 0x0102, "US", 0)
    dataset.add_new(group << 16 | 0x3000, "OW", b"\x09\x00")
    if comments:
        dataset.add_new(group << 16 | 0x4000, "LT", "SYNTHETIC OVERLAY COMMENT")


def add_overlay_in_pixel_data(dataset, group=0x6002):
    """Give a data set an overlay group without Overlay Data."""
    dataset.add_new(group << 16 | 0x0100, "US", 16)
    dataset.add_new(group << 16 | 0x0102, "US", 15)


def add_graphic_annotation(dataset):
    """Give a data set a Graphic Annotation Sequence of one item."""
    item = pydicom.Dataset()
    item.GraphicLayer = "SYNTHETIC"
    dataset.GraphicAnnotationSequence = [item]


def _ct(*additions):
    dataset = synthetic.collection()[0]
    for add in additions:
        add(dataset)
    return dataset


def _rt_dose():
    (dose,) = [
        dataset
        for dataset in synthetic.collection()
        if dataset.SOPClassUID == synthetic.RT_DOSE_STORAGE
    ]
    return dose


def _counted(*results):
    """Count ``results``, each a source data set and the transform's result
    for it."""
    counter = graphics.GraphicsCounter()
    for dataset, result in results:
        data = dataset if isinstance(dataset, bytes) else synthetic.written(dataset)
        counter.transform(lambda *_, result=result: result)(data, None)
    return counter.counts()


def _written(dataset):
    return Transformed(None, synthetic.written(dataset))


def _counts(**counts):
    return {field: counts.get(field, 0) for field in graphics.COUNTED}


@pytest.mark.parametrize(
    "add, found",
    [
        (add_curve, "curve_data"),
        (lambda dataset: add_curve(dataset, 0x501E), "curve_data"),
        (add_overlay, "overlay_data"),
        (lambda dataset: add_overlay(dataset, 0x601E), "overlay_data"),
        (add_overlay_in_pixel_data, "overlay_in_pixel_data"),
        (add_graphic_annotation, "graphic_annotation_sequence"),
    ],
)
def test_each_graphic_is_found(add, found):
    dataset = pydicom.Dataset()
    add(dataset)

    assert graphics.graphics_of(dataset) == {found}


def test_overlay_comments_are_found_beside_their_overlay():
    dataset = pydicom.Dataset()
    add_overlay(dataset, comments=True)

    assert graphics.graphics_of(dataset) == {"overlay_data", "overlay_comments"}


def test_comments_without_overlay_data_are_an_overlay_in_pixel_data_too():
    # The engine reads an overlay group without Overlay Data as one whose
    # overlay may lie in Pixel Data, whatever else it holds (D-041).
    dataset = pydicom.Dataset()
    dataset.add_new(0x60044000, "LT", "SYNTHETIC OVERLAY COMMENT")

    assert graphics.graphics_of(dataset) == {
        "overlay_comments",
        "overlay_in_pixel_data",
    }


@pytest.mark.parametrize(
    "tag, vr, value",
    [
        # Past the 16 groups of each repeating group.
        (0x50200005, "US", 2),
        (0x60203000, "OW", b"\x00\x00"),
        # Odd groups are private.
        (0x50010010, "LO", "SYNTHETIC CREATOR"),
        (0x60010010, "LO", "SYNTHETIC CREATOR"),
        # A group length alone is no curve.
        (0x50000000, "UL", 0),
        # Another attribute of the Graphic Annotation's group.
        (0x00700002, "CS", "SYNTHETIC"),
    ],
)
def test_attributes_outside_the_options_rows_are_not_graphics(tag, vr, value):
    dataset = pydicom.Dataset()
    dataset.add_new(tag, vr, value)

    assert not graphics.graphics_of(dataset)


def test_graphics_within_a_sequence_are_not_counted():
    # The IODs define the four rows at the top level, where they are looked for.
    item = pydicom.Dataset()
    add_overlay(item)
    add_curve(item)
    dataset = pydicom.Dataset()
    dataset.ReferencedImageSequence = [item]

    assert not graphics.graphics_of(dataset)


def test_each_instance_and_written_file_is_counted_by_sop_class():
    counts = _counted(
        (_ct(add_overlay), _written(_ct())),
        (_ct(add_curve, add_graphic_annotation), _written(_ct(add_curve))),
        # An instance with graphics that the transform sequestered.
        (_ct(add_overlay_in_pixel_data), Sequestered(())),
        # An instance without, written.
        (_ct(), _written(_ct())),
        # A written file that cannot be read cannot be shown to hold none.
        (_rt_dose(), Transformed(None, b"not a DICOM file")),
    )

    assert counts == {
        "CT Image Storage": _counts(
            instances=4,
            instances_with_graphics=3,
            curve_data=1,
            overlay_data=1,
            graphic_annotation_sequence=1,
            overlay_in_pixel_data=1,
            written=3,
            written_with_graphics=1,
        ),
        "RT Dose Storage": _counts(instances=1, written=1, written_with_graphics=1),
    }
    assert list(counts) == ["CT Image Storage", "RT Dose Storage"]
    assert all(list(each) == list(graphics.COUNTED) for each in counts.values())


def test_an_instance_that_cannot_be_read_is_counted_apart():
    counts = _counted((b"not a DICOM file", Sequestered(())))

    assert counts == {"unreadable": _counts(instances=1)}


def test_a_transform_that_raises_has_its_instance_counted():
    def failing(data, record):
        raise RuntimeError("synthetic failure")

    counter = graphics.GraphicsCounter()
    with pytest.raises(RuntimeError):
        counter.transform(failing)(synthetic.written(_ct(add_overlay)), None)

    assert counter.counts() == {
        "CT Image Storage": _counts(
            instances=1, instances_with_graphics=1, overlay_data=1
        )
    }


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
    transform = graphics.GraphicsCounter().transform(prepared)

    getattr(transform, "prepare")({0: None}, len)

    assert prepared.prepared == ({0: None}, len)
    assert not hasattr(graphics.GraphicsCounter().transform(lambda *_: None), "prepare")


def test_shards_counts_add_up():
    def document(shard, counts):
        return {
            "format": "f",
            "versions": {"shard": shard},
            "coverage": {"graphics": counts},
        }

    first = _counted((_ct(add_overlay), _written(_ct())))
    second = _counted(
        (_ct(), _written(_ct())),
        (_rt_dose(), _written(_rt_dose())),
    )
    whole = _counted(
        (_ct(add_overlay), _written(_ct())),
        (_ct(), _written(_ct())),
        (_rt_dose(), _written(_rt_dose())),
    )

    for shards in ([first, second], [second, first]):
        combined = combine(
            [document(f"{n}/2", counts) for n, counts in enumerate(shards, 1)]
        )
        assert combined["coverage"]["graphics"] == whole
