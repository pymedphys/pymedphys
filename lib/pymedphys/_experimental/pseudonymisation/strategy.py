# Copyright (C) 2020 Stuart Swerdloff, Simon Biggs
# Copyright (C) 2018 Matthew Jennings, Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import datetime
import hashlib
import logging
import random
from decimal import Decimal

from pymedphys._imports import pydicom

from pymedphys._dicom.anonymise import get_baseline_keyword_vr_dict
from pymedphys._dicom.uid import PYMEDPHYS_ROOT_UID

EPOCH_START = "20000101"
DEFAULT_EARLIEST_STUDY_DATE = "20040415"
DICOM_DATE_FORMAT_STR = "%Y%m%d"
DICOM_DATETIME_FORMAT_STR = "%Y%m%d%H%M%S.%f"


def get_pseudonymous_replacement_value(keyword, value):
    """
    Get an appropriate value for a DICOM element based on its VR
    that ensures consistent one way mapping to a replacement value
    which will not reveal Private Health Information

    Parameters
    ----------
    keyword : A text string representing which DICOM attribute is to have it's value replaced

    value:  The current value of the DICOM element


    Returns
    -------
    An appropriate value for a DICOM element based on its VR.
    Strings are hashed.  Dates are shifted. Ages are jittered.
    A KeyError will be raised if the VR of the attribute is not addressed by the dispatch table

    """
    vr = get_baseline_keyword_vr_dict()[keyword]
    replacement_value = pseudonymisation_dispatch[vr](value)

    return replacement_value


def _pseudonymise_plaintext(value):
    """
    Appropriate for DICOM VR that are unstructured text, e.g. SH, AE, LO
    Not appropriate for Numeric Strings (DS, IS)
    Not appropriate for DateTime (DA, TM, DT)

    Parameters
    ----------
    value : String
        the DICOM element value for an element of type SH, AE, LO.

    Returns
    -------
    The base64 text representation of the hashed input value

    """
    try:
        encoded_value = value.encode("ASCII")
    except AttributeError:
        encoded_value = str(value).encode("ASCII")

    my_hash_func = hashlib.new("sha3_256")
    my_hash_func.update(encoded_value)
    my_digest = my_hash_func.digest()
    # my_hex_digest = HASH3_256.hexdigest()
    # print ( "Hex: " + my_hex_digest )
    # print ( "Base64: " + str(base64.standard_b64encode(my_digest)) )
    my_pseudonym = base64.standard_b64encode(my_digest)
    text_pseudonym = my_pseudonym.decode("ASCII")
    # eliminate trailing '='
    pseudonym_length = len(text_pseudonym)
    if text_pseudonym[pseudonym_length - 1] == "=":
        text_pseudonym = text_pseudonym[0 : pseudonym_length - 1]
    return text_pseudonym


def _strip_plus_slash_from_base64(value):
    if value is None:
        return None
    return value.replace("+", "").replace("/", "")


def _pseudonymise_AE(value):
    my_pseudonym = _pseudonymise_plaintext(value)
    my_sliced_pseudonym = my_pseudonym[0:16]
    return my_sliced_pseudonym


def _pseudonymise_AS(value):
    """
    Attempt to provide an Age that is similar but not a match
    Round down to 80 if over 80
    Round down to decade if 20 to 80
    Add a pseudo-random value from -2 to 2 if 10 to 20
    If less than 10, switch to smaller unit Y->M->W->D and add a
    pseudo-random value from -2 to 2 to the value after converting to the
    smaller unit.

    Parameters
    ----------
    value : string conforming to DICOM AS VR
        DESCRIPTION.

    Returns
    -------
    somewhat pseudonymised equivalent of the age as DICOM VR AS

    """
    random.seed()
    increment = random.randrange(-2, 2)
    numeric = int(value[0:3])
    unit = value[3]
    pseudo_unit = unit
    if numeric > 20:
        pseudo_numeric = numeric - (numeric % 10)
        if numeric > 80:
            pseudo_numeric = 80  # very old people are rare, too rare to avoid id
    elif numeric > 10:
        pseudo_numeric = numeric + increment
    else:  # highly problematic if the value is too small
        if unit == "Y":
            pseudo_numeric = 12 * numeric + increment
            pseudo_unit = "M"
        elif unit == "M":
            pseudo_numeric = 4 * numeric + increment
            pseudo_unit = "W"
        elif unit == "W":
            pseudo_numeric = 7 * numeric + increment
            pseudo_unit = "D"

    pseudo_age = str(pseudo_numeric).zfill(3) + pseudo_unit
    return pseudo_age


