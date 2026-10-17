"""Export (SHO only, after approval) and public verification. docs/HACKATHON_PLAN.md §6.6.

The FIR draft is an HTML page the officer prints to PDF from the browser
(Chrome shapes Malayalam correctly; reportlab doesn't). It carries the head
hash of the custody chain at export time and a QR code linking to
<PUBLIC_BASE_URL>/verify/<ref>/<head>. Re-exporting creates a new version.
"""
import base64
import csv
import io
import json
import os
from io import BytesIO

import qrcode
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

from app import custody, storage
from app.auth import current_user, require_sho
from app.config import settings
from app.db import get_db
from app.routes.analysis import referral_csv
from app.routes.common import get_case, is_locked
from app.util import clean_all, fmt_ist, now_iso

router = APIRouter()
_env = Environment(loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), "..", "templates")), autoescape=True)
KINDS = {"pdf": "FIR draft (print / save as PDF, with QR code)", "json": "FIR draft (JSON)",
         "manifest": "Evidence manifest (CSV)", "referrals": "Forensic referral sheet (CSV)",
         "bsa": "BSA s.63 certificate helper (pre-filled hashes)"}
SCREEN_TXT = {"none": "No screening concern", "review": "Recommend forensic review", "not": "Not screened", "na": "Not applicable"}
KIND_LABEL = {"financial_record": "Financial record", "ip_trace": "IP trace report", "conversation": "Conversation", "media": "Media", "call_log": "Call log",
              "audio": "Audio", "other": "Other"}


