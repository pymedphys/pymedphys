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

"""Values checked against their VR (PS3.5 Table 6.2-1) and VM (PS3.6).

Unless noted, examples and limits are from the definitions in Table 6.2-1 of
the 2026d PS3.5.
"""

import datetime
import ipaddress

from pymedphys._imports import hypothesis, pydicom, pytest

from pymedphys._dicom.deidentify import (
    dates,
    keys,
    pseudonyms,
    standard,
    uids,
    values,
)

st = hypothesis.strategies

VALID = [
    # AE: at most 16 characters, not only spaces.
    ("AE", "STORESCP"),
    ("AE", " A" + "E" * 13 + " "),
    # AS: nnnD, nnnW, nnnM, or nnnY.
    ("AS", "018M"),
    ("AS", "045Y"),
    ("AS", "000D"),
    # CS: upper case, digits, space, and underscore, at most 16.
    ("CS", "ORIGINAL"),
    ("CS", "FOR PRESENTATION"),
    ("CS", "DEID_1"),
    # DA: YYYYMMDD, a Gregorian date.
    ("DA", "19930822"),
    ("DA", "20240229"),
    ("DA", "15821015"),
    # DS: fixed or floating point, optionally padded, at most 16.
    ("DS", "1.5"),
    ("DS", "-1.5e3"),
    ("DS", "+.5"),
    ("DS", "7."),
    ("DS", " 12 "),
    ("DS", "1.23456789012345"),
    # DT: YYYYMMDDHHMMSS.FFFFFF&ZZXX, trailing components optional.
    ("DT", "195308"),
    ("DT", "19530827111300.0"),
    ("DT", "2007-0500"),
    ("DT", "20070101+1400"),
    ("DT", "20070101-1200"),
    ("DT", "20260930123456.123456+0100"),
    ("DT", "2026 "),
    # IS: an integer in [-2**31, 2**31 - 1], optionally padded, at most 12.
    ("IS", "+12"),
    ("IS", " -7 "),
    ("IS", "2147483647"),
    ("IS", "-2147483648"),
    # LO, SH: no backslash or control character.
    ("LO", "L" * 64),
    ("LO", "Müller"),
    ("SH", "S" * 16),
    # ST, LT, UT: text with TAB, CR, LF, and FF; a backslash is allowed. A
    # decoded value has no ESC, which encoding adds.
    ("ST", "S" * 1024),
    ("ST", "First\\second\r\n\tthird\f"),
    ("LT", "L" * 10240),
    ("UT", "Unlimited\\text\n"),
    # UC: no backslash or control character.
    ("UC", "U" * 100_000),
    # PN: up to three component groups of up to five components each.
    ("PN", "DEIDENTIFIED^ABCDEFGHIJKLMNOP"),
    ("PN", "Family^Given^Middle^Prefix^Suffix"),
    # Decoded from the Japanese example of PS3.5 Annex H.
    ("PN", "Yamada^Tarou=山田^太郎=やまだ^たろう"),
    # Each group's 64 characters include the "=" before it (PS3.5 Section
    # 6.2.1.2).
    ("PN", "P" * 64 + "=" + "Q" * 63 + "=" + "R" * 63),
    # TM: HHMMSS.FFFFFF, trailing components optional, trailing padding.
    ("TM", "070907.0705 "),
    ("TM", "1010"),
    ("TM", "0000"),
    ("TM", "23"),
    ("TM", "235960"),
    # UI: numeric components without leading zeros, at most 64.
    ("UI", "1.2.840.10008.5.1.4.1.1.481.5"),
    ("UI", "2.25." + "9" * 59),
    # UR: a URI reference of RFC 3986, with trailing padding.
    ("UR", "https://example.org/path?q=a%20b#frag"),
    ("UR", "relative/path "),
    ("UR", "https://user:pass@[2001:db8::7]:8080/a/b?c?d/e#f/g?h"),
    ("UR", "urn:oasis:names:specification:docbook:dtd:xml:4.1.2"),
    # Binary numbers within their ranges.
    ("US", 0),
    ("US", 65535),
    ("SS", -32768),
    ("UL", 2**32 - 1),
    ("SL", -(2**31)),
    ("SV", 2**63 - 1),
    ("UV", 2**64 - 1),
    ("FL", 1.5),
    ("FL", -3.4028234663852886e38),
    # How NumPy prints the largest 32-bit float, which rounds to it.
    ("FL", 3.4028235e38),
    ("FL", 2),
    ("FD", 1e308),
    ("AT", 0x00100010),
    # Byte strings of whole words.
    ("OB", b"\x01\x02\x03"),
    ("UN", b"\x01"),
    ("OW", b"\x01\x02"),
    ("OF", b"\x00" * 8),
    ("OL", b"\x00" * 4),
    ("OD", b"\x00" * 16),
    ("OV", b"\x00" * 8),
]


