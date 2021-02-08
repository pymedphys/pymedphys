"""Copyright (C) 2021 Matthew Jennings

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from pymedphys._imports import pydicom  # pylint: disable=unused-import


def pretty_patient_name(
    ds: "pydicom.dataset.Dataset",
    surname_first: bool = False,
    capitalise_surname: bool = True,
    include_honorific: bool = False,
) -> str:
    """Return a prettier version of a DICOM PatientName

    Parameters
    ----------
    ds : pydicom.dataset.Dataset
        The DICOM dataset that contains the PatientName to be made
        pretty.

    surname_first : bool
        If True, the pretty patient name will look like
        '[Hon]. LastName, FirstName [MiddleName]'.
        If False, the pretty patient name will look like
        '[Hon]. FirstName [MiddleName] LastName'.
        Defaults to False.

    capitalise_surname : bool
        If True, the pretty patient name will have the surname
        capitalised. If False, surname will be in title case. Defaults
        to True.

    include_honorific: bool
        If True, the pretty patient name will include the patient's
        honorific at the beginning, if it exists. Defaults to False.

    Returns
    -------
    str
        A pretty version of PatientName.
    """

    names_as_str = str(ds.PatientName)

    if include_honorific and "^^" not in names_as_str:
        raise ValueError(
            "The PatientName for this DICOM dataset does not contain "
            "an honorific. Please set `include_honorific=False`"
        )

    names, honorific = (
        names_as_str.split("^^") if "^^" in names_as_str else (names_as_str, "")
    )

    name_list = names.split("^")
    name_list.append(name_list.pop(0))  # Move surname to end

    name_list_in_pretty_case = [n.title() for n in name_list]
    honorific = honorific.title()

    if capitalise_surname:
        name_list_in_pretty_case[-1] = name_list_in_pretty_case[-1].upper()

    if surname_first:
        pretty_name = (
            f"{name_list_in_pretty_case[-1]}, {' '.join(name_list_in_pretty_case[:-1])}"
        )
    else:
        pretty_name = f"{' '.join(name_list_in_pretty_case)}"

    if include_honorific:
        pretty_name = f"{honorific}. {pretty_name}"

    return pretty_name
