"""
Ollama-compatible HTTP client for text and vision LLM calls.

Falls back gracefully when the server is unreachable — callers should
use HeuristicEnrichmentProvider when LLM responses are unavailable.
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


class OllamaLLMClient:
    """Thin wrapper around Ollama's /api/chat endpoint."""

    def __init__(
        self,
        base_url: str | None = None,
        text_model: str | None = None,
        vision_model: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = (base_url or settings.CATALOG_LLM_BASE_URL).rstrip("/")
        self.text_model = text_model or settings.CATALOG_LLM_MODEL
        self.vision_model = vision_model or settings.CATALOG_VLM_MODEL
        self.timeout = timeout

    def is_available(self) -> bool:
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            return response.status_code == 200
        except (httpx.HTTPError, OSError):
            return False

    def complete_text(self, prompt: str, system: str = "") -> str:
        return self._chat(model=self.text_model, prompt=prompt, system=system)

    def complete_vision(self, prompt: str, image_path: str | Path) -> str:
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(f"Image not found: {path}")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return self._chat(
            model=self.vision_model,
            prompt=prompt,
            system="",
            images=[encoded],
        )

    def parse_json_response(self, raw: str) -> dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(line for line in lines if not line.strip().startswith("```"))
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        return json.loads(text)

    def _chat(
        self,
        model: str,
        prompt: str,
        system: str = "",
        images: list[str] | None = None,
    ) -> str:
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        user_message: dict[str, Any] = {"role": "user", "content": prompt}
        if images:
            user_message["images"] = images
        messages.append(user_message)

        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "format": "json",
        }
        response = httpx.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "")
        if not content:
            raise ValueError("Empty LLM response")
        return content
