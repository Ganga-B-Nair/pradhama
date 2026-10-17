"""Jurisdiction Lookup and the station outbox.

PIN codes come from IP trace reports in the evidence (or are typed by the
officer). The lookup recommends stations and shows its reasoning; people
decide everything after that:

1. The officer chooses the recipient stations, edits the message and confirms
   it ("Awaiting SHO approval").
2. The SHO approves it ("Approved for dispatch") or returns it with a reason.
   Approval checks the notice hash, so the approved notice is exactly the one
   the officer confirmed.
3. Whoever delivers it records the channel ("Dispatched"). TRACE does not
   deliver notices itself; delivery goes through the station's usual channel,
   using the printable copy per station.

Every lookup and every step of a notice is written to the custody chain.
"""
import os
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

from app import custody, jurisdiction
from app.agents import parsers
from app.auth import current_user, require_sho
from app.config import settings
from app.db import get_db
from app.routes.common import get_case
from app.util import IST, clean_all, fmt_ist, now_iso, parse_iso

router = APIRouter()
_env = Environment(loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "..", "templates")), autoescape=True)
NOTICE_KINDS = ["Suspect information", "Lookout notice", "Request for assistance"]
CHANNELS = ["Official email", "CCTNS message", "Phone (followed up in writing)", "Hand delivery", "Other"]
AWAITING, APPROVED, RETURNED, DISPATCHED = "Awaiting SHO approval", "Approved for dispatch", "Returned by SHO", "Dispatched"


def _traces(case: dict) -> dict[str, list[dict]]:
    year = parse_iso(case["created_at"]).astimezone(IST).year
    by_pin: dict[str, list[dict]] = {}
    # Files not analysed yet are read too, so PINs show up as soon as a report is uploaded.
    q = {"case_id": case["id"], "status": "accepted", "kind": {"$in": ["ip_trace", None]}}
    for f in get_db().files.find(q).sort("uploaded_at", 1):
        for row in parsers.parse_ip_traces(f, parsers.text_lines(f) or [], year):
            by_pin.setdefault(row["pin"], []).append({**row, "file_name": f["name"]})
    return by_pin


def _state(case: dict) -> dict:
    j = case.get("jurisdiction") or {}
    traces = _traces(case)
    pins = list(traces) + [p for p in j.get("manual_pins", []) if p not in traces]
    results = j.get("results", {})
    return {
        "pins": [{"pin": p, "traces": traces.get(p, []), "manual": p not in traces, "lookup": results.get(p)} for p in pins],
        "online": settings.jurisdiction_online, "google_configured": bool(settings.google_maps_api_key),
        "notice_kinds": NOTICE_KINDS, "channels": CHANNELS, "station": settings.station_name,
    }


@router.get("/api/cases/{case_id}/jurisdiction")
def get_jurisdiction(case_id: str, user: dict = Depends(current_user)):
    return _state(get_case(case_id))


class PinBody(BaseModel):
    pin: str


@router.post("/api/cases/{case_id}/jurisdiction/pins")
def add_pin(case_id: str, body: PinBody, user: dict = Depends(current_user)):
    get_case(case_id)
    pin = body.pin.strip()
    if not re.fullmatch(r"[1-8]\d{5}", pin):
        raise HTTPException(422, "Enter a 6-digit PIN code.")
    get_db().cases.update_one({"id": case_id}, {"$addToSet": {"jurisdiction.manual_pins": pin}})
    custody.append(case_id, "JURISDICTION_PIN_ADDED", pin, user["name"])
    return _state(get_case(case_id))


class LookupBody(BaseModel):
    pins: list[str]
    refresh: bool = False


@router.post("/api/cases/{case_id}/jurisdiction/lookup")
def run_lookup(case_id: str, body: LookupBody, user: dict = Depends(current_user)):
    case = get_case(case_id)
    pins = [p for p in dict.fromkeys(body.pins) if re.fullmatch(r"[1-8]\d{5}", p)]
    if not pins:
        raise HTTPException(422, "Choose at least one PIN code.")
    results = jurisdiction.lookup_many(pins, body.refresh)
    db = get_db()
    for pin, res in results.items():
        db.cases.update_one({"id": case_id}, {"$set": {f"jurisdiction.results.{pin}": res}})
        recs = ", ".join(s["name"] for s in res["stations"] if s["recommended"]) or "none"
        custody.append(case_id, "JURISDICTION_LOOKUP",
                       f"PIN {pin}: {res['verdict']}; recommended {recs}" + ("; saved result" if res.get("cached") else ""), user["name"])
    return _state(get_case(case_id))


# -------------------------------------------------------------------- outbox


class Recipient(BaseModel):
    name: str
    link: str | None = None
    pin: str | None = None
    source: str | None = None
    recommended: bool = False


class NoticeBody(BaseModel):
    kind: str
    subject: str
    body: str
    recipients: list[Recipient]
    confirmed: bool = False


def _content(doc: dict) -> dict:
    return {k: doc[k] for k in ("kind", "subject", "body", "recipients")}


