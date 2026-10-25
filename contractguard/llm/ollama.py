"""Local models through Ollama's HTTP API (HLD 9.1): the option for confidential documents.

Uses the standard library only (``POST /api/chat`` with ``format`` = the JSON schema), so the
``ollama`` package is not needed.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from contractguard.llm.base import LLMError
from contractguard.llm.gemini import parse_json_object


class OllamaProvider:
    name = "ollama"

    def __init__(self, model: str, host: str = "http://localhost:11434") -> None:
        self.model = model
        self.host = host.rstrip("/")

    def generate_json(
        self,
        system: str,
        user: str,
        schema: dict[str, Any],
        temperature: float = 0.2,
        timeout_s: int = 30,
    ) -> dict[str, Any]:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "format": schema,
            "stream": False,
            "options": {"temperature": temperature},
        }
        request = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as resp:  # noqa: S310
                payload = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raise LLMError(f"Ollama error {exc.code}", exc.code >= 500 or exc.code == 429) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise LLMError(f"Ollama unreachable at {self.host}", retryable=True) from exc
        return parse_json_object(payload.get("message", {}).get("content", ""))
