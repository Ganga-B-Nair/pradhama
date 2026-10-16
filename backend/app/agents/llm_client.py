"""Thin Ollama client: JSON-schema output, one retry, timeout, keep_alive control.

docs/HACKATHON_PLAN.md §4/§6.3: temperature 0, format=json, and the LAST call of
a job should pass keep_alive="0" so the model unloads before the next job's
speech-to-text subprocess needs that memory back.
"""
import json

import requests

from app.config import settings

OLLAMA_TIMEOUT_SECONDS = 60


class LlmError(Exception):
    pass


def generate_json(prompt: str, *, unload_after: bool = False, model: str | None = None) -> dict:
    """Calls Ollama's /api/generate with format=json and temperature 0.
    Retries once on any failure (timeout, connection error, invalid JSON).
    Raises LlmError if both attempts fail — callers decide the fallback.
    """
    payload = {
        "model": model or settings.ollama_model,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {"temperature": 0},
    }
    if unload_after:
        payload["keep_alive"] = "0"

    last_error: Exception | None = None
    for _attempt in range(2):
        try:
            resp = requests.post(
                f"{settings.ollama_host}/api/generate",
                json=payload,
                timeout=OLLAMA_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            raw_response = resp.json()["response"]
            return json.loads(raw_response)
        except (requests.RequestException, KeyError, json.JSONDecodeError) as exc:
            last_error = exc
    raise LlmError(f"Ollama call failed after retry: {last_error}")
