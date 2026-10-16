from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import get_db

router = APIRouter()


class BnsDecision(BaseModel):
    decision: str  # "accepted" | "rejected"


@router.post("/api/bns/{suggestion_id}/decision")
def decide_bns(suggestion_id: str, body: BnsDecision):
    db = get_db()
    result = db.bns_decisions.update_one(
        {"id": suggestion_id}, {"$set": {"decision": body.decision}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    return {"id": suggestion_id, "decision": body.decision}
