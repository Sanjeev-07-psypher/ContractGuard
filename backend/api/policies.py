"""Policy endpoints (HLD 10.1): list, read, and validated, versioned updates."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, Depends

from backend.errors import APIError
from backend.state import AppState, get_state
from contractguard.errors import PolicyError
from contractguard.policy.schema import list_policies, load_policy, save_policy

router = APIRouter(prefix="/policies", tags=["policies"])


def _raise(exc: PolicyError) -> None:
    status = 404 if exc.code == PolicyError.NOT_FOUND else 422
    raise APIError(status, exc.code, exc.message) from exc


@router.get("")
def get_policies(state: AppState = Depends(get_state)) -> list[dict[str, str]]:
    return [{"policy_id": p.policy_id, "name": p.name, "version": p.version}
            for p in list_policies(state.policies_dir)]  # fmt: skip


@router.get("/{policy_id}")
def get_policy(policy_id: str, state: AppState = Depends(get_state)) -> dict[str, Any]:
    try:
        load_policy(policy_id, state.policies_dir)  # validates and checks it exists
    except PolicyError as exc:
        _raise(exc)
    data: dict[str, Any] = json.loads((state.policies_dir / f"{policy_id}.json").read_text())
    return data


@router.put("/{policy_id}")
def put_policy(
    policy_id: str, body: dict[str, Any] = Body(...), state: AppState = Depends(get_state)
) -> dict[str, Any]:
    try:
        policy = save_policy(policy_id, body, state.policies_dir)
    except PolicyError as exc:
        _raise(exc)
    return policy.model_dump(mode="json", exclude_none=True)
