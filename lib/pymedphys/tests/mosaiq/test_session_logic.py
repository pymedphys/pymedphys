# Copyright (C) 2021 Derek Lane

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from pymedphys._imports import pytest

from pymedphys._mosaiq.sessions import (
    localization_offset_for_site,
    mean_session_offset_for_site,
    session_offsets_for_site,
    sessions_for_site,
)

from . import _connect
from .data import mocks


@pytest.fixture(name="connection")
def fixture_check_create_test_db():
    """ will create the test database, if it does not already exist on the instance """
    mocks.check_create_test_db()

    return _connect.connect()


@pytest.mark.mosaiqdb
def test_sessions_for_site(connection):
    """ creates basic tx field and site metadata for the mock patients """

    # the create_mock_patients output is the patient_ident dataframe
    mock_patient_ident_df = mocks.create_mock_patients()
    mock_site_df = mocks.create_mock_treatment_sites(mock_patient_ident_df)
    mock_txfield_df = mocks.create_mock_treatment_fields(mock_site_df)
    mocks.create_mock_treatment_sessions(mock_site_df, mock_txfield_df)

    # sit_set_id = 1 should be a NAL site
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
def test_session_offsets_for_site(connection):  # pylint: disable = unused-argument
    """ creates basic tx field and site metadata for the mock patients """

    # the create_mock_patients output is the patient_ident dataframe
    mock_patient_ident_df = mocks.create_mock_patients()
    mock_site_df = mocks.create_mock_treatment_sites(mock_patient_ident_df)
    mock_txfield_df = mocks.create_mock_treatment_fields(mock_site_df)
    mocks.create_mock_treatment_sessions(mock_site_df, mock_txfield_df)

    # should be a NAL site
    sit_set_id = 1

    # test the get_patient_fields helper function
    sessions_for_one_site = sessions_for_site(connection, sit_set_id)
    sessions_for_one_site = list(sessions_for_one_site)
    print(sessions_for_one_site)

    # make sure the correct number of rows were returned
    assert len(sessions_for_one_site) >= 3

    # for each treatment field
    previous_session_number = None

    for session_number, session_offset in session_offsets_for_site(
        connection, sit_set_id
    ):
        if previous_session_number:
            # check that the sessions are in order
            assert session_number > previous_session_number

        if session_offset is not None:
            assert session_offset[0] == -1.0
            assert session_offset[1] == 0.0
            assert session_offset[2] == 1.0

        previous_session_number = session_number

    mean_session_offset = mean_session_offset_for_site(connection, sit_set_id)
    assert mean_session_offset[0] == -1.0
    assert mean_session_offset[1] == 0.0
    assert mean_session_offset[2] == 1.0

    localization_offset = localization_offset_for_site(connection, sit_set_id)
    assert localization_offset[0] == -1.0
    assert localization_offset[1] == 0.0
    assert localization_offset[2] == 1.0
