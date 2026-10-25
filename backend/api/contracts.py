"""Contract endpoints (HLD 10.1): upload, list, status, report, clauses, delete."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Response, UploadFile
from sqlmodel import Session, col, select

from backend.errors import APIError
from backend.jobs import delete_contract, run_job
from backend.state import AppState, get_state
from backend.tables import ContractRow
from contractguard.errors import PolicyError
from contractguard.models import CONTRACT_TYPES
from contractguard.pipeline import Options
from contractguard.policy.schema import load_policy

router = APIRouter(prefix="/contracts", tags=["contracts"])
ALLOWED_EXTENSIONS = {".pdf": "pdf", ".docx": "docx"}
_UNSAFE = re.compile(r"[^A-Za-z0-9._ -]+")


def sanitize_filename(name: str) -> str:
    """Keep the base name only, drop unsafe characters, never return an empty or dot name."""
    base = Path(name.replace("\\", "/")).name
    cleaned = _UNSAFE.sub("_", base).strip(" .")
    return cleaned[:120] or "upload"


def _row(state: AppState, contract_id: str) -> ContractRow:
    with Session(state.engine) as session:
        row = session.get(ContractRow, contract_id)
    if row is None:
        raise APIError(404, "CONTRACT_NOT_FOUND", f"No contract with id {contract_id}")
    return row


@router.post("", status_code=202)
async def upload_contract(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    contract_type: str = Form("auto"),
    our_org_name: str | None = Form(None),
    policy_id: str | None = Form(None),
    use_llm: bool = Form(True),
    state: AppState = Depends(get_state),
) -> dict[str, str]:
    if state.resources is None:
        raise APIError(503, "MODELS_NOT_LOADED", state.load_error or "Models are not loaded.")
    filename = sanitize_filename(file.filename or "")
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise APIError(415, "UNSUPPORTED_FILE_TYPE", "Only .pdf and .docx files are supported.")
    if contract_type != "auto" and contract_type not in CONTRACT_TYPES:
        raise APIError(422, "INVALID_CONTRACT_TYPE", f"Unknown contract type: {contract_type}")
    policy_id = policy_id or state.settings.policy.default_policy_id
    try:
        load_policy(policy_id, state.policies_dir)
    except PolicyError as exc:
        raise APIError(422, exc.code, exc.message) from exc

    max_bytes = state.settings.limits.max_file_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise APIError(413, "FILE_TOO_LARGE",
                       f"File is larger than {state.settings.limits.max_file_mb} MB.")  # fmt: skip
    if not data:
        raise APIError(422, "EMPTY_FILE", "The uploaded file is empty.")

    contract_id = uuid.uuid4().hex
    folder = state.uploads_dir / contract_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    path.write_bytes(data)

    org = (our_org_name or "").strip() or None
    with Session(state.engine) as session:
        session.add(ContractRow(
            id=contract_id, filename=filename, file_type=ALLOWED_EXTENSIONS[ext],
            contract_type=None if contract_type == "auto" else contract_type,
            our_org_name=org, policy_id=policy_id, use_llm=use_llm,
        ))  # fmt: skip
        session.commit()
    options = Options(contract_type=contract_type, our_org_name=org, policy_id=policy_id,
                      use_llm=use_llm)  # fmt: skip
    background.add_task(run_job, state.engine, state.resources, contract_id, path, options)
    return {"contract_id": contract_id, "status": "QUEUED"}


@router.get("")
def list_contracts(state: AppState = Depends(get_state)) -> list[dict[str, Any]]:
    with Session(state.engine) as session:
        rows = session.exec(select(ContractRow).order_by(col(ContractRow.created_at).desc())).all()
    return [
        {"contract_id": r.id, "filename": r.filename, "status": r.status,
         "created_at": r.created_at.isoformat(),
         "counts": json.loads(r.counts_json) if r.counts_json else None}
        for r in rows
    ]  # fmt: skip


@router.get("/{contract_id}/status")
def contract_status(contract_id: str, state: AppState = Depends(get_state)) -> dict[str, Any]:
    r = _row(state, contract_id)
    return {"status": r.status, "stage": r.stage, "progress": r.progress, "error": r.error}


@router.get("/{contract_id}/report")
def contract_report(contract_id: str, state: AppState = Depends(get_state)) -> Response:
    r = _row(state, contract_id)
    if r.status != "DONE" or r.report_json is None:
        raise APIError(409, "REPORT_NOT_READY", f"Report is not ready (status {r.status}).")
    return Response(r.report_json, media_type="application/json")


@router.get("/{contract_id}/clauses")
def contract_clauses(contract_id: str, state: AppState = Depends(get_state)) -> Any:
    r = _row(state, contract_id)
    if r.status != "DONE" or r.report_json is None:
        raise APIError(409, "REPORT_NOT_READY", f"Clauses are not ready (status {r.status}).")
    return json.loads(r.report_json)["clauses"]


@router.delete("/{contract_id}", status_code=204)
def remove_contract(contract_id: str, state: AppState = Depends(get_state)) -> Response:
    if not delete_contract(state.engine, contract_id, state.uploads_dir):
        raise APIError(404, "CONTRACT_NOT_FOUND", f"No contract with id {contract_id}")
    return Response(status_code=204)
