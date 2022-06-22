# Copyright (C) 2021 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import asyncio
import concurrent.futures
import json
import logging
import random

import grpclib.server

from .._proto.pymedphys import (
    Double1DArray,
    Double2DArray,
    DoubleArray,
    GammaReply,
    GammaServiceBase,
)
from . import _async

PORT_RETRIES = 50
PORT_MIN = 34200
PORT_MAX = 35300


def start(token: str):
    def shutdown_callback():
        pass

    def server_start(
        loop: asyncio.AbstractEventLoop,
        _process_executor: concurrent.futures.ProcessPoolExecutor,
        thread_executor: concurrent.futures.ThreadPoolExecutor,
    ):
        loop.run_until_complete(main(token=token, executor=thread_executor))

    _async.start(server_start, shutdown_callback)


class GammaService(GammaServiceBase):
    def __init__(
        self,
        token: str,
        executor: concurrent.futures.ThreadPoolExecutor,
    ):
        self._token = token
        self._loop = asyncio.get_running_loop()
        self._executor = executor

    async def _token_guard(self, token: str):
        if token != self._token:
            raise ValueError(
                f"Token doesn't match. Received {token}, expected {self._token}."
            )

    async def gamma(
        self,
        token: str,
        axes_reference: Double2DArray,
        dose_reference: DoubleArray,
        axes_evaluation: Double2DArray,
        dose_evaluation: DoubleArray,
        dose_percent_threshold: float,
        distance_threshold: float,
        lower_percent_dose_cutoff: float,
        interpolation_fraction: float,
        max_gamma: float,
        local_gamma: bool,
        global_normalisation: float,
        random_subset: int,
        ram_available: int,
    ) -> GammaReply:
        logging.info("gamma called")

        await self._token_guard(token=token)

        print(max_gamma)

        return GammaReply(data=DoubleArray(array_1_d=Double1DArray([])))


async def main(token: str, executor: concurrent.futures.ThreadPoolExecutor):
    server = grpclib.server.Server([GammaService(token=token, executor=executor)])

    for i in range(PORT_RETRIES):
        port = random.randint(PORT_MIN, PORT_MAX)
        try:
            await server.start(host="127.0.0.1", port=port)
            break
        except OSError:
            if i >= PORT_RETRIES - 1:
                raise

    print(json.dumps({"port": port}), flush=True)

    await server.wait_closed()
