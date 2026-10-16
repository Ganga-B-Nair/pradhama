from fastapi import HTTPException

from app.db import get_db

LOCKED = ("approved", "exported")


def get_case(case_id: str) -> dict:
    case = get_db().cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(404, "Case not found")
    return case


def is_locked(case: dict) -> bool:
    return case["status"] in LOCKED


def ensure_editable(case: dict, *, allow_running: bool = False) -> None:
    if is_locked(case):
        raise HTTPException(409, "The case is approved and read-only. The SHO can reopen it from Approval.")
    if case.get("analysis", {}).get("running") and not allow_running:
        raise HTTPException(409, "Analysis is running. Try again when it finishes.")


def mark_stale(case_id: str) -> None:
    db = get_db()
    case = db.cases.find_one({"id": case_id})
    if case and case.get("analysis", {}).get("done"):
        db.cases.update_one({"id": case_id}, {"$set": {"analysis.stale": True}})
