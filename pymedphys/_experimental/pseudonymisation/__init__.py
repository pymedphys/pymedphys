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
from os.path import abspath, basename, dirname, isdir, isfile
from os.path import join as pjoin

from pymedphys._imports import immutables

from pymedphys._dicom.anonymise import (
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
    with open(IDENTIFYING_UIDS_FILEPATH) as infile:
        IDENTIFYING_UIDS = json.load(infile)
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


def get_copy_of_strategy():
    """replacement strategy, i.e. dictionary of VR and function references for anonymisation to achieve pseudonymisation,
    as well as behaviour control parameters, including:
    delete_private_tags
    delete_unknown_tags
    To modify the copy of the strategy received involves creating a mutated version of the copy provided.
    See PEP 603, or the PyPi immutables package

    Returns
    -------
    ``immutables.Map``
        keys are either VR or behaviour control parameters, values with VR as keys are function references,
        values with behaviour control parameters are variant (appropriate to the parameter)
    """
    strategy_map = immutables.Map(strategy.pseudonymisation_dispatch)
    with strategy_map.mutate() as strategy_copy:
        strategy_copy["replace_values"] = True
        strategy_copy["keywords_to_leave_unchanged"] = ()
        strategy_copy["delete_private_tags"] = True
        strategy_copy["delete_unknown_tags"] = None
        strategy_copy["copy_dataset"] = True
        strategy_copy["identifying_keywords"] = get_default_pseudonymisation_keywords()
        strategy_map = strategy_copy.finish()
    is_valid_strategy_for_keywords(
        strategy_map["identifying_keywords"], replacement_strategy=strategy_map
    )
    return strategy_map
