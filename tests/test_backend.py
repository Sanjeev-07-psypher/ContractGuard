"""FastAPI backend (HLD 10): every endpoint, via TestClient. Models are fakes; the LLM is mocked.

TestClient runs background tasks before returning the response, so an upload is DONE (or FAILED)
by the time the next request is made.
"""

import json
import shutil

import pytest
from fakes import fake_resources
from fastapi.testclient import TestClient

from backend.api.contracts import sanitize_filename
from backend.main import create_app
from contractguard.config import REPO_ROOT, get_settings
from contractguard.errors import ModelArtifactError
from contractguard.llm.mock import MockProvider

GOLD = REPO_ROOT / "evaluation" / "gold"
API = "/api/v1"


def make_settings(tmp_path):
    s = get_settings().model_copy(deep=True)
    s.paths.sqlite_path = str(tmp_path / "cg.db")
    s.paths.uploads_dir = str(tmp_path / "uploads")
    policies = tmp_path / "policies"
    policies.mkdir()
    for name in ("policy.schema.json", "default_vendor_v1.json"):
        shutil.copy(REPO_ROOT / "policies" / name, policies / name)
    s.policy.policies_dir = str(policies)
    return s


@pytest.fixture
def client(tmp_path):
    app = create_app(make_settings(tmp_path), lambda s: fake_resources(MockProvider(), settings=s))
    with TestClient(app) as c:
        yield c


def upload(client, path, **form):
    with path.open("rb") as fh:
        return client.post(f"{API}/contracts", files={"file": (path.name, fh)}, data=form)


def test_health(client):
    body = client.get(f"{API}/health").json()
    assert body["models_loaded"] and body["llm_provider"] == "mock"
    assert body["status"] == "ok" and "not legal advice" in body["disclaimer"]


def test_health_and_upload_when_models_missing(tmp_path):
    def fail(_):
        raise ModelArtifactError("Classifier artifact missing: models/classifier.joblib")

    with TestClient(create_app(make_settings(tmp_path), fail)) as c:
        body = c.get(f"{API}/health").json()
        assert not body["models_loaded"] and "Classifier artifact missing" in body["error"]
        r = upload(c, GOLD / "gc01" / "contract.docx")
        assert r.status_code == 503 and r.json()["error_code"] == "MODELS_NOT_LOADED"


@pytest.mark.parametrize("name", ["contract.docx", "contract_text.pdf", "contract_scanned.pdf"])
def test_upload_to_done_for_each_format(client, name):
    r = upload(client, GOLD / "gc01" / name, use_llm="true")
    assert r.status_code == 202 and r.json()["status"] == "QUEUED"
    cid = r.json()["contract_id"]

    status = client.get(f"{API}/contracts/{cid}/status").json()
    assert status == {"status": "DONE", "stage": "DONE", "progress": 100, "error": None}

    report = client.get(f"{API}/contracts/{cid}/report").json()
    assert report["contract_id"] == cid and len(report["findings"]) == 10
    assert report["meta"]["contract_type"] == "VENDOR_SERVICE"
    assert report["policy_version"] == "1.0.0"

    clauses = client.get(f"{API}/contracts/{cid}/clauses").json()
    assert len(clauses) == len(report["clauses"]) and clauses[0]["clause_id"] == "c001"

    listed = client.get(f"{API}/contracts").json()
    assert listed[0]["contract_id"] == cid and listed[0]["counts"]["CLAUSES"] > 0


def test_options_are_passed_through(client):
    r = upload(
        client,
        GOLD / "gc01" / "contract.docx",
        contract_type="NDA",
        use_llm="false",
        our_org_name="ABC Technologies Pvt. Ltd.",
    )
    report = client.get(f"{API}/contracts/{r.json()['contract_id']}/report").json()
    assert report["meta"]["contract_type"] == "NDA"
    assert report["meta"]["contract_type_source"] == "user" and not report["llm_used"]


