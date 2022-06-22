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
import dataclasses
import logging
import signal
from typing import Callable, Optional


class ShutdownAsyncLoop(Exception):
    pass


@dataclasses.dataclass
class ExceptionStore:
    exception: Optional[Exception]


def start(
    # Inspired by https://www.roguelynn.com/words/asyncio-true-concurrency/
    server_start: Callable[
        [
            asyncio.AbstractEventLoop,
            concurrent.futures.ProcessPoolExecutor,
            concurrent.futures.ThreadPoolExecutor,
        ],
        None,
    ],
    shutdown_callback: Callable,
    max_workers: Optional[int] = None,
):
    exception_store = ExceptionStore(exception=None)

    with concurrent.futures.ProcessPoolExecutor(
        max_workers=max_workers
    ) as process_executor:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers
        ) as thread_executor:
            loop = asyncio.get_event_loop()
            loop.set_debug(True)

            handle_exception, shutdown = _create_exception_and_shutdown_handler(
                process_executor=process_executor,
                thread_executor=thread_executor,
                shutdown_callback=shutdown_callback,
                exception_store=exception_store,
            )

            try:
                signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT, signal.SIGQUIT)
                for s in signals:
                    loop.add_signal_handler(
                        s, lambda s=s: asyncio.create_task(shutdown(loop, sig=s))
                    )
            except AttributeError:
                pass

            loop.set_exception_handler(handle_exception)
            server_start(loop, process_executor, thread_executor)
            loop.run_forever()

    if exception_store.exception is not None:
        try:
            raise exception_store.exception
        except Exception:  # pylint: disable = broad-except
            import sys

            try:
                from IPython.core.ultratb import ColorTB  # type: ignore

                tb = "".join(ColorTB().structured_traceback(*sys.exc_info()))
                logging.error(tb)
            except ImportError:
                pass

            raise


def _create_exception_and_shutdown_handler(
    process_executor: concurrent.futures.ProcessPoolExecutor,
    thread_executor: concurrent.futures.ThreadPoolExecutor,
    shutdown_callback: Callable,
    exception_store: ExceptionStore,
):
    def handle_exception(loop: asyncio.AbstractEventLoop, context):
        try:
            exception_store.exception = context["exception"]
        except KeyError:
            pass

        if isinstance(exception_store.exception, ShutdownAsyncLoop):
            exception_store.exception = None
        else:
            msg = context.get("exception", context["message"])
            logging.error(f"Caught exception: {msg}")

            loop.default_exception_handler(context)

        logging.error("Shutting down due to exception.")
        loop.set_exception_handler(None)
        asyncio.create_task(shutdown(loop))

    async def shutdown(
        loop: asyncio.AbstractEventLoop,
        sig: Optional[signal.Signals] = None,  # pylint: disable = no-member
    ):
        """Cleanup tasks tied to the service's shutdown."""
        if sig:
            logging.info(f"Received exit signal {sig.name}...")

        shutdown_callback()

        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

        _ = [task.cancel() for task in tasks]
        logging.info(f"Cancelling {len(tasks)} outstanding tasks")
        await asyncio.gather(*tasks, return_exceptions=True)

        shutdown_threads(thread_executor)
        shutdown_processes(process_executor)

        logging.info("TODO: Flushing metrics")
        loop.stop()

    return handle_exception, shutdown


def shutdown_threads(thread_executor):
    logging.info("Shutting down ThreadPoolExecutor")
    thread_executor.shutdown(wait=False)

    threads = (
        thread_executor._threads  # type: ignore  # pylint: disable = protected-access
    )
    logging.info(f"Releasing {len(threads)} threads from executor")
    for thread in threads:
        try:
            thread._tstate_lock.release()  # pylint: disable = protected-access
        except Exception:  # pylint: disable = broad-except
            pass


def shutdown_processes(process_executor):
    logging.info("Shutting down ProcessPoolExecutor")
    process_executor.shutdown(wait=True)
