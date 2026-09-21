"""Ollama client.

Talks to the local Ollama HTTP API with the standard library so the project's only
third-party dependency stays Pillow. No network egress beyond localhost.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5vl:7b"


class BackendError(RuntimeError):
    """Ollama is unreachable, the model is missing, or generation failed."""


@dataclass
class Ollama:
    model: str = DEFAULT_MODEL
    host: str = DEFAULT_HOST
    timeout: int = 600
    # Low but non-zero: deterministic enough to make eval runs comparable,
    # without the degenerate repetition that temperature 0 can induce.
    temperature: float = 0.1

    def _post(self, path: str, payload: dict, timeout: int | None = None) -> dict:
        req = urllib.request.Request(
            f"{self.host}{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.URLError as e:
            raise BackendError(
                f"cannot reach Ollama at {self.host} ({e.reason}). "
                "Is it running? Start it with: ollama serve"
            ) from e

    def available_models(self) -> list[str]:
        req = urllib.request.Request(f"{self.host}/api/tags")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                tags = json.loads(resp.read()).get("models", [])
        except urllib.error.URLError as e:
            raise BackendError(
                f"cannot reach Ollama at {self.host} ({e.reason}). "
                "Is it running? Start it with: ollama serve"
            ) from e
        return [m["name"] for m in tags]

    def check(self) -> None:
        """Fail early and legibly rather than mid-batch."""
        models = self.available_models()
        # Ollama reports "name:tag"; accept a bare name as matching any tag.
        if self.model in models:
            return
        if any(m.split(":", 1)[0] == self.model for m in models):
            return
        listed = ", ".join(models) if models else "none installed"
        raise BackendError(
            f"model {self.model!r} not found in Ollama (have: {listed}). "
            f"Pull it with: ollama pull {self.model}"
        )

    def transcribe(self, image_b64: str, system: str, user: str) -> str:
        """One page in, LaTeX body out."""
        result = self._post(
            "/api/generate",
            {
                "model": self.model,
                "system": system,
                "prompt": user,
                "images": [image_b64],
                "stream": False,
                "options": {"temperature": self.temperature},
            },
        )
        if "error" in result:
            raise BackendError(f"Ollama: {result['error']}")
        text = result.get("response", "").strip()
        if not text:
            raise BackendError("model returned nothing")
        return _strip_fences(text)


def _strip_fences(text: str) -> str:
    """Models wrap output in markdown fences despite being told not to."""
    lines = text.splitlines()
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
        # Drop the closing fence wherever it landed.
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].lstrip().startswith("```"):
                lines = lines[:i]
                break
    return "\n".join(lines).strip()
