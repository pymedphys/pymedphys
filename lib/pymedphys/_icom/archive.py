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

"""Read archived iCOM records with bounded output, input, and decoder memory."""

import lzma

# Per-record output budget and resource limits for the compressed decoder.
MAX_DECOMPRESSED_ICOM_BYTES = 256 * 1024 * 1024
MAX_COMPRESSED_ICOM_BYTES = 128 * 1024 * 1024
MAX_LZMA_DECODER_MEMORY = 128 * 1024 * 1024
ICOM_INPUT_CHUNK_BYTES = 64 * 1024


def read_icom_archive(path, *, limit=MAX_DECOMPRESSED_ICOM_BYTES):
    """Read a single archive without unbounded expansion or dictionary use.

    The fixed errors deliberately omit source path and decompressed content.
    Concatenated XZ streams are accepted, as with lzma.open.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise ValueError("iCOM decompression limit must be non-negative")

    output = bytearray()
    compressed_bytes = 0
    pending = b""
    decoder = None
    seen_stream = False
    with open(path, "rb") as source:
        while True:
            if decoder is None:
                if pending:
                    chunk, pending = pending, b""
                else:
                    chunk = source.read(ICOM_INPUT_CHUNK_BYTES)
                    compressed_bytes += len(chunk)
                if not chunk:
                    if not seen_stream:
                        raise ValueError("Empty or invalid iCOM archive")
                    break

                if seen_stream:
                    # XZ permits zero padding between concatenated streams.
                    chunk = chunk.lstrip(b"\x00")
                    if not chunk:
                        continue
                decoder = lzma.LZMADecompressor(
                    format=lzma.FORMAT_AUTO, memlimit=MAX_LZMA_DECODER_MEMORY
                )
            elif decoder.needs_input:
                if pending:
                    chunk, pending = pending, b""
                else:
                    chunk = source.read(ICOM_INPUT_CHUNK_BYTES)
                    compressed_bytes += len(chunk)
                if not chunk:
                    raise ValueError("Incomplete iCOM archive")
            else:
                chunk = b""

            if compressed_bytes > MAX_COMPRESSED_ICOM_BYTES:
                raise ValueError("iCOM archive exceeds the compressed size limit")
            try:
                data = decoder.decompress(
                    chunk,
                    max_length=min(
                        ICOM_INPUT_CHUNK_BYTES, limit - len(output) + 1
                    ),
                )
            except lzma.LZMAError:
                raise ValueError("Unsafe or invalid iCOM archive") from None

            output.extend(data)
            if len(output) > limit:
                raise ValueError("iCOM archive exceeds the decompressed size limit")
            if decoder.eof:
                seen_stream = True
                pending = decoder.unused_data + pending
                decoder = None

    return bytes(output)
