"""One in-process background worker, one job at a time (docs/HACKATHON_PLAN.md §5).

No Celery/Redis: FastAPI holds a single asyncio.Queue, consumed serially, so two
cases never compete for Whisper/Ollama memory. Requests never wait on the
pipeline: POST /runs returns 202 at once and the UI polls GET /api/runs/{id}.

Pipeline order is fixed (§4): deterministic stages -> speech-to-text (its own
process, exits) -> LLM stages -> Gap Hunter (no model). LangGraph wraps the
6 nodes (triage, metadata, asr, timeline, gaps, draft) as a StateGraph; if
LangGraph can't be imported, the same node functions run as a plain loop.
A failed node never blocks the case: it is marked failed and the rest continue.
"""
import asyncio
import logging
import traceback

from app import custody
from app.agents import bns_adapter, draft, gaps, metadata, narration, referrals, timeline, triage
from app.db import get_db
from app.util import now_iso

log = logging.getLogger("trace.worker")
job_queue: asyncio.Queue = asyncio.Queue()

STEPS = [("triage", "Content Triage"), ("metadata", "Metadata"), ("asr", "Speech-to-text"),
         ("timeline", "Timeline"), ("gaps", "Gap Hunter"), ("draft", "Draft builder")]


def _draft_stage(case_id: str) -> str:
    notes = [draft.run(case_id), bns_adapter.run(case_id), referrals.run(case_id)]
    return "; ".join(notes)


STAGE_FN = {
    "triage": triage.run,
    "metadata": metadata.run,
    "asr": narration.transcribe,
    "timeline": timeline.build,
    "gaps": gaps.run,
    "draft": _draft_stage,
}


def _set_step(run_id: str, name: str, state: str, note: str | None = None):
    get_db().runs.update_one({"id": run_id, "steps.name": name},
                             {"$set": {"steps.$.state": state, "steps.$.note": note}})


def _make_node(name: str):
    def node(state: dict) -> dict:
        run_id, case_id = state["run_id"], state["case_id"]
        if name not in state["todo"]:
            return state
        _set_step(run_id, name, "running")
        try:
            note = STAGE_FN[name](case_id)
            _set_step(run_id, name, "done", note)
        except Exception as exc:  # noqa: BLE001 - surfaced to the officer, never swallowed
            log.error("stage %s failed: %s", name, traceback.format_exc())
            _set_step(run_id, name, "failed", str(exc)[:400])
            custody.append(case_id, "ANALYSIS_STEP_FAILED", f"{name}: {str(exc)[:200]}", custody.MACHINE)
            state = {**state, "failed": state["failed"] + [name]}
        return state
    return node


def _build_graph():
    try:
        from langgraph.graph import END, StateGraph
    except ImportError:
        return None
    g = StateGraph(dict)
    for name, _label in STEPS:
        g.add_node(name, _make_node(name))
    g.set_entry_point(STEPS[0][0])
    for (a, _), (b, _) in zip(STEPS, STEPS[1:]):
        g.add_edge(a, b)
    g.add_edge(STEPS[-1][0], END)
    return g.compile()


_graph = _build_graph()
ENGINE = "LangGraph StateGraph" if _graph else "plain function"


def run_pipeline_sync(run_id: str) -> None:
    db = get_db()
    run = db.runs.find_one({"id": run_id})
    if not run:
        return
    case_id = run["case_id"]
    db.runs.update_one({"id": run_id}, {"$set": {"state": "running", "started_at": now_iso()}})
    state = {"run_id": run_id, "case_id": case_id, "todo": run["todo"], "failed": []}
    if _graph is not None:
        state = _graph.invoke(state)
    else:
        for name, _label in STEPS:
            state = _make_node(name)(state)

    final = db.runs.find_one({"id": run_id})
    summary = "; ".join(f"{s['label']}: {s['state']}" for s in final["steps"])
    db.runs.update_one({"id": run_id}, {"$set": {"state": "failed" if state["failed"] else "done", "finished_at": now_iso()}})
    case = db.cases.find_one({"id": case_id})
    upd = {"analysis.running": False, "analysis.done": True, "analysis.ran_at": now_iso()}
    if case.get("status") not in ("approved", "exported"):
        upd["status"] = "review"
    db.cases.update_one({"id": case_id}, {"$set": upd})
    custody.append(case_id, "ANALYSIS_COMPLETED", summary, custody.MACHINE)


def transcribe_sync(case_id: str) -> None:
    try:
        narration.transcribe(case_id)
    except Exception:  # noqa: BLE001 - state already written to the narration document
        log.error("transcription failed: %s", traceback.format_exc())


async def worker_loop():
    while True:
        kind, ref = await job_queue.get()
        try:
            if kind == "run":
                await asyncio.to_thread(run_pipeline_sync, ref)
            elif kind == "asr":
                await asyncio.to_thread(transcribe_sync, ref)
        except Exception:  # noqa: BLE001 - keep the single worker alive
            log.error("job failed: %s", traceback.format_exc())
        finally:
            job_queue.task_done()


def resume_interrupted() -> list:
    """After a restart, mark runs that were mid-flight as failed so the UI can retry."""
    db = get_db()
    jobs = []
    for r in db.runs.find({"state": {"$in": ["queued", "running"]}}):
        db.runs.update_one({"id": r["id"]}, {"$set": {"state": "failed"}})
        for s in r["steps"]:
            if s["state"] in ("waiting", "running"):
                _set_step(r["id"], s["name"], "failed", "Interrupted by a server restart. Retry the analysis.")
        db.cases.update_one({"id": r["case_id"]}, {"$set": {"analysis.running": False}})
    for n in db.narrations.find({"status": "transcribing"}):
        db.narrations.update_one({"_id": n["_id"]}, {"$set": {"status": "pending"}})
        jobs.append(("asr", n["case_id"]))
    for n in db.narrations.find({"status": "pending"}):
        if ("asr", n["case_id"]) not in jobs:
            jobs.append(("asr", n["case_id"]))
    return jobs
