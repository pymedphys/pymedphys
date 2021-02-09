from pymedphys._imports import pytest

from pymedphys._mosaiq.sessions import session_offsets_for_site, sessions_for_site
from pymedphys.mosaiq import connect

from .create_mock_data import (
    check_create_test_db,
    create_mock_patients,
    create_mock_treatment_fields,
    create_mock_treatment_sessions,
    create_mock_treatment_sites,
)

msq_server = "."
test_db_name = "MosaiqTest77008"

sa_user = "sa"
sa_password = "sqlServerPassw0rd"


@pytest.fixture(name="do_check_create_test_db")
def fixture_check_create_test_db():
    """ will create the test database, if it does not already exist on the instance """
    check_create_test_db()


@pytest.mark.mosaiqdb
def test_sessions_for_site(
    do_check_create_test_db,
):  # pylint: disable = unused-argument
    """ creates basic tx field and site metadata for the mock patients """

    # the create_mock_patients output is the patient_ident dataframe
    mock_patient_ident_df = create_mock_patients()
    mock_site_df = create_mock_treatment_sites(mock_patient_ident_df)
    mock_txfield_df = create_mock_treatment_fields(mock_site_df)
    create_mock_treatment_sessions(mock_site_df, mock_txfield_df)

    with connect(
        msq_server,
        port=1433,
        database=test_db_name,
        username=sa_user,
        password=sa_password,
    ) as connection:

        sit_set_id = 1

        # test the get_patient_fields helper function
        sessions_for_one_site = sessions_for_site(connection, sit_set_id)
        sessions_for_one_site = list(sessions_for_one_site)
        print(sessions_for_one_site)

        # make sure the correct number of rows were returned
        assert len(sessions_for_one_site) >= 3

        # for each treatment field
        previous_session_number = None
        previous_session_end = None

        for session_number, session_start, session_end in sessions_for_one_site:
            print(session_number, session_start, session_end)

            if previous_session_number is not None:
                # check that the sessions are in order
                assert session_number > previous_session_number

            if previous_session_end is not None:
                assert session_start > previous_session_end

            assert session_end > session_start

            previous_session_end = session_number
            previous_session_end = session_end


@pytest.mark.mosaiqdb
def test_session_offsets_for_site(
    do_check_create_test_db,
):  # pylint: disable = unused-argument
    """ creates basic tx field and site metadata for the mock patients """

    # the create_mock_patients output is the patient_ident dataframe
    mock_patient_ident_df = create_mock_patients()
    mock_site_df = create_mock_treatment_sites(mock_patient_ident_df)
    mock_txfield_df = create_mock_treatment_fields(mock_site_df)
    create_mock_treatment_sessions(mock_site_df, mock_txfield_df)

    with connect(
        msq_server,
        port=1433,
        database=test_db_name,
        username=sa_user,
        password=sa_password,
    ) as connection:

        sit_set_id = 1

        # test the get_patient_fields helper function
        sessions_for_one_site = sessions_for_site(connection, sit_set_id)
        sessions_for_one_site = list(sessions_for_one_site)
        print(sessions_for_one_site)

        # make sure the correct number of rows were returned
        assert len(sessions_for_one_site) >= 3

        # for each treatment field
        previous_session_number = None
        previous_session_offset_when = None

        for session_number, session_offset in session_offsets_for_site(
            connection, sit_set_id
        ):
            if previous_session_number is not None:
                # check that the sessions are in order
                assert session_number > previous_session_number

            if session_offset is not None:
                if previous_session_offset_when is not None:
                    assert session_offset[0] > previous_session_offset_when
                assert abs(session_offset[1]) <= 10.0
                assert abs(session_offset[2]) <= 10.0
                assert abs(session_offset[3]) <= 10.0

                previous_session_offset_when = session_offset[0]

            previous_session_number = session_number
