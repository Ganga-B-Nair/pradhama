import base64
import os
from datetime import datetime
from io import BytesIO

import qrcode
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader

from app.config import settings
from app.custody import append_entry, verify_chain
from app.db import get_db

router = APIRouter()

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
_jinja_env = Environment(loader=FileSystemLoader(_TEMPLATES_DIR), autoescape=True)


def _qr_base64(data: str) -> str:
    img = qrcode.make(data)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _export_context(case_id: str) -> dict:
    db = get_db()
    case = db.cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    files = list(db.files.find({"case_id": case_id}, {"_id": 0}))
    draft = db.drafts.find_one({"case_id": case_id}, {"_id": 0}, sort=[("version", -1)])
    narrations = list(db.narrations.find({"case_id": case_id}, {"_id": 0}))
    bns_suggestions = list(db.bns_decisions.find({"case_id": case_id, "decision": "accepted"}, {"_id": 0}))
    return {"case": case, "files": files, "draft": draft, "narrations": narrations, "bns_suggestions": bns_suggestions}


@router.post("/api/cases/{case_id}/export")
def export_case(case_id: str):
    db = get_db()
    case = db.cases.find_one({"id": case_id})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if case.get("status") != "approved":
        raise HTTPException(status_code=409, detail="Case must be SHO-approved before export")

    # Append the export action FIRST, then compute the head hash — the QR code
    # must encode the chain's actual head at the moment of export, including
    # this very action, or verification would always show a mismatch.
    append_entry(case_id, "OFFICER_ACTION", {"action": "exported"})
    db.cases.update_one({"id": case_id}, {"$set": {"status": "exported"}})

    verification = verify_chain(case_id)
    head_hash = verification["entry"]["entry_hash"] if verification["entry"] else None

    return {
        "version": 1,
        "head_hash": head_hash,
        "html_url": f"{settings.api_public_base_url}/api/cases/{case_id}/export/html",
        "json_url": f"{settings.api_public_base_url}/api/cases/{case_id}/export/json",
        "cert_url": f"{settings.api_public_base_url}/api/cases/{case_id}/export/certificate",
        "verify_url": f"{settings.public_base_url}/verify/{case_id}/{head_hash}",
    }


@router.get("/api/cases/{case_id}/export/html", response_class=HTMLResponse)
def export_html(case_id: str):
    context = _export_context(case_id)
    verification = verify_chain(case_id)
    head_hash = verification["entry"]["entry_hash"] if verification["entry"] else "unknown"
    verify_url = f"{settings.public_base_url}/verify/{case_id}/{head_hash}"
    template = _jinja_env.get_template("export.html.jinja2")
    html = template.render(**context, head_hash=head_hash, qr_base64=_qr_base64(verify_url))
    return HTMLResponse(html)


@router.get("/api/cases/{case_id}/export/certificate", response_class=HTMLResponse)
def export_certificate(case_id: str):
    context = _export_context(case_id)
    verification = verify_chain(case_id)
    head_hash = verification["entry"]["entry_hash"] if verification["entry"] else "unknown"
    template = _jinja_env.get_template("certificate.html.jinja2")
    html = template.render(
        case=context["case"], files=context["files"], head_hash=head_hash,
        generated_at=datetime.utcnow().isoformat(),
    )
    return HTMLResponse(html)


@router.get("/api/cases/{case_id}/export/json")
def export_json(case_id: str):
    context = _export_context(case_id)
    verification = verify_chain(case_id)
    context["head_hash"] = verification["entry"]["entry_hash"] if verification["entry"] else None
    return JSONResponse(context)


@router.get("/api/verify/{case_ref}/{head_hash}")
def verify_export(case_ref: str, head_hash: str):
    verification = verify_chain(case_ref)
    if verification["result"] != "match":
        return {"result": verification["result"], "entry": None}
    actual_head = verification["entry"]["entry_hash"]
    if actual_head == head_hash:
        return {"result": "match", "entry": verification["entry"]}
    return {"result": "mismatch", "entry": verification["entry"]}
