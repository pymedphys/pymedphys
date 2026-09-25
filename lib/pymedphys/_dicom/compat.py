# Copyright (C) 2025-2026 Matthew Jennings

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from pymedphys._imports import pydicom


def ensure_transfer_syntax(ds: pydicom.dataset.Dataset) -> pydicom.dataset.Dataset:
    """
    Ensure ``ds.file_meta.TransferSyntaxUID`` is present.

    pydicom >= 3.0 requires a FileMetaDataset with a TransferSyntaxUID to
    decode PixelData, and gives it priority when choosing the encoding to
    write. Historical or programmatically constructed datasets may lack
    it. An existing TransferSyntaxUID is never modified.

    When it is missing, the transfer syntax is inferred from the legacy
    ``is_implicit_VR`` and ``is_little_endian`` flags if the dataset
    carries them (pydicom sets both when it reads a file that has no file
    meta information). Any flag that is unset defaults to Implicit VR
    Little Endian, the DICOM default transfer syntax. Unlike the explicit
    VR transfer syntaxes it has no 64 kB element length limit, which
    matters for large programmatically built elements such as RT Structure
    Set ContourData.

    The flags are only read, never written. pydicom 3 deprecates them and
    pydicom 4 removes them, and every supported pydicom version derives
    the write encoding from the Transfer Syntax UID when they are unset.
    """
    transfer_syntax_map = {
        (True, True): pydicom.uid.ImplicitVRLittleEndian,
        # (True, False): pydicom.uid.ImplicitVRBigEndian, # Retired UID
        (False, True): pydicom.uid.ExplicitVRLittleEndian,
        (False, False): pydicom.uid.ExplicitVRBigEndian,
    }

    if not hasattr(ds, "file_meta"):
        ds.file_meta = pydicom.dataset.FileMetaDataset()

    if not hasattr(ds.file_meta, "TransferSyntaxUID"):
        is_implicit_VR = getattr(ds, "is_implicit_VR", None)
        is_little_endian = getattr(ds, "is_little_endian", None)

        ds.file_meta.TransferSyntaxUID = transfer_syntax_map[
            (
                True if is_implicit_VR is None else is_implicit_VR,
                True if is_little_endian is None else is_little_endian,
            )
        ]

    return ds
