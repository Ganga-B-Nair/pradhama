from fastapi import APIRouter

from app.db import get_db

router = APIRouter()


@router.get("/api/cases/{case_id}/manifest")
def get_manifest(case_id: str):
    db = get_db()
    files = list(db.files.find({"case_id": case_id}, {"_id": 0}))
    return {"files": files}


@router.get("/api/cases/{case_id}/timeline")
def get_timeline(case_id: str):
    db = get_db()
    events = list(db.timeline_events.find({"case_id": case_id}, {"_id": 0}).sort("timestamp", 1))
    return {"events": events}


@router.get("/api/cases/{case_id}/gaps")
def get_gaps(case_id: str):
    db = get_db()
    gaps = list(db.gaps.find({"case_id": case_id}, {"_id": 0}))
    return {"gaps": gaps}


@router.get("/api/cases/{case_id}/draft")
def get_draft(case_id: str):
    db = get_db()
    draft = db.drafts.find_one({"case_id": case_id}, {"_id": 0}, sort=[("version", -1)])
    return draft or {}


@router.get("/api/cases/{case_id}/bns")
def get_bns(case_id: str):
    db = get_db()
    suggestions = list(db.bns_decisions.find({"case_id": case_id}, {"_id": 0}))
    return {"suggestions": suggestions}