def _value_id(value):
    """Shorten a long string value in a test ID.

    pytest puts the test ID in the PYTEST_CURRENT_TEST environment variable,
    which Windows limits to 32767 characters.
    """
    if isinstance(value, str) and len(value) > 64:
        return f"{value[:8]}...{len(value)}chars"
    return None


@pytest.mark.parametrize("vr, value", VALID, ids=_value_id)
def test_valid_values(vr, value):
    assert values.value_problem(vr, value) is None


# Each invalid value contains "SECRET" where it can, to show that the
# problem never quotes it.
INVALID = [
    ("AE", "SECRET\\SECRET"),
    ("AE", "SECRETSECRETSECRE"),
    ("AE", "    "),
    ("AE", "SECRET\n"),
    ("AS", "18M"),
    ("AS", "018m"),
    ("AS", "018X"),
    ("CS", "Secret"),
    ("CS", "SECRETSECRETSECRE"),
    ("CS", "SECRET-1"),
    # ACR-NEMA's form, which PS3.5 says is not compliant.
    ("DA", "1993.08.22"),
    ("DA", "19930230"),
    ("DA", "20230229"),
    ("DA", "1993082"),
    ("DA", "19930822 "),
    ("DS", "1 5"),
    ("DS", "NaN"),
    ("DS", "1.00000000000000001"),
    ("DS", "SECRET"),
    ("DT", "20071301"),
    ("DT", "200713"),
    ("DT", "20070230"),
    ("DT", "20260930123456.123456+0100 "),
    ("DT", "20070101-0000"),
    ("DT", "20070101+1500"),
    ("DT", "20070101-1300"),
    ("DT", "20070101+0160"),
    ("DT", "2007010124"),
    ("DT", "20070101120000."),
    ("DT", "20070101120000.1234567"),
    ("DT", " 2007"),
    ("IS", "2147483648"),
    ("IS", "-2147483649"),
    ("IS", "1.0"),
    ("IS", "1 2"),
    ("IS", "+000000000001"),
    ("LO", "SECRET" * 10 + "SECRE"),
    ("LO", "SECRET\\SECRET"),
    ("LO", "SECRET\nSECRET"),
    ("LO", "SECRET\x00"),
    # DELETE and a C1 control (PS3.5 Section 6.1.2.3).
    ("LO", "SECRET\x7f"),
    ("SH", "SECRET\x85"),
    # A decoded value has no escape sequences: encoding adds them.
    ("LO", "SECRET\x1b[31m"),
    ("SH", "SECRETSECRETSECRE"),
    ("ST", "S" * 1025),
    ("ST", "SECRET\x00"),
    ("ST", "SECRET\x1b"),
    ("LT", "L" * 10241),
    ("UT", "SECRET\x07"),
    ("UC", "SECRET\\SECRET"),
    ("PN", "A^B^C^D^E^SECRET"),
    ("PN", "A=B=C=SECRET"),
    ("PN", "SECRET" * 10 + "SECRE"),
    ("PN", "SECRET\\SECRET"),
    ("PN", "SECRET\r"),
    ("PN", "P" * 64 + "=" + "SECRET" * 10 + "SECR"),
    ("PN", "=" + "SECRET" * 10 + "SECR"),
    ("PN", "SECRET\x1b$B"),
    # PS3.5's own example of an invalid Value.
    ("TM", "021 "),
    ("TM", "2400"),
    ("TM", "236"),
    ("TM", "1260"),
    ("TM", "120061"),
    ("TM", "120000.123456  "),
    ("TM", "120000."),
    ("TM", " 1200"),
    ("TM", "12:00:00"),
    ("UI", "1.02"),
    ("UI", "2.25." + "9" * 60),
    ("UI", "1.2."),
    ("UI", "1.2.840.10008.5.1.4.1.1.481.5\x00"),
    ("UR", " https://example.org/SECRET"),
    ("UR", "https://example.org/SECRET SECRET"),
    ("UR", "https://example.org/SECRET\\SECRET"),
    ("UR", "https://example.org/%zzSECRET"),
    # URI characters that do not make a URI reference (RFC 3986): a second
    # "#", a bracketed host that is no IP address, a malformed IPv6 address,
    # an unclosed bracket, a port that is not a number, "[" in a path, "@"
    # in a host, and a scheme that is empty or starts with a digit.
    ("UR", "https://example.org/SECRET#a#b"),
    ("UR", "https://[SECRET]/"),
    ("UR", "https://[2001:db8::7::1]/SECRET"),
    ("UR", "https://[2001:db8::7/SECRET"),
    ("UR", "https://[::1]SECRET/"),
    ("UR", "https://example.org:80SECRET/"),
    ("UR", "https://example.org/SECRET[1]"),
    ("UR", "https://example.org/SECRET["),
    ("UR", "https://SECRET@SECRET@example.org/"),
    ("UR", ":SECRET"),
    ("UR", "1SECRET:x"),
    ("US", 65536),
    ("US", -1),
    ("US", True),
    ("US", 1.0),
    ("SS", 32768),
    ("UL", 2**32),
    ("SL", 2**31),
    ("SV", -(2**63) - 1),
    ("UV", -1),
    ("FL", 3.5e38),
    ("FL", 3.4028236e38),
    ("FL", "1.5"),
    ("FL", 2**1024),
    ("FD", 2**1024),
    ("FD", "SECRET"),
    ("AT", 2**32),
    ("AT", "(0010,0010)"),
    ("OB", "SECRET"),
    ("OW", b"\x01"),
    ("OF", b"\x00" * 6),
    ("OL", b"\x00" * 2),
    ("OD", b"\x00" * 12),
    ("OV", b"\x00" * 4),
    ("LO", b"SECRET"),
    ("LO", 1),
]


