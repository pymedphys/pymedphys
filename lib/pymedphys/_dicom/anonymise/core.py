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

import functools
import json
import logging
from copy import copy  # , deepcopy
from glob import glob
from os.path import abspath, basename, dirname
from os.path import join as pjoin

from pymedphys._imports import numpy as np
from pymedphys._imports import pydicom

from pymedphys._dicom.anonymise import strategy
from pymedphys._dicom.constants import (
    DICOM_SOP_CLASS_NAMES_MODE_PREFIXES,
    NotInBaselineError,
    get_baseline_dict_entry,
    get_baseline_keyword_vr_dict,
)

HERE = dirname(abspath(__file__))

IDENTIFYING_KEYWORDS_FILEPATH = pjoin(HERE, "identifying_keywords.json")


@functools.lru_cache()
def _get_default_identifying_keywords():
    with open(IDENTIFYING_KEYWORDS_FILEPATH) as infile:
        IDENTIFYING_KEYWORDS = json.load(infile)
    return tuple(IDENTIFYING_KEYWORDS)


def get_default_identifying_keywords():
    return list(_get_default_identifying_keywords())


def filter_identifying_keywords(keywords_to_leave_unchanged, identifying_keywords=None):
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


def non_private_tags_in_dicom_dataset(ds):
    """Return all non-private tags from a DICOM dataset."""

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


def anonymise_tags(
    ds_anon, keywords_to_anonymise, replace_values, replacement_strategy=None
):
    """Anonymise all desired DICOM elements."""
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
            anonymise_tags(
                seq_item,
                keywords_to_anonymise,
                replace_values,
                replacement_strategy=replacement_strategy,
            )

    return ds_anon


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
    try:
        replacement_value = replacement_strategy[vr](current_value)
    except KeyError:
        logging.error(
            "Unable to anonymise %s with VR %s, current value is %s",
            keyword,
            vr,
            current_value,
        )
        raise

    return replacement_value


def create_filename_from_dataset(ds, dirpath=""):
    mode_prefix = DICOM_SOP_CLASS_NAMES_MODE_PREFIXES[ds.SOPClassUID.name]
    return pjoin(dirpath, "{}.{}.dcm".format(mode_prefix, ds.SOPInstanceUID))


def label_dicom_filepath_as_anonymised(filepath):
    basename_anon = "{}_Anonymised.dcm".format(
        ".".join(basename(filepath).split(".")[:-1])
    )
    return pjoin(dirname(filepath), basename_anon)


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
