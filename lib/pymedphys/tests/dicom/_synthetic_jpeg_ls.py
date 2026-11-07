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

"""A JPEG-LS encoder written here from ITU-T T.87, for test images.

pydicom and the decoders the engine uses encode no JPEG-LS at 6 or 7 bits,
and an image encoded by the library that decodes it would test that
library only against itself. :func:`encode` therefore codes one frame
as ITU-T T.87 Annex A gives it: regular mode with the default thresholds
(Section C.2.4.1.1), context bias correction, and limited-length Golomb
codes; run mode with its run interruption samples; near-lossless coding
where ``near`` is greater than zero; and one scan per component
(interleave mode 0, ILV = 0), so that colour needs nothing but the same
coding three times. It also returns each sample as a decoder reconstructs
it, which equals the sample where ``near`` is 0 and is within ``near`` of
it otherwise, so a test compares a decoder with the standard's
reconstruction rather than with another decoder.

Only what a test needs is written: no preset parameters (LSE) marker
segment, no mapping tables, no restart markers, and no point transform.
Pixels are coded in raster order, each scan's context variables starting
afresh (Section A.2.1). The variable names are T.87's.
"""

import bisect
import dataclasses
import struct
from collections.abc import Iterator

from pymedphys._imports import numpy as np

# The run-length order of each value of RUNindex (T.87 Section A.2.1).
_J = (0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3)
_J += (4, 4, 5, 5, 6, 6, 7, 7, 8, 9, 10, 11, 12, 13, 14, 15)
_RESET = 64
_MIN_C, _MAX_C = -128, 127
# The two run interruption contexts follow the 365 regular ones.
_RUN_CONTEXTS = 365


@dataclasses.dataclass
class _Parameters:
    """The coding parameters of one scan (T.87 Sections A.2.1 and C.2.4.1.1)."""

    maxval: int
    near: int

    def __post_init__(self) -> None:
        maxval, near = self.maxval, self.near
        self.range = (maxval + 2 * near) // (2 * near + 1) + 1
        self.qbpp = (self.range - 1).bit_length()
        bpp = max(2, maxval.bit_length())
        self.limit = 2 * (bpp + max(8, bpp))
        self.t1, self.t2, self.t3 = _default_thresholds(maxval, near)


