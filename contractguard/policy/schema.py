"""Policy and rule models (HLD 8.1, 8.2), loading, validation and versioned saving.

The JSON Schema in ``policies/policy.schema.json`` is the source of truth for validation; the
Pydantic models mirror it so the engine works with typed objects. Saving a policy bumps the patch
version and keeps the previous file in ``policies/history/{id}@{version}.json`` (HLD 8.4).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import jsonschema
from pydantic import BaseModel, Field

from contractguard.config import Settings, get_settings
from contractguard.errors import PolicyError
from contractguard.models import Severity

Check = Literal["CLAUSE_PRESENT", "BOOLEAN_EQUALS", "NUMERIC_MIN", "NUMERIC_MAX", "ENUM_IN"]


class Rule(BaseModel):
    id: str
    name: str
    category: str
    applies_to: list[str]
    check: Check
    fact: str | None = None
    expected: bool | None = None
    threshold: float | None = None
    allowed: list[str] | None = None
    required_clause: bool = False
    severity: Severity
    policy_text: str
    recommendation_template: str


class PolicyThresholds(BaseModel):
    tau_missing: float | None = None


class Policy(BaseModel):
    policy_id: str
    name: str
    version: str
    our_org_default: str | None = None
    thresholds: PolicyThresholds = Field(default_factory=PolicyThresholds)
    rules: list[Rule]


def policies_dir(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    return settings.resolve_path(settings.policy.policies_dir)


@lru_cache(maxsize=4)
def _schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_policy(data: dict[str, Any], directory: Path | None = None) -> Policy:
    """Validate ``data`` against the JSON Schema and return a ``Policy``.

    Raises ``PolicyError(INVALID)`` with every schema error joined into one readable message.
    """
    directory = directory or policies_dir()
    validator = jsonschema.Draft202012Validator(_schema(directory / "policy.schema.json"))
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        parts = []
        for err in errors:
            where = "/".join(str(p) for p in err.absolute_path) or "(root)"
            parts.append(f"{where}: {err.message}")
        raise PolicyError("Policy is invalid: " + "; ".join(parts), PolicyError.INVALID)
    ids = [r["id"] for r in data["rules"]]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise PolicyError(f"Duplicate rule ids: {', '.join(duplicates)}", PolicyError.INVALID)
    return Policy.model_validate(data)


def list_policies(directory: Path | None = None) -> list[Policy]:
    directory = directory or policies_dir()
    out = []
    for path in sorted(directory.glob("*.json")):
        if path.name == "policy.schema.json":
            continue
        out.append(load_policy(path.stem, directory))
    return out


def load_policy(policy_id: str, directory: Path | None = None) -> Policy:
    directory = directory or policies_dir()
    if not policy_id.replace("_", "").isalnum():
        raise PolicyError(f"Invalid policy id: {policy_id!r}", PolicyError.NOT_FOUND)
    path = directory / f"{policy_id}.json"
    if not path.is_file():
        raise PolicyError(f"Policy not found: {policy_id}", PolicyError.NOT_FOUND)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PolicyError(f"Policy file is not valid JSON: {exc}", PolicyError.INVALID) from exc
    return validate_policy(data, directory)


def bump_patch(version: str) -> str:
    major, minor, patch = (int(x) for x in version.split("."))
    return f"{major}.{minor}.{patch + 1}"


def save_policy(policy_id: str, data: dict[str, Any], directory: Path | None = None) -> Policy:
    """Validate and save a policy edit (HLD 8.4, ``PUT /policies/{id}``).

    The current file is archived to ``history/``; the new version is the current version with its
    patch number bumped (whatever version the client sent). ``policy_id`` in the body must match.
    """
    directory = directory or policies_dir()
    current = load_policy(policy_id, directory)
    if data.get("policy_id") != policy_id:
        raise PolicyError("policy_id in the body must match the URL", PolicyError.INVALID)
    data = {**data, "version": bump_patch(current.version)}
    policy = validate_policy(data, directory)

    history = directory / "history"
    history.mkdir(exist_ok=True)
    path = directory / f"{policy_id}.json"
    (history / f"{policy_id}@{current.version}.json").write_text(
        path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return policy
