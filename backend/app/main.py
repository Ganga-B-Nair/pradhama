import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import ensure_indexes
from app.routes import auth, bns, cases, draft, export, files, gaps, results, runs
from app.worker import worker_loop

app = FastAPI(title="TRACE API")

app.add_middleware(
    CORSMiddleware,
    # allow_origin_regex (not just allow_origins) because the demo laptop is
    # opened by its LAN IP from a phone (for the QR-verify scan) — the browser
    # sends that LAN origin, not localhost, so a localhost-only allowlist
    # silently breaks every API call the moment it's opened off a phone.
    allow_origins=["http://localhost:3000"],
    allow_origin_regex=r"^http://(192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
                        r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}):3000$",
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
