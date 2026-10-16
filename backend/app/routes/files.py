"""Evidence intake and narration.

Each upload is hashed (SHA-256) as it arrives and FILE_RECEIVED is written to the
custody chain before anything else reads the bytes. Then the type check and
malware scan run; accepted files are stored as evidence/<sha256>, read-only.
"""
import os
import re
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import custody
from app.auth import current_user
from app.config import settings
from app.db import get_db
from app.routes.common import ensure_editable, get_case, mark_stale
from app.schemas import FileRecord, checked
from app.util import clean, clean_all, now_iso
from app.worker import job_queue

router = APIRouter()

ALLOWED = {".jpg": "jpg", ".jpeg": "jpg", ".png": "png", ".webp": "webp", ".heic": "heic", ".pdf": "pdf",
           ".txt": "text", ".csv": "text", ".xlsx": "zip", ".zip": "zip", ".ogg": "ogg", ".opus": "ogg",
           ".mp3": "mp3", ".m4a": "m4a", ".wav": "wav"}
AUDIO_EXT = {".ogg", ".opus", ".mp3", ".m4a", ".wav", ".webm"}
MAX_FILE = 50 * 1024 * 1024
MAX_CASE = 500 * 1024 * 1024
EICAR = b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"
MIME = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp", "pdf": "application/pdf", "wav": "audio/wav",
        "mp3": "audio/mpeg", "ogg": "audio/ogg", "m4a": "audio/mp4", "webm": "audio/webm"}


def sniff(b: bytes) -> str | None:
    if b[:3] == b"\xff\xd8\xff":
        return "jpg"
    if b[:4] == b"\x89PNG":
        return "png"
    if b[:4] == b"%PDF":
        return "pdf"
    if b[:4] in (b"PK\x03\x04", b"PK\x05\x06"):
        return "zip"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "webp"
    if b[:4] == b"RIFF" and b[8:12] == b"WAVE":
        return "wav"
    if b[:4] == b"OggS":
        return "ogg"
    if b[:4] == b"\x1aE\xdf\xa3":
        return "webm"
    if b[:3] == b"ID3" or (len(b) > 1 and b[0] == 0xFF and (b[1] & 0xE0) == 0xE0):
        return "mp3"
    if b[4:8] == b"ftyp":
        return "heic" if re.match(rb"hei|mif1|msf1", b[8:12]) else "m4a"
    if b[:2] == b"MZ":
        return "exe"
    return None


def _check(data: bytes, ext: str, case_total: int) -> tuple[str | None, str | None]:
    """Returns (reason_if_rejected, sniffed_kind)."""
    if ext not in ALLOWED and ext not in AUDIO_EXT:
        return f"File type {ext or '(none)'} is not allowed", None
    if len(data) > MAX_FILE:
        return "Larger than 50 MB", None
    if case_total + len(data) > MAX_CASE:
        return "Case total would exceed 500 MB", None
    kind = sniff(data[:64])
    want = ALLOWED.get(ext, ext.lstrip("."))
    if kind == "exe":
        return "Content is an executable program, not the claimed file type", kind
    if want == "text":
        if b"\x00" in data[:2048] or kind:
            return f"Content does not match the {ext} extension", kind
    elif kind != want and not (want == "ogg" and kind == "webm"):
        return f"Content does not match the {ext} extension" + (f" (looks like {kind.upper()})" if kind else ""), kind
    if EICAR in data[:1048576]:
        return "Malware scan: EICAR test signature found; file quarantined", kind
    return None, kind or "text"


def store(case: dict, name: str, data: bytes, user: dict, *, narration: bool = False) -> dict:
    db = get_db()
    cid = case["id"]
    ext = os.path.splitext(name)[1].lower()
    sha = custody.sha256_hex(data)
    custody.append(cid, "FILE_RECEIVED", f"{name} sha256={sha}", user["name"])
    total = sum(f["size"] for f in db.files.find({"case_id": cid, "status": "accepted"}, {"size": 1}))
    reason, kind = _check(data, ext, total)
    rec = {"id": str(uuid.uuid4()), "case_id": cid, "name": name, "ext": ext, "size": len(data), "sha256": sha,
           "uploaded_at": now_iso(), "uploaded_by": user["name"], "narration": narration}
    if reason:
        rec.update(status="rejected", reason=reason, ev_id=None)
        db.files.insert_one(dict(checked(FileRecord, rec)))
        custody.append(cid, "FILE_REJECTED", f"{name}: {reason} sha256={sha}", user["name"])
        return clean(rec)
    path = os.path.join(settings.evidence_dir, sha)
    os.makedirs(settings.evidence_dir, exist_ok=True)
    if not os.path.exists(path):
        with open(path, "wb") as fh:
            fh.write(data)
        os.chmod(path, 0o444)
    n = db.files.count_documents({"case_id": cid, "status": "accepted"}) + 1
    rec.update(status="accepted", reason=None, ev_id=f"EV-{n:03d}", sniff=kind, kind=None, lang="—",
               screen=None, meta=None, dup=None)
    db.files.insert_one(dict(checked(FileRecord, rec)))
    custody.append(cid, "FILE_ACCEPTED", f"{rec['ev_id']} type check and malware scan passed", user["name"])
    mark_stale(cid)
    return clean(rec)


