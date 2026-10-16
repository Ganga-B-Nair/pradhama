from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.custody import append_entry
from app.db import get_db

router = APIRouter()


class SentenceIn(BaseModel):
    sentence: str
    event_ids: list[str] = []
    supported: bool


class DraftUpdate(BaseModel):
    sentences: list[SentenceIn]


@router.put("/api/cases/{case_id}/draft")
def update_draft(case_id: str, body: DraftUpdate):
    db = get_db()
    if not db.cases.find_one({"id": case_id}):
        raise HTTPException(status_code=404, detail="Case not found")

    last = db.drafts.find_one({"case_id": case_id}, sort=[("version", -1)])
    next_version = (last["version"] + 1) if last else 1

    draft = {
        "id": f"{case_id}-v{next_version}",
        "case_id": case_id,
        "version": next_version,
        "sentences": [s.model_dump() for s in body.sentences],
    }
    db.drafts.insert_one(dict(draft))
    append_entry(case_id, "ARTIFACT_DERIVED", {"artifact": "draft", "version": next_version})
    draft.pop("_id", None)
    return draft


@router.post("/api/cases/{case_id}/approve")
def approve_case(case_id: str):
    db = get_db()
    case = db.cases.find_one({"id": case_id})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    # TODO(G): enforce SHO-only via the role cookie set in routes/auth.py once
    # the frontend sends it; for the hackathon demo this is checked in the UI
    # too, but the backend should not trust the UI alone.
    db.cases.update_one({"id": case_id}, {"$set": {"status": "approved"}})
    append_entry(case_id, "OFFICER_ACTION", {"action": "sho_approved"})
    return {"status": "approved"}
