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

"""Read contour coordinates stored as DS or as oversized UN values."""

import math
import re


def get_contour_data(contour):
    """Return numeric Contour Data without replacing the source element.

    PS3.3 C.8.8.6 and PS3.5 6.2.2 permit oversized DS values to be written
    as UN in Explicit VR. pydicom preserves those values as bytes. Contour
    Data has a known DS representation, consisting of ASCII decimal values
    separated by backslashes. Existing decoded DS values pass through.
    """
    element = contour["ContourData"]
    if element.VR != "UN":
        return element.value

    message = "Contour Data (3006,0050) has invalid encoded coordinates"
    if not isinstance(element.value, bytes):
        raise ValueError(message)
    try:
        parts = element.value.decode("ascii").split("\\")
    except UnicodeDecodeError:
        raise ValueError(message) from None

    values = []
    for part in parts:
        part = part.strip(" ")
        if (
            len(part) > 16
            or re.fullmatch(
                r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", part
            )
            is None
        ):
            raise ValueError(message)
        value = float(part)
        if not math.isfinite(value):
            raise ValueError(message)
        values.append(value)

    if len(values) % 3 or (
        "NumberOfContourPoints" in contour
        and len(values) != 3 * contour.NumberOfContourPoints
    ):
        raise ValueError(message)
    return values
