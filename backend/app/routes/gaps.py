from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agents import gaps as gaps_agent
from app.db import get_db

router = APIRouter()


class GapPatch(BaseModel):
    answer: str | None = None
    dismiss_reason: str | None = None


@router.patch("/api/gaps/{gap_id}")
def patch_gap(gap_id: str, body: GapPatch):
    db = get_db()
    gap = db.gaps.find_one({"id": gap_id})
    if not gap:
        raise HTTPException(status_code=404, detail="Gap not found")

    if body.answer is not None:
        update = {"status": "answered", "answer": body.answer}
    elif body.dismiss_reason is not None:
        update = {"status": "dismissed", "dismiss_reason": body.dismiss_reason}
    else:
        raise HTTPException(status_code=400, detail="answer or dismiss_reason required")

    db.gaps.update_one({"id": gap_id}, {"$set": update})
    # Gap Hunter re-run only (rebuild Neo4j subgraph, re-evaluate the 6 rules) —
    # not a full pipeline re-run. §6.4 "Re-run after the officer answers".
    gaps_agent.run(gap["case_id"])
    refreshed = db.gaps.find_one({"id": gap_id}, {"_id": 0}) or {**gap, **update, "id": gap_id}
    return refreshed
