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

"""Encapsulated PDF: supported, and sequestered at its document (D-010, D-022).

The Basic Profile gives Encapsulated Document (0042,0011) D, no option of
Table E.1-1 gives it another action, and no reviewed rule gives a document a
dummy value, so every Encapsulated PDF that holds one is sequestered, under
every policy, with that attribute and action as its reason, and nothing of
it is written.
"""

import io
import itertools
import os
import shutil
import tempfile
from pathlib import Path

from pymedphys._imports import pydicom, pytest

from pymedphys._dicom.deidentify import pilot_command, policy, run, scope
from pymedphys._dicom.deidentify.descriptor_cleaning import DescriptorCleaning
from pymedphys._dicom.deidentify.file_layout import ElementPath
from pymedphys._dicom.deidentify.instance_transform import InstanceTransform
from pymedphys._dicom.deidentify.keys import DeidKey
from pymedphys._dicom.deidentify.references import InstanceRecord
from pymedphys._dicom.deidentify.reviewed_roi_names import ReviewedNames
from pymedphys._dicom.deidentify.walker import SequesterReason

from . import _corpus_run
from . import _synthetic_references as synthetic
from .test_deidentify_pilot_command import _pilot, _source

pytestmark = [pytest.mark.pydicom, pytest.mark.usefixtures("pydicom_behaviour")]

KEY = DeidKey(bytes(range(32)))
DOCUMENT_INSTANCE = "2.25.992"
# Identifying text planted in the document's page, in its document
# information dictionary, and in the header attributes that the review
# covered.
PAGE_SENTINEL = "QUILLON-ZEBEDEE-4417"
AUTHOR_SENTINEL = "MARGOLIS-TREVANION-2286"
TITLE_SENTINEL = "TREATMENT SUMMARY FOR PERSEPHONE ABERNATHY-9051"
DOCUMENT = ElementPath((), "(0042,0011)")


def _pdf():
    """Return a one-page PDF that shows PAGE_SENTINEL and names AUTHOR_SENTINEL."""
    stream = f"BT /F1 12 Tf 72 720 Td ({PAGE_SENTINEL}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        f"<< /Author ({AUTHOR_SENTINEL}) >>".encode("ascii"),
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(data))
        data += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(data)
    data += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        data += b"%010d 00000 n \n" % offset
    data += b"trailer\n<< /Size %d /Root 1 0 R /Info 6 0 R >>\n" % (len(objects) + 1)
    data += b"startxref\n%d\n%%%%EOF\n" % xref
    return bytes(data)


def _encapsulated_pdf():
    """Return an Encapsulated PDF of the synthetic patient's study."""
    dataset = synthetic.instance(
        synthetic.ENCAPSULATED_PDF_STORAGE, DOCUMENT_INSTANCE, synthetic.OTHER_SERIES
    )
    document = _pdf()
    dataset.Modality = "DOC"
    dataset.SeriesNumber = 1
    dataset.InstanceNumber = 1
    dataset.ConversionType = "WSD"
    dataset.SecondaryCaptureDeviceManufacturer = "INVENTED SYSTEMS"
    dataset.SecondaryCaptureDeviceManufacturerModelName = "INVENTED PRINTER"
    dataset.SecondaryCaptureDeviceSoftwareVersions = "1.0"
    dataset.BurnedInAnnotation = "YES"
    dataset.DocumentTitle = TITLE_SENTINEL
    dataset.ConceptNameCodeSequence = []
    dataset.MIMETypeOfEncapsulatedDocument = "application/pdf"
    dataset.EncapsulatedDocument = document
    dataset.EncapsulatedDocumentLength = len(document)
    return dataset


def _policies():
    """Every preset, every set of the presets' options, and each other option.

    The sets are every subset of the options that the presets select, among
    them Clean Recognizable Visual Features, that a custom policy accepts, so
    without both Retain Device Identity and Retain Longitudinal Temporal
    Information with Modified Dates. Each option that the engine applies and
    no preset selects, such as Retain UIDs or Clean Pixel Data, is taken alone.
    """
    in_presets = [
        option
        for option in policy.ENGINE_OPTIONS
        if any(option in options for options in policy.PRESETS.values())
    ]
    subsets = [
        subset
        for size in range(len(in_presets) + 1)
        for subset in itertools.combinations(in_presets, size)
        if not {policy.DEVICE_IDENTITY, policy.MODIFIED_DATES} <= set(subset)
    ]
    others = [(option,) for option in policy.ENGINE_OPTIONS if option not in in_presets]
    return [policy.compose_policy(preset) for preset in policy.PRESETS] + [
        policy.compose_custom_policy(options) for options in [*subsets, *others]
    ]


