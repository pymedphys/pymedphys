# Copyright (C) 2020 Stuart Swerdloff, Matthew Jennings, Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import functools
import json
import os.path
import pprint
from copy import deepcopy
from glob import glob
from os.path import abspath, basename, dirname, isdir, isfile
from os.path import join as pjoin
import hashlib
import base64
import datetime
from decimal import Decimal, DecimalTuple
import random
from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from pymedphys._dicom.constants import (
    DICOM_SOP_CLASS_NAMES_MODE_PREFIXES,
    PYMEDPHYS_ROOT_UID,
    NotInBaselineError,
    get_baseline_dict_entry,
    get_baseline_keyword_vr_dict,
)
from pymedphys._dicom.utilities import remove_file

HERE = dirname(abspath(__file__))

IDENTIFYING_KEYWORDS_FILEPATH = pjoin(HERE, "identifying_keywords.json")
IDENTIFYING_UIDS_FILEPATH = pjoin(HERE, "identify_uids.json")

with open(IDENTIFYING_KEYWORDS_FILEPATH) as input_file:
    IDENTIFYING_KEYWORDS = json.load(input_file)

with open(IDENTIFYING_UIDS_FILEPATH) as uid_input_file:
    IDENTIFYING_UIDS = json.load(uid_input_file)

KEYWORDS_FOR_PSEUDONYMS = list(set(IDENTIFYING_KEYWORDS + IDENTIFYING_UIDS))

HASH3_256 = hashlib.new("sha3_256")

EPOCH_START = "20000101"
DEFAULT_EARLIEST_STUDY_DATE = "20040415"
DICOM_DATE_FORMAT_STR = "%Y%m%d"
DICOM_DATETIME_FORMAT_STR = "%Y%m%d%H%M%S.%f"


@functools.lru_cache(maxsize=1)
def get_vr_anonymous_replacement_value_dict():
    VR_ANONYMOUS_REPLACEMENT_VALUE_DICT = {
        "AE": "Anonymous",
        "AS": "100Y",
        "CS": "ANON",
        "DA": "20190303",
        "DS": "12345678.9",
        "DT": "20190303000900.000000",
        "LO": "Anonymous",
        "LT": "Anonymous",
        "OB": (0).to_bytes(2, "little"),
        "OB or OW": (0).to_bytes(2, "little"),
        "OW": (0).to_bytes(2, "little"),
        "PN": "Anonymous",
        "SH": "Anonymous",
        "SQ": [pydicom.Dataset()],
        "ST": "Anonymous",
        "TM": "000900.000000",
        "UI": PYMEDPHYS_ROOT_UID,
        "US": 12345,
    }

    return VR_ANONYMOUS_REPLACEMENT_VALUE_DICT


def label_dicom_filepath_as_pseudonymised(filepath):
    basename_anon = "{}_Pseudonymised.dcm".format(
        ".".join(basename(filepath).split(".")[:-1])
    )
    return pjoin(dirname(filepath), basename_anon)


def create_filename_from_dataset(ds, dirpath=""):
    mode_prefix = DICOM_SOP_CLASS_NAMES_MODE_PREFIXES[ds.SOPClassUID.name]
    return pjoin(dirpath, "{}.{}.dcm".format(mode_prefix, ds.SOPInstanceUID))


