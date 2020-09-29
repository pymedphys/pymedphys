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


import logging
import os
import pprint
from copy import deepcopy
from glob import glob
from os.path import dirname, isdir, isfile

from pymedphys._imports import pydicom

from pymedphys._dicom.anonymise import core
from pymedphys._dicom.utilities import remove_file


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

    unknown_tags = core.unknown_tags_in_dicom_dataset(ds_anon)

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

    keywords_to_anonymise = core.filter_identifying_keywords(
        keywords_to_leave_unchanged, identifying_keywords=identifying_keywords
    )

    ds_anon = core.anonymise_tags(
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

    Returns
    -------
    ``str``
    The file path of the anonymised file
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
        filepath_used = core.create_filename_from_dataset(
            ds, dirpath=dirname(output_filepath)
        )
    else:
        filepath_used = output_filepath

    dicom_anon_filepath = core.label_dicom_filepath_as_anonymised(filepath_used)

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
    fail_fast=True,
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

    fail_fast: ``bool``, optional, default to True
        If set to false, will continue attempts to convert files and only
        after completing translation and deleting original files (if specified)
        will raise an error to indicate not all files could be translated.

    Returns
    -------
    ``list`` of anonymised file paths
    """
    dicom_dirpath = str(dicom_dirpath)

    dicom_filepaths = glob(dicom_dirpath + "/**/*.dcm", recursive=True)
    failing_filepaths = []
    successful_filepaths = []
    anon_filepaths = []
    errors = []

    for dicom_filepath in dicom_filepaths:
        if output_dirpath is not None:
            relative_path = os.path.relpath(dicom_filepath, start=dicom_dirpath)
            output_filepath = os.path.join(output_dirpath, relative_path)
        else:
            output_filepath = None
        try:
            dicom_anon_filepath = anonymise_file(
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
            successful_filepaths.append(dicom_filepath)
            anon_filepaths.append(dicom_anon_filepath)
        except (AttributeError, LookupError, TypeError, OSError, ValueError) as error:
            errors.append(error)
            failing_filepaths.append(dicom_filepath)
            logging.warning("Unable to anonymise %s", dicom_filepath)
            logging.warning(str(error))
            if fail_fast:
                raise error

    # Separate loop provides the ability to raise Exceptions from the
    # unsuccessful deletion of the original DICOM files while preventing
    # these Exceptions from interrupting the batch anonymisation.
    if delete_original_files:
        for dicom_filepath in dicom_filepaths:
            if not dicom_filepath in failing_filepaths:
                remove_file(dicom_filepath)

    if len(errors) > 0:
        logging.info("Succeeded in anonymising: \n%s", "\n".join(successful_filepaths))
        raise errors[0]
    return anon_filepaths


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
