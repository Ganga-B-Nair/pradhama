"""Analysis runs (202 + polling) and the review screens' results:
manifest, timeline, gap questions, draft FIR, BNS sections, forensic referrals."""
import csv
import io
import re
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app import custody
from app.agents import bns_adapter, gaps as gaps_agent, metadata, referrals as referrals_agent, timeline, triage
from app.agents.gaps import RULES, lint
from app.agents.triage import LIMITATION_TEXT
from app.auth import current_user, require_sho
from app.db import get_db
from app.routes.common import ensure_editable, get_case
from app.schemas import DraftVersion, Run, checked
from app.util import clean, clean_all, now_iso
from app.worker import ENGINE, STEPS, job_queue

router = APIRouter()


class RunBody(BaseModel):
    start_at: str | None = None


@router.post("/api/cases/{case_id}/runs", status_code=202)
async def start_run(case_id: str, body: RunBody | None = None, user: dict = Depends(current_user)):
    case = get_case(case_id)
    ensure_editable(case)
    db = get_db()
    if not db.files.count_documents({"case_id": case_id, "status": "accepted"}) and not db.narrations.find_one({"case_id": case_id}):
        raise HTTPException(409, "Add evidence or narration first.")
    names = [n for n, _ in STEPS]
    start_at = (body.start_at if body else None) or names[0]
    if start_at not in names:
        raise HTTPException(422, "Unknown step")
    prev = db.runs.find_one({"case_id": case_id}, sort=[("created_at", -1)])
    prev_steps = {s["name"]: s for s in (prev or {}).get("steps", [])}
    todo = names[names.index(start_at):]
    steps = []
    for n, label in STEPS:
        if n in todo:
            steps.append({"name": n, "label": label, "state": "waiting", "note": None})
        else:
            old = prev_steps.get(n, {})
            steps.append({"name": n, "label": label, "state": old.get("state", "done"), "note": old.get("note")})
    run_id = str(uuid.uuid4())
    db.runs.insert_one(checked(Run, {"id": run_id, "case_id": case_id, "state": "queued", "steps": steps, "todo": todo,
                        "created_at": now_iso(), "by": user["name"], "engine": ENGINE}))
    db.cases.update_one({"id": case_id}, {"$set": {"status": "analysing" if case["status"] in ("draft", "review", "analysing") else case["status"],
                                                   "analysis.running": True, "analysis.stale": False}})
    files_n = db.files.count_documents({"case_id": case_id, "status": "accepted"})
    action = "ANALYSIS_STEP_RETRY" if start_at != names[0] else "ANALYSIS_STARTED"
    custody.append(case_id, action, f"{files_n} files, narration {'yes' if db.narrations.find_one({'case_id': case_id}) else 'no'}"
                   + (f", from {start_at}" if start_at != names[0] else ""), user["name"])
    await job_queue.put(("run", run_id))
    return {"run_id": run_id}


@router.get("/api/runs/{run_id}")
def get_run(run_id: str, user: dict = Depends(current_user)):
    run = get_db().runs.find_one({"id": run_id}, {"_id": 0})
    if not run:
        raise HTTPException(404, "Run not found")
    return run


@router.get("/api/cases/{case_id}/runs/latest")
def latest_run(case_id: str, user: dict = Depends(current_user)):
    return clean(get_db().runs.find_one({"case_id": case_id}, {"_id": 0}, sort=[("created_at", -1)]))


@router.post("/api/runs/{run_id}/skip/{step}")
def skip_step(run_id: str, step: str, user: dict = Depends(current_user)):
    db = get_db()
    run = db.runs.find_one({"id": run_id})
    if not run:
        raise HTTPException(404, "Run not found")
    db.runs.update_one({"id": run_id, "steps.name": step}, {"$set": {"steps.$.state": "skipped",
                       "steps.$.note": "Skipped by officer; continue by hand."}})
    custody.append(run["case_id"], "ANALYSIS_STEP_SKIPPED", step, user["name"])
    return get_run(run_id, user)


# ------------------------------------------------------------------ results


@router.get("/api/cases/{case_id}/manifest")
def manifest(case_id: str, user: dict = Depends(current_user)):
    get_case(case_id)
    return {"files": clean_all(get_db().files.find({"case_id": case_id, "status": "accepted"}, {"_id": 0, "phash": 0}).sort("uploaded_at", 1)),
            "limitation": LIMITATION_TEXT}


@router.get("/api/cases/{case_id}/timeline")
def get_timeline(case_id: str, user: dict = Depends(current_user)):
    get_case(case_id)
    return {"events": timeline.events_for(case_id)}


@router.get("/api/cases/{case_id}/gaps")
def get_gaps(case_id: str, user: dict = Depends(current_user)):
    get_case(case_id)
    gs = clean_all(get_db().gaps.find({"case_id": case_id}, {"_id": 0}))
    order = {"High": 0, "Medium": 1, "Low": 2}
    gs.sort(key=lambda g: (order[g["sev"]], int(g["id"][1:])))
    return {"gaps": [{**g, "rule_text": RULES[g["rule"]], "lint": lint(g["q"])} for g in gs]}


