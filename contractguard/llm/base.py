"""LLM provider interface (HLD 9.2) and the errors the explainer reacts to."""

from __future__ import annotations

from typing import Any, Protocol


class LLMError(Exception):
    """A provider call failed. ``retryable`` marks rate limits (429), 5xx and timeouts."""

    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class LLMProvider(Protocol):
    name: str
    model: str

    def generate_json(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        temperature: float = 0.2,
        timeout_s: int = 30,
    ) -> dict[str, Any]:
        """Return the model's JSON object. Raise ``LLMError`` on failure."""
        ...
