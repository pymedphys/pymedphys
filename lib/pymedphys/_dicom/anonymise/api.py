# Copyright (C) 2019, 2026 Matthew Jennings
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
import sys
from copy import deepcopy
from glob import glob
from os.path import dirname, isdir, isfile

from pymedphys._imports import pydicom

from pymedphys._dicom.anonymise import core
from pymedphys._dicom.anonymise.limitations import LIMITATION_NOTICE
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
    r"""Replace the values of a fixed list of identifying attributes in a
    DICOM dataset.

    The default list of keywords is
    `here <https://github.com/pymedphys/pymedphys/blob/main/lib/pymedphys/_dicom/anonymise/identifying_keywords.json>`__.
    It was drawn from `DICOM Supplement 142
    <https://www.dicomstandard.org/supplements/>`__, an earlier version of
    the attribute confidentiality profile in DICOM PS3.15 Annex E. It
    contains no UIDs and omits most RT attributes, so Study, Series, SOP
    Instance, and Frame of Reference UIDs keep their original values, as
    do attributes such as RT Plan Label, ROI Name, Beam Name, Treatment
    Machine Name, and RT Plan Date. Nested sequences are processed, but
    reference sequences on the list, such as Referenced Image Sequence,
    are replaced with a single empty item by default.

    The output can still identify patients; review it before sharing it.
    See `DICOM de-identification <https://docs.pymedphys.com/en/latest/users/background/dicom-deidentification.html>`__ for these and other limitations.

    **We do not claim conformance to any DICOM Application Level
    Confidentiality Profile**.

    Parameters
    ----------
    ds : ``pydicom.dataset.Dataset``
        The DICOM dataset to be anonymised.

    replace_values : ``bool``, optional
        If ``True`` (the default), each listed attribute that has a value
        is given a fixed dummy value for its value representation, for
        example ``ANONYMOUS^PATIENT`` for person names, ``ANON`` for code
        strings such as Patient's Sex (not a permitted value), and a single
        empty item for sequences. Some commercial software needs values
        to read the file. If ``False``, the values are emptied instead,
        and OB and OW values become two zero bytes.

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
        If ``True`` (the default), a modified copy of ``ds`` is returned
        and ``ds`` is unchanged. If ``False``, ``ds`` is modified in place
        and ``None`` is returned.

    replacement_strategy: ``dict`` (keys are VR, value is dispatch function), optional
        If left as the default value of ``None``, the hardcode replacement strategy is used.

    identifying_keywords: ``list``, optional
        If left as None, the default values for/list of identifying keywords are used

    Returns
    -------
    ds_anon : ``pydicom.dataset.Dataset`` or ``None``
        The modified copy of ``ds``, or ``None`` if ``copy_dataset`` is
        ``False``.
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
    r"""Replace the values of a fixed list of identifying attributes in a
    DICOM file, and write the result to a new file.

    The attributes are processed as in ``anonymise_dataset``. The file
    preamble and File Meta Information are written unchanged, so the
    original Media Storage SOP Instance UID remains in the output. The
    output can still identify patients; review it before sharing it.

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

        The file name therefore contains the original SOP Instance
        UID. If set to ``False``, ``anonymise_file()`` appends
        "_Anonymised" to the original file name, which may itself
        contain identifying information. Defaults to ``True``.

    replace_values : ``bool``, optional
        If ``True`` (the default), each listed attribute that has a value
        is given a fixed dummy value for its value representation, for
        example ``ANONYMOUS^PATIENT`` for person names, ``ANON`` for code
        strings such as Patient's Sex (not a permitted value), and a single
        empty item for sequences. Some commercial software needs values
        to read the file. If ``False``, the values are emptied instead,
        and OB and OW values become two zero bytes.

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
        The path of the file written. Without ``output_filepath``, it
        is written beside the original.
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
    r"""Apply ``anonymise_file`` to every file whose name ends in ``.dcm``
    (case-sensitive) in a directory and its subdirectories.

    Other files are not processed. With ``output_dirpath``, the output
    keeps the source folder structure, so folder names, which may include
    a patient's name, are copied; without it, each file is written beside
    its original. The output can still identify patients; review it
    before sharing it.

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

        The file names therefore contain the original SOP Instance
        UIDs. If ``False``, ``anonymise_directory()`` appends
        "_Anonymised" to the original file names, which may themselves
        contain identifying information. Defaults to ``True``.

    replace_values : ``bool``, optional
        If ``True`` (the default), each listed attribute that has a value
        is given a fixed dummy value for its value representation, for
        example ``ANONYMOUS^PATIENT`` for person names, ``ANON`` for code
        strings such as Patient's Sex (not a permitted value), and a single
        empty item for sequences. Some commercial software needs values
        to read the file. If ``False``, the values are emptied instead,
        and OB and OW values become two zero bytes.

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
    ``list`` of ``str``
        The paths of the files written.
    """
    dicom_dirpath = str(dicom_dirpath)

    # Sorted so that the file numbers in log messages are reproducible.
    dicom_filepaths = sorted(glob(dicom_dirpath + "/**/*.dcm", recursive=True))
    failing_filepaths = []
    anon_filepaths = []
    errors = []

    for file_number, dicom_filepath in enumerate(dicom_filepaths, start=1):
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
            anon_filepaths.append(dicom_anon_filepath)
        except (AttributeError, LookupError, TypeError, OSError, ValueError) as error:
            errors.append(error)
            failing_filepaths.append(dicom_filepath)
            # Neither the path nor the error message is logged: both can
            # contain identifying information.
            logging.warning(
                "Unable to anonymise file %d of %d (in sorted path order): %s",
                file_number,
                len(dicom_filepaths),
                type(error).__name__,
            )
            if fail_fast:
                raise error

    # Separate loop provides the ability to raise Exceptions from the
    # unsuccessful deletion of the original DICOM files while preventing
    # these Exceptions from interrupting the batch anonymisation.
    if delete_original_files:
        for dicom_filepath in dicom_filepaths:
            if dicom_filepath not in failing_filepaths:
                remove_file(dicom_filepath)

    if len(errors) > 0:
        logging.info(
            "Anonymised %d of %d files; re-raising the first error",
            len(anon_filepaths),
            len(dicom_filepaths),
        )
        raise errors[0]
    return anon_filepaths


def anonymise_cli(args):
    print(f"Warning: {LIMITATION_NOTICE}", file=sys.stderr)

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
        file_count = 1

    elif isdir(args.input_path):
        anon_filepaths = anonymise_directory(
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
        file_count = len(anon_filepaths)

    else:
        raise FileNotFoundError(
            "No file or directory was found at the supplied input path."
        )

    print_cli_summary(file_count)


def print_cli_summary(file_count: int) -> None:
    """Print the one-line summary of an anonymisation command.

    File paths are not printed. Input paths often contain patient names, and
    output file names contain the original SOP Instance UID.
    """
    print(
        f"Wrote {file_count} file(s). File paths are not shown because they "
        "can contain identifying information."
    )
