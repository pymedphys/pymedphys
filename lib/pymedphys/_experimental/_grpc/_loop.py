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

from .._proto import gamma
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


class AppService(gamma.ElectronPythonInterfaceBase):
    def __init__(
        self,
        token: str,
        executor: concurrent.futures.ThreadPoolExecutor,
        aiohttp_session: aiohttp.ClientSession,
    ):
        self._token = token
        self._loop = asyncio.get_running_loop()
        self._executor = executor
        self._aiohttp_session = aiohttp_session

    async def _token_guard(self, token: str):
        if token != self._token:
            raise ValueError("Token doesn't match")

    async def get_dicom_service_user(self, token: str) -> app.DicomServiceUser:
        await self._token_guard(token=token)

        logging.info("get_dicom_service_user was called")

        dicom_service_id = await _deploy.get_dicom_service_user(
            aiohttp_session=self._aiohttp_session
        )

        response = app.DicomServiceUser(dicom_service_id=dicom_service_id)

        logging.info(f"Response: {response}")
        return response

    async def create_dicom_service_user(
        self, token: str, organisation_id: str, deployer_id: str
    ) -> app.DicomServiceUser:
        await self._token_guard(token=token)

        logging.info("create_dicom_service_user was called")

        dicom_service_id = await _deploy.create_dicom_service_user(
            executor=self._executor,
            aiohttp_session=self._aiohttp_session,
            organisation_id=organisation_id,
            deployer_id=deployer_id,
        )

        response = app.DicomServiceUser(dicom_service_id=dicom_service_id)

        logging.info(f"Response: {response}")
        return response

    async def get_local_hmac(self, token: str) -> app.Hmac:
        await self._token_guard(token=token)

        logging.info("get_local_hmac was called")

        hmac = await self._loop.run_in_executor(
            self._executor,
            _deploy.get_local_hmac,
        )

        response = app.Hmac(hmac=hmac)

        logging.info(f"Response: {response}")
        return response

    async def trigger_firewall(self, token: str):
        await self._token_guard(token=token)

        logging.info("trigger_firewall was called")

        await self._loop.run_in_executor(
            self._executor,
            _deploy.trigger_firewall,
        )

        return app.Empty()


async def main(token: str, executor: concurrent.futures.ThreadPoolExecutor):
    async with aiohttp.ClientSession() as aiohttp_session:
        server = grpclib.server.Server(
            [
                AppService(
                    token=token, executor=executor, aiohttp_session=aiohttp_session
                )
            ]
        )

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
