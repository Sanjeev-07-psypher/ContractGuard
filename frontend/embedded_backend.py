"""Start the API inside the Streamlit process when no separate API server is running.

Streamlit Community Cloud runs a single process, so there the UI starts the FastAPI backend
in a background thread on 127.0.0.1:8000. Locally and in Docker the API runs separately and
this module does nothing. Set ``CG_EMBED_BACKEND=1`` to force it on, ``0`` to force it off.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import requests
import streamlit as st

HOST = "127.0.0.1"
PORT = 8000


def _wanted() -> bool:
    flag = os.environ.get("CG_EMBED_BACKEND")
    if flag is not None:
        return flag == "1"
    return Path("/mount/src").exists()  # the folder Streamlit Community Cloud clones into


def _healthy(url: str) -> bool:
    try:
        return requests.get(f"{url}/health", timeout=2).ok
    except requests.RequestException:
        return False


@st.cache_resource(show_spinner="Starting the analysis engine (first visit takes a minute)...")
def _start(url: str) -> bool:
    if _healthy(url):
        return True
    import uvicorn

    server = uvicorn.Server(
        uvicorn.Config("backend.main:app", host=HOST, port=PORT, log_level="warning")
    )
    threading.Thread(target=server.run, daemon=True, name="contractguard-api").start()
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        if _healthy(url):
            return True
        time.sleep(1)
    return False


def ensure_backend() -> None:
    """Start the embedded API once per process if this deployment needs it."""
    if not _wanted():
        return
    url = f"http://{HOST}:{PORT}/api/v1"
    os.environ["CG_API_URL"] = url
    if not _start(url):
        st.error("The analysis engine did not start. Check the app logs.")
