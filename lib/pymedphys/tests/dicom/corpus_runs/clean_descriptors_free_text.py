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

"""Clean Descriptors alone, with technique descriptors that its vocabulary keeps.

The CT images' Series Description, in place of its planted marker, is made
only of words of the reviewed technique vocabulary, so the automatic tier
keeps it (D-036); every other planted descriptor is cleaned by neither tier
and takes its action without the option. The structure set is as the
preset's run has it.
"""

import dataclasses

from pymedphys._imports import pydicom

from pymedphys._dicom.deidentify import synthetic_corpus as corpus_module

from .._corpus_run import (
    MAPPED_NAME,
    VOCABULARY_NAME,
    CorpusRun,
    mapped_planted_name,
    with_a_second_roi,
)

# A Series Description of vocabulary words only.
TECHNIQUE_DESCRIPTION = "AXIAL CHEST"
_CT_IMAGE = "CT Image"


def with_technique_descriptions(
    corpus: corpus_module.SyntheticCorpus,
) -> corpus_module.SyntheticCorpus:
    """Return the preset's corpus with the CT images' Series Description replaced.

    pydicom writes each CT image again, which keeps every other planted value.
    """
    corpus = with_a_second_roi(corpus)
    files = []
    for file in corpus.files:
        if file.manifest.iod == _CT_IMAGE:
            dataset = pydicom.dcmread(pydicom.filebase.DicomBytesIO(file.data))
            dataset.SeriesDescription = TECHNIQUE_DESCRIPTION
            buffer = pydicom.filebase.DicomBytesIO()
            dataset.save_as(buffer, enforce_file_format=True)
            file = dataclasses.replace(file, data=buffer.getvalue())
        files.append(file)
    return dataclasses.replace(corpus, files=tuple(files))


RUN = CorpusRun(
    "clean-descriptors-free-text",
    options=("clean_descriptors",),
    corpus=with_technique_descriptions,
    reviewed_roi_names=mapped_planted_name,
    roi_names=(MAPPED_NAME, VOCABULARY_NAME),
)