def _default_thresholds(maxval: int, near: int) -> tuple[int, int, int]:
    """Return T1, T2, and T3 as T.87 Section C.2.4.1.1.1 gives them by default."""

    def clamp(value: int, low: int) -> int:
        return low if value > maxval or value < low else value

    if maxval >= 128:
        factor = (min(maxval, 4095) + 128) // 256
        t1 = clamp(factor * (3 - 2) + 2 + 3 * near, near + 1)
        t2 = clamp(factor * (7 - 3) + 3 + 5 * near, t1)
        t3 = clamp(factor * (21 - 4) + 4 + 7 * near, t2)
    else:
        factor = 256 // (maxval + 1)
        t1 = clamp(max(2, 3 // factor + 3 * near), near + 1)
        t2 = clamp(max(3, 7 // factor + 5 * near), t1)
        t3 = clamp(max(4, 21 // factor + 7 * near), t2)
    return t1, t2, t3


class _Bits:
    """Bits written most significant first, with a 0 bit stuffed at the top
    of each byte after a byte of 0xFF (T.87 Section A.1)."""

    def __init__(self) -> None:
        self.data = bytearray()
        self._byte = 0
        self._count = 0
        self._capacity = 8

    def write(self, value: int, count: int) -> None:
        for shift in range(count - 1, -1, -1):
            self._byte = (self._byte << 1) | ((value >> shift) & 1)
            self._count += 1
            if self._count == self._capacity:
                self.data.append(self._byte)
                self._capacity = 7 if self._byte == 0xFF else 8
                self._byte = self._count = 0

    def finish(self) -> bytes:
        """Return the bits, padded with 0 to a whole byte, and never ending
        with 0xFF, since a marker follows them."""
        if self._count:
            self.write(0, self._capacity - self._count)
        if self.data and self.data[-1] == 0xFF:
            self.write(0, 7)
        return bytes(self.data)


@dataclasses.dataclass
class _Context:
    a: int
    b: int = 0
    c: int = 0
    n: int = 1
    nn: int = 0


class _Scan:
    """Codes one component, as T.87 Annex A gives it."""

    def __init__(self, parameters: _Parameters) -> None:
        self.p = parameters
        initial = max(2, (parameters.range + 32) // 64)
        self.contexts = [_Context(initial) for _ in range(_RUN_CONTEXTS + 2)]
        self.indices: dict[tuple[int, int, int], int] = {}
        self.run_index = 0
        self.bits = _Bits()

    def quantised_gradient(self, d: int) -> int:
        """Return the region, -4 to 4, of a local gradient (T.87 Code
        segment A.4), by the largest gradient of each region but the last."""
        p = self.p
        bounds = (
            -p.t3,
            -p.t2,
            -p.t1,
            -p.near - 1,
            p.near,
            p.t1 - 1,
            p.t2 - 1,
            p.t3 - 1,
        )
        return bisect.bisect_left(bounds, d) - 4

    def quantised_error(self, errval: int) -> int:
        near = self.p.near
        if errval > near:
            return (errval + near) // (2 * near + 1)
        if errval < -near:
            return -((near - errval) // (2 * near + 1))
        return 0

    def modulo_range(self, errval: int) -> int:
        if errval < 0:
            errval += self.p.range
        if errval >= (self.p.range + 1) // 2:
            errval -= self.p.range
        return errval

    def reconstructed(self, prediction: int, errval: int) -> int:
        """Return the sample a decoder reconstructs from a prediction and a
        quantised error, with the sign applied."""
        p = self.p
        value = prediction + errval * (2 * p.near + 1)
        if value < -p.near:
            value += p.range * (2 * p.near + 1)
        elif value > p.maxval + p.near:
            value -= p.range * (2 * p.near + 1)
        return min(max(value, 0), p.maxval)

    def golomb(self, mapped: int, k: int, limit: int) -> None:
        qbpp = self.p.qbpp
        high = mapped >> k
        if high < limit - qbpp - 1:
            self.bits.write(1, high + 1)
            self.bits.write(mapped & ((1 << k) - 1), k)
        else:
            self.bits.write(1, limit - qbpp)
            self.bits.write((mapped - 1) & ((1 << qbpp) - 1), qbpp)

    def regular(self, x: int, ra: int, rb: int, rc: int, rd: int) -> int:
        """Code one sample in regular mode, returning its reconstruction."""
        p = self.p
        q = [self.quantised_gradient(d) for d in (rd - rb, rb - rc, rc - ra)]
        sign = -1 if next(v for v in q if v) < 0 else 1
        q = tuple(sign * v for v in q)
        context = self.contexts[self.indices.setdefault(q, len(self.indices))]
        if rc >= max(ra, rb):
            prediction = min(ra, rb)
        elif rc <= min(ra, rb):
            prediction = max(ra, rb)
        else:
            prediction = ra + rb - rc
        prediction = min(max(prediction + sign * context.c, 0), p.maxval)
        errval = self.modulo_range(self.quantised_error(sign * (x - prediction)))
        k = 0
        while (context.n << k) < context.a:
            k += 1
        if p.near == 0 and k == 0 and 2 * context.b <= -context.n:
            mapped = 2 * errval + 1 if errval >= 0 else -2 * (errval + 1)
        else:
            mapped = 2 * errval if errval >= 0 else -2 * errval - 1
        self.golomb(mapped, k, p.limit)
        context.b += errval * (2 * p.near + 1)
        context.a += abs(errval)
        if context.n == _RESET:
            context.a >>= 1
            context.b = context.b >> 1 if context.b >= 0 else -((1 - context.b) >> 1)
            context.n >>= 1
        context.n += 1
        if context.b <= -context.n:
            context.b += context.n
            context.c = max(context.c - 1, _MIN_C)
            if context.b <= -context.n:
                context.b = -context.n + 1
        elif context.b > 0:
            context.b -= context.n
            context.c = min(context.c + 1, _MAX_C)
            context.b = min(context.b, 0)
        return self.reconstructed(prediction, sign * errval)

    def run_length(self, count: int, end_of_line: bool) -> None:
        while count >= 1 << _J[self.run_index]:
            self.bits.write(1, 1)
            count -= 1 << _J[self.run_index]
            self.run_index = min(self.run_index + 1, 31)
        if end_of_line:
            if count:
                self.bits.write(1, 1)
        else:
            self.bits.write(0, 1)
            self.bits.write(count, _J[self.run_index])

    def interruption(self, x: int, ra: int, rb: int) -> int:
        """Code a run interruption sample, returning its reconstruction."""
        p = self.p
        ri_type = 1 if abs(ra - rb) <= p.near else 0
        prediction = ra if ri_type else rb
        sign = -1 if not ri_type and ra > rb else 1
        errval = self.modulo_range(self.quantised_error(sign * (x - prediction)))
        context = self.contexts[_RUN_CONTEXTS + ri_type]
        temp = context.a + (context.n >> 1) * ri_type
        k = 0
        while (context.n << k) < temp:
            k += 1
        mapping = (
            (k == 0 and errval > 0 and 2 * context.nn < context.n)
            or (errval < 0 and 2 * context.nn >= context.n)
            or (errval < 0 and k != 0)
        )
        mapped = 2 * abs(errval) - ri_type - int(mapping)
        self.golomb(mapped, k, p.limit - _J[self.run_index] - 1)
        if errval < 0:
            context.nn += 1
        context.a += (mapped + 1 - ri_type) >> 1
        if context.n == _RESET:
            context.a >>= 1
            context.n >>= 1
            context.nn >>= 1
        context.n += 1
        self.run_index = max(self.run_index - 1, 0)
        return self.reconstructed(prediction, sign * errval)

    def code(self, samples: "np.ndarray") -> Iterator["np.ndarray"]:
        """Code a component, yielding each line as a decoder reconstructs it."""
        rows, columns = samples.shape
        near = self.p.near
        # The reconstructed samples, with a column on each side: T.87 Section
        # A.2.1 takes Ra of a line's first sample, and Rc of the next line's,
        # from the sample above it, and Rd of its last from Rb.
        above = np.zeros(columns + 2, dtype=np.int64)
        for row in range(rows):
            line = np.zeros(columns + 2, dtype=np.int64)
            line[0] = above[1]
            above[columns + 1] = above[columns]
            column = 0
            while column < columns:
                x = int(samples[row, column])
                ra, rb = int(line[column]), int(above[column + 1])
                rc, rd = int(above[column]), int(above[column + 2])
                if max(abs(rd - rb), abs(rb - rc), abs(rc - ra)) > near:
                    line[column + 1] = self.regular(x, ra, rb, rc, rd)
                    column += 1
                    continue
                count = 0
                while column < columns and abs(int(samples[row, column]) - ra) <= near:
                    line[column + 1] = ra
                    count += 1
                    column += 1
                self.run_length(count, column == columns)
                if column < columns:
                    x, rb = int(samples[row, column]), int(above[column + 1])
                    line[column + 1] = self.interruption(x, ra, rb)
                    column += 1
            above = line
            yield above[1 : columns + 1].copy()


def _segment(marker: int, payload: bytes) -> bytes:
    return struct.pack(">HH", 0xFF00 | marker, len(payload) + 2) + payload


def encode(samples, *, precision: int, near: int = 0) -> tuple[bytes, "np.ndarray"]:
    """Return a frame as a JPEG-LS codestream, and its samples as a decoder
    reconstructs them.

    Parameters
    ----------
    samples : numpy.ndarray
        Rows by columns, or rows by columns by components, of unsigned
        integers below ``2 ** precision``: signed samples' two's complement
        bit patterns of ``precision`` bits, as DICOM codes them.
    precision : int
        Bits per sample, from 2 to 16.
    near : int
        NEAR, the largest difference between a sample and its
        reconstruction; 0 for lossless coding.
    """
    samples = np.asarray(samples, dtype=np.int64)
    planes = samples[..., np.newaxis] if samples.ndim == 2 else samples
    rows, columns, components = planes.shape
    maxval = (1 << precision) - 1
    if planes.min() < 0 or planes.max() > maxval:
        raise ValueError("a sample does not fit the precision")
    frame = struct.pack(">BHHB", precision, rows, columns, components)
    frame += b"".join(bytes([index + 1, 0x11, 0]) for index in range(components))
    codestream = b"\xff\xd8" + _segment(0xF7, frame)
    reconstructed = np.zeros_like(planes)
    for index in range(components):
        scan = _Scan(_Parameters(maxval, near))
        for row, line in enumerate(scan.code(planes[..., index])):
            reconstructed[row, :, index] = line
        # Ns 1, the component, no mapping table, NEAR, ILV 0, and no point
        # transform.
        header = bytes([1, index + 1, 0, near, 0, 0])
        codestream += _segment(0xDA, header) + scan.bits.finish()
    codestream += b"\xff\xd9"
    return codestream, reconstructed.reshape(samples.shape)
