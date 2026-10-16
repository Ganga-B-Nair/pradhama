"""SHA-256 custody chain, append-only, stored in the audit_chain Mongo collection.

Two layers (docs/HACKATHON_PLAN.md §5, Trace-QnA.docx §2):
- Raw layer: original files, hashed on arrival, immutable.
- Derived layer: transcripts/translations/metadata/draft versions, each its own
  versioned entry — an officer edit appends a new entry, nothing is overwritten.

entry_hash = SHA256(prev_hash || canonical_json(payload))
"""
import hashlib
import json
import uuid
from datetime import datetime

from app.db import get_db


def _canonical_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _last_hash(case_id: str) -> str | None:
    db = get_db()
    last = db.audit_chain.find_one({"case_id": case_id}, sort=[("_id", -1)])
    return last["entry_hash"] if last else None


def append_entry(case_id: str, entry_type: str, payload: dict) -> dict:
    db = get_db()
    prev_hash = _last_hash(case_id)
    entry_hash = hashlib.sha256(
        ((prev_hash or "") + _canonical_json(payload)).encode("utf-8")
    ).hexdigest()
    entry = {
        "id": str(uuid.uuid4()),
        "case_id": case_id,
        "entry_type": entry_type,
        "payload": payload,
        "prev_hash": prev_hash,
        "entry_hash": entry_hash,
        "created_at": datetime.utcnow(),
    }
    db.audit_chain.insert_one(entry)
    return entry


def hash_file_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_chain(case_id: str) -> dict:
    """Recompute the chain from the start; returns the first mismatched entry, if any."""
    db = get_db()
    entries = list(db.audit_chain.find({"case_id": case_id}).sort("_id", 1))
    prev_hash = None
    for entry in entries:
        expected = hashlib.sha256(
            ((prev_hash or "") + _canonical_json(entry["payload"])).encode("utf-8")
        ).hexdigest()
        if expected != entry["entry_hash"]:
            return {"result": "mismatch", "entry": entry}
        prev_hash = entry["entry_hash"]
    if not entries:
        return {"result": "not_found", "entry": None}
    return {"result": "match", "entry": entries[-1]}