def test_rejects_bad_uploads(client, tmp_path):
    txt = tmp_path / "notes.txt"
    txt.write_text("hello")
    r = upload(client, txt)
    assert r.status_code == 415 and r.json()["error_code"] == "UNSUPPORTED_FILE_TYPE"

    r = upload(client, GOLD / "gc01" / "contract.docx", contract_type="LEASE")
    assert r.status_code == 422 and r.json()["error_code"] == "INVALID_CONTRACT_TYPE"

    r = upload(client, GOLD / "gc01" / "contract.docx", policy_id="nope")
    assert r.status_code == 422 and r.json()["error_code"] == "POLICY_NOT_FOUND"

    r = client.post(f"{API}/contracts", data={"contract_type": "auto"})
    assert r.status_code == 422 and r.json()["error_code"] == "VALIDATION_ERROR"


def test_renamed_file_fails_with_readable_error(client, tmp_path):
    fake = tmp_path / "contract.pdf"
    fake.write_bytes(b"PK\x03\x04 this is really a zip")
    cid = upload(client, fake).json()["contract_id"]
    status = client.get(f"{API}/contracts/{cid}/status").json()
    assert status["status"] == "FAILED" and status["error"]
    r = client.get(f"{API}/contracts/{cid}/report")
    assert r.status_code == 409 and r.json()["error_code"] == "REPORT_NOT_READY"


def test_unknown_contract_404(client):
    for path in ("status", "report", "clauses"):
        r = client.get(f"{API}/contracts/doesnotexist/{path}")
        assert r.status_code == 404 and r.json()["error_code"] == "CONTRACT_NOT_FOUND"
    assert client.delete(f"{API}/contracts/doesnotexist").status_code == 404


def test_delete_removes_rows_and_file(client, tmp_path):
    cid = upload(client, GOLD / "gc01" / "contract.docx").json()["contract_id"]
    folder = tmp_path / "uploads" / cid
    assert folder.is_dir()
    assert client.delete(f"{API}/contracts/{cid}").status_code == 204
    assert not folder.exists()
    assert client.get(f"{API}/contracts/{cid}/status").status_code == 404
    assert client.get(f"{API}/contracts").json() == []


def test_policies_list_get_put(client):
    assert client.get(f"{API}/policies").json() == [
        {
            "policy_id": "default_vendor_v1",
            "name": "Default Vendor & SaaS Contract Policy",
            "version": "1.0.0",
        }
    ]
    policy = client.get(f"{API}/policies/default_vendor_v1").json()
    policy["rules"][2]["threshold"] = 45
    r = client.put(
        f"{API}/policies/default_vendor_v1",
        content=json.dumps(policy),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200 and r.json()["version"] == "1.0.1"
    assert client.get(f"{API}/policies/default_vendor_v1").json()["rules"][2]["threshold"] == 45


def test_policy_put_validation_error(client):
    policy = client.get(f"{API}/policies/default_vendor_v1").json()
    policy["rules"][0]["check"] = "MAGIC"
    r = client.put(f"{API}/policies/default_vendor_v1", json=policy)
    assert r.status_code == 422 and r.json()["error_code"] == "POLICY_INVALID"
    assert "rules/0/check" in r.json()["message"]
    assert client.get(f"{API}/policies/nope").status_code == 404


def test_report_uses_new_policy_version(client):
    policy = client.get(f"{API}/policies/default_vendor_v1").json()
    client.put(f"{API}/policies/default_vendor_v1", json=policy)
    cid = upload(client, GOLD / "gc01" / "contract.docx").json()["contract_id"]
    assert client.get(f"{API}/contracts/{cid}/report").json()["policy_version"] == "1.0.1"


@pytest.mark.parametrize(
    "raw,clean",
    [
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("C:\\Users\\x\\My File (1).docx", "My File _1_.docx"),
        ("...", "upload"),
        ("", "upload"),
    ],
)
def test_sanitize_filename(raw, clean):
    assert sanitize_filename(raw) == clean
