# Copyright (C) 2020 Stuart Swerdloff
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

import functools
import json
import logging
import os.path
import pprint
from copy import copy, deepcopy
from glob import glob
from os.path import abspath, basename, dirname, isdir, isfile
from os.path import join as pjoin

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from pymedphys._dicom.constants import (
    DICOM_SOP_CLASS_NAMES_MODE_PREFIXES,
    NotInBaselineError,
    get_baseline_dict_entry,
    get_baseline_keyword_vr_dict,
)
from pymedphys._dicom.utilities import remove_file

from . import strategy

HERE = dirname(abspath(__file__))

IDENTIFYING_KEYWORDS_FILEPATH = pjoin(HERE, "identifying_keywords.json")


@functools.lru_cache()
def _get_default_identifying_keywords():
    with open(IDENTIFYING_KEYWORDS_FILEPATH) as infile:
        IDENTIFYING_KEYWORDS = json.load(infile)
    return tuple(IDENTIFYING_KEYWORDS)


def get_default_identifying_keywords():
    return list(_get_default_identifying_keywords())


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
    replacement_strategy=None,
    identifying_keywords=None,
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

    replacement_strategy: ``dict`` (keys are VR, value is dispatch function), optional
        If left as the default value of ``None``, the hardcode replacement strategy is used.

    identifying_keywords: ``list``, optional
        If left as None, the default values for/list of identifying keywords are used

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

    keywords_to_anonymise = _filter_identifying_keywords(
        keywords_to_leave_unchanged, identifying_keywords=identifying_keywords
    )

    ds_anon = _anonymise_tags(
        ds_anon,
        keywords_to_anonymise,
        replace_values,
        replacement_strategy=replacement_strategy,
    )

    if copy_dataset:
        return ds_anon


