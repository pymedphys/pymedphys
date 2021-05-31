# Copyright (C) 2020 Stuart Swerdloff, Simon Biggs

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
import pathlib
from os.path import abspath, dirname, isdir, isfile
from os.path import join as pjoin

from pymedphys._imports import pydicom

from pymedphys._dicom.anonymise import (
    anonymise_dataset,
    anonymise_directory,
    anonymise_file,
    get_baseline_keyword_vr_dict,
    get_default_identifying_keywords,
)

from . import strategy

HERE = dirname(abspath(__file__))

IDENTIFYING_UIDS_FILEPATH = pjoin(HERE, "identifying_uids.json")


@functools.lru_cache()
def _get_default_identifying_uids():
    with open(IDENTIFYING_UIDS_FILEPATH) as uid_file:
        IDENTIFYING_UIDS = json.load(uid_file)
    return tuple(IDENTIFYING_UIDS)


def get_default_identifying_uids():
    return list(_get_default_identifying_uids())


@functools.lru_cache()
def _get_default_pseudonymisation_keywords():
    anon_keyword_list = get_default_identifying_keywords()
    # The preferred approach is to pseudonymise the contents
    # of sequences, rather than operate on the sequence itself
    #
    # Eliminating the keywords that are sequences fixes issue #1034
    # for default usage
    identifying_keywords_less_sequences = [
        x for x in anon_keyword_list if not x.endswith("Sequence")
    ]
    anon_keyword_set = set(identifying_keywords_less_sequences)
    pseudo_uid_set = set(get_default_identifying_uids())
    return tuple(anon_keyword_set.union(pseudo_uid_set))


def get_default_pseudonymisation_keywords():
    return list(_get_default_pseudonymisation_keywords())


def anonymise_with_pseudo_cli(args):

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

    replacement_strategy = None
    if args.pseudo:
        logging.info("Was run with pseudo!")
        identifying_keywords_for_pseudo = get_default_pseudonymisation_keywords()
        logging.info("Using pseudonymisation keywords")
        replacement_strategy = strategy.pseudonymisation_dispatch
        logging.info("Using pseudonymisation strategy")

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
            identifying_keywords=identifying_keywords_for_pseudo,
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
            identifying_keywords=identifying_keywords_for_pseudo,
        )

    else:
        raise FileNotFoundError(
            "No file or directory was found at the supplied input path."
        )


def is_valid_strategy_for_keywords(
    identifying_keywords=None, replacement_strategy=None
):
    if identifying_keywords is None:
        identifying_keywords = get_default_pseudonymisation_keywords()

    if replacement_strategy is None:
        replacement_strategy = strategy.pseudonymisation_dispatch

    baseline_keyword_vr_dict = get_baseline_keyword_vr_dict()
    for keyword in identifying_keywords:
        vr = baseline_keyword_vr_dict[keyword]
        # pydicom.datadict.dictionary_VR(pydicom.datadict.tag_for_keyword(keyword))
        if vr not in replacement_strategy:
            return False
    return True


def pseudonymise(dicom_input, output_path=None):
    """Convenient API to pseudonymisation.
    Elements whose tags are not in the pydicom dictionary will be deleted
    PatientSex will not be modified/pseudonymised
    For fine tune control, use anonymise_dataset() instead

    Parameters
    ----------
    dicom_input : ``pydicom.dataset.Dataset | str | pathlib.Path``
        Either a dataset, a path to a file or a path to a directory
    output_path : ``str | pathlib.Path``, optional
        If the input is a file or a path, the directory to place the
        pseudonymised files, by default None

    Returns
    -------
    ``pydicom.dataset.Dataset`` | ``str`` | ``list`` of ``str``
        if the dicom_input was a dataset, return the pseudonymised dataset
        if the dicom input was a file, return the path to the pseudonymised file.
        if the dicom input was a directory, return the list of successfully
        anonymised files, and return that instead of None
    """
    replacement_strategy = strategy.pseudonymisation_dispatch
    identifying_keywords_for_pseudo = get_default_pseudonymisation_keywords()
    if not is_valid_strategy_for_keywords():
        logging.error("Pseudonymisation strategy is not valid for keywords")
        logging.error("Please submit issue to PyMedPhys")
        # but continue on, the data might not contain the offending keywords
        # and if it does... there will be some kind of error raised
    keywords_to_leave_unchanged = list("PatientSex")

    if isinstance(dicom_input, pydicom.dataset.Dataset):
        pseudo_ds = anonymise_dataset(
            dicom_input,
            keywords_to_leave_unchanged=keywords_to_leave_unchanged,
            delete_unknown_tags=True,
            replacement_strategy=replacement_strategy,
            identifying_keywords=identifying_keywords_for_pseudo,
        )
        return pseudo_ds

    if pathlib.Path().joinpath(dicom_input).is_dir():
        pseudonymised_file_list = anonymise_directory(
            dicom_input,
            output_dirpath=output_path,
            keywords_to_leave_unchanged=keywords_to_leave_unchanged,
            delete_unknown_tags=True,
            replacement_strategy=replacement_strategy,
            identifying_keywords=identifying_keywords_for_pseudo,
        )
        return pseudonymised_file_list

    if not pathlib.Path().joinpath(dicom_input).is_file():
        raise FileNotFoundError(f"Unable to find {dicom_input}")
    pseudonymised_filepath = anonymise_file(
        dicom_input,
        output_filepath=output_path,
        keywords_to_leave_unchanged=keywords_to_leave_unchanged,
        delete_unknown_tags=True,
        replacement_strategy=replacement_strategy,
        identifying_keywords=identifying_keywords_for_pseudo,
    )
    return pseudonymised_filepath