def pseudonymise_dataset(  # pylint: disable = inconsistent-return-statements
    ds,
    replace_values=True,
    keywords_to_leave_unchanged=(),
    delete_private_tags=True,
    delete_unknown_tags=None,
    copy_dataset=True,
):
    r"""A tool to anonymise a DICOM dataset, replacing attributes that might
    contain identifying information with values that are either hashed using
    a SHA3 algorithm, or jittering (possibly with a consistent epoch shift)

    You can find the list of DICOM keywords that are included in default
    anonymisation `here <./identifying_keywords.json>`__.
    These were drawn from `DICOM Supp 142
    <https://www.dicomstandard.org/supplements/>`__

    **We do not yet claim conformance to any DICOM Application Level
    Confidentiality Profile**, but plan to be in a position to do so in the
    not-to-distant future.

    Parameters
    ----------
    ds : ``pydicom.dataset.Dataset``
        The DICOM dataset to be anonymised.

    replace_values : ``bool``, optional
        If set to ``True``, DICOM tags will be anonymised using dummy
        "anonymous" values. This is often required for commercial
        software to successfully read anonymised DICOM files. If set to
        ``False``, anonymised tags are simply given empty string values.
        Defaults to ``True``.

    keywords_to_leave_unchanged : ``sequence``, optional
        A sequence of DICOM keywords (corresponding to tags) to exclude
        from anonymisation. Private and unknown tags can be supplied.
        Empty by default.

    delete_private_tags : ``bool``, optional
        A boolean to flag whether or not to remove all private
        (non-standard) DICOM tags from the DICOM file. These may also
        contain identifying information. Defaults to ``True``.

    delete_unknown_tags : ``bool``, pseudo-optional
        If left as the default value of ``None`` and ``ds`` contains tags
        that are not present in PyMedPhys' copy of ``pydicom``'s DICOM
        dictionary, ``anonymise_dataset()`` will raise an error. The
        user must then either pass ``True`` or ``False`` to proceed. If set
        to ``True``, all unrecognised tags that haven't been listed in
        ``keywords_to_leave_unchanged`` will be deleted. If set to
        ``False``, these tags are simply ignored. Pass ``False`` with
        caution, since unrecognised tags may contain identifying
        information.

    copy_dataset : ``bool``, optional
        If ``True``, then a copy of ``ds`` is returned.

    Returns
    -------
    ds_anon : ``pydicom.dataset.Dataset``
        An anonymised version of the input DICOM dataset.
    """

    if copy_dataset:
        ds_anon = deepcopy(ds)
    else:
        ds_anon = ds

    unknown_tags = unknown_tags_in_dicom_dataset(ds_anon)

    if delete_unknown_tags is None and unknown_tags:
        unknown_tags_to_print = {hex(tag): ds_anon[tag].keyword for tag in unknown_tags}
        printer = pprint.PrettyPrinter(width=30)

        raise ValueError(
            "At least one of the non-private tags within your DICOM "
            "file is not within PyMedPhys copy of the DICOM "
            "dictionary. It is possible that one or more of these tags "
            "contains identifying information. The unrecognised tags "
            "are:\n\n{}\n\nTo exclude these unknown tags from the "
            "pseudonymised DICOM dataset, pass `delete_unknown_tags=True` "
            "to this function. Any unknown tags passed to "
            "`tags_to_leave_unchanged` will not be deleted. If you'd "
            "like to ignore this error and keep all unknown tags in "
            "the pseudonymised DICOM dataset, pass "
            "`delete_unknown_tags=False` to this function. Finally, "
            "if you suspect that the PyMedPhys DICOM dictionary is out "
            "of date, please raise an issue on GitHub at "
            "https://github.com/pymedphys/pymedphys/issues.".format(
                printer.pformat(unknown_tags_to_print)
            )
        )

    if delete_unknown_tags:
        unwanted_unknown_tags = []

        for tag in unknown_tags:
            if ds_anon[tag].keyword not in keywords_to_leave_unchanged:
                unwanted_unknown_tags.append(tag)
                del ds_anon[tag]

        for tag in unwanted_unknown_tags:
            if tag in ds_anon:
                raise AssertionError("Could not delete all unwanted, unknown tags.")

    if delete_private_tags:
        ds_anon.remove_private_tags()

    keywords_to_anonymise = _filter_identifying_keywords(keywords_to_leave_unchanged)

    ds_anon = _pseudonymise_tags(ds_anon, keywords_to_anonymise, replace_values)

    if copy_dataset:
        return ds_anon