@router.post("/api/cases/{case_id}/files")
def upload_files(case_id: str, files: list[UploadFile], user: dict = Depends(current_user)):
    case = get_case(case_id)
    if not case["complainant"].get("consent_at"):
        raise HTTPException(409, "Record the complainant's consent first.")
    ensure_editable(case)
    return [store(case, f.filename or "unnamed", f.file.read(), user) for f in files]


@router.get("/api/cases/{case_id}/files")
def list_files(case_id: str, user: dict = Depends(current_user)):
    get_case(case_id)
    return clean_all(get_db().files.find({"case_id": case_id}, {"_id": 0, "phash": 0}).sort("uploaded_at", 1))


@router.delete("/api/cases/{case_id}/files/{file_id}")
def clear_rejected(case_id: str, file_id: str, user: dict = Depends(current_user)):
    res = get_db().files.delete_one({"case_id": case_id, "id": file_id, "status": "rejected"})
    if not res.deleted_count:
        raise HTTPException(409, "Accepted files can't be removed; they are part of the custody record.")
    return {"ok": True}


def _file(case_id: str, ev_id: str) -> dict:
    f = get_db().files.find_one({"case_id": case_id, "ev_id": ev_id, "status": "accepted"}, {"_id": 0, "phash": 0})
    if not f:
        raise HTTPException(404, f"{ev_id} is not in this case.")
    return f


