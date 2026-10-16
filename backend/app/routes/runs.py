import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException

from app.db import get_db
from app.worker import job_queue

router = APIRouter()

STEP_NAMES = ["triage", "metadata", "asr", "timeline", "gaps", "draft"]


@router.post("/api/cases/{case_id}/runs")
async def start_run(case_id: str):
    db = get_db()
    if not db.cases.find_one({"id": case_id}):
        raise HTTPException(status_code=404, detail="Case not found")

    run_id = str(uuid.uuid4())
    run = {
        "id": run_id,
        "case_id": case_id,
        "state": "queued",
        "steps": [{"name": name, "state": "waiting", "note": None} for name in STEP_NAMES],
        "created_at": datetime.utcnow(),
    }
    db.runs.insert_one(run)
    await job_queue.put(run_id)
    return {"run_id": run_id}


@router.get("/api/runs/{run_id}")
def get_run(run_id: str):
    db = get_db()
    run = db.runs.find_one({"id": run_id}, {"_id": 0})
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