def _qr(data: str) -> str:
    buf = BytesIO()
    qrcode.make(data, box_size=6, border=2).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def verify_url(ref: str, head: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/verify/{ref}/{head}"


class ExportBody(BaseModel):
    opts: list[str]


@router.post("/api/cases/{case_id}/exports")
def create_export(case_id: str, body: ExportBody, user: dict = Depends(current_user)):
    require_sho(user)
    case = get_case(case_id)
    if not is_locked(case):
        raise HTTPException(409, "Exports are available after the SHO approves the case.")
    opts = [o for o in body.opts if o in KINDS]
    if not opts:
        raise HTTPException(422, "Choose at least one export.")
    db = get_db()
    v = db.exports.count_documents({"case_id": case_id}) + 1
    entry = custody.append(case_id, "EXPORT_CREATED", f"v{v}: {', '.join(opts)}", user["name"])
    doc = {"case_id": case_id, "v": v, "at": entry["at"], "by": user["name"], "head": entry["hash"], "opts": opts,
           "draft_version": case["approval"]["version"]}
    db.exports.insert_one(dict(doc))
    db.cases.update_one({"id": case_id}, {"$set": {"status": "exported"}})
    return list_exports(case_id, user)


@router.get("/api/cases/{case_id}/exports")
def list_exports(case_id: str, user: dict = Depends(current_user)):
    get_case(case_id)
    return {"exports": clean_all(get_db().exports.find({"case_id": case_id}, {"_id": 0}).sort("v", -1)), "kinds": KINDS}


def _context(case: dict, ex: dict) -> dict:
    db = get_db()
    cid = case["id"]
    draft = db.drafts.find_one({"case_id": cid, "v": ex["draft_version"]}, {"_id": 0}) or \
        db.drafts.find_one({"case_id": cid}, {"_id": 0}, sort=[("v", -1)])
    n = db.narrations.find_one({"case_id": cid}) or {}
    return {
        "case": case, "ex": ex, "draft": draft, "station": settings.station_name,
        "files": list(db.files.find({"case_id": cid, "status": "accepted"}, {"_id": 0}).sort("uploaded_at", 1)),
        "bns": list(db.bns_decisions.find({"case_id": cid, "decision": "Accepted"}, {"_id": 0})),
        "ml_segments": [s for s in n.get("segments") or [] if s.get("ml")],
        "verify_url": verify_url(case["ref"], ex["head"]),
        "approved_at": fmt_ist(case["approval"].get("at")), "fmt": fmt_ist,
    }


@router.get("/api/cases/{case_id}/exports/{v}/{kind}")
def get_export(case_id: str, v: int, kind: str, user: dict = Depends(current_user)):
    case = get_case(case_id)
    ex = get_db().exports.find_one({"case_id": case_id, "v": v}, {"_id": 0})
    if not ex or kind not in ex["opts"]:
        raise HTTPException(404, "Export not found")
    custody.append(case_id, "EXPORT_DOWNLOADED", f"v{v} {kind}", user["name"])
    ctx = _context(case, ex)
    base = f"{case['ref']}_export_v{v}"
    if kind == "pdf":
        return HTMLResponse(_env.get_template("fir.html.j2").render(**ctx, qr=_qr(ctx["verify_url"])))
    if kind == "bsa":
        return HTMLResponse(_env.get_template("bsa63.html.j2").render(**ctx, generated_at=fmt_ist(now_iso())))
    if kind == "json":
        d = ctx["draft"] or {}
        payload = {
            "case": case["ref"], "station": settings.station_name, "export_version": v, "head_hash": ex["head"],
            "verify_url": ctx["verify_url"], "approved_by": case["approval"]["by"], "approved_at": case["approval"]["at"],
            "draft_version": d.get("v"), "complainant": case["complainant"], "occurrence": d.get("fields"),
            "narrative": d.get("narrative"), "sentences": d.get("sentences"),
            "malayalam_original": [s["ml"] for s in ctx["ml_segments"]],
            "bns_accepted_advisory": [f"{b['section']} {b['title']}" for b in ctx["bns"]],
            "evidence": [{"id": f["ev_id"], "name": f["name"], "sha256": f["sha256"], "type": KIND_LABEL.get(f.get("kind"), "")} for f in ctx["files"]],
        }
        return Response(json.dumps(payload, indent=2, ensure_ascii=False), media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{base}.json"'})
    if kind == "manifest":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Evidence ID", "File", "Type", "Language", "Uploaded", "SHA-256", "Duplicate group", "Metadata", "Screening"])
        for f in ctx["files"]:
            w.writerow([f["ev_id"], f["name"], KIND_LABEL.get(f.get("kind"), ""), f.get("lang"), f["uploaded_at"], f["sha256"],
                        (f.get("dup") or {}).get("group", ""), (f.get("meta") or {}).get("status", ""),
                        SCREEN_TXT.get((f.get("screen") or {}).get("status"), "")])
        return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{base}_manifest.csv"'})
    if kind == "referrals":
        return Response(referral_csv(case), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{base}_referrals.csv"'})
    raise HTTPException(404, "Unknown export")


@router.get("/api/verify/{ref}/{head}")
def verify(ref: str, head: str):
    """Public: whether an exported record matches. No case content is returned."""
    db = get_db()
    case = db.cases.find_one({"ref": ref})
    head = head.strip().lower()
    if not case:
        return {"result": "not_found", "message": "No case with this reference at this station."}
    res = custody.verify(case["id"], head)
    ex = db.exports.find_one({"case_id": case["id"], "head": head}, {"_id": 0})
    if res.get("ok"):
        files = list(db.files.find({"case_id": case["id"], "status": "accepted"}))
        good = 0
        for f in files:
            try:
                good += custody.sha256_hex(storage.get(f["sha256"])) == f["sha256"]
            except Exception:  # noqa: BLE001 - missing original counts as not matching
                pass
        return {"result": "match", "ref": ref, "export_version": ex["v"] if ex else None, "seq": res["at"]["seq"],
                "at": res["at"]["at"], "files_checked": len(files), "files_ok": good}
    if res.get("not_found"):
        return {"result": "not_found", "message": "This head hash is not in the case's audit chain. The document may have been altered or was not produced by TRACE."}
    bad = res["bad"]
    return {"result": "mismatch", "seq": bad["seq"], "at": bad["at"], "action": bad["action"]}