def pseudonymise_file(
    dicom_filepath,
    output_filepath=None,
    delete_original_file=False,
    anonymise_filename=True,
    replace_values=True,
    keywords_to_leave_unchanged=(),
    delete_private_tags=True,
    delete_unknown_tags=None,
):
    r"""A tool to anonymise a DICOM file, replacing attributes that might
    contain identifying information with values that are either hashed using
    a SHA3 algorithm, jittering (possibly with a consistent epoch shift).

    Parameters
    ----------
    dicom_filepath : ``str`` or ``pathlib.Path``
        The path to the DICOM file to be anonymised.

    delete_original_file : ``bool``, optional
        If `True` and anonymisation completes successfully, then the
        original DICOM is deleted. Defaults to ``False``.

    anonymise_filename : ``bool``, optional
        If ``True``, the DICOM filename is replaced by a filename of the
        form:

        "<2 char DICOM modality>.<SOP Instance UID>_Pseudonymised.dcm".

        E.g.: "RP.2.16.840.1.113669.[...]_Pseudonymised.dcm"

        This ensures that the filename contains no identifying
        information, and the SOP Instance UID will already have gone through
        being pseudonymised. If set to ``False``, ``anonymise_file()`` simply
        appends "_Pseudonymised" to the original DICOM filename. Defaults
        to ``True``.

    replace_values : ``bool``, optional
        If set to ``True``, DICOM tags will be pseudonymised using dummy
        "anonymous" values. This is often required for commercial
        software to successfully read anonymised DICOM files. If set to
        ``False``, anonymised tags are simply given empty string values.
        Defaults to ``True``.

    keywords_to_leave_unchanged : ``sequence``, optional
        A sequence of DICOM keywords (corresponding to tags) to exclude
        from anonymisation. Private and unknown tags can be supplied.
        Empty by default.

    delete_private_tags : ``bool``, optional
        A boolean to flag whether or not to remove all private
        (non-standard) DICOM tags from the DICOM file. These may
        also contain identifying information. Defaults to ``True``.

    delete_unknown_tags : ``bool``, pseudo-optional
        If left as the default value of ``None`` and ``ds`` contains
        tags that are not present in PyMedPhys' copy of ``pydicom``'s
        DICOM dictionary, ``anonymise_dataset()`` will raise an error.
        The user must then either pass ``True`` or ``False`` to proceed.
        If set to ``True``, all unrecognised tags that haven't been
        listed in ``keywords_to_leave_unchanged`` will be deleted. If
        set to ``False``, these tags are simply ignored. Pass ``False``
        with caution, since unrecognised tags may contain identifying
        information.
    """
    dicom_filepath = str(dicom_filepath)

    ds = pydicom.dcmread(dicom_filepath, force=True)

    pseudonymise_dataset(
        ds=ds,
        replace_values=replace_values,
        keywords_to_leave_unchanged=keywords_to_leave_unchanged,
        delete_private_tags=delete_private_tags,
        delete_unknown_tags=delete_unknown_tags,
        copy_dataset=False,
    )

    if output_filepath is None:
        output_filepath = dicom_filepath
    else:
        os.makedirs(os.path.split(output_filepath)[0], exist_ok=True)

    if anonymise_filename:
        filepath_used = create_filename_from_dataset(
            ds, dirpath=dirname(output_filepath)
        )
    else:
        filepath_used = output_filepath

    dicom_anon_filepath = label_dicom_filepath_as_pseudonymised(filepath_used)

    print(f"{dicom_filepath} --> {dicom_anon_filepath}")

    ds.save_as(dicom_anon_filepath)

    if delete_original_file:
        remove_file(dicom_filepath)

    return dicom_anon_filepath