@pytest.mark.parametrize("vr, value", INVALID, ids=_value_id)
def test_invalid_values(vr, value):
    problem = values.value_problem(vr, value)

    assert problem
    assert "SECRET" not in problem
    if isinstance(value, str) and len(value.strip()) > 2:
        assert value.strip() not in problem


@pytest.mark.parametrize(
    "reference",
    [
        # The URIs of RFC 3986 Section 1.1.2.
        "ftp://ftp.is.co.za/rfc/rfc1808.txt",
        "http://www.ietf.org/rfc/rfc2396.txt",
        "ldap://[2001:db8::7]/c=GB?objectClass?one",
        "mailto:John.Doe@example.com",
        "news:comp.infosystems.www.servers.unix",
        "tel:+1-816-555-1212",
        "telnet://192.0.2.16:80/",
        "urn:oasis:names:specification:docbook:dtd:xml:4.1.2",
        # Relative references from RFC 3986 Section 5.4.
        "g:h",
        "./g",
        "//g",
        "?y",
        "#s",
        "g;x?y#s",
        ".",
        "../..",
        "../../../g",
        "/./g",
        "g;x=1/../y",
        "g?y/./x",
        "g#s/../x",
        # A colon after the first segment, an empty port, a percent-encoded
        # host, and a host in the IPvFuture form.
        "a/b:c",
        "http://example.org:/",
        "http://ex%41mple.org/",
        "http://[v7.fe80::1+abc]/",
        # ABNF literals, such as the "v" of IPvFuture, are case-insensitive
        # (RFC 5234 Section 2.3).
        "http://[V7.fe80::1+abc]/",
    ],
)
def test_a_uri_reference_is_a_valid_ur_value(reference):
    assert values.value_problem("UR", reference) is None


def _is_ipv6_address(text):
    try:
        ipaddress.IPv6Address(text)
    except ValueError:
        return False
    return True


_HEX_COLON_DOT = "0123456789abcdefABCDEF:."


