"""Optional polling for environments where cross-thread event-loop wakeups stall.

This runs the real Starlette client, API handlers, workers, and database. It adds
no mocked persistence or HTTP behavior. Normal hosts don't need the option.
"""
import asyncio
import os
from fastapi.testclient import TestClient as StarletteClient


def polling_loop():
    loop = asyncio.new_event_loop()
    def tick():
        loop.call_later(0.02, tick)
    loop.call_soon(tick)
    return loop


def TestClient(app, **kwargs):
    if os.environ.get("STASH_TEST_POLL") == "1":
        kwargs["backend_options"] = {"loop_factory": polling_loop}
    return StarletteClient(app, **kwargs)
