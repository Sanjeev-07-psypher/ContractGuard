"""Gemini through Google AI Studio (HLD 9.1), using the ``google-genai`` SDK.

Free-tier data may be used by Google: demo only with synthetic or public contracts.
"""

from __future__ import annotations

import json
from typing import Any

from contractguard.llm.base import LLMError

RETRYABLE_CODES = frozenset({408, 429, 500, 502, 503, 504})


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str) -> None:
        from google import genai

        self.model = model
        self._client = genai.Client(api_key=api_key)

    def generate_json(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        temperature: float = 0.2,
        timeout_s: int = 30,
    ) -> dict[str, Any]:
        from google.genai import errors, types

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json",
            response_json_schema=schema,
            http_options=types.HttpOptions(timeout=timeout_s * 1000),
        )
        try:
            response = self._client.models.generate_content(
                model=self.model, contents=user, config=config
            )
        except errors.APIError as exc:
            raise LLMError(f"Gemini error {exc.code}", exc.code in RETRYABLE_CODES) from exc
        except Exception as exc:  # network errors and timeouts
            raise LLMError(f"Gemini call failed: {type(exc).__name__}", retryable=True) from exc
        return parse_json_object(response.text or "")


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object, tolerating a ```json fence that some models add anyway."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMError("model returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise LLMError("model returned JSON that is not an object")
    return data