@router.get("/api/cases/{case_id}/files/{ev_id}/view")
def view_file(case_id: str, ev_id: str, line: int = 0, user: dict = Depends(current_user)):
    """Opening an original is recorded in the audit trail."""
    f = _file(case_id, ev_id)
    custody.append(case_id, "ORIGINAL_VIEWED", f"{ev_id}{f' line {line}' if line else ''}", user["name"])
    lines = None
    if f["ext"] in (".txt", ".csv"):
        with open(os.path.join(settings.evidence_dir, f["sha256"]), encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    log = clean_all(get_db().audit_chain.find({"case_id": case_id, "detail": {"$regex": f"(^|\\s){ev_id}(\\s|$)"}},
                                              {"_id": 0}).sort("seq", -1).limit(8))
    return {**f, "lines": lines, "access_log": log}


@router.get("/api/cases/{case_id}/files/{ev_id}/raw")
def raw_file(case_id: str, ev_id: str, download: bool = False, user: dict = Depends(current_user)):
    f = _file(case_id, ev_id)
    if download:
        custody.append(case_id, "ORIGINAL_DOWNLOADED", ev_id, user["name"])
    return FileResponse(os.path.join(settings.evidence_dir, f["sha256"]), media_type=MIME.get(f.get("sniff"), "application/octet-stream"),
                        filename=f["name"] if download else None)


# ----------------------------------------------------------------- narration


@router.get("/api/cases/{case_id}/narration")
def get_narration(case_id: str, user: dict = Depends(current_user)):
    get_case(case_id)
    return clean(get_db().narrations.find_one({"case_id": case_id}, {"_id": 0}))


@router.post("/api/cases/{case_id}/narration")
async def upload_narration(case_id: str, file: UploadFile, source: str = Form(""), user: dict = Depends(current_user)):
    case = get_case(case_id)
    ensure_editable(case)
    db = get_db()
    if db.narrations.find_one({"case_id": case_id}):
        raise HTTPException(409, "Replace the current narration first.")
    name = file.filename or "narration.webm"
    if os.path.splitext(name)[1].lower() not in AUDIO_EXT:
        raise HTTPException(422, "Upload an audio file (WAV, MP3, M4A, OGG/OPUS).")
    rec = store(case, name, await file.read(), user, narration=True)
    if rec["status"] != "accepted":
        raise HTTPException(422, rec["reason"])
    db.narrations.insert_one({"case_id": case_id, "audio_ev": rec["ev_id"], "audio_sha": rec["sha256"],
                              "source": source or f"Uploaded audio: {name}", "lang": "Malayalam", "manual": False,
                              "status": "pending", "segments": [], "created_at": now_iso(), "error": None})
    custody.append(case_id, "NARRATION_AUDIO_RECEIVED", f"{rec['ev_id']} {source or name} sha256={rec['sha256']}", user["name"])
    await job_queue.put(("asr", case_id))
    return get_narration(case_id, user)


class TypedBody(BaseModel):
    text: str


@router.post("/api/cases/{case_id}/narration/typed")
def typed_narration(case_id: str, body: TypedBody, user: dict = Depends(current_user)):
    case = get_case(case_id)
    ensure_editable(case)
    db = get_db()
    if db.narrations.find_one({"case_id": case_id}):
        raise HTTPException(409, "Replace the current narration first.")
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", body.text.strip()) if p.strip()]
    if not parts:
        raise HTTPException(422, "Type the narration first.")
    segs = [{"id": i, "t": 0, "end": 0, "ml": "", "en": p, "ml_machine": "", "en_machine": p, "edited": False}
            for i, p in enumerate(parts, start=1)]
    db.narrations.insert_one({"case_id": case_id, "audio_ev": None, "audio_sha": None, "source": "Typed by officer",
                              "lang": "English", "manual": True, "status": "done", "segments": segs, "created_at": now_iso()})
    custody.append(case_id, "NARRATION_TYPED", f"{len(parts)} sentences", user["name"])
    custody.derived(case_id, "typed_narration", segs, model="none (typed)")
    mark_stale(case_id)
    return get_narration(case_id, user)


class SegmentBody(BaseModel):
    ml: str | None = None
    en: str


@router.patch("/api/cases/{case_id}/narration/segments/{seg_id}")
def edit_segment(case_id: str, seg_id: int, body: SegmentBody, user: dict = Depends(current_user)):
    case = get_case(case_id)
    ensure_editable(case)
    db = get_db()
    n = db.narrations.find_one({"case_id": case_id})
    seg = next((s for s in (n or {}).get("segments", []) if s["id"] == seg_id), None)
    if not seg:
        raise HTTPException(404, "Segment not found")
    ml = seg["ml"] if body.ml is None else body.ml
    what = " and ".join(x for x, ch in (("Malayalam", ml != seg["ml"]), ("English", body.en != seg["en"])) if ch)
    if not what:
        return clean(n)
    db.narrations.update_one({"case_id": case_id, "segments.id": seg_id}, {"$set": {
        "segments.$.ml": ml, "segments.$.en": body.en, "segments.$.edited": True,
        "segments.$.edited_by": user["name"], "segments.$.edited_at": now_iso()}})
    custody.append(case_id, "TRANSCRIPT_EDITED", f"Segment {seg_id} {what} corrected", user["name"])
    mark_stale(case_id)
    return get_narration(case_id, user)


@router.delete("/api/cases/{case_id}/narration")
def replace_narration(case_id: str, user: dict = Depends(current_user)):
    case = get_case(case_id)
    ensure_editable(case)
    db = get_db()
    n = db.narrations.find_one({"case_id": case_id})
    if n and n.get("status") == "transcribing":
        raise HTTPException(409, "Transcription is running. Try again when it finishes.")
    if n:
        db.narrations.delete_one({"case_id": case_id})
        db.cases.update_one({"id": case_id}, {"$set": {"analysis.narration_facts": None}})
        custody.append(case_id, "NARRATION_REPLACED", f"{len(n.get('segments', []))} segments discarded (audio stays in evidence)", user["name"])
        mark_stale(case_id)
    return {"ok": True}


@router.post("/api/cases/{case_id}/narration/retry")
async def retry_narration(case_id: str, user: dict = Depends(current_user)):
    db = get_db()
    n = db.narrations.find_one({"case_id": case_id})
    if not n or n.get("manual") or n.get("status") not in ("failed", "pending"):
        raise HTTPException(409, "Nothing to retry.")
    db.narrations.update_one({"case_id": case_id}, {"$set": {"status": "pending", "error": None}})
    await job_queue.put(("asr", case_id))
    return get_narration(case_id, user)
