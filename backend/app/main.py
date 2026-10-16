import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import ensure_indexes
from app.routes import auth, bns, cases, draft, export, files, gaps, results, runs
from app.worker import worker_loop

app = FastAPI(title="TRACE API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in [auth.router, cases.router, files.router, runs.router, results.router,
               gaps.router, draft.router, bns.router, export.router]:
    app.include_router(router)


@app.on_event("startup")
async def startup():
    ensure_indexes()
    asyncio.create_task(worker_loop())


@app.get("/api/health")
def health():
    return {"status": "ok"}
