import threading
import time

import trio
from anyio.from_thread import BlockingPortal
from pymedphys._imports import streamlit as st
from streamlit.runtime.scriptrunner.script_run_context import (
    add_script_run_ctx,
    get_script_run_ctx,
)


def get_streamlit_trio_portal() -> BlockingPortal:
    """Run this at the top of your app to create an anyio portal object
    that gives you access to a long running thread containing a session
    specific trio event loop.
    """
    ctx = get_script_run_ctx()

    if "portal" not in st.session_state or "thread" not in st.session_state:
        thread = threading.Thread(target=_create_event_loop_with_portal)

        st.session_state.thread = thread
        add_script_run_ctx(thread=st.session_state.thread, ctx=ctx)

        thread.start()

        while True:
            if "portal" not in st.session_state:
                time.sleep(0.1)
                continue

            break

    add_script_run_ctx(thread=st.session_state.thread, ctx=ctx)

    return st.session_state.portal


def _create_event_loop_with_portal():
    trio.run(_create_portal)


async def _create_portal():
    async with BlockingPortal() as portal:
        st.session_state.portal = portal
        await portal.sleep_until_stopped()

    del st.session_state.portal
