"""One in-process background worker, one job at a time (docs/HACKATHON_PLAN.md §5, §8).

No Celery/Redis. FastAPI holds a single asyncio.Queue; a background task consumes
it serially so two cases never compete for Ollama/Whisper memory at once.

Pipeline order is fixed (§4): deterministic stages -> speech-to-text (own
process, exits) -> LLM stages -> Gap Hunter (no model). Implemented here as a
plain function rather than a LangGraph StateGraph (the plan's own cut-list
fallback, §8) — six stages in a fixed order don't need a graph library, and
this way there's one less moving part on a machine this was never run on.
"""
import asyncio

from app.agents import bns_adapter, gaps, metadata, triage
from app.agents import timeline as timeline_agent
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
    """Runs the 6 stages in order: triage, metadata, asr, timeline, gaps, draft.
    The set_step(running) / set_step(done|failed) bracketing is what the UI's
    polling (GET /api/runs/{run_id}) reflects as live progress.
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
    """Deterministic stages run inline; ASR and the Ollama calls inside
    timeline/draft are blocking, so each stage runs in a worker thread to
    avoid blocking the asyncio event loop (the API keeps answering other
    requests while a stage is in progress).
    """
    if step_name == "triage":
        await asyncio.to_thread(triage.run, case_id)
    elif step_name == "metadata":
        await asyncio.to_thread(metadata.run, case_id)
    elif step_name == "asr":
        await asyncio.to_thread(timeline_agent.run_asr, case_id)
    elif step_name == "timeline":
        await asyncio.to_thread(timeline_agent.run_timeline, case_id)
    elif step_name == "gaps":
        await asyncio.to_thread(gaps.run, case_id)
    elif step_name == "draft":
        await asyncio.to_thread(timeline_agent.run_draft, case_id)
        await asyncio.to_thread(bns_adapter.run, case_id)
    else:
        raise ValueError(f"unknown pipeline stage '{step_name}'")
