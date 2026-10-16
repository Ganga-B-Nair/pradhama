import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import ensure_indexes
from app.routes import analysis, auth, cases, export, files
from app.worker import job_queue, resume_interrupted, worker_loop

logging.basicConfig(level=logging.INFO)
logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)  # "unknown label" notices on a fresh graph
app = FastAPI(title="TRACE API")

# The UI normally reaches the API through the Next.js /api proxy (same origin).
# CORS is only for running the frontend dev server against the API directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_origin_regex=r"^http://(192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
                       r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}):3000$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in [auth.router, cases.router, files.router, analysis.router, export.router]:
    app.include_router(router)


@app.on_event("startup")
async def startup():
    ensure_indexes()
    for job in resume_interrupted():
        await job_queue.put(job)
    asyncio.create_task(worker_loop())


@app.get("/api/health")
def health():
    return {"status": "ok"}
