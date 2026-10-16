"""Narration: runs the speech-to-text subprocess and stores paired segments.

The Malayalam original (transcribe pass) and the English (translate pass) are
kept side by side. The English segmentation is the base; each English segment
carries the Malayalam text whose time span overlaps it. Officer corrections
keep the machine version (`ml_machine`, `en_machine`).

Every good transcript is saved to cache/asr_<audio sha>.json; with DEMO_CACHE=1
a failed or timed-out run falls back to it (golden-run cache, §9).
"""
import json
import os
import subprocess
import sys

from app import custody, storage
from app.config import settings
from app.db import get_db
from app.util import now_iso


def _cache_path(sha: str) -> str:
    return os.path.join(settings.cache_dir, f"asr_{sha}.json")


def _run_subprocess(audio_path: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "app.agents.asr", audio_path, settings.asr_model_size, settings.asr_device],
        capture_output=True, text=True, encoding="utf-8", timeout=settings.asr_timeout_seconds,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    )
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-1:] or ["unknown error"]
        raise RuntimeError(f"Speech-to-text failed: {tail[0][:300]}")
    return json.loads(proc.stdout)


def pair_segments(result: dict) -> list[dict]:
    ml, en = result.get("malayalam", []), result.get("english", [])
    base = en or ml
    out = []
    for i, seg in enumerate(base, start=1):
        overl = [m["text"] for m in ml if min(m["end"], seg["end"]) - max(m["start"], seg["start"]) > 0.2]
        if not overl and ml:
            mid = (seg["start"] + seg["end"]) / 2
            overl = [min(ml, key=lambda m: abs((m["start"] + m["end"]) / 2 - mid))["text"]]
        ml_text = " ".join(dict.fromkeys(overl)) if en else seg["text"]
        en_text = seg["text"] if en else ""
        out.append({"id": i, "t": int(seg["start"]), "end": int(round(seg["end"])), "ml": ml_text, "en": en_text,
                    "ml_machine": ml_text, "en_machine": en_text, "edited": False})
    return out


def transcribe(case_id: str) -> str:
    """Transcribe the case's narration audio if it hasn't been done yet."""
    db = get_db()
    n = db.narrations.find_one({"case_id": case_id})
    if not n or n.get("manual"):
        return "Typed narration; no audio to transcribe" if n else "No narration audio"
    if n.get("status") == "done":
        return f"{len(n['segments'])} segments (transcribed earlier)"
    db.narrations.update_one({"case_id": case_id}, {"$set": {"status": "transcribing", "error": None}})
    cached = False
    try:
        audio = db.files.find_one({"case_id": case_id, "ev_id": n["audio_ev"]}) or {}
        with storage.temp_copy(n["audio_sha"], audio.get("ext", "")) as audio_path:
            result = _run_subprocess(audio_path)
        os.makedirs(settings.cache_dir, exist_ok=True)
        with open(_cache_path(n["audio_sha"]), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
    except (RuntimeError, subprocess.TimeoutExpired, ValueError, OSError) as exc:
        if settings.demo_cache and os.path.exists(_cache_path(n["audio_sha"])):
            with open(_cache_path(n["audio_sha"]), encoding="utf-8") as f:
                result = json.load(f)
            cached = True
        else:
            msg = "Speech-to-text timed out" if isinstance(exc, subprocess.TimeoutExpired) else str(exc)
            db.narrations.update_one({"case_id": case_id}, {"$set": {"status": "failed", "error": msg}})
            custody.append(case_id, "NARRATION_TRANSCRIPTION_FAILED", msg, custody.MACHINE)
            raise RuntimeError(msg) from exc

    segments = pair_segments(result)
    model = result.get("model", "faster-whisper") + (" (cached result)" if cached else "")
    db.narrations.update_one({"case_id": case_id}, {"$set": {
        "status": "done", "segments": segments, "lang": "Malayalam", "model": model, "transcribed_at": now_iso()}})
    custody.derived(case_id, "transcript+translation", segments, model=model, prompt="whisper-transcribe+translate")
    custody.append(case_id, "NARRATION_TRANSCRIBED", f"{len(segments)} segments, Malayalam with English translation",
                   custody.MACHINE)
    return f"{len(segments)} segments transcribed and translated" + (" (cached result)" if cached else "")