class GapBody(BaseModel):
    status: str  # answered | dismissed | open
    text: str = ""
    voice: bool = False


@router.patch("/api/cases/{case_id}/gaps/{gap_id}")
def set_gap(case_id: str, gap_id: str, body: GapBody, user: dict = Depends(current_user)):
    case = get_case(case_id)
    ensure_editable(case)
    db = get_db()
    g = db.gaps.find_one({"case_id": case_id, "id": gap_id})
    if not g:
        raise HTTPException(404, "Question not found")
    if body.status in ("answered", "dismissed") and not body.text.strip():
        raise HTTPException(422, "A reason is required to dismiss a question." if body.status == "dismissed" else "Enter the answer.")
    upd = {"status": body.status, "by": user["name"], "at": now_iso(), "voice": body.voice, "answer": None, "reason": None}
    if body.status == "answered":
        upd["answer"] = body.text.strip()
    elif body.status == "dismissed":
        upd["reason"] = body.text.strip()
    db.gaps.update_one({"_id": g["_id"]}, {"$set": upd})
    action = {"open": "GAP_REOPENED", "answered": "GAP_ANSWERED", "dismissed": "GAP_DISMISSED"}[body.status]
    custody.append(case_id, action, f"{gap_id} ({g['rule']})" + (f": {body.text.strip()}" if body.text.strip() else ""), user["name"])
    # §6.4: re-run the rules only (graph rebuild + 6 rules, under a second).
    gaps_agent.run(case_id)
    return get_gaps(case_id, user)


@router.post("/api/cases/{case_id}/gaps/recheck")
def recheck(case_id: str, user: dict = Depends(current_user)):
    """Re-run checks after new evidence or answers: deterministic stages only
    (triage, metadata, timeline parsers with the cached narration reading, Gap
    Hunter). No model is loaded, so this stays fast."""
    case = get_case(case_id)
    ensure_editable(case)
    t0 = time.time()
    db = get_db()
    before = {g["id"] for g in db.gaps.find({"case_id": case_id, "status": "open"})}
    triage.run(case_id)
    metadata.run(case_id)
    timeline.build(case_id, use_llm=False)
    note = gaps_agent.run(case_id)
    bns_adapter.run(case_id)
    referrals_agent.run(case_id)
    after = {g["id"] for g in db.gaps.find({"case_id": case_id, "status": "open"})}
    resolved = sorted(before - after)
    custody.append(case_id, "GAP_CHECKS_RERUN", f"{len(resolved)} question(s) resolved", user["name"])
    return {"seconds": round(time.time() - t0, 1), "resolved": resolved, "note": note}


# -------------------------------------------------------------------- draft


def _split(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9₹])", text.strip()) if s.strip()]


@router.get("/api/cases/{case_id}/draft")
def get_draft(case_id: str, user: dict = Depends(current_user)):
    get_case(case_id)
    db = get_db()
    versions = clean_all(db.drafts.find({"case_id": case_id}, {"_id": 0}).sort("v", 1))
    n = db.narrations.find_one({"case_id": case_id}) or {}
    ml = " ".join(s.get("ml", "") for s in n.get("segments") or [] if s.get("ml"))
    return {"versions": versions, "ml_readback": ml, "ml_source": "Complainant's own words (Malayalam transcript)" if ml else None}


class DraftBody(BaseModel):
    fields: dict
    narrative: str
    note: str = "Officer edit"


@router.put("/api/cases/{case_id}/draft")
def save_draft(case_id: str, body: DraftBody, user: dict = Depends(current_user)):
    case = get_case(case_id)
    ensure_editable(case)
    db = get_db()
    prev = db.drafts.find_one({"case_id": case_id}, sort=[("v", -1)])
    fields = {k: str(body.fields.get(k, "")) for k in ("place", "period", "report_date", "delay_reason")}
    narrative = body.narrative.strip()
    if prev and prev["fields"] == fields and prev["narrative"] == narrative:
        return get_draft(case_id, user)
    machine = db.drafts.find_one({"case_id": case_id, "edited": False}, sort=[("v", -1)])
    by_text = {s["t"]: s for s in (machine or {}).get("sentences", [])}
    sentences = [{"t": t, "event_ids": by_text[t]["event_ids"], "src": by_text[t]["src"], "supported": by_text[t]["supported"]}
                 if t in by_text else {"t": t, "event_ids": [], "src": [], "supported": None} for t in _split(narrative)]
    v = (prev["v"] + 1) if prev else 1
    db.drafts.insert_one(checked(DraftVersion, {"case_id": case_id, "v": v, "by": user["name"], "at": now_iso(), "edited": True,
                                                "note": body.note, "fields": fields, "narrative": narrative, "sentences": sentences}))
    changed = "unchanged" if prev and prev["narrative"] == narrative else "edited"
    custody.append(case_id, "DRAFT_SAVED", f"v{v} (narrative {changed})", user["name"])
    custody.derived(case_id, f"draft_v{v}", {"fields": fields, "narrative": narrative}, model="officer edit")
    return get_draft(case_id, user)


# ---------------------------------------------------------------------- BNS


