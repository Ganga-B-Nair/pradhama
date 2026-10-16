"""SHA-256 custody chain, append-only, one chain per case (audit_chain collection).

Two layers (docs/HACKATHON_PLAN.md §5, Trace-QnA.docx §2):
- Raw layer: each original file is hashed as it arrives and stored as
  evidence/<sha256>, read-only. FILE_RECEIVED is written before anything reads it.
- Derived layer: transcripts, timeline, gaps and draft versions are recorded as
  ARTIFACT_DERIVED entries carrying their own SHA-256, model, prompt and code
  version. Officer edits append; nothing is overwritten.

entry_hash = SHA256(prev_hash || canonical_json(entry)); the first entry's
prev_hash is a per-case genesis value. Verification recomputes from the start.
"""
import hashlib
import json
import threading

from app.config import settings
from app.db import get_db
from app.util import now_iso

_lock = threading.Lock()
MACHINE = "TRACE (machine)"


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _entry_canon(entry: dict) -> str:
    return canonical({k: entry[k] for k in ("action", "at", "detail", "seq", "user")})


def genesis(case_id: str) -> str:
    return sha256_hex(f"TRACE|{settings.station_code}|{case_id}")


def append(case_id: str, action: str, detail: str = "", user: str = "system") -> dict:
    db = get_db()
    with _lock:
        last = db.audit_chain.find_one({"case_id": case_id}, sort=[("seq", -1)])
        prev = last["hash"] if last else genesis(case_id)
        entry = {
            "case_id": case_id,
            "seq": (last["seq"] + 1) if last else 1,
            "at": now_iso(),
            "user": user,
            "action": action,
            "detail": detail,
            "prev": prev,
        }
        entry["hash"] = sha256_hex(prev + _entry_canon(entry))
        db.audit_chain.insert_one(dict(entry))
    db.cases.update_one({"id": case_id}, {"$set": {"updated_at": entry["at"]}})
    return entry


def derived(case_id: str, artifact: str, content, *, model: str = "none", prompt: str = "none") -> dict:
    """Record a derived artifact (transcript, timeline, gaps, draft) with its own hash."""
    digest = sha256_hex(canonical(content))
    detail = f"{artifact} sha256={digest} model={model} prompt={prompt} code={settings.code_version}"
    return append(case_id, "ARTIFACT_DERIVED", detail, MACHINE)


def verify(case_id: str, stop_at: str | None = None) -> dict:
    """Recompute the chain. With stop_at, succeed once that hash is reached intact."""
    prev = genesis(case_id)
    count = 0
    for entry in get_db().audit_chain.find({"case_id": case_id}, {"_id": 0}).sort("seq", 1):
        h = sha256_hex(prev + _entry_canon(entry))
        if h != entry["hash"] or entry["prev"] != prev:
            return {"ok": False, "bad": entry}
        count += 1
        if stop_at and h == stop_at:
            return {"ok": True, "at": entry, "count": count}
        prev = h
    if stop_at:
        return {"ok": False, "not_found": True}
    return {"ok": True, "count": count}
