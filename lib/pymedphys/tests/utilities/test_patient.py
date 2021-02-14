from pymedphys._imports import pytest

from pymedphys._utilities.patient import convert_patient_name


def test_convert_patient_name():
    last_name = "Jones"
    first_name = "Davy"
    middle_initial = "L"
    honorific = "Dr"
    degree_suffix = "PhD"
    full_name_as_list = [
        last_name,
        first_name,
        middle_initial,
        honorific,
        degree_suffix,
    ]
    expected_patient_name = (
        f"{str(last_name).upper()}, {str(first_name).lower().capitalize()}"
    )

    # dog fooding
    resulting_patient_name = convert_patient_name(expected_patient_name)
    assert resulting_patient_name == expected_patient_name

    for separator in ["^", ", "]:
        for num_components in range(2, 6):
            single_string_name = separator.join(full_name_as_list[0:num_components])
            resulting_patient_name = convert_patient_name(single_string_name)
            assert resulting_patient_name == expected_patient_name


def test_convert_exceptional_patient_name():
    last_name = "De La Cruz"
    first_name = "Immanuel"
    full_name_as_list = [last_name, first_name]
    expected_patient_name = (
        f"{str(last_name).upper()}, {str(first_name).lower().capitalize()}"
    )
    for separator in [":", ";"]:
        single_string_name = separator.join(full_name_as_list)
        with pytest.raises(ValueError):
            resulting_patient_name = convert_patient_name(single_string_name)
            assert resulting_patient_name == expected_patient_name

    resulting_patient_name = convert_patient_name("^".join(full_name_as_list))
    assert resulting_patient_name == expected_patient_name
