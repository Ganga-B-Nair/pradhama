"""MongoDB: the single source of truth. One shared client, reused everywhere.

Collections: cases, files, audit_chain, runs, narrations, timeline_events, gaps, drafts, bns_decisions.
Nothing here uses multi-document transactions — every write is one document,
so there is never a transaction held open across a model call.
"""
from pymongo import MongoClient
from pymongo.database import Database

from app.config import settings

_client: MongoClient | None = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(settings.mongo_uri)
    return _client


def get_db() -> Database:
    return get_client()[settings.mongo_db]


def ensure_indexes() -> None:
    db = get_db()
    db.cases.create_index("created_at")
    db.files.create_index("case_id")
    db.files.create_index("sha256")
    db.audit_chain.create_index("case_id")
    db.runs.create_index("case_id")
    db.narrations.create_index("case_id")
    db.timeline_events.create_index("case_id")
    db.gaps.create_index("case_id")
    db.drafts.create_index([("case_id", 1), ("version", 1)])
    db.bns_decisions.create_index("case_id")