# Each of the nine forms of IPv6address in RFC 3986 Section 3.2.2, including
# RFC 4291's example of an IPv4-mapped address, and addresses that none fits.
@hypothesis.example("1:2:3:4:5:6:7:8")
@hypothesis.example("1:2:3:4:5:6:1.2.3.4")
@hypothesis.example("::2:3:4:5:6:7:8")
@hypothesis.example("1::3:4:5:6:7:8")
@hypothesis.example("1:2::4:5:6:7:8")
@hypothesis.example("1:2:3::5:6:7:8")
@hypothesis.example("1:2:3:4::6:7:8")
@hypothesis.example("1:2:3:4:5::7:8")
@hypothesis.example("1:2:3:4:5:6::8")
@hypothesis.example("1:2:3:4:5:6:7::")
@hypothesis.example("::FFFF:129.144.52.38")
@hypothesis.example("1:2:3:4:5:6:7:8:9")
@hypothesis.example("1::2::3")
@hypothesis.example("1::2:3:4:5:6:7:8")
@hypothesis.example("1:2::3:4:5:6:7:8")
@hypothesis.example("12345::")
@hypothesis.example("::1.2.3.256")
@hypothesis.example("::01.2.3.4")
@hypothesis.example("1:2:3:4:5:6:7:1.2.3.4")
@hypothesis.example(":1::")
@hypothesis.example("")
@hypothesis.given(
    st.one_of(
        st.text(alphabet=_HEX_COLON_DOT, max_size=45),
        st.ip_addresses(v=6).map(str),
        st.ip_addresses(v=6).map(lambda address: address.exploded),
        st.ip_addresses(v=4).map(lambda address: f"::ffff:{address}"),
    )
)
def test_a_bracketed_host_is_an_ipv6_address(host):
    # Python's ipaddress module, an independent parser of the same textual
    # forms (RFC 4291 Section 2.2), without the zone identifiers that RFC 3986
    # does not allow and that "%" would introduce.
    assert (values.value_problem("UR", f"//[{host}]/") is None) == _is_ipv6_address(
        host
    )


BYTE_VRS = {"OB", "OD", "OF", "OL", "OV", "OW", "UN"}
NUMBER_VRS = {"AT", "FD", "FL", "SL", "SS", "SV", "UL", "US", "UV"}


@pytest.mark.parametrize("vr", sorted(standard.VRS - {"SQ"} - NUMBER_VRS))
def test_an_empty_string_or_byte_value_is_valid(vr):
    assert values.value_problem(vr, b"" if vr in BYTE_VRS else "") is None


@pytest.mark.parametrize("vr", sorted(NUMBER_VRS))
def test_an_empty_number_has_no_value_to_check(vr):
    # An empty element of these VRs has no values at all.
    assert values.value_problem(vr, "") is not None
    assert values.values_problem(vr, "1", []) is None


@pytest.mark.parametrize("vr", ["SQ", "XX", "US or SS", ""])
def test_a_vr_without_values_to_check_is_rejected(vr):
    with pytest.raises(ValueError, match="VR"):
        values.value_problem(vr, "")


@pytest.mark.parametrize(
    "vm, count",
    [
        ("1", 1),
        ("3", 3),
        ("1-3", 2),
        ("1-n", 1),
        ("1-n", 40),
        ("2-n", 2),
        ("2-2n", 2),
        ("2-2n", 6),
        ("3-3n", 9),
        ("1-n or 1", 5),
        # An empty attribute has no values, whatever its VM.
        ("2", 0),
    ],
)
def test_counts_a_vm_allows(vm, count):
    assert values.vm_problem(vm, count) is None


@pytest.mark.parametrize(
    "vm, count",
    [
        ("1", 2),
        ("3", 2),
        ("1-3", 4),
        ("2-n", 1),
        ("2-2n", 3),
        ("2-2n", 1),
        ("3-3n", 4),
        ("6-n", 5),
    ],
)
def test_counts_a_vm_does_not_allow(vm, count):
    problem = values.vm_problem(vm, count)

    assert problem
    assert f"VM {vm}" in problem


@pytest.mark.parametrize("vm", ["", "n", "1-", "2-3n", "See Note 2"])
def test_a_malformed_vm_is_rejected(vm):
    with pytest.raises(ValueError, match="VM"):
        values.vm_problem(vm, 1)


def test_values_are_checked_for_their_vm_and_vr():
    assert values.values_problem("DS", "3", ["1.0", "2.5", "-3e2"]) is None
    assert values.values_problem("CS", "1-n", []) is None

    problem = values.values_problem("DS", "3", ["1.0", "2.5"])
    assert problem is not None
    assert "VM 3" in problem

    problem = values.values_problem("CS", "1-n", ["ORIGINAL", "secret"])
    assert problem is not None
    assert "value 2" in problem
    assert "secret" not in problem


@pytest.mark.parametrize("vr", ["LT", "ST", "UR", "UT"])
def test_lt_st_ur_and_ut_have_one_value(vr):
    # PS3.5 Section 6.4, although PS3.6 gives some such attributes VM 1-n,
    # such as Data Streaming Protocol (0014,6025), an ST. Two ST values
    # written with pydicom read back as one value containing a backslash.
    assert values.values_problem(vr, "1-n", ["first", "second"]) is not None
    assert values.values_problem(vr, "1-n", ["only"]) is None


