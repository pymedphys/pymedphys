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

"""Clean application entity titles under Retain Device Identity: keyed tokens.

Under the Retain Device Identity Option, Table E.1-1 gives C to eleven
attributes of VR AE, which name an application entity or a network, such as
Station AE Title (0008,0055) and Retrieve AE Title (0008,0054). PS3.15
E.3.8 has them cleaned rather than kept, "since they may contain embedded
institution or person identification information". C replaces a value "with
values of similar meaning known not to contain identifying information and
consistent with the VR" (Table E.1-1a), so each value becomes a token of the
run's key (D-034): ``AE`` followed by the first 14 characters of the base32
encoding of the value's HMAC-SHA256 in the ``"ae-title"`` domain
(:meth:`~pymedphys._dicom.deidentify.keys.DeidKey.derive`), 16 characters
in all, the most that VR AE allows (PS3.5 Table 6.2-1), each an upper-case
letter or a digit from 2 to 7.

A token is derived from the value alone, once the leading and trailing
spaces that VR AE makes insignificant are removed, so within a run an
application entity has the same token in every attribute and instance, and
different entities have different tokens, as a device's identity needs,
unless two of them collide in 70 bits, which for a thousand entities has a
probability below one in 10**15. A
token holds nothing of the value but its keyed digest, so tokens agree
across runs only under one project key, never under run-scoped keys (D-004). Each value
of a multi-valued attribute is replaced on its own; an empty value, or one
of spaces only, stays empty; and an attribute with no value is written with
none.
"""

from __future__ import annotations

import base64

from .keys import DeidKey

# The derivation domain of the tokens, one of keys.DOMAINS.
DOMAIN = "ae-title"
# A token is the prefix and this many characters of the base32 encoding of
# its value's derivation, 16 characters in all, the most that VR AE allows.
TOKEN_PREFIX = "AE"
TOKEN_CHARACTERS = 14
# The attributes that Retain Device Identity gives C in Table E.1-1 of
# PS3.15 2026d, all of VR AE.
TAGS = frozenset(
    {
        "(0008,0054)",  # Retrieve AE Title
        "(0008,0055)",  # Station AE Title
        "(0008,1000)",  # Network ID
        "(0032,1021)",  # Scheduled Study Location AE Title
        "(0040,0001)",  # Scheduled Station AE Title
        "(0040,0241)",  # Performed Station AE Title
        "(0072,005E)",  # Selector AE Value
        "(0074,1234)",  # Receiving AE
        "(0074,1236)",  # Requesting AE
        "(2100,0070)",  # Originator
        "(2100,0140)",  # Destination AE
    }
)
VRS = frozenset({"AE"})


def ae_token(value: str, key: DeidKey) -> str:
    """Return the token of one AE value, or ``""`` for an empty one.

    Parameters
    ----------
    value : str
        One value, without the backslash that separates values.
    key : DeidKey
        The run's key.

    Examples
    --------
    >>> key = DeidKey(bytes(32))
    >>> token = ae_token("  CT_SCANNER_1 ", key)
    >>> len(token), token.startswith("AE"), token == ae_token("CT_SCANNER_1", key)
    (16, True, True)
    >>> ae_token("   ", key)
    ''
    """
    title = value.strip(" ")
    if not title:
        return ""
    encoded = base64.b32encode(key.derive(DOMAIN, title)).decode("ascii")
    return TOKEN_PREFIX + encoded[:TOKEN_CHARACTERS]


def ae_tokens(source: str, key: DeidKey) -> tuple[str, ...]:
    """Return the tokens that replace an AE attribute's values.

    Parameters
    ----------
    source : str
        The attribute's decoded values, separated by backslashes, which VR
        AE does not allow within a value; ``""`` for an attribute with no
        value.
    key : DeidKey
        The run's key.

    Returns
    -------
    tuple of str
        A token for each value, in order, ``""`` for an empty one; ``()``
        for an attribute with no value.
    """
    if not source:
        return ()
    return tuple(ae_token(value, key) for value in source.split("\\"))
