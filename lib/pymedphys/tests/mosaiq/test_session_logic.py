from pymedphys._imports import pytest

from pymedphys._mosaiq.delivery import delivery_data_sql
from pymedphys._mosaiq.sessions import (
    get_session_offsets_for_site,
    get_sessions_for_site,
)
from pymedphys.mosaiq import connect, execute

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
def test_get_sessions_for_site(
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

        # test the get_patient_fields helper function
        fields_for_moe_df = get_patient_fields(connection, "MR8002")
        print(fields_for_moe_df)

        # make sure the correct number of rows were returned
        assert len(fields_for_moe_df) == 3

        # for each treatment field
        for fld_id, txfield in fields_for_moe_df.iterrows():
            print(fld_id, txfield)

            # check that the field label matches the field name
            assert f"Field{txfield['field_label']}" == txfield["field_name"]

            # check for txfield control points
            field_results, point_results = delivery_data_sql(
                connection, txfield["field_id"]
            )

            assert field_results[0][0] == "MU"
            print(point_results)

            # iterate over the txfield results and see if they match
            current_index = 0.0
            for tx_point in point_results:
                assert tx_point[0] >= current_index
                current_index = tx_point[0]


@pytest.mark.mosaiqdb
def test_get_session_offsets_for_site(
    do_check_create_test_db,
):  # pylint: disable = unused-argument
    """ creates basic tx field and site metadata for the mock patients """
    pass