@router.get("/api/cases/{case_id}/bns")
def get_bns(case_id: str, user: dict = Depends(current_user)):
    get_case(case_id)
    return {"suggestions": clean_all(get_db().bns_decisions.find({"case_id": case_id}, {"_id": 0}).sort("id", 1))}


class DecisionBody(BaseModel):
    decision: str | None  # Accepted | Rejected | None (clear)
    note: str = ""


@router.post("/api/cases/{case_id}/bns/{bid}/decision")
def decide_bns(case_id: str, bid: str, body: DecisionBody, user: dict = Depends(current_user)):
    require_sho(user)
    case = get_case(case_id)
    ensure_editable(case)
    db = get_db()
    b = db.bns_decisions.find_one({"case_id": case_id, "id": bid})
    if not b:
        raise HTTPException(404, "Suggestion not found")
    if body.decision is None:
        db.bns_decisions.update_one({"_id": b["_id"]}, {"$set": {"decision": None, "note": "", "by": None, "at": None}})
        custody.append(case_id, "BNS_DECISION_CLEARED", b["section"], user["name"])
    else:
        db.bns_decisions.update_one({"_id": b["_id"]}, {"$set": {"decision": body.decision, "note": body.note.strip(),
                                                                 "by": user["name"], "at": now_iso()}})
        custody.append(case_id, "BNS_DECIDED", f"{b['section']}: {body.decision}" + (f" ({body.note.strip()})" if body.note.strip() else ""), user["name"])
    return get_bns(case_id, user)


# ---------------------------------------------------------------- referrals


def _refs(case_id: str) -> dict:
    return get_db().referrals.find_one({"case_id": case_id}, {"_id": 0}) or {"case_id": case_id, "items": [], "removed": [], "confirmed": None}


@router.get("/api/cases/{case_id}/referrals")
def get_referrals(case_id: str, user: dict = Depends(current_user)):
    get_case(case_id)
    return {**_refs(case_id), "limitation": LIMITATION_TEXT}


class RefBody(BaseModel):
    op: str  # move | remove | add | confirm
    index: int = 0
    delta: int = 0
    file: str = ""
    reason: str = ""


@router.post("/api/cases/{case_id}/referrals")
def edit_referrals(case_id: str, body: RefBody, user: dict = Depends(current_user)):
    require_sho(user)
    case = get_case(case_id)
    ensure_editable(case)
    doc = _refs(case_id)
    items = doc["items"]
    if body.op == "move":
        j = body.index + body.delta
        if not (0 <= body.index < len(items) and 0 <= j < len(items)):
            raise HTTPException(422, "Invalid position")
        items[body.index], items[j] = items[j], items[body.index]
        action, detail = "REFERRAL_REORDERED", f"{items[j]['file']} moved to rank {j + 1}"
    elif body.op == "remove":
        if not body.reason.strip():
            raise HTTPException(422, "A reason is required.")
        r = items.pop(body.index)
        doc["removed"].append({"file": r["file"], "why": body.reason.strip(), "by": user["name"]})
        action, detail = "REFERRAL_REMOVED", f"{r['file']}: {body.reason.strip()}"
    elif body.op == "add":
        if not body.reason.strip():
            raise HTTPException(422, "A reason is required.")
        items.append({"file": body.file, "reason": body.reason.strip(), "conf": None, "by": user["name"]})
        doc["removed"] = [r for r in doc["removed"] if r["file"] != body.file]
        action, detail = "REFERRAL_ADDED", f"{body.file}: {body.reason.strip()}"
    elif body.op == "confirm":
        doc["confirmed"] = {"by": user["name"], "at": now_iso()}
        action, detail = "REFERRALS_CONFIRMED", ", ".join(r["file"] for r in items) or "(empty list)"
    else:
        raise HTTPException(422, "Unknown operation")
    if body.op != "confirm":
        doc["confirmed"] = None
    get_db().referrals.replace_one({"case_id": case_id}, doc, upsert=True)
    custody.append(case_id, action, detail, user["name"])
    return get_referrals(case_id, user)


def referral_csv(case: dict) -> str:
    db = get_db()
    files = {f["ev_id"]: f for f in db.files.find({"case_id": case["id"], "status": "accepted"})}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Case", "Rank", "Evidence ID", "File", "SHA-256", "Reason", "Confidence"])
    for i, r in enumerate(_refs(case["id"])["items"], start=1):
        f = files.get(r["file"], {})
        w.writerow([case["ref"], i, r["file"], f.get("name"), f.get("sha256"), r["reason"], r["conf"] if r["conf"] is not None else ""])
    buf.write(f"\nNote: {LIMITATION_TEXT}\n")
    return buf.getvalue()


@router.get("/api/cases/{case_id}/referrals.csv")
def referrals_csv(case_id: str, user: dict = Depends(current_user)):
    case = get_case(case_id)
    custody.append(case_id, "REFERRAL_SHEET_DOWNLOADED", f"{len(_refs(case_id)['items'])} files", user["name"])
    return Response(referral_csv(case), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{case["ref"]}_referral_sheet.csv"'})

