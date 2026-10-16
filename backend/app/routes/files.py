import os
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, UploadFile

from app.config import settings
from app.custody import append_entry, hash_file_bytes
from app.db import get_db

router = APIRouter()

ALLOWED_EXTENSIONS = {
    ".txt", ".csv", ".jpg", ".jpeg", ".png", ".wav", ".mp3", ".m4a", ".pdf",
}
MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB, matches PRD F1


def _save_and_hash(case_id: str, upload: UploadFile) -> dict:
    data = upload.file.read()
    ext = os.path.splitext(upload.filename or "")[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        return {
            "id": str(uuid.uuid4()), "name": upload.filename, "sha256": None,
            "status": "rejected", "reason": f"file type {ext} not allowed",
        }
    if len(data) > MAX_FILE_BYTES:
        return {
            "id": str(uuid.uuid4()), "name": upload.filename, "sha256": None,
            "status": "rejected", "reason": "file exceeds 50MB limit",
        }

    sha256 = hash_file_bytes(data)
    os.makedirs(settings.evidence_dir, exist_ok=True)
    dest_path = os.path.join(settings.evidence_dir, sha256)
    if not os.path.exists(dest_path):
        with open(dest_path, "wb") as f:
            f.write(data)
        os.chmod(dest_path, 0o444)  # read-only, matches custody design

    file_id = str(uuid.uuid4())
    record = {
        "id": file_id,
        "case_id": case_id,
        "name": upload.filename,
        "sha256": sha256,
        "mime_type": upload.content_type,
        "size_bytes": len(data),
        "status": "accepted",
        "reason": None,
        "kind": None,  # filled in by the Content Triage agent
        "is_duplicate_of": None,
        "screening": None,  # filled in by the Content Triage agent
        "metadata": None,  # filled in by the Metadata agent
        "uploaded_at": datetime.utcnow(),
    }
    db = get_db()
    db.files.insert_one(dict(record))
    append_entry(case_id, "FILE_RECEIVED", {"file_id": file_id, "name": upload.filename, "sha256": sha256})
    return record


@router.post("/api/cases/{case_id}/files")
def upload_files(case_id: str, files: list[UploadFile]):
    db = get_db()
    if not db.cases.find_one({"id": case_id}):
        raise HTTPException(status_code=404, detail="Case not found")
    results = [_save_and_hash(case_id, f) for f in files]
    return results


@router.post("/api/cases/{case_id}/narration")
def upload_narration(case_id: str, file: UploadFile):
    db = get_db()
    if not db.cases.find_one({"id": case_id}):
        raise HTTPException(status_code=404, detail="Case not found")
    return _save_and_hash(case_id, file)
