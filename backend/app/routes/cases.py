import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import custody
from app.auth import current_user, require_sho
from app.config import settings
from app.db import get_db, next_seq
from app.routes.common import ensure_editable, get_case, is_locked
from app.schemas import Case, checked
from app.util import clean_all, now_iso

router = APIRouter()

CONSENT_VERSION = "CN-1.0"


class ComplainantBody(BaseModel):
    name: str
    contact: str = ""
    address: str = ""
    language: str = "Malayalam"
    consent: bool = False


def summary(case: dict) -> dict:
    db = get_db()
    cid = case["id"]
    latest_run = db.runs.find_one({"case_id": cid}, {"_id": 0, "id": 1, "state": 1}, sort=[("created_at", -1)])
    narration = db.narrations.find_one({"case_id": cid}, {"_id": 0, "status": 1, "segments": 1})
    return {
        **case,
        "files_count": db.files.count_documents({"case_id": cid, "status": "accepted"}),
        "open_gaps": db.gaps.count_documents({"case_id": cid, "status": "open"}),
        "narration_status": (narration or {}).get("status"),
        "narration_segments": len((narration or {}).get("segments") or []),
        "draft_versions": db.drafts.count_documents({"case_id": cid}),
        "exports_count": db.exports.count_documents({"case_id": cid}),
        "latest_run": latest_run,
    }


@router.get("/api/cases")
def list_cases(user: dict = Depends(current_user)):
    db = get_db()
    cases = clean_all(db.cases.find({}, {"analysis.narration_facts": 0}).sort("updated_at", -1))
    open_counts = {r["_id"]: r["n"] for r in db.gaps.aggregate([{"$match": {"status": "open"}},
                                                                {"$group": {"_id": "$case_id", "n": {"$sum": 1}}}])}
    return [{**c, "open_gaps": open_counts.get(c["id"], 0)} for c in cases]


@router.post("/api/cases")
def create_case(body: ComplainantBody, user: dict = Depends(current_user)):
    if not body.name.strip():
        raise HTTPException(422, "Name is required.")
    if not body.consent:
        raise HTTPException(422, "Record consent before saving a new case.")
    db = get_db()
    ref = f"{settings.station_code}-{now_iso()[:4]}-{next_seq('case_ref'):05d}"
    now = now_iso()
    case = {
        "id": str(uuid.uuid4()), "ref": ref, "status": "draft", "created_by": user["name"], "created_at": now,
        "updated_at": now,
        "complainant": {"name": body.name.strip(), "contact": body.contact.strip(), "address": body.address.strip(),
                        "language": body.language, "consent_at": now, "consent_version": CONSENT_VERSION},
        "analysis": {"running": False, "done": False, "stale": False, "ran_at": None},
        "approval": {"acks": {}, "at": None, "by": None, "version": None},
        "sent_back": None, "fir_no": "",
    }
    db.cases.insert_one(dict(checked(Case, case)))
    custody.append(case["id"], "CASE_CREATED", ref, user["name"])
    custody.append(case["id"], "CONSENT_RECORDED", f"Notice {CONSENT_VERSION} read out in {body.language}", user["name"])
    return summary(get_case(case["id"]))


@router.get("/api/cases/{case_id}")
def read_case(case_id: str, user: dict = Depends(current_user)):
    case = get_case(case_id)
    case.get("analysis", {}).pop("narration_facts", None)
    return summary(case)


@router.put("/api/cases/{case_id}/complainant")
def update_complainant(case_id: str, body: ComplainantBody, user: dict = Depends(current_user)):
    case = get_case(case_id)
    ensure_editable(case)
    if not body.name.strip():
        raise HTTPException(422, "Name is required.")
    vals = {"name": body.name.strip(), "contact": body.contact.strip(), "address": body.address.strip(), "language": body.language}
    changed = [k for k, v in vals.items() if case["complainant"].get(k) != v]
    upd = {f"complainant.{k}": v for k, v in vals.items()}
    db = get_db()
    db.cases.update_one({"id": case_id}, {"$set": upd})
    if changed:
        custody.append(case_id, "COMPLAINANT_UPDATED", ", ".join(changed), user["name"])
    return summary(get_case(case_id))


# ------------------------------------------------------------------ approval


