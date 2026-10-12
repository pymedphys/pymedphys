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

"""The ``basic`` preset over the corpus with its images compressed.

Each image is in a transfer syntax that encapsulates Pixel Data, with text
planted in its codestreams' metadata segments. The run is skipped where a
decoding plugin of those syntaxes is not installed, as with the ``dicom``
extra alone, which installs neither GDCM nor pylibjpeg-openjpeg.
"""

from pymedphys._imports import pytest

from .. import _synthetic_compressed as compressed
from .._corpus_run import COMPRESSED, CorpusRun, decoders_installed

RUN = CorpusRun(
    COMPRESSED,
    preset="basic",
    corpus=compressed.compressed_corpus,
    marks=(
        pytest.mark.skipif(
            not decoders_installed(),
            reason="a decoding plugin of the compressed corpus is not installed",
        ),
    ),
)
