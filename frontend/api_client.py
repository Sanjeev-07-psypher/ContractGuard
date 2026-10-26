"""Thin ``requests`` wrapper around the ContractGuard API (HLD 11)."""

from __future__ import annotations

import os
from typing import Any

import requests

from contractguard.config import get_settings


class APIError(Exception):
    def __init__(self, status: int, error_code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.error_code, self.message = status, error_code, message


def base_url() -> str:
    return os.environ.get("CG_API_URL") or get_settings().frontend.api_url


def _call(method: str, path: str, timeout: float = 30, **kwargs: Any) -> Any:
    try:
        r = requests.request(method, f"{base_url()}{path}", timeout=timeout, **kwargs)
    except requests.ConnectionError as exc:
        raise APIError(
            0, "BACKEND_UNREACHABLE", f"Cannot reach the backend at {base_url()}. Is it running?"
        ) from exc
    if r.status_code >= 400:
        try:
            body = r.json()
            raise APIError(
                r.status_code, body.get("error_code", "ERROR"), body.get("message", r.text)
            )
        except ValueError:
            raise APIError(r.status_code, "ERROR", r.text) from None
    if r.status_code == 204 or not r.content:
        return None
    return r.json()


def health() -> dict[str, Any]:
    return _call("GET", "/health", timeout=5)


def upload(
    filename: str, data: bytes, contract_type: str, our_org_name: str, policy_id: str, use_llm: bool
) -> dict[str, Any]:
    return _call(
        "POST",
        "/contracts",
        timeout=120,
        files={"file": (filename, data)},
        data={
            "contract_type": contract_type,
            "our_org_name": our_org_name,
            "policy_id": policy_id,
            "use_llm": str(use_llm).lower(),
        },
    )


def contracts() -> list[dict[str, Any]]:
    return _call("GET", "/contracts")


def status(contract_id: str) -> dict[str, Any]:
    return _call("GET", f"/contracts/{contract_id}/status")


def report(contract_id: str) -> dict[str, Any]:
    return _call("GET", f"/contracts/{contract_id}/report")


def clauses(contract_id: str) -> list[dict[str, Any]]:
    return _call("GET", f"/contracts/{contract_id}/clauses")


def delete(contract_id: str) -> None:
    _call("DELETE", f"/contracts/{contract_id}")


def policies() -> list[dict[str, Any]]:
    return _call("GET", "/policies")


def policy(policy_id: str) -> dict[str, Any]:
    return _call("GET", f"/policies/{policy_id}")


def save_policy(policy_id: str, body: dict[str, Any]) -> dict[str, Any]:
    return _call("PUT", f"/policies/{policy_id}", json=body)