def checklist(case: dict) -> dict:
    db = get_db()
    cid = case["id"]
    bns = list(db.bns_decisions.find({"case_id": cid}, {"_id": 0}))
    pend = sum(1 for b in bns if not b.get("decision"))
    high = list(db.gaps.find({"case_id": cid, "sev": "High", "status": "open"}, {"_id": 0}))
    acks = case.get("approval", {}).get("acks", {})
    acked = sum(1 for g in high if acks.get(g["id"]))
    ref = db.referrals.find_one({"case_id": cid}) or {}
    dv = db.drafts.count_documents({"case_id": cid})
    a = case.get("analysis", {})
    items = [
        ["Consent recorded", bool(case["complainant"].get("consent_at"))],
        ["Analysis complete and up to date", bool(a.get("done") and not a.get("stale") and not a.get("running"))],
        [f"BNS suggestions decided ({len(bns) - pend} of {len(bns)})", pend == 0],
        [f"Open High-severity gaps acknowledged ({acked} of {len(high)})", acked == len(high)],
        ["Forensic referral list confirmed", bool(ref.get("confirmed"))],
        [f"Draft version to approve: v{dv}" if dv else "A draft exists", dv > 0],
    ]
    return {"items": items, "high": high, "ok": all(v for _, v in items), "draft_version": dv}


@router.get("/api/cases/{case_id}/approval")
def get_approval(case_id: str, user: dict = Depends(current_user)):
    return checklist(get_case(case_id))


class AckBody(BaseModel):
    gap_id: str
    value: bool


@router.post("/api/cases/{case_id}/approval/ack")
def ack_gap(case_id: str, body: AckBody, user: dict = Depends(current_user)):
    require_sho(user)
    case = get_case(case_id)
    ensure_editable(case)
    get_db().cases.update_one({"id": case_id}, {"$set": {f"approval.acks.{body.gap_id}": body.value}})
    custody.append(case_id, "GAP_ACKNOWLEDGED" if body.value else "GAP_ACK_WITHDRAWN", body.gap_id, user["name"])
    return checklist(get_case(case_id))


@router.post("/api/cases/{case_id}/approve")
def approve(case_id: str, user: dict = Depends(current_user)):
    require_sho(user)
    case = get_case(case_id)
    ensure_editable(case)
    ck = checklist(case)
    if not ck["ok"]:
        raise HTTPException(409, "Complete the checklist before approving.")
    approval = {**case["approval"], "at": now_iso(), "by": user["name"], "version": ck["draft_version"]}
    get_db().cases.update_one({"id": case_id}, {"$set": {"status": "approved", "approval": approval, "sent_back": None}})
    custody.append(case_id, "CASE_APPROVED", f"Draft v{ck['draft_version']} approved", user["name"])
    return summary(get_case(case_id))


class TextBody(BaseModel):
    text: str


@router.post("/api/cases/{case_id}/send-back")
def send_back(case_id: str, body: TextBody, user: dict = Depends(current_user)):
    require_sho(user)
    case = get_case(case_id)
    ensure_editable(case)
    if not body.text.strip():
        raise HTTPException(422, "A comment is required.")
    get_db().cases.update_one({"id": case_id}, {"$set": {"sent_back": {"by": user["name"], "at": now_iso(), "comment": body.text.strip()}}})
    custody.append(case_id, "SENT_BACK", body.text.strip(), user["name"])
    return summary(get_case(case_id))


@router.post("/api/cases/{case_id}/reopen")
def reopen(case_id: str, body: TextBody, user: dict = Depends(current_user)):
    require_sho(user)
    case = get_case(case_id)
    if not is_locked(case):
        raise HTTPException(409, "The case is not approved.")
    if not body.text.strip():
        raise HTTPException(422, "A reason is required.")
    get_db().cases.update_one({"id": case_id}, {"$set": {"status": "review", "approval": {"acks": {}, "at": None, "by": None, "version": None}}})
    custody.append(case_id, "CASE_REOPENED", body.text.strip(), user["name"])
    return summary(get_case(case_id))


@router.post("/api/cases/{case_id}/fir-number")
def fir_number(case_id: str, body: TextBody, user: dict = Depends(current_user)):
    require_sho(user)
    get_case(case_id)
    if not body.text.strip():
        raise HTTPException(422, "Enter the FIR number.")
    get_db().cases.update_one({"id": case_id}, {"$set": {"fir_no": body.text.strip()}})
    custody.append(case_id, "FIR_NUMBER_RECORDED", f"Official FIR {body.text.strip()}", user["name"])
    return summary(get_case(case_id))


# --------------------------------------------------------------------- audit


@router.get("/api/cases/{case_id}/audit")
def audit(case_id: str, user: dict = Depends(current_user)):
    require_sho(user)
    get_case(case_id)
    return clean_all(get_db().audit_chain.find({"case_id": case_id}, {"_id": 0}).sort("seq", 1))


@router.post("/api/cases/{case_id}/audit/verify")
def audit_verify(case_id: str, user: dict = Depends(current_user)):
    require_sho(user)
    get_case(case_id)
    return custody.verify(case_id)
