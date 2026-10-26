"""Streamlit pages (HLD 11) end to end against a live local backend.

The backend runs in a thread with uvicorn (fake classifier, mock LLM); each page is executed
headless with Streamlit's AppTest, which talks to it over HTTP like the real UI.
"""

import socket
import threading
import time

import pytest
import requests
import uvicorn
from fakes import fake_resources
from streamlit.testing.v1 import AppTest
from test_backend import GOLD, make_settings

from backend.main import create_app
from contractguard.config import REPO_ROOT
from contractguard.llm.mock import MockProvider

FRONTEND = REPO_ROOT / "frontend"


@pytest.fixture(scope="module")
def backend(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ui")
    app = create_app(make_settings(tmp), lambda s: fake_resources(MockProvider(), settings=s))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}/api/v1"
    for _ in range(100):
        try:
            requests.get(f"{url}/health", timeout=1)
            break
        except requests.ConnectionError:
            time.sleep(0.1)
    with (GOLD / "gc01" / "contract_text.pdf").open("rb") as fh:
        cid = requests.post(
            f"{url}/contracts", files={"file": ("gc01.pdf", fh)}, data={"use_llm": "true"}
        ).json()["contract_id"]
    for _ in range(300):
        if requests.get(f"{url}/contracts/{cid}/status").json()["status"] == "DONE":
            break
        time.sleep(0.1)
    yield url, cid
    server.should_exit = True
    thread.join(timeout=5)


def run_page(name, backend, monkeypatch, session=None):
    url, _ = backend
    monkeypatch.setenv("CG_API_URL", url)
    at = AppTest.from_file(str(FRONTEND / name), default_timeout=60)
    for k, v in (session or {}).items():
        at.session_state[k] = v
    return at.run()


def texts(at):
    return " ".join(
        str(x.value) for x in [*at.markdown, *at.caption, *at.info, *at.warning, *at.subheader]
    )


def test_home_shows_health(backend, monkeypatch):
    at = run_page("home.py", backend, monkeypatch)
    assert not at.exception
    assert [m.value for m in at.metric][:2] == ["Online", "Loaded"]
    assert "not legal advice" in texts(at)


def test_upload_page_lists_recent(backend, monkeypatch):
    at = run_page("pages/1_Upload.py", backend, monkeypatch)
    assert not at.exception
    assert at.selectbox[0].value == "auto" and at.toggle[0].value is True
    assert "gc01.pdf" in texts(at)


def test_upload_without_file_warns(backend, monkeypatch):
    at = run_page("pages/1_Upload.py", backend, monkeypatch)
    at.button[0].click().run()
    assert any("Choose a PDF or DOCX" in w.value for w in at.warning)


def test_report_page(backend, monkeypatch):
    at = run_page("pages/2_Report.py", backend, monkeypatch, {"contract_id": backend[1]})
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert int(metrics["High"]) >= 1 and "Clauses" in metrics
    body = texts(at)
    assert "IT SUPPORT SERVICES AGREEMENT" in body and "Why flagged" in body
    assert "AI-generated" in body
    assert any("R03" in e.label for e in at.expander)


def test_report_filters(backend, monkeypatch):
    at = run_page("pages/2_Report.py", backend, monkeypatch, {"contract_id": backend[1]})
    at.multiselect[0].set_value(["COMPLIANT"]).run()
    assert at.expander and all("R03" not in e.label for e in at.expander)


def test_clause_explorer(backend, monkeypatch):
    at = run_page("pages/3_Clauses.py", backend, monkeypatch, {"contract_id": backend[1]})
    assert not at.exception
    assert len(at.dataframe[0].value) > 10
    assert "c001" in " ".join(s.value for s in at.subheader)


def test_policy_editor_saves_json(backend, monkeypatch):
    at = run_page("pages/4_Policy.py", backend, monkeypatch)
    assert not at.exception
    raw = at.text_area[0]
    raw.set_value(raw.value.replace('"threshold": 30', '"threshold": 31', 1)).run()
    at.button[1].click().run()
    assert any("Saved as version 1.0.1" in s.value for s in at.success)


def test_policy_editor_shows_validation_error(backend, monkeypatch):
    at = run_page("pages/4_Policy.py", backend, monkeypatch)
    raw = at.text_area[0]
    raw.set_value(raw.value.replace('"severity": "HIGH"', '"severity": "SEVERE"', 1)).run()
    at.button[1].click().run()
    assert any("Not saved" in e.value and "severity" in e.value for e in at.error)


def test_policy_editor_table_round_trip(backend, monkeypatch):
    url, _ = backend
    before = requests.get(f"{url}/policies/default_vendor_v1").json()
    at = run_page("pages/4_Policy.py", backend, monkeypatch)
    at.button[0].click().run()
    assert any("Saved as version" in s.value for s in at.success), [e.value for e in at.error]
    after = requests.get(f"{url}/policies/default_vendor_v1").json()
    assert after["rules"] == before["rules"]  # saving an unchanged table changes nothing
