from fastapi import APIRouter, HTTPException

from app.config import settings
from app.custody import append_entry, verify_chain
from app.db import get_db

router = APIRouter()


@router.post("/api/cases/{case_id}/export")
def export_case(case_id: str):
    db = get_db()
    case = db.cases.find_one({"id": case_id})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.get("status") != "approved":
        raise HTTPException(status_code=409, detail="Case must be SHO-approved before export")

    # TODO(G): render the Jinja2 HTML template (FIR draft, Malayalam annex,
    # manifest, accepted BNS sections, §63 certificate draft) and the QR code
    # pointing at PUBLIC_BASE_URL + /verify/<case_ref>/<head_hash>.
    # See docs/HACKATHON_PLAN.md §6.6.
    verification = verify_chain(case_id)
    head_hash = verification["entry"]["entry_hash"] if verification["entry"] else None

    append_entry(case_id, "OFFICER_ACTION", {"action": "exported"})
    db.cases.update_one({"id": case_id}, {"$set": {"status": "exported"}})

    return {
        "version": 1,
        "head_hash": head_hash,
        "html_url": f"{settings.public_base_url}/export/{case_id}",
        "json_url": f"{settings.public_base_url}/export/{case_id}.json",
        "cert_url": f"{settings.public_base_url}/export/{case_id}/certificate",
    }


@router.get("/api/verify/{case_ref}/{head_hash}")
def verify_export(case_ref: str, head_hash: str):
    verification = verify_chain(case_ref)
    if verification["result"] != "match":
        return {"result": verification["result"], "entry": None}
    actual_head = verification["entry"]["entry_hash"]
    if actual_head == head_hash:
        return {"result": "match", "entry": verification["entry"]}
    return {"result": "mismatch", "entry": verification["entry"]}
