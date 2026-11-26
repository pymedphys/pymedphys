# Copyright (C) 2026 Jeff

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Failed pseudonymisation batches must not become downloadable archives."""

from pymedphys._imports import pytest

pytest.importorskip("streamlit")
pytest.importorskip("pydicom")

from pymedphys._streamlit.apps import pseudonymise as app  # noqa: E402


@pytest.mark.parametrize("bad_batches", [[True], [True, False], [False, True]])
def test_only_successful_batches_receive_download_links(monkeypatch, bad_batches):
    files = [object() for _ in range(2 * len(bad_batches))]
    boundaries = list(range(2, len(files) + 1, 2))
    monkeypatch.setattr(
        app, "_gen_index_list_to_fifty_mbyte_increment", lambda _: boundaries
    )
    monkeypatch.setattr(app.st, "write", lambda *_: None)
    messages = []
    monkeypatch.setattr(app.st, "text", messages.append)
    downloads = []
    monkeypatch.setattr(
        app,
        "link_to_zipbuffer_download",
        lambda name, data: downloads.append((name, data)),
    )
    attempts = []

    def pseudonymise_batch(batch, buffer, first_file_number):
        index = len(attempts)
        attempts.append((batch, buffer, first_file_number))
        # A failed converter can already have written a partial archive.
        buffer.write(f"synthetic-batch-{index}".encode())
        return bad_batches[index]

    monkeypatch.setattr(app, "_zip_pseudo_fifty_mbytes", pseudonymise_batch)
    app.pseudonymise_buffer_list(files)

    assert len(attempts) == len(bad_batches)
    assert len(downloads) == bad_batches.count(False)
    assert len(messages) == bad_batches.count(True)
    for index, (batch, buffer, first_file_number) in enumerate(attempts):
        assert batch == files[index * 2 : (index + 1) * 2]
        assert first_file_number == index * 2 + 1
        assert buffer.closed
    expected = [
        f"synthetic-batch-{index}".encode()
        for index, bad in enumerate(bad_batches)
        if not bad
    ]
    assert [data for _, data in downloads] == expected
    assert all(message == "Problem processing DICOM data" for message in messages)
