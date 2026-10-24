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

"""The Clean Graphics Option: graphics removed by their Basic Profile actions.

PS3.15 E.3.3 has the option remove "any information encoded in graphics,
text annotations or overlays corresponding to the Attribute information
specified to be removed by the Profile and any other Options specified", as
described in Table E.1-1, which gives C under the option to four rows whose
Basic Profile action removes them: Curve Data (50xx,xxxx), Overlay Data
(60xx,3000), and Overlay Comments (60xx,4000), each X, and Graphic
Annotation Sequence (0070,0001), D. No cleaner of overlays, curves, or
graphic annotations is designed yet, so each takes its Basic Profile action
under the option (D-041): the element rules give a sequence or a masked row
to which the policy gives C that action
(:class:`~pymedphys._dicom.deidentify.element_rules.ElementRules`). Removing
Overlay Data removes every attribute of its overlay group where the IOD's
Overlay Plane Module is user-optional, as under the Basic Profile (D-020),
and a plain D on Graphic Annotation Sequence removes it from every supported
IOD, since only the Presentation State IODs define it, and they are out of
scope (Note 13 after Table E.1-1a; D-010). The
instance still meets the option, since E.3.3 specifies what the option
removes, and Table E.1-1 gives the minimum actions, as for Clean Descriptors
(D-009).

One overlay escapes those actions. PS3.3 before 2004 let an overlay lie in
unused bits of Pixel Data (PS3.3 Section C.9.2), so an overlay group
without Overlay Data may keep its graphics in Pixel Data when the group's
attributes are removed. Under the option, the transform clears the bit plane
of each such overlay in native Pixel Data, where
:func:`~pymedphys._dicom.deidentify.pixel_cleaning.overlay_planes` finds it
above High Bit, in the same write as Clean Pixel Data's redaction, and
checks that the written Pixel Data differs from the source in nothing else
(:func:`~pymedphys._dicom.deidentify.pixel_cleaning.redaction_problem`).
:func:`overlay_in_pixel_data` sequesters an instance whose overlay cannot be
so cleared, such as one in compressed Pixel Data or within Bits Stored,
since writing it with the option's code would claim a removal that did not
happen.
"""

from __future__ import annotations

from .policy import CLEAN_GRAPHICS, Policy
from .reasons import TransformReason

__all__ = ["CLEAN_GRAPHICS", "overlay_in_pixel_data"]


def overlay_in_pixel_data(
    policy: Policy, overlays: int | None
) -> tuple[TransformReason, ...]:
    """Return why an instance whose overlay lies in Pixel Data is sequestered.

    Parameters
    ----------
    policy : Policy
        The run's policy.
    overlays : int or None
        The bits of Pixel Data that hold the source's overlays, as
        :func:`~pymedphys._dicom.deidentify.pixel_cleaning.overlay_planes`
        gives them: None where an overlay group without Overlay Data
        (60xx,3000) places its overlay where it cannot be cleared.

    Returns
    -------
    tuple of TransformReason
        :attr:`~.reasons.TransformReason.OVERLAY_IN_PIXEL_DATA` where the
        policy selects Clean Graphics and ``overlays`` is None; otherwise
        ``()``.
    """
    if CLEAN_GRAPHICS not in policy.options or overlays is not None:
        return ()
    return (TransformReason.OVERLAY_IN_PIXEL_DATA,)
