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

"""Clean Structured Content alone, over acquisition context items it can keep.

The corpus plants markers in every element of each Acquisition Context
Sequence (0040,0555) item and of its Content Item Modifier Sequence
(0040,0441) item, which have no Value Type and no concept name code, so the
engine could not keep them. Here each becomes a content item: the item a
Calibration DateTime and its modifier a Person Observer Name, both listed
in Table E.3.4-1 with D, so their markers are replaced. A NUMERIC item that
the table does not list is added after them. The items' other elements take
their own actions, none of which is K without another option, so no marker
in the sequence is kept (D-047).
"""

import dataclasses

from pymedphys._imports import pydicom

from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module

from .._corpus_run import CorpusRun

# Two concept names that Table E.3.4-1 lists, with their Value Types, and
# one that it does not.
CALIBRATION_DATETIME = ("113723", "Calibration DateTime", "DATETIME")
PERSON_OBSERVER_NAME = ("121008", "Person Observer Name", "PNAME")
UNLISTED_NUMERIC = ("113845", "Exposure Index", "NUMERIC")


def _concept_name(item, concept):
    value, meaning, value_type = concept
    item.ValueType = value_type
    if "ConceptNameCodeSequence" not in item:
        item.ConceptNameCodeSequence = [pydicom.Dataset()]
    (code,) = item.ConceptNameCodeSequence
    code.CodeValue = value
    code.CodingSchemeDesignator = "DCM"
    code.CodeMeaning = meaning


def _numeric_item():
    item = pydicom.Dataset()
    _concept_name(item, UNLISTED_NUMERIC)
    item.NumericValue = "100"
    units = pydicom.Dataset()
    units.CodeValue = "1"
    units.CodingSchemeDesignator = "UCUM"
    units.CodeMeaning = "no units"
    item.MeasurementUnitsCodeSequence = [units]
    return item


def _with_content_items(data: bytes) -> bytes:
    dataset = pydicom.dcmread(pydicom.filebase.DicomBytesIO(data))
    for item in dataset.AcquisitionContextSequence:
        _concept_name(item, CALIBRATION_DATETIME)
        for modifier in item.get("ContentItemModifierSequence", ()):
            _concept_name(modifier, PERSON_OBSERVER_NAME)
    dataset.AcquisitionContextSequence.append(_numeric_item())
    buffer = pydicom.filebase.DicomBytesIO()
    dataset.save_as(buffer, enforce_file_format=True)
    return buffer.getvalue()


def with_acquisition_context_items(
    corpus: corpus_module.SyntheticCorpus,
) -> corpus_module.SyntheticCorpus:
    """Return the corpus with content items in each Acquisition Context Sequence.

    pydicom writes each such instance again, which keeps every planted value.
    """
    files = []
    for file in corpus.files:
        dataset = pydicom.dcmread(
            pydicom.filebase.DicomBytesIO(file.data), stop_before_pixels=True
        )
        if "AcquisitionContextSequence" in dataset:
            file = dataclasses.replace(file, data=_with_content_items(file.data))
        files.append(file)
    return dataclasses.replace(corpus, files=tuple(files))


RUN = CorpusRun(
    "clean-structured-content",
    options=("clean_structured_content",),
    corpus=with_acquisition_context_items,
)