def pseudonymise_directory(
    dicom_dirpath,
    output_dirpath=None,
    delete_original_files=False,
    anonymise_filenames=True,
    replace_values=True,
    keywords_to_leave_unchanged=(),
    delete_private_tags=True,
    delete_unknown_tags=None,
):
    r"""A tool to pseudonymise all DICOM files in a directory and
    its subdirectories in a fashion that maintains the relationship between
    the files (reference UIDs) and temporal relationships between timestamps.

    Parameters
    ----------
    dicom_dirpath : ``str`` or ``pathlib.Path``
        The path to the directory containing DICOM files to be
        pseudonymised.

    delete_original_files : ``bool``, optional
        If set to `True` and pseudonymisation completes successfully, then
        the original DICOM files are deleted. Defaults to `False`.

    anonymise_filenames : ``bool``, optional
        If ``True``, the DICOM filenames are replaced by filenames of
        the form:

        "<2 char DICOM modality>.<SOP Instance UID>_Pseudonymised.dcm".

        E.g.: "RP.2.16.840.1.113669.[...]_Pseudonymised.dcm"

        This ensures that the filenames contain no identifying
        information, and the SOP Instance UID will already have gone through
        being pseudonymised. If ``False``, ``anonymise_directory()`` simply
        appends "_Pseudonymised" to the original DICOM filenames. Defaults
        to ``True``.

    replace_values : ``bool``, optional
        If set to ``True``, DICOM tags will be anonymised using dummy
        "anonymous" values. This is often required for commercial
        software to successfully read anonymised DICOM files. If set to
        ``False``, anonymised tags are simply given empty string values.
        Defaults to ``True``.

    keywords_to_leave_unchanged : ``sequence``, optional
        A sequence of DICOM keywords (corresponding to tags) to exclude
        from anonymisation. Private and unknown tags can be supplied.
        Empty by default.

    delete_private_tags : ``bool``, optional
        A boolean to flag whether or not to remove all private
        (non-standard) DICOM tags from the DICOM file. These may also
        contain identifying information. Defaults to ``True``.

    delete_unknown_tags : ``bool``, pseudo-optional
        If left as the default value of ``None`` and ``ds`` contains
        tags that are not present in PyMedPhys` copy of `pydicom`'s
        DICOM dictionary, ``pseudonymise_dataset()`` will raise an error.
        The user must then either pass ``True`` or ``False`` to proceed.
        If set to ``True``, all unrecognised tags that haven't been
        listed in ``keywords_to_leave_unchanged`` will be deleted. If
        set to ``False``, these tags are simply ignored. Pass ``False``
        with caution, since unrecognised tags may contain identifying
        information.
    """
    dicom_dirpath = str(dicom_dirpath)

    dicom_filepaths = glob(dicom_dirpath + "/**/*.dcm", recursive=True)
    failing_filepaths = []
    # errors = []

    for dicom_filepath in dicom_filepaths:
        if output_dirpath is not None:
            relative_path = os.path.relpath(dicom_filepath, start=dicom_dirpath)
            output_filepath = os.path.join(output_dirpath, relative_path)
        else:
            output_filepath = None

        pseudonymise_file(
            dicom_filepath,
            output_filepath=output_filepath,
            delete_original_file=delete_original_files,
            anonymise_filename=anonymise_filenames,
            replace_values=replace_values,
            keywords_to_leave_unchanged=keywords_to_leave_unchanged,
            delete_private_tags=delete_private_tags,
            delete_unknown_tags=delete_unknown_tags,
        )

    # Separate loop provides the ability to raise Exceptions from the
    # unsuccessful deletion of the original DICOM files while preventing
    # these Exceptions from interrupting the batch anonymisation.
    if delete_original_files:
        for dicom_filepath in dicom_filepaths:
            if dicom_filepath not in failing_filepaths:
                remove_file(dicom_filepath)