def anonymise_file(
    dicom_filepath,
    output_filepath=None,
    delete_original_file=False,
    anonymise_filename=True,
    replace_values=True,
    keywords_to_leave_unchanged=(),
    delete_private_tags=True,
    delete_unknown_tags=None,
    replacement_strategy=None,
    identifying_keywords=None,
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

    replacement_strategy: ``dict`` (keys are VR, value is dispatch function), optional
        If left as the default value of ``None``, the hardcode replacement strategy is used.

    identifying_keywords: ``list``, optional
        If left as None, the default values for/list of identifying keywords are used
    """
    dicom_filepath = str(dicom_filepath)

    ds = pydicom.dcmread(dicom_filepath, force=True)

    anonymise_dataset(
        ds=ds,
        replace_values=replace_values,
        keywords_to_leave_unchanged=keywords_to_leave_unchanged,
        delete_private_tags=delete_private_tags,
        delete_unknown_tags=delete_unknown_tags,
        copy_dataset=False,
        replacement_strategy=replacement_strategy,
        identifying_keywords=identifying_keywords,
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

    dicom_anon_filepath = label_dicom_filepath_as_anonymised(filepath_used)

    print(f"{dicom_filepath} --> {dicom_anon_filepath}")

    ds.save_as(dicom_anon_filepath)

    if delete_original_file:
        remove_file(dicom_filepath)

    return dicom_anon_filepath


def anonymise_directory(
    dicom_dirpath,
    output_dirpath=None,
    delete_original_files=False,
    anonymise_filenames=True,
    replace_values=True,
    keywords_to_leave_unchanged=(),
    delete_private_tags=True,
    delete_unknown_tags=None,
    replacement_strategy=None,
    identifying_keywords=None,
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

    replacement_strategy: ``dict`` (keys are VR, value is dispatch function), optional
        If left as the default value of ``None``, the hardcode replacement strategy is used.

    identifying_keywords: ``list``, optional
        If left as None, the default values for/list of identifying keywords are used
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

        anonymise_file(
            dicom_filepath,
            output_filepath=output_filepath,
            delete_original_file=delete_original_files,
            anonymise_filename=anonymise_filenames,
            replace_values=replace_values,
            keywords_to_leave_unchanged=keywords_to_leave_unchanged,
            delete_private_tags=delete_private_tags,
            delete_unknown_tags=delete_unknown_tags,
            replacement_strategy=replacement_strategy,
            identifying_keywords=identifying_keywords,
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

    replacement_strategy = (
        None  # at some point use args.pseudo to drive this, or something similar
    )

    if isfile(args.input_path):
        anonymise_file(
            dicom_filepath=args.input_path,
            output_filepath=args.output_path,
            delete_original_file=args.delete_original_files,
            anonymise_filename=not args.preserve_filenames,
            replace_values=not args.clear_values,
            keywords_to_leave_unchanged=keywords_to_leave_unchanged,
            delete_private_tags=not args.keep_private_tags,
            delete_unknown_tags=handle_unknown_tags,
            replacement_strategy=replacement_strategy,
        )

    elif isdir(args.input_path):
        anonymise_directory(
            dicom_dirpath=args.input_path,
            output_dirpath=args.output_path,
            delete_original_files=args.delete_original_files,
            anonymise_filenames=not args.preserve_filenames,
            replace_values=not args.clear_values,
            keywords_to_leave_unchanged=keywords_to_leave_unchanged,
            delete_private_tags=not args.keep_private_tags,
            delete_unknown_tags=handle_unknown_tags,
            replacement_strategy=replacement_strategy,
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
        if elem.keyword in get_default_identifying_keywords():
            dummy_value = get_anonymous_replacement_value(elem.keyword)
            if not elem.value in ("", [], dummy_value, None):
                if elem.VR == "DS" and np.isclose(
                    float(elem.value), float(dummy_value)
                ):
                    continue
                logging.info("%s is not considered to be anonymised", elem.name)
                return False

        elif elem.tag.is_private and not ignore_private_tags:
            logging.info(
                "%s is private and private tags are not being ignored", elem.tag
            )
            return False
        elif elem.VR == "SQ":
            contents_are_anonymous = True
            for seq in elem.value:
                contents_are_anonymous = is_anonymised_dataset(seq, ignore_private_tags)
                if not contents_are_anonymous:
                    logging.info(
                        "%s contained an element not considered to be anonymised",
                        elem.name,
                    )
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


def _anonymise_tags(
    ds_anon, keywords_to_anonymise, replace_values, replacement_strategy=None
):
    """Anonymise all desired DICOM elements.
    """
    if not replace_values and replacement_strategy is not None:
        logging.warning(
            "Conflicting approach to anonymisation specified, a replacement strategy was specified in addition to a directive"
            "to eliminate values rather than replace them.  Adhering to directive to eliminate values"
        )

    for keyword in keywords_to_anonymise:
        if hasattr(ds_anon, keyword):
            if replace_values:
                if ds_anon[keyword].value in ("", None, []):
                    logging.debug(
                        "%s has value of empty list, None or empty string, no need to modify to anonymise",
                        keyword,
                    )
                    continue
                replacement_value = get_anonymous_replacement_value(
                    keyword,
                    current_value=ds_anon[keyword].value,
                    replacement_strategy=replacement_strategy,
                )
            else:
                if get_baseline_keyword_vr_dict()[keyword] in ("OB", "OW"):
                    replacement_value = (0).to_bytes(2, "little")
                else:
                    replacement_value = ""
            setattr(ds_anon, keyword, replacement_value)

    remaining_seq_only_list = [
        x for x in ds_anon if (x.VR == "SQ" and x.name not in keywords_to_anonymise)
    ]
    for seq in remaining_seq_only_list:
        for seq_item in seq.value:
            _anonymise_tags(
                seq_item,
                keywords_to_anonymise,
                replace_values,
                replacement_strategy=replacement_strategy,
            )

    return ds_anon


def _filter_identifying_keywords(
    keywords_to_leave_unchanged, identifying_keywords=None
):
    r"""Removes DICOM keywords that the user desires to leave unchanged
    from the list of known DICOM identifying keywords and returns the
    resulting keyword list.
    """
    if identifying_keywords is None:
        keywords_filtered = get_default_identifying_keywords()
    else:
        keywords_filtered = copy(identifying_keywords)

    for keyword in keywords_to_leave_unchanged:
        try:
            keywords_filtered.remove(keyword)
        except ValueError:
            # Value not in list. TODO: Warn?
            pass

    return keywords_filtered


def get_anonymous_replacement_value(
    keyword, current_value=None, replacement_strategy=None
):
    """Get an appropriate anonymisation value for a DICOM element
    based on its value representation (VR)
    Parameters
    ----------
    keyword: text string that is the pydicom name for the DICOM attribute/element

    current_value: optional, the value that is currently assigned to the element

    replacement_strategy: optional, a dispatch dictionary whose keys are the text representation
    of the VR of the element, and whose values are function references that take the current value
    of the element.

    Returns
    -------
    A value that is a suitable replacement for the element whose attributes are identified by the keyword

    TODO
    ----
    Address VR of CS to ensure DICOM conformance and if possible, interoperability
    CS typically implies a defined set of values, or in some cases, a strict enumeration of values
    and replacement with a value that is not in a defined set will often break interoperability.
    Replacement with a value that is not in an enumerated set breaks DICOM conformance.

    """
    vr = get_baseline_keyword_vr_dict()[keyword]
    if vr == "CS":
        #       An example, although this exact code breaks unit tests because
        #       the unit tests are expecting the CS hardcoded replacement string "ANON"
        #       if keyword == "PatientSex":
        #           replacement_value = "O"  # or one can replace with an empty string because PatientSex is typically type 2
        #       else:
        logging.warning(
            "Keyword %s has Value Representation CS and may require special processing to avoid breaking DICOM conformance or interoperability",
            keyword,
        )
        #   elif ...

    if replacement_strategy is None:
        replacement_strategy = strategy.ANONYMISATION_HARDCODE_DISPATCH
    replacement_value = replacement_strategy[vr](current_value)

    return replacement_value