def _notice(case_id: str, nid: str) -> dict:
    doc = get_db().notices.find_one({"case_id": case_id, "id": nid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Notice not found")
    return doc


@router.post("/api/cases/{case_id}/notices")
def create_notice(case_id: str, body: NoticeBody, user: dict = Depends(current_user)):
    case = get_case(case_id)
    if body.kind not in NOTICE_KINDS:
        raise HTTPException(422, "Choose the type of notice.")
    if not body.recipients:
        raise HTTPException(422, "Choose at least one police station.")
    if not body.subject.strip() or not body.body.strip():
        raise HTTPException(422, "The subject and message can't be empty.")
    if not body.confirmed:
        raise HTTPException(422, "Confirm that you have checked the recipients and the message.")
    db = get_db()
    n = db.notices.count_documents({"case_id": case_id}) + 1
    recipients = [r.model_dump() for r in body.recipients]
    content = {"kind": body.kind, "subject": body.subject.strip(), "body": body.body.strip(), "recipients": recipients}
    digest = custody.sha256_hex(custody.canonical(content))
    at = now_iso()
    doc = {"id": f"N-{n:03d}", "case_id": case_id, "case_ref": case["ref"], **content, "sha256": digest,
           "status": AWAITING, "created_by": user["name"], "created_role": user["role"], "created_at": at,
           "off_recommendation": [r["name"] for r in recipients if not r["recommended"]],
           "history": [{"at": at, "by": user["name"], "role": user["role"], "step": "Prepared and confirmed", "comment": ""}]}
    db.notices.insert_one(dict(doc))
    off = f"; chosen outside TRACE's recommendation: {', '.join(doc['off_recommendation'])}" if doc["off_recommendation"] else ""
    custody.append(case_id, "NOTICE_PREPARED", f"{doc['id']} {body.kind} to {', '.join(r['name'] for r in recipients)} "
                                               f"(confirmed by {user['name']}{off}) sha256={digest}", user["name"])
    return list_notices(case_id, user)


class DecisionBody(BaseModel):
    decision: str  # "approve" | "return"
    comment: str = ""


@router.post("/api/cases/{case_id}/notices/{nid}/decision")
def decide_notice(case_id: str, nid: str, body: DecisionBody, user: dict = Depends(current_user)):
    require_sho(user)
    doc = _notice(case_id, nid)
    if doc["status"] != AWAITING:
        raise HTTPException(409, f"This notice is already {doc['status'].lower()}.")
    if custody.sha256_hex(custody.canonical(_content(doc))) != doc["sha256"]:
        raise HTTPException(409, "The notice no longer matches its recorded hash, so it can't be approved.")
    comment = body.comment.strip()
    if body.decision == "approve":
        status, step, action = APPROVED, "Approved for dispatch", "NOTICE_APPROVED"
    elif body.decision == "return":
        if not comment:
            raise HTTPException(422, "Give a reason for returning the notice.")
        status, step, action = RETURNED, "Returned", "NOTICE_RETURNED"
    else:
        raise HTTPException(422, "Decision must be approve or return.")
    entry = {"at": now_iso(), "by": user["name"], "role": user["role"], "step": step, "comment": comment}
    get_db().notices.update_one({"case_id": case_id, "id": nid}, {"$set": {"status": status}, "$push": {"history": entry}})
    custody.append(case_id, action, f"{nid} sha256={doc['sha256']}" + (f": {comment}" if comment else ""), user["name"])
    return list_notices(case_id, user)


class DispatchBody(BaseModel):
    channel: str
    note: str = ""


@router.post("/api/cases/{case_id}/notices/{nid}/dispatch")
def record_dispatch(case_id: str, nid: str, body: DispatchBody, user: dict = Depends(current_user)):
    doc = _notice(case_id, nid)
    if doc["status"] != APPROVED:
        raise HTTPException(409, "Only a notice approved by the SHO can be dispatched.")
    if body.channel not in CHANNELS:
        raise HTTPException(422, "Choose how the notice was delivered.")
    note = body.note.strip()
    entry = {"at": now_iso(), "by": user["name"], "role": user["role"], "step": f"Dispatched by {body.channel}", "comment": note}
    get_db().notices.update_one({"case_id": case_id, "id": nid},
                                {"$set": {"status": DISPATCHED, "channel": body.channel}, "$push": {"history": entry}})
    custody.append(case_id, "NOTICE_DISPATCHED", f"{nid} by {body.channel}" + (f": {note}" if note else ""), user["name"])
    return list_notices(case_id, user)


@router.get("/api/cases/{case_id}/notices")
def list_notices(case_id: str, user: dict = Depends(current_user)):
    get_case(case_id)
    return clean_all(get_db().notices.find({"case_id": case_id}, {"_id": 0}).sort("created_at", -1))


@router.get("/api/cases/{case_id}/notices/{nid}/print", response_class=HTMLResponse)
def print_notice(case_id: str, nid: str, user: dict = Depends(current_user)):
    case = get_case(case_id)
    doc = _notice(case_id, nid)
    custody.append(case_id, "NOTICE_PRINTED", f"{nid} ({doc['status']})", user["name"])
    ok = next((h for h in doc.get("history", []) if h["step"] == "Approved for dispatch"), None)
    return HTMLResponse(_env.get_template("notice.html.j2").render(
        n=doc, case=case, station=settings.station_name, sent_at=fmt_ist(doc["created_at"]),
        approved={**ok, "at": fmt_ist(ok["at"])} if ok else None, draft=doc["status"] in (AWAITING, RETURNED)))
