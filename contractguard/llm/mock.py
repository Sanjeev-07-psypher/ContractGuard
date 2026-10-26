"""Deterministic provider for tests and offline demos (HLD 0.5)."""

from __future__ import annotations

import re
from typing import Any

from contractguard.llm.base import LLMError

_CLAUSE = re.compile(r'"""(?P<text>.*?)"""', re.S)
_STATUS = re.compile(r"status=(?P<status>[A-Z_]+)")
_RULE = re.compile(r"Policy rule: (?P<rule>.+?) - ")


class MockProvider:
    """Builds a grounded answer from the prompt itself, or replays ``responses`` in order.

    A scripted response that is an ``Exception`` is raised instead of returned.
    """

    name = "mock"

    def __init__(self, responses: list[dict[str, Any] | Exception] | None = None) -> None:
        self.model = "mock-1"
        self.responses = list(responses) if responses is not None else None
        self.calls: list[tuple[str, str]] = []

    def generate_json(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        temperature: float = 0.2,
        timeout_s: int = 30,
    ) -> dict[str, Any]:
        self.calls.append((system, user))
        if self.responses is not None:
            if not self.responses:
                raise LLMError("mock: no scripted responses left")
            item = self.responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        if "executive_summary" in schema.get("properties", {}):
            return {"executive_summary": "Mock overview of the flagged findings."}
        status = m.group("status") if (m := _STATUS.search(user)) else "UNKNOWN"
        rule = m.group("rule") if (m := _RULE.search(user)) else "the rule"
        clause = m.group("text").strip() if (m := _CLAUSE.search(user)) else ""
        first = re.split(r"(?<=[.;])\s", clause, maxsplit=1)[0] if clause else ""
        return {
            "summary": f"{rule}: automated status {status}.",
            "explanation": "This explanation was produced by the mock provider.",
            "why_it_matters": "Mock impact statement.",
            "suggested_review_action": "Review the clause against the policy.",
            "quoted_evidence": "" if status == "MISSING" else first,
        }
