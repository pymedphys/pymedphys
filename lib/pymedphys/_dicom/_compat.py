# Copyright (C) 2025 Matthew Jennings

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

from pydicom import uid
from pydicom.dataset import Dataset, FileMetaDataset

transfer_syntax_map = {
    (True, True): uid.ImplicitVRLittleEndian,
    # (True, False): uid.ImplicitVRBigEndian, # Retired UID
    (False, True): uid.ExplicitVRLittleEndian,
    (False, False): uid.ExplicitVRBigEndian,
}


def ensure_transfer_syntax(ds: Dataset) -> Dataset:
    """
    Ensure ds.file_meta.TransferSyntaxUID is present and consistent.

    pydicom >= 3.0 requires a FileMetaDataset with a TransferSyntaxUID
    to decode PixelData. Historical or programmatically constructed
    datasets may lack this. We infer a suitable transfer syntax from
    'is_little_endian' and 'is_implicit_VR' when available; otherwise
    default to Explicit VR Little Endian.
    """

    if not hasattr(ds, "file_meta"):
        ds.file_meta = FileMetaDataset()

    if not hasattr(ds.file_meta, "TransferSyntaxUID"):
        if not hasattr(ds, "is_implicit_VR"):
            ds.is_implicit_VR = False
        if not hasattr(ds, "is_little_endian"):
            ds.is_little_endian = True

        ds.file_meta.TransferSyntaxUID = transfer_syntax_map[
            (ds.is_implicit_VR, ds.is_little_endian)
        ]

    return ds
