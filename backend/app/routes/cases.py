import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.custody import append_entry, verify_chain
from app.db import get_db

router = APIRouter()


class CreateCaseRequest(BaseModel):
    complainant_name: str
    complainant_contact: str | None = None
    consent_given: bool
    location: str | None = None


@router.get("/api/cases")
def list_cases():
    db = get_db()
    cases = list(db.cases.find({}, {"_id": 0}).sort("created_at", -1))
    return cases


@router.post("/api/cases")
def create_case(body: CreateCaseRequest):
    db = get_db()
    case = {
        "id": str(uuid.uuid4()),
        "complainant_name": body.complainant_name,
        "complainant_contact": body.complainant_contact,
        "consent_given": body.consent_given,
        "location": body.location,
        "created_at": datetime.utcnow(),
        "status": "intake",
    }
    db.cases.insert_one(case)
    append_entry(case["id"], "OFFICER_ACTION", {"action": "case_created", "consent_given": body.consent_given})
    case.pop("_id", None)
    return case


@router.get("/api/cases/{case_id}")
def get_case(case_id: str):
    db = get_db()
    case = db.cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


@router.get("/api/cases/{case_id}/audit")
def get_audit(case_id: str):
    db = get_db()
    entries = list(db.audit_chain.find({"case_id": case_id}, {"_id": 0}).sort("created_at", 1))
    verification = verify_chain(case_id)
    verification["entry"] = None if not verification["entry"] else {
        k: v for k, v in verification["entry"].items() if k != "_id"
    }
    return {"entries": entries, "verification": verification}
