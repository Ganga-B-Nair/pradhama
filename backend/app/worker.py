"""One in-process background worker, one job at a time (docs/HACKATHON_PLAN.md §5, §8).

No Celery/Redis. FastAPI holds a single asyncio.Queue; a background task consumes
it serially so two cases never compete for Ollama/Whisper memory at once.

Pipeline order is fixed (§4): deterministic stages -> speech-to-text (own
process, exits) -> LLM stages -> Gap Hunter (no model). This file wires the
LangGraph StateGraph. If LangGraph isn't working by H11, swap `build_graph()`'s
body for the `run_pipeline_plain()` fallback below — call sites don't change.
"""
import asyncio
from datetime import datetime

from app.db import get_db

job_queue: asyncio.Queue = asyncio.Queue()


async def worker_loop():
    while True:
        run_id = await job_queue.get()
        try:
            await run_pipeline(run_id)
        finally:
            job_queue.task_done()


def _set_step(run_id: str, name: str, state: str, note: str | None = None):
    db = get_db()
    db.runs.update_one(
        {"id": run_id, "steps.name": name},
        {"$set": {"steps.$.state": state, "steps.$.note": note}},
    )


async def run_pipeline(run_id: str):
    """6 LangGraph nodes: triage, metadata, asr, timeline, gaps, draft.
    TODO(G/V): replace each _stub with the real agent call. Keep the
    set_step(running) / set_step(done|failed) bracketing so the UI's polling
    (GET /api/runs/{run_id}) always reflects real progress.
    """
    db = get_db()
    run = db.runs.find_one({"id": run_id})
    if not run:
        return
    case_id = run["case_id"]
    db.runs.update_one({"id": run_id}, {"$set": {"state": "running"}})

    for step_name in ["triage", "metadata", "asr", "timeline", "gaps", "draft"]:
        _set_step(run_id, step_name, "running")
        try:
            await _run_stage(step_name, case_id)
            _set_step(run_id, step_name, "done")
        except Exception as exc:  # noqa: BLE001 - surfaced to the officer, not swallowed
            _set_step(run_id, step_name, "failed", note=str(exc))
            db.runs.update_one({"id": run_id}, {"$set": {"state": "failed"}})
            return

    db.runs.update_one({"id": run_id}, {"$set": {"state": "done"}})


async def _run_stage(step_name: str, case_id: str):
    # TODO(G): "triage", "metadata" -> app.agents.triage / app.agents.metadata
    # TODO(V): "asr", "timeline", "gaps", "draft" -> app.agents.*
    raise NotImplementedError(f"stage '{step_name}' not wired yet for case {case_id}")
