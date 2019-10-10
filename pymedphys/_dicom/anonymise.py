# Copyright (C) 2018 Matthew Jennings, Simon Biggs

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version (the "AGPL-3.0+").

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License and the additional terms for more
# details.

# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# ADDITIONAL TERMS are also included as allowed by Section 7 of the GNU
# Affero General Public License. These additional terms are Sections 1, 5,
# 6, 7, 8, and 9 from the Apache License, Version 2.0 (the "Apache-2.0")
# where all references to the definition "License" are instead defined to
# mean the AGPL-3.0+.

# You should have received a copy of the Apache-2.0 along with this
# program. If not, see <http://www.apache.org/licenses/LICENSE-2.0>.

import json
import pprint
from copy import deepcopy
from glob import glob
from os.path import abspath, basename, dirname, isdir, isfile
from os.path import join as pjoin

import numpy as np

import pydicom

from pymedphys._dicom.constants import (
    BASELINE_KEYWORD_VR_DICT,
    DICOM_SOP_CLASS_NAMES_MODE_PREFIXES,
    PYMEDPHYS_ROOT_UID,
    NotInBaselineError,
    get_baseline_dict_entry,
)
from pymedphys._dicom.utilities import remove_file

HERE = dirname(abspath(__file__))

IDENTIFYING_KEYWORDS_FILEPATH = pjoin(HERE, "identifying_keywords.json")

with open(IDENTIFYING_KEYWORDS_FILEPATH) as infile:
    IDENTIFYING_KEYWORDS = json.load(infile)

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


def label_dicom_filepath_as_anonymised(filepath):
    basename_anon = "{}_Anonymised.dcm".format(
        ".".join(basename(filepath).split(".")[:-1])
    )
    return pjoin(dirname(filepath), basename_anon)


def create_filename_from_dataset(ds, dirpath=""):
    mode_prefix = DICOM_SOP_CLASS_NAMES_MODE_PREFIXES[ds.SOPClassUID.name]
    return pjoin(dirpath, "{}.{}.dcm".format(mode_prefix, ds.SOPInstanceUID))


def anonymise_dataset(  # pylint: disable = inconsistent-return-statements
    ds,
    replace_values=True,
    keywords_to_leave_unchanged=(),
    delete_private_tags=True,
    delete_unknown_tags=None,
    copy_dataset=True,
):
    r"""A simple tool to anonymise a DICOM dataset.

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
            "file is not within PyMedPhys's copy of the DICOM "
            "dictionary. It is possible that one or more of these tags "
            "contains identifying information. The unrecognised tags "
            "are:\n\n{}\n\nTo exclude these unknown tags from the "
            "anonymised DICOM dataset, pass `delete_unknown_tags=True` "
            "to this function. Any unknown tags passed to "
            "`tags_to_leave_unchanged` will not be deleted. If you'd "
            "like to ignore this error and keep all unknown tags in "
            "the anonymised DICOM dataset, pass "
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

    ds_anon = _anonymise_tags(ds_anon, keywords_to_anonymise, replace_values)

    if copy_dataset:
        return ds_anon


def anonymise_file(
    dicom_filepath,
    delete_original_file=False,
    anonymise_filename=True,
    replace_values=True,
    keywords_to_leave_unchanged=(),
    delete_private_tags=True,
    delete_unknown_tags=None,
):
    r"""A simple tool to anonymise a DICOM file.

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

        "<2 char DICOM modality>.<SOP Instance UID>_Anonymised.dcm".

        E.g.: "RP.2.16.840.1.113669.[...]_Anonymised.dcm"

        This ensures that the filename contains no identifying
        information. If set to ``False``, ``anonymise_file()`` simply
        appends "_Anonymised" to the original DICOM filename. Defaults
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
    ds = pydicom.dcmread(str(dicom_filepath), force=True)

    anonymise_dataset(
        ds=ds,
        replace_values=replace_values,
        keywords_to_leave_unchanged=keywords_to_leave_unchanged,
        delete_private_tags=delete_private_tags,
        delete_unknown_tags=delete_unknown_tags,
        copy_dataset=False,
    )

    if anonymise_filename:
        filepath_used = create_filename_from_dataset(
            ds, dirpath=dirname(dicom_filepath)
        )
    else:
        filepath_used = dicom_filepath

    dicom_anon_filepath = label_dicom_filepath_as_anonymised(filepath_used)

    ds.save_as(dicom_anon_filepath)

    if delete_original_file:
        remove_file(dicom_filepath)

    return dicom_anon_filepath