def pseudonymise_cli(args):
    if args.delete_unknown_tags:
        handle_unknown_tags = True
    elif args.ignore_unknown_tags:
        handle_unknown_tags = False
    else:
        handle_unknown_tags = None

    if not args.keywords_to_leave_unchanged:
        keywords_to_leave_unchanged = ()
    else:
        keywords_to_leave_unchanged = args.keywords_to_leave_unchanged

    if isfile(args.input_path):
        pseudonymise_file(
            dicom_filepath=args.input_path,
            output_filepath=args.output_path,
            delete_original_file=args.delete_original_files,
            anonymise_filename=not args.preserve_filenames,
            replace_values=not args.clear_values,
            keywords_to_leave_unchanged=keywords_to_leave_unchanged,
            delete_private_tags=not args.keep_private_tags,
            delete_unknown_tags=handle_unknown_tags,
        )

    elif isdir(args.input_path):
        pseudonymise_directory(
            dicom_dirpath=args.input_path,
            output_dirpath=args.output_path,
            delete_original_files=args.delete_original_files,
            anonymise_filenames=not args.preserve_filenames,
            replace_values=not args.clear_values,
            keywords_to_leave_unchanged=keywords_to_leave_unchanged,
            delete_private_tags=not args.keep_private_tags,
            delete_unknown_tags=handle_unknown_tags,
        )

    else:
        raise FileNotFoundError(
            "No file or directory was found at the supplied input path."
        )


def is_anonymised_dataset(ds, ignore_private_tags=False):
    r"""Check whether a DICOM dataset has been (fully) anonymised.

    This function specifically checks whether the dataset has been
    anonymised using a PyMedPhys anonymiser. It is very likely that it
    will return ``False`` for an anonymous dataset that was anonymised
    using a different tool.

    Parameters
    ----------
    ds : ``pydicom.dataset.Dataset``
        The DICOM dataset to check for anonymity

    ignore_private_tags : ``bool``, optional
        If set to ``False``, ``is_anonymised_dataset()`` will return
        ``False`` if any private (non-standard) DICOM tags exist in
        ``ds``. Set to ``True`` to ignore private tags when checking for
        anonymity. Do so with caution, since private tags may contain
        identifying information. Defaults to ``False``.

    Returns
    -------
    is_anonymised : ``bool``
        `True` if `ds` has been anonymised, `False` otherwise.
    """
    for elem in ds:
        if elem.keyword in KEYWORDS_FOR_PSEUDONYMS:
            dummy_value = get_anonymous_replacement_value(elem.keyword)
            if elem.value not in ("", [], dummy_value, None):
                if elem.VR == "DS" and np.isclose(
                    float(elem.value), float(dummy_value)
                ):
                    continue

                return False

        elif elem.tag.is_private and not ignore_private_tags:
            return False

    return True


def is_anonymised_file(filepath, ignore_private_tags=False):
    r"""Check whether a DICOM file has been (fully) anonymised.

    This function specifically checks whether the DICOM file has been
    anonymised using a PyMedPhys anonymiser. It is very likely that it
    will return ``False`` for an anonymous DICOM file that was
    anonymised using a different tool.

    Parameters
    ----------
    filepath : ``str`` or ``pathlib.Path``
        The path to the DICOM file to check for anonymity.

    ignore_private_tags : ``bool``, optional
        If set to ``False``, ``is_anonymised_file()`` will return
        ``False`` if any private (non-standard) DICOM tags exist in the
        DICOM file. Set to ``True`` to ignore private tags when checking
        for anonymity. Do so with caution, since private tags may
        contain identifying information. Defaults to ``False``.

    Returns
    -------
    is_anonymised : ``bool``
        ``True`` if the DICOM dataset read from ``filepath`` has been
        anonymised, ``False`` otherwise.
    """
    ds = pydicom.dcmread(str(filepath))

    return is_anonymised_dataset(ds, ignore_private_tags=ignore_private_tags)


