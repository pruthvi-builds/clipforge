"""Minimal Ollama client (local only).

Only the two endpoints we need: ``/api/tags`` (list models) and ``/api/chat``
(generate). No streaming — clip evaluation prompts are short. Uses httpx with a
generous timeout because 7B models on CPU can take a while.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from ..logging_setup import get_logger
from ..util.errors import LLMError

log = get_logger("clipforge.ollama")


@dataclass
class OllamaClient:
    base_url: str = "http://localhost:11434"
    timeout: float = 180.0

    def _url(self, path: str) -> str:
        return self.base_url.rstrip("/") + path

    def ping(self) -> bool:
        try:
            r = httpx.get(self._url("/api/tags"), timeout=5.0)
            return r.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        try:
            r = httpx.get(self._url("/api/tags"), timeout=10.0)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            raise LLMError(
                "Could not reach Ollama.",
                hint=f"Is `ollama serve` running at {self.base_url}? ({e})",
            ) from e
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]

    def has_model(self, name: str) -> bool:
        try:
            models = self.list_models()
        except LLMError:
            return False
        # match "qwen2.5:7b" or bare "qwen2.5"
        return any(m == name or m.split(":")[0] == name.split(":")[0] for m in models)

    def chat_json(
        self,
        *,
        model: str,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 1600,
    ) -> str:
        """Return the assistant message content (expected to be JSON text)."""
        payload = {
            "model": model,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "top_p": 0.9,
            },
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            r = httpx.post(self._url("/api/chat"), json=payload, timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as e:
            raise LLMError(
                f"Ollama returned HTTP {e.response.status_code}.",
                hint="Check the model name in Settings and that it is pulled "
                     "(`ollama pull <model>`).",
            ) from e
        except Exception as e:
            raise LLMError(f"Ollama request failed: {e}") from e

        msg = (data.get("message") or {}).get("content", "")
        if not msg:
            raise LLMError("Ollama returned an empty response.")
        return msg
