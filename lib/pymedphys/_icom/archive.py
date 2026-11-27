# Copyright (C) 2026 PyMedPhys contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Read archived iCOM records without unbounded LZMA expansion."""

import lzma

# A single archive is one recorded delivery, not an entire treatment dataset.
# This allows large deliveries while bounding an accidental or hostile LZMA bomb.
MAX_DECOMPRESSED_ICOM_BYTES = 256 * 1024 * 1024


def read_icom_archive(path, *, limit=MAX_DECOMPRESSED_ICOM_BYTES):
    """Return archive bytes or reject an overlong decompressed stream.

    The exception intentionally omits the source path and decompressed content,
    which could identify a patient.
    """
    if not isinstance(limit, int) or limit < 0:
        raise ValueError("iCOM decompression limit must be non-negative")

    with lzma.open(path, "rb") as archive:
        data = archive.read(limit + 1)
    if len(data) > limit:
        raise ValueError("iCOM archive exceeds the decompressed size limit")
    return data