def is_anonymised_directory(dirpath, ignore_private_tags=False):
    r"""Check whether all DICOM files in a directory have been (fully)
    anonymised.

    This function specifically checks whether the DICOM files have been
    anonymised using a PyMedPhys anonymiser. It is very likely that it
    will return ``False`` for an anonymous DICOM file that was
    anonymised using a different tool.

    Parameters
    ----------
    dirpath : ``str`` or ``pathlib.Path``
        The path to the directory containing DICOM files to check for
        anonymity.

    ignore_private_tags : ``bool``, optional
        If set to ``False``, ``is_anonymised_directory()`` will return
        ``False`` if any private (non-standard) DICOM tags exist in any
        of the DICOM files in ``dirpath``. Set to `True` to ignore
        private tags when checking for anonymity. Do so with caution,
        since private tags may contain identifying information. Defaults
        to ``False``.

    Returns
    -------
    is_anonymised : ``bool``
        ``True`` if all of the DICOM datasets read from ``dirpath`` have
        been anonymised, ``False`` otherwise.
    """
    is_anonymised = True
    dicom_filepaths = glob(str(dirpath) + "/**/*.dcm", recursive=True)

    for dicom_filepath in dicom_filepaths:
        if not is_anonymised_file(
            dicom_filepath, ignore_private_tags=ignore_private_tags
        ):
            is_anonymised = False
            break

    return is_anonymised


def non_private_tags_in_dicom_dataset(ds):
    """Return all non-private tags from a DICOM dataset.
    """

    non_private_tags = []

    for elem in ds:
        if not elem.tag.is_private and not (
            # Ignore retired Group Length elements
            elem.tag.element == 0
            and elem.tag.group > 6
        ):
            non_private_tags.append(elem.tag)
    return non_private_tags


def unknown_tags_in_dicom_dataset(ds):
    """Return all non-private tags from a DICOM dataset that do not
    exist in the PyMedPhys copy of the DICOM dictionary.
    """

    non_private_tags_in_dataset = np.array(non_private_tags_in_dicom_dataset(ds))

    are_non_private_tags_in_dict_baseline = []
    for tag in non_private_tags_in_dataset:
        try:
            get_baseline_dict_entry(tag)
            are_non_private_tags_in_dict_baseline.append(True)
        except NotInBaselineError:
            are_non_private_tags_in_dict_baseline.append(False)

    unknown_tags = list(
        non_private_tags_in_dataset[
            np.invert(np.array(are_non_private_tags_in_dict_baseline, dtype=bool))
        ]
    )

    return unknown_tags


def _pseudonymise_tags(ds_anon, keywords_to_anonymise, replace_values):
    """Anonymise all desired DICOM elements.
    """
    for keyword in keywords_to_anonymise:
        if hasattr(ds_anon, keyword):
            if replace_values:
                value = ds_anon[keyword].value
                if value is None:
                    replacement_value = None
                elif value == "":
                    replacement_value = ""
                else:
                    if get_baseline_keyword_vr_dict()[keyword] in ("SQ"):
                        for seq_item in value:
                            _pseudonymise_tags(
                                seq_item, keywords_to_anonymise, replace_values
                            )
                        continue  # so as to bypass the assignment of replacement value
                    else:
                        replacement_value = get_pseudonymous_replacement_value(
                            keyword, value
                        )
            else:
                if get_baseline_keyword_vr_dict()[keyword] in ("OB", "OW"):
                    replacement_value = (0).to_bytes(2, "little")
                else:
                    replacement_value = ""
            setattr(ds_anon, keyword, replacement_value)

    return ds_anon


def _filter_identifying_keywords(keywords_to_leave_unchanged):
    r"""Removes DICOM keywords that the user desires to leave unchanged
    from the list of known DICOM identifying keywords and returns the
    resulting keyword list.
    """
    keywords_filtered = list(KEYWORDS_FOR_PSEUDONYMS)
    for keyword in keywords_to_leave_unchanged:
        try:
            keywords_filtered.remove(keyword)
        except ValueError:
            # Value not in list. TODO: Warn?
            pass

    return keywords_filtered


def get_anonymous_replacement_value(keyword):
    """Get an appropriate dummy anonymisation value for a DICOM element
    based on its value representation (VR)
    """
    vr = get_baseline_keyword_vr_dict()[keyword]
    return get_vr_anonymous_replacement_value_dict()[vr]