def test_a_byte_vr_has_one_value():
    # PS3.5 Section 6.4: the VM of OB, OD, OF, OL, OV, OW, and UN is 1.
    assert values.values_problem("OW", "1-n", [b"\x00\x01", b"\x00\x02"])
    assert (
        values.values_problem("US or SS or OW", "1-n or 1", [b"\x00\x01", b"\x00\x02"])
        is not None
    )
    assert values.values_problem("US or SS or OW", "1-n or 1", [1, 2]) is None


def test_alternative_vrs_and_vms_allow_any_that_fits():
    # The engine checks the VR that the data set determines; on its own, a
    # value may fit any alternative.
    # Such as LUT Data (0028,3006), "US or OW", and Pixel Padding Value
    # (0028,0120), "US or SS".
    assert values.values_problem("US or SS", "1", [-5]) is None
    assert values.values_problem("US or SS", "1", [60000]) is None
    assert values.values_problem("US or SS or OW", "1-n or 1", [b"\x00\x01"]) is None
    assert values.values_problem("US or SS", "1-n or 1", [1, 2, 3]) is None
    # Every value must fit the same VR.
    assert values.values_problem("US or SS", "1-n", [-5, 60000]) is not None
    assert values.values_problem("US or SS", "1", [70000]) is not None


def test_every_vr_the_dictionary_uses_can_be_checked():
    used = {
        vr
        for attribute in standard.load_data_dictionary().attributes
        if attribute.vr and not attribute.vr.startswith("See Note")
        for vr in attribute.vr.split(" or ")
    }

    assert used - {"SQ"} <= set(values.CHECKED_VRS)
    assert set(values.CHECKED_VRS) == standard.VRS - {"SQ"}


@pytest.mark.parametrize(
    "single",
    [
        "ORIGINAL",
        b"\x00\x01",
        bytearray(b"\x00"),
        pydicom.valuerep.PersonName("Doe^John"),
        {"ORIGINAL", "PRIMARY"},
    ],
)
def test_a_single_value_is_not_taken_as_its_characters(single):
    # pydicom gives an attribute with one value as that value alone.
    with pytest.raises(TypeError, match="sequence of values"):
        values.values_problem("CS", "2-n", single)


def test_pydicom_multiple_values_are_a_sequence():
    dataset = pydicom.Dataset()
    dataset.ImageType = ["ORIGINAL", "PRIMARY", "AXIAL"]

    assert values.values_problem("CS", "2-n", dataset.ImageType) is None


def test_every_vm_the_dictionary_uses_can_be_checked():
    vms = {
        attribute.vm
        for attribute in standard.load_data_dictionary().attributes
        if attribute.vm
    }

    assert len(vms) == 20
    for vm in vms:
        values.vm_problem(vm, 1)


@pytest.mark.parametrize("vr, value", [("DS", 1.5), ("US", -1), ("OW", "SECRET")])
def test_problems_name_the_vr(vr, value):
    problem = values.value_problem(vr, value)

    assert problem is not None
    assert f"a value of VR {vr}" in problem


@hypothesis.given(
    st.binary(min_size=32, max_size=32).map(keys.DeidKey),
    st.text(min_size=1, max_size=16).filter(lambda value: value.strip(" \x00")),
    st.dates(min_value=datetime.date(11, 1, 1)),
    st.integers(min_value=dates.MIN_OFFSET_WEEKS, max_value=dates.MAX_OFFSET_WEEKS),
)
def test_the_primitives_write_valid_values(key, patient_id, day, weeks):
    identity = pseudonyms.SubjectIdentity.from_patient_id(patient_id)
    pseudonym = pseudonyms.patient_pseudonym(key, identity)
    da = f"{day.year:04d}{day.month:02d}{day.day:02d}"

    assert values.value_problem("LO", pseudonym.patient_id) is None
    assert values.value_problem("PN", pseudonym.patients_name) is None
    assert values.value_problem("UI", uids.replacement_uid(key, "1.2.3.4")) is None
    assert values.value_problem("DA", dates.shift_date(da, weeks)) is None
    assert (
        values.value_problem("DT", dates.shift_datetime(da + "123456.5+1000", weeks))
        is None
    )
