"""Thin Ollama client: JSON-schema output, one retry, timeout, keep_alive control.

docs/HACKATHON_PLAN.md §4/§6.3: temperature 0, JSON-schema `format`, and the
LAST call of a job passes keep_alive=0 so the model unloads before the next
job's speech-to-text subprocess needs that memory back.

Every good response is saved to cache/llm_<prompt hash>.json. With
DEMO_CACHE=1 a failed call falls back to that saved output (golden-run cache, §9).
"""
import json
import os

import requests

from app.config import settings
from app.custody import sha256_hex


class LlmError(Exception):
    pass


def _cache_path(key: str) -> str:
    return os.path.join(settings.cache_dir, f"llm_{key}.json")


def generate_json(prompt: str, schema: dict | None = None, *, unload_after: bool = False) -> tuple[dict, str]:
    """Returns (parsed JSON, provenance note). Raises LlmError when the model is
    unavailable and no cached result can stand in."""
    key = sha256_hex(settings.ollama_model + "\n" + prompt)[:32]
    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "format": schema or "json",
        "stream": False,
        "options": {"temperature": 0},
    }
    if unload_after:
        payload["keep_alive"] = 0

    last_error: Exception | None = None
    for _attempt in range(2):
        try:
            resp = requests.post(f"{settings.ollama_host}/api/generate", json=payload,
                                 timeout=settings.ollama_timeout_seconds)
            resp.raise_for_status()
            result = json.loads(resp.json()["response"])
            try:
                os.makedirs(settings.cache_dir, exist_ok=True)
                with open(_cache_path(key), "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False)
            except OSError:
                pass
            return result, settings.ollama_model
        except (requests.RequestException, KeyError, ValueError) as exc:
            last_error = exc

    if settings.demo_cache and os.path.exists(_cache_path(key)):
        with open(_cache_path(key), encoding="utf-8") as f:
            return json.load(f), f"{settings.ollama_model} (cached result)"
    raise LlmError(f"Ollama unavailable ({type(last_error).__name__})")


def unload() -> None:
    """Ask Ollama to drop the model from memory now (keep_alive 0)."""
    try:
        requests.post(f"{settings.ollama_host}/api/generate",
                      json={"model": settings.ollama_model, "keep_alive": 0}, timeout=10)
    except requests.RequestException:
        pass