def get_pseudonymous_replacement_value(keyword, value):
    """
    Get an appropriate value for a DICOM element based on its VR and
    take in to account if it is an SOP Class UID.
    Cache values of keywords that have already come in and re-use
    the pseudonym for the *value* if it has already been used/replaced.

    Parameters
    ----------
    keyword : TYPE
        DESCRIPTION.

    Returns
    -------
    None.

    """
    vr = get_baseline_keyword_vr_dict()[keyword]
    replacement_value = value
    if vr in pseudonymisation_dispatch:
        replacement_value = pseudonymisation_dispatch[vr](value)
    else:
        print("VR of " + vr + " not found in pseudonymisation dispatch table")

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
    encoded_value = value.encode("ASCII")
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


def _pseudonymise_DA(
    value, format_str=DICOM_DATE_FORMAT_STR, earliest_study=DEFAULT_EARLIEST_STUDY_DATE
):
    epoch_start = EPOCH_START
    # earliest_study = DEFAULT_EARLIEST_STUDY_DATE
    # format_str = DICOM_DATE_FORMAT_STR
    try:
        my_datetime_obj = datetime.datetime.strptime(value, format_str)
    except ValueError:
        my_datetime_obj = datetime.datetime.strptime(value, DICOM_DATE_FORMAT_STR)
    try:
        earliest_study_datetime_obj = datetime.datetime.strptime(
            earliest_study, format_str
        )
    except ValueError:
        earliest_study_datetime_obj = datetime.datetime.strptime(
            earliest_study, DICOM_DATE_FORMAT_STR
        )
    try:
        epoch_start_datetime_obj = datetime.datetime.strptime(epoch_start, format_str)
    except ValueError:
        epoch_start_datetime_obj = datetime.datetime.strptime(
            epoch_start, DICOM_DATE_FORMAT_STR
        )

    time_delta = my_datetime_obj - earliest_study_datetime_obj
    my_new_date = epoch_start_datetime_obj + time_delta
    my_pseudonym_date = my_new_date.strftime(DICOM_DATE_FORMAT_STR)
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
    my_decimal = Decimal(value)
    as_tuple = my_decimal.as_tuple()
    digits = as_tuple.digits
    count_digits = len(digits)
    my_hash_func = hashlib.new("sha3_256")
    encoded_value = digits.encode("ASCII")
    my_hash_func.update(encoded_value)
    # my_digest = my_hash_func.digest()
    my_hex_digest = my_hash_func.hex_digest()
    sliced_digest = my_hex_digest[0:count_digits]
    my_integer = int(sliced_digest, 16)
    my_integer_string = str(my_integer)
    # string_count = len(my_integer_string)
    new_digits = list()
    for i in range(0, count_digits):
        new_digits.append(my_integer_string[i : i + 1])

    new_decimal_tuple = DecimalTuple(
        as_tuple.sign, tuple(new_digits), as_tuple.exponent
    )
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
    persons_name_three = pydicom.valuerep.PersonName3(value)
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
    return _pseudonymise_unchanged(value)


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
        "TM": _pseudonymise_TM,
        "UI": _pseudonymise_UI,
        "US": _pseudonymise_US,
    }
)


"""
 "AE": "Anonymous",
        "AS": "100Y",
        "CS": "ANON",
        "DA": "20190303",
        "DS": "12345678.9",
        "DT": "20190303000900.000000",
        "LO": "Anonymous",
        "LT": "Anonymous",
        "OB": (0).to_bytes(2, "little"),
        "OB or OW": (0).to_bytes(2, "little"),
        "OW": (0).to_bytes(2, "little"),
        "PN": "Anonymous",
        "SH": "Anonymous",
        "SQ": [pydicom.Dataset()],
        "ST": "Anonymous",
        "TM": "000900.000000",
        "UI": PYMEDPHYS_ROOT_UID,
        "US": 12345,
"""
