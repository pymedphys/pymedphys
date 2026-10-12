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

"""What the conformance statement says of instances in a transfer syntax
that encapsulates Pixel Data."""

import dataclasses

from pymedphys._imports import pytest

from pymedphys._dicom.deidentify import conformance_markdown, source

from .test_deidentify_conformance import _section, _statement


@pytest.mark.deid_requirement("MIDI-BP-14")
def test_the_statement_says_how_compressed_instances_are_written():
    statement = _statement("basic")
    section = _section(
        conformance_markdown.render_markdown(statement), "Supported instances"
    )

    assert "1.2.840.10008.1.2.4.70" in {s.uid for s in statement.transfer_syntaxes}
    assert "without decoding and re-encoding" in section
    assert "comment and application segments" in section
    assert "to the same pixels as its source's frame" in section
    assert "every coding pass of every code-block" in section
    assert "drops only whole code-blocks is not detected" in section

    native = dataclasses.replace(
        statement,
        transfer_syntaxes=tuple(
            s
            for s in statement.transfer_syntaxes
            if s.uid in source.NATIVE_TRANSFER_SYNTAXES
        ),
    )
    assert "re-encoding" not in _section(
        conformance_markdown.render_markdown(native), "Supported instances"
    )