def _pseudonymise_CS(value):
    my_pseudonym = _pseudonymise_plaintext(value)
    # In addition to changing to upper case, remove or replace base64 characters that
    # are not in: alphanumeric, the space character, or the underscore character
    my_upper_pseudonym = str(my_pseudonym.upper().replace("+", "").replace("/", "_"))
    my_sliced_pseudonym = my_upper_pseudonym[0:15]
    return my_sliced_pseudonym


def _add_tzinfo(d: datetime.datetime, tz: datetime.timezone) -> datetime.datetime:
    return datetime.datetime.combine(d.date(), d.time(), tz)


def _pseudonymise_DA(
    value, format_str=DICOM_DATE_FORMAT_STR, earliest_study=DEFAULT_EARLIEST_STUDY_DATE
):
    epoch_start = EPOCH_START
    # earliest_study = DEFAULT_EARLIEST_STUDY_DATE
    # format_str = DICOM_DATE_FORMAT_STR

    # let pydicom do the heavy lifting on parsing the datetime values
    my_datetime_obj = pydicom.valuerep.DT(value)
    earliest_study_datetime_obj = pydicom.valuerep.DT(earliest_study)
    epoch_start_datetime_obj = pydicom.valuerep.DT(epoch_start)

    # convert to pure datetime.datetime for date arithmetic
    earliest_study_datetime_obj = _add_tzinfo(
        earliest_study_datetime_obj, my_datetime_obj.tzinfo
    )
    epoch_start_datetime_obj = _add_tzinfo(
        epoch_start_datetime_obj, my_datetime_obj.tzinfo
    )
    my_datetime_obj = _add_tzinfo(my_datetime_obj, my_datetime_obj.tzinfo)

    time_delta = my_datetime_obj - earliest_study_datetime_obj
    # this failed when using type DT instead of datetime.datetime
    my_new_date = epoch_start_datetime_obj + time_delta

    my_pseudonym_date = my_new_date.strftime(format_str)
    return my_pseudonym_date


def _pseudonymise_DS(value):
    """
    Keep sign and exponent, but hash the digits and then convert the
    same number of digits from the hash back in to the decimal digits

    Parameters
    ----------
    value : decimal string
        A decimal string meeting the spec from DICOM

    Returns
    -------
    str
        a decimal string of the same sign and exponent.

    """
    # must call string on value because it is actually of type DSfloat
    # so to get the original string, invoke __str__(), see class DSfloat in pydicom
    # str(value) invokes value.__str__()
    original_DS_value = str(value)
    my_decimal = Decimal(original_DS_value)
    as_tuple = my_decimal.as_tuple()
    digits = as_tuple.digits
    # print ("digits :" + str(digits))
    count_digits = len(digits)
    my_hash_func = hashlib.new("sha3_256")
    encoded_value = original_DS_value.encode("ASCII")
    my_hash_func.update(encoded_value)

    my_hex_digest = my_hash_func.hexdigest()

    sliced_digest = my_hex_digest[0:count_digits]
    # convert the hex digest values to a base ten integer
    my_integer = int(sliced_digest, 16)
    my_integer_string = str(my_integer)

    new_digits = list()
    for i in range(0, count_digits):
        new_digits.append(int(my_integer_string[i : i + 1]))
    # print("new digits : " + str(new_digits))
    new_decimal_tuple = tuple((as_tuple.sign, tuple(new_digits), as_tuple.exponent))
    new_decimal = Decimal(new_decimal_tuple)
    return str(new_decimal)


def _pseudonymize_DT(value):
    return _pseudonymise_DA(value, format_str=DICOM_DATETIME_FORMAT_STR)


def _pseudonymise_LO(value):
    my_pseudonym = _pseudonymise_plaintext(value)
    my_sliced_pseudonym = my_pseudonym[0:64]
    return my_sliced_pseudonym


def _pseudonymise_LT(value):
    my_pseudonym = _pseudonymise_plaintext(value)
    my_sliced_pseudonym = my_pseudonym[0:10240]
    return my_sliced_pseudonym


def _pseudonymise_unchanged(value):
    return value


def _pseudonymise_OB(value):
    return _pseudonymise_unchanged(value)


def _pseudonymise_OW(value):
    return _pseudonymise_unchanged(value)


