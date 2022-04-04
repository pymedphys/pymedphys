# Copyright (C) 2022 Rafael Ayala

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import socket
from unittest import mock, TestCase
from pymedphys._experimental.quickcheck.qcheck import QuickCheck


def mock_send_quickcheck(self, message):
    if message == 'SER':
        self.data = 'SER;1000'
    elif message == 'MEASCNT':
        self.data = 'MEASCNT;3'
    elif message.startswith('MEASGET;INDEX-MEAS='):
        self.data = 'MEASGET;INDEX-MEAS=1;MD=[ID=1636992223;Date=2021-11-15;Time=16:03:43];WORK=[' \
                    'ID=1628265817;Name=VERSA BETA];TASK=[ID=188165042;TUnit=VERSA BETA;Prot=[' \
                    'Name=HGUGM;Flat=2;Sym=1];Mod=Photons;En=6;Fs=200x200;SDD=1000;Ga=0;We=0;MU=100;My=1.0000E+00' \
                    ';Info=QA DIARIO: 6 MV];MV=[' \
                    'CAX=1.0572E+00;G10=1.0894E+00;L10=1.0869E+00;T10=1.0874E+00;R10=1.0846E+00;G20=1.0990E+00;L20=1' \
                    '.0884E+00;T20=1.0965E+00;R20=1.0923E+00;E1=9.9593E-01;E2=1.0490E+00;E3=1.0794E+00;E4=1.1317E+00' \
                    ';Temp=2.3590E+01;Press=9.3290E+02;CAXRate=5.4921E+00;ExpTime=1.1550E+01];AV=[CAX=[' \
                    'Min=9.7500E+01;Max=1.0250E+02;Target=1.0000E+02;Norm=9.5371E+01;Value=1.0083E+02;Valid=1];FLAT=[' \
                    'Min=9.7000E+01;Max=1.0300E+02;Target=1.0000E+02;Norm=9.5919E+01;Value=9.9709E+01;Valid=1];SYMGT' \
                    '=[Min=9.7000E+01;Max=1.0300E+02;Target=1.0000E+02;Norm=9.9028E-01;Value=9.9253E+01;Valid=1' \
                    '];SYMLR=[Min=9.7000E+01;Max=1.0300E+02;Target=1.0000E+02;Norm=9.9062E-01;Value=9.9423E+01;Valid' \
                    '=1];BQF=[Min=9.5000E+01;Max=1.0500E+02;Target=1.0000E+02;Norm=1.6314E+01;Value=1.0059E+02;Valid' \
                    '=1];We=[Min=0.0000E+00;Max=0.0000E+00;Target=0.0000E+00;Norm=1.0000E+00;Value=0.0000E+00;Valid=1' \
                    ']];3229717283 '


@mock.patch.object(QuickCheck, 'send_quickcheck', autospec=True)
class TestQcMethods(TestCase):

    def test_connect(self, send_quickcheck):
        qc = QuickCheck('192.168.1.1')
        send_quickcheck.side_effect = mock_send_quickcheck
        qc.connect()
        self.assertTrue(qc.connected)
        self.assertEqual(qc.data, 'SER;1000')

    def test_get_measurements(self, send_quickcheck):
        qc = QuickCheck('192.168.1.1')
        send_quickcheck.side_effect = mock_send_quickcheck
        qc.connect()
        qc.get_measurements()
        self.assertTrue(qc.connected)
        self.assertEqual(qc.measurements.shape, (3, 73))

    def test_not_connected(self, send_quickcheck):
        qc = QuickCheck('192.168.1.1')
        send_quickcheck.side_effect = mock_send_quickcheck
        self.assertTrue(qc.connected)
        with self.assertRaises(ValueError):
            qc.get_measurements()


def mock_sendto(qc, message, connection_details):
    print(message)
    if message == b'SER\r\n':
        qc.raw_data = b'SER;1571\r\n'
    elif message == b'MEASCNT':
        qc.data = 'MEASCNT;3'
    elif message.startswith(b'MEASGET;INDEX-MEAS='):
        qc.data = 'MEASGET;INDEX-MEAS=1;MD=[ID=1636992223;Date=2021-11-15;Time=16:03:43];WORK=[' \
                    'ID=1628265817;Name=VERSA BETA];TASK=[ID=188165042;TUnit=VERSA BETA;Prot=[' \
                    'Name=HGUGM;Flat=2;Sym=1];Mod=Photons;En=6;Fs=200x200;SDD=1000;Ga=0;We=0;MU=100;My=1.0000E+00' \
                    ';Info=QA DIARIO: 6 MV];MV=[' \
                    'CAX=1.0572E+00;G10=1.0894E+00;L10=1.0869E+00;T10=1.0874E+00;R10=1.0846E+00;G20=1.0990E+00;L20=1' \
                    '.0884E+00;T20=1.0965E+00;R20=1.0923E+00;E1=9.9593E-01;E2=1.0490E+00;E3=1.0794E+00;E4=1.1317E+00' \
                    ';Temp=2.3590E+01;Press=9.3290E+02;CAXRate=5.4921E+00;ExpTime=1.1550E+01];AV=[CAX=[' \
                    'Min=9.7500E+01;Max=1.0250E+02;Target=1.0000E+02;Norm=9.5371E+01;Value=1.0083E+02;Valid=1];FLAT=[' \
                    'Min=9.7000E+01;Max=1.0300E+02;Target=1.0000E+02;Norm=9.5919E+01;Value=9.9709E+01;Valid=1];SYMGT' \
                    '=[Min=9.7000E+01;Max=1.0300E+02;Target=1.0000E+02;Norm=9.9028E-01;Value=9.9253E+01;Valid=1' \
                    '];SYMLR=[Min=9.7000E+01;Max=1.0300E+02;Target=1.0000E+02;Norm=9.9062E-01;Value=9.9423E+01;Valid' \
                    '=1];BQF=[Min=9.5000E+01;Max=1.0500E+02;Target=1.0000E+02;Norm=1.6314E+01;Value=1.0059E+02;Valid' \
                    '=1];We=[Min=0.0000E+00;Max=0.0000E+00;Target=0.0000E+00;Norm=1.0000E+00;Value=0.0000E+00;Valid=1' \
                    ']];3229717283 '


def mock_recvfrom(max_bytes):
    pass


@mock.patch.object(socket.socket, 'sendto', autospec=True)
@mock.patch.object(socket.socket, 'recvfrom', autospec=True)
class TestQcMethods2(TestCase):

    def test_connect2(self, sendto, recvfrom):
        qc = QuickCheck('192.168.1.1')
        sendto.side_effect = mock_sendto
        recvfrom.side_effect = mock_recvfrom
        qc.connect()
        print('MSG:', qc.MSG)
        print('raw_data:', qc.raw_data)
        qc.sock.sendto.args
        self.assertTrue(qc.connected)
        self.assertEqual(qc.data, 'SER;1000')


