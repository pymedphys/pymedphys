# Copyright (C) 2020 Rafael Ayala

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import sys

from .qcheck import QuickCheck


def export_cli(args):
    """
    expose a cli to allow export of Quickcheck data to csv
    """

    ip = args.ip
    csv_path = args.csv_path
    # Create a logger to std out for cli
    log_level = logging.INFO
    logger = logging.getLogger(__name__)
    logger.setLevel(log_level)

    ch = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    ch.setFormatter(formatter)
    ch.setLevel(log_level)
    logger.addHandler(ch)

    qc = QuickCheck(ip)
    qc.connect()
    if qc.connected:
        qc.get_measurements()
        print(" Saving data to " + csv_path)
        qc.close()
        qc.measurements.to_csv(csv_path)