def _pseudonymise_OB_or_OW(value):
    return _pseudonymise_unchanged(value)


def _pseudonymise_PN(
    value, max_component_length=64, strip_name_prefix=True, strip_name_suffix=True
):
    """
    create a pseudonym from a person's name.
    Break in to surname, given name, and middle name, as well as title and honorifics
    doesn't deal with Unicode (yet)

    Parameters
    ----------
    value : string representation of Persons Name
        DESCRIPTION.
    max_component_length : integer, optional
        DESCRIPTION. The default is 64.
    strip_name_prefix : Boolean, optional
        DESCRIPTION. The default is True.
    strip_name_suffix : Boolean, optional
        DESCRIPTION. The default is True.

    Returns
    -------
    string conforming to DICOM PN format
        A pseudonym, but doesn't deal with Unicode (yet)

    """
    persons_name_three = pydicom.valuerep.PersonName(value)
    family_name = persons_name_three.family_name
    given_name = persons_name_three.given_name
    middle_name = persons_name_three.middle_name
    base64_pseudo_family = _pseudonymise_plaintext(family_name)
    pseudo_family = _strip_plus_slash_from_base64(base64_pseudo_family)
    if pseudo_family is not None:
        pseudo_family = pseudo_family[0:max_component_length]
    else:
        pseudo_family = ""

    pseudo_given = _strip_plus_slash_from_base64(_pseudonymise_plaintext(given_name))
    if pseudo_given is not None:
        pseudo_given = pseudo_given[0:max_component_length]
    else:
        pseudo_given = ""

    pseudo_middle = _strip_plus_slash_from_base64(_pseudonymise_plaintext(middle_name))
    if pseudo_middle is not None:
        pseudo_middle = pseudo_middle[0:max_component_length]
    else:
        pseudo_middle = ""

    prefix = persons_name_three.name_prefix
    suffix = persons_name_three.name_suffix
    if strip_name_prefix:
        prefix = ""
    if strip_name_suffix:
        suffix = ""

    pseudonym = "{0}^{1}^{2}^{3}^{4}".format(
        pseudo_family, pseudo_given, pseudo_middle, prefix, suffix
    )
    return pseudonym


def _pseudonymise_SH(value):
    return _pseudonymise_plaintext(value)[0:16]


def _pseudonymise_SQ(value):
    # returning an empty sequence addresses issue #1034,
    # should the programmer choose to include a sequence
    # in the list of identifying keywords.
    # But the default list of identifying keywords from
    # pseudonymisation has had sequences removed
    # so that the contents will be pseudonymised rather
    # than the sequences themselves
    logging.warning(
        "Recommend against using identifying keywords that are Sequences in pseudonymisation: %s",
        value,
    )
    return [pydicom.Dataset()]


def _pseudonymise_ST(value):
    return _pseudonymise_plaintext(value)[0:1024]


def _pseudonymise_TM(value):
    return _pseudonymise_unchanged(value)


def _pseudonymise_UI(value):
    encoded_value = value.encode("ASCII")
    my_hash_func = hashlib.new("sha3_256")
    my_hash_func.update(encoded_value)
    # my_digest = HASH3_256.digest()
    my_hex_digest = my_hash_func.hexdigest()
    chars_available = 63 - len(PYMEDPHYS_ROOT_UID)  # 64 less '.'
    big_int = int(my_hex_digest[0:chars_available], 16)
    pseudonymous_ui = PYMEDPHYS_ROOT_UID + "." + str(big_int)[0:chars_available]
    return pseudonymous_ui


def _pseudonymise_US(value):
    return _pseudonymise_unchanged(value)


pseudonymisation_dispatch = dict(
    {
        "AE": _pseudonymise_AE,
        "AS": _pseudonymise_AS,
        "CS": _pseudonymise_CS,
        "DA": _pseudonymise_DA,
        "DS": _pseudonymise_DS,
        "DT": _pseudonymize_DT,
        "LO": _pseudonymise_LO,
        "LT": _pseudonymise_LT,
        "OB": _pseudonymise_OB,
        "OB or OW": _pseudonymise_OB_or_OW,
        "OW": _pseudonymise_OW,
        "PN": _pseudonymise_PN,
        "SH": _pseudonymise_SH,
        "ST": _pseudonymise_ST,
        "SQ": _pseudonymise_SQ,
        "TM": _pseudonymise_TM,
        "UI": _pseudonymise_UI,
        "US": _pseudonymise_US,
    }
)
