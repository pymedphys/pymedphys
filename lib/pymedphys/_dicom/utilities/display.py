from pymedphys._imports import pydicom  # pylint: disable=unused-import


def get_pretty_patient_name_from_dicom_dataset(
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
        pretty_patient_name = (
            f"{name_list_in_pretty_case[-1]}, {' '.join(name_list_in_pretty_case[:-1])}"
        )
    else:
        pretty_patient_name = f"{' '.join(name_list_in_pretty_case)}"

    if include_honorific:
        pretty_patient_name = f"{honorific}. {pretty_patient_name}"

    return pretty_patient_name