class _NoText:
    """A text finder that finds nothing, for Clean Pixel Data."""

    method = {"finder": "none"}

    def find(self, frame):
        del frame
        return ()


@pytest.fixture(name="tmp_path")
def _short_tmp_path(tmp_path):
    """Give a base directory short enough for Windows' path limit."""
    if os.name != "nt":
        yield tmp_path
        return
    short = Path(tempfile.mkdtemp(prefix="d"))
    yield short
    shutil.rmtree(short, ignore_errors=True)


def test_the_synthetic_document_is_a_pdf_that_holds_its_sentinels():
    document = _pdf()

    assert document.startswith(b"%PDF-1.4\n")
    assert document.endswith(b"%%EOF\n")
    assert PAGE_SENTINEL.encode() in document
    assert AUTHOR_SENTINEL.encode() in document
    # Each cross-reference entry gives the offset of its object.
    xref = document.index(b"\nxref\n") + 1
    entries = document[xref:].split(b"\n")[3:9]
    for number, entry in enumerate(entries, start=1):
        offset = int(entry[:10])
        assert document[offset:].startswith(b"%d 0 obj\n" % number)


@pytest.mark.deid_requirement("MIDI-BP-06")
def test_an_encapsulated_pdf_is_supported():
    dataset = _encapsulated_pdf()

    found = scope.classify(dataset.SOPClassUID, synthetic.EXPLICIT_VR_LITTLE_ENDIAN)

    assert found == scope.Classification(
        scope.Disposition.SUPPORTED, "Encapsulated PDF"
    )


@pytest.mark.deid_requirement("MIDI-BP-03", "MIDI-BP-06")
@pytest.mark.parametrize(
    "composed", _policies(), ids=lambda composed: ",".join(composed.options)
)
def test_every_policy_sequesters_an_encapsulated_pdf_at_its_document(composed):
    data = synthetic.written(_encapsulated_pdf())
    transform = InstanceTransform(
        composed,
        KEY,
        cleaning=(
            DescriptorCleaning(None, ReviewedNames.empty())
            if "clean_descriptors" in composed.options
            else None
        ),
        finder=_NoText() if policy.CLEAN_PIXEL_DATA in composed.options else None,
        face_review=_corpus_run.face_review_for(composed),
        unvalidated_policy=True,
    )

    result = transform(data, InstanceRecord.from_file(data))

    assert isinstance(result, run.Sequestered)
    (sequestration,) = result.reasons
    assert (
        sequestration.path,
        sequestration.action,
        sequestration.vr,
        sequestration.reason,
    ) == (DOCUMENT, "D", "OB", SequesterReason.NO_DUMMY_VALUE)


@pytest.mark.deid_requirement("MIDI-BP-06")
def test_a_run_writes_nothing_of_an_encapsulated_pdf_and_reports_its_reason(
    tmp_path,
):
    source = _source(tmp_path, _encapsulated_pdf())
    release = tmp_path / "release"

    status, out, err = _pilot(source, "--preset", "basic", "--release", release)

    assert (status, err) == (pilot_command.EXIT_WITHHELD, "")
    lines = out.splitlines()
    assert "  sequestered: 1" in lines
    start = lines.index("release report, sequestered instances by reason:")
    assert lines[start + 1].startswith("  stage=walker code=no-dummy-value ")
    assert "attribute=(0042,0011)" in lines[start + 1]
    assert lines[start + 1].endswith(": 1")
    # Nothing of the document, its title, or its patient leaves in the
    # release, in its reports, or in what the command prints.
    released = b"".join(
        path.read_bytes() for path in release.rglob("*") if path.is_file()
    )
    for sentinel in (
        PAGE_SENTINEL,
        AUTHOR_SENTINEL,
        TITLE_SENTINEL,
        synthetic.PATIENT_ID,
        synthetic.PATIENTS_NAME,
    ):
        assert sentinel.encode() not in released, sentinel
        assert sentinel not in out, sentinel
    # The rest of the collection is released.
    written = [
        pydicom.dcmread(io.BytesIO(path.read_bytes()))
        for path in release.rglob("*.dcm")
    ]
    assert len(written) == len(synthetic.collection())
    assert synthetic.ENCAPSULATED_PDF_STORAGE not in {
        each.SOPClassUID for each in written
    }
