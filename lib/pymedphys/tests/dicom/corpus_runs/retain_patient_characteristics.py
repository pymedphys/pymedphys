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

"""The Retain Patient Characteristics Option alone, over free text with no value.

The corpus plants a marker in every attribute of free text that the Option
gives C, and no method yet cleans such text, so the engine holds every
instance in which one has a value (D-038). This run empties them in each
file instead, so that the Option's kept rows are checked in instances that
it releases; holding an instance with a value is tested in
``test_deidentify_patient_characteristics.py``.
"""

import dataclasses

from pymedphys._imports import pydicom

from pymedphys._dicom.deidentify import patient_characteristics
from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module

from .._corpus_run import CorpusRun


def _tag(text: str) -> int:
    return int(text[1:5] + text[6:10], 16)


def _sequence(holder: pydicom.Dataset, tag: int) -> pydicom.Sequence:
    """Return a sequence that pydicom's dictionary may not know.

    pydicom 3.0 reads Sex Parameters for Clinical Use Category Sequence
    (0010,0043) in an Implicit VR file as UN, so it is read again as SQ.
    """
    raw = holder.get_item(tag)
    if isinstance(raw, pydicom.dataelem.RawDataElement) and raw.VR in (None, "UN"):
        holder[tag] = pydicom.dataelem.convert_raw_data_element(
            raw._replace(VR="SQ"), ds=holder
        )
    return holder[tag].value


def _emptied(file: corpus_module.CorpusFile) -> corpus_module.CorpusFile:
    placements = [
        placement
        for placement in file.manifest.placements
        if placement.profile_tag in patient_characteristics.TAGS
    ]
    if not placements:
        return file
    dataset = pydicom.dcmread(pydicom.filebase.DicomBytesIO(file.data))
    for placement in placements:
        holder = dataset
        for tag, index in placement.path.items:
            holder = _sequence(holder, _tag(tag))[index]
        element = holder[_tag(placement.path.tag)]
        element.value = b"" if element.VR == "UN" else ""
    buffer = pydicom.filebase.DicomBytesIO()
    dataset.save_as(buffer, enforce_file_format=True)
    manifest = dataclasses.replace(
        file.manifest,
        placements=tuple(
            placement
            for placement in file.manifest.placements
            if placement not in placements
        ),
    )
    return dataclasses.replace(file, data=buffer.getvalue(), manifest=manifest)


def with_empty_free_text(
    corpus: corpus_module.SyntheticCorpus,
) -> corpus_module.SyntheticCorpus:
    """Return the corpus with the Option's attributes of free text emptied."""
    return dataclasses.replace(
        corpus, files=tuple(_emptied(file) for file in corpus.files)
    )


RUN = CorpusRun(
    "retain-patient-characteristics",
    options=("retain_patient_characteristics",),
    corpus=with_empty_free_text,
)