def anonymise_directory(
    dicom_dirpath,
    delete_original_files=False,
    anonymise_filenames=True,
    replace_values=True,
    keywords_to_leave_unchanged=(),
    delete_private_tags=True,
    delete_unknown_tags=None,
):
    r"""A simple tool to anonymise all DICOM files in a directory and
    its subdirectories.

    Parameters
    ----------
    dicom_dirpath : ``str`` or ``pathlib.Path``
        The path to the directory containing DICOM files to be
        anonymised.

    delete_original_files : ``bool``, optional
        If set to `True` and anonymisation completes successfully, then
        the original DICOM files are deleted. Defaults to `False`.

    anonymise_filenames : ``bool``, optional
        If ``True``, the DICOM filenames are replaced by filenames of
        the form:

        "<2 char DICOM modality>.<SOP Instance UID>_Anonymised.dcm".

        E.g.: "RP.2.16.840.1.113669.[...]_Anonymised.dcm"

        This ensures that the filenames contain no identifying
        information. If ``False``, ``anonymise_directory()`` simply
        appends "_Anonymised" to the original DICOM filenames. Defaults
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
        DICOM dictionary, ``anonymise_dataset()`` will raise an error.
        The user must then either pass ``True`` or ``False`` to proceed.
        If set to ``True``, all unrecognised tags that haven't been
        listed in ``keywords_to_leave_unchanged`` will be deleted. If
        set to ``False``, these tags are simply ignored. Pass ``False``
        with caution, since unrecognised tags may contain identifying
        information.
    """
    dicom_filepaths = glob(str(dicom_dirpath) + "/**/*.dcm", recursive=True)
    failing_filepaths = []
    # errors = []

    for dicom_filepath in dicom_filepaths:
        anonymise_file(
            dicom_filepath,
            delete_original_file=False,
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
            if not dicom_filepath in failing_filepaths:
                remove_file(dicom_filepath)


def anonymise_cli(args):
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
        anonymise_file(
            dicom_filepath=args.input_path,
            delete_original_file=args.delete_original_files,
            anonymise_filename=not args.preserve_filenames,
            replace_values=not args.clear_values,
            keywords_to_leave_unchanged=keywords_to_leave_unchanged,
            delete_private_tags=not args.keep_private_tags,
            delete_unknown_tags=handle_unknown_tags,
        )

    elif isdir(args.input_path):
        anonymise_directory(
            dicom_dirpath=args.input_path,
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
        if elem.keyword in IDENTIFYING_KEYWORDS:
            dummy_value = get_anonymous_replacement_value(elem.keyword)
            if not elem.value in ("", [], dummy_value):
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


def _anonymise_tags(ds_anon, keywords_to_anonymise, replace_values):
    """Anonymise all desired DICOM elements.
    """
    for keyword in keywords_to_anonymise:
        if hasattr(ds_anon, keyword):
            if replace_values:
                replacement_value = get_anonymous_replacement_value(keyword)
            else:
                if BASELINE_KEYWORD_VR_DICT[keyword] in ("OB", "OW"):
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
    keywords_filtered = list(IDENTIFYING_KEYWORDS)
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
    vr = BASELINE_KEYWORD_VR_DICT[keyword]
    return VR_ANONYMOUS_REPLACEMENT_VALUE_DICT[vr]
