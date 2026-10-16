"""MongoDB: the single source of truth. One shared client, reused everywhere.

Collections: cases, files, narrations, audit_chain, runs, timeline_events, gaps,
drafts, bns_decisions, referrals, exports, sessions, counters.
Every write is a single-document insert/update — never a multi-document
transaction — so nothing is held open across a model call.
"""
from pymongo import ASCENDING, MongoClient, ReturnDocument
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


def next_seq(name: str) -> int:
    doc = get_db().counters.find_one_and_update(
        {"_id": name}, {"$inc": {"value": 1}}, upsert=True, return_document=ReturnDocument.AFTER
    )
    return doc["value"]


def ensure_indexes() -> None:
    db = get_db()
    db.cases.create_index("id", unique=True)
    db.cases.create_index("ref", unique=True)
    db.cases.create_index("updated_at")
    db.files.create_index([("case_id", ASCENDING), ("ev_id", ASCENDING)])
    db.files.create_index("sha256")
    db.narrations.create_index("case_id", unique=True)
    db.audit_chain.create_index([("case_id", ASCENDING), ("seq", ASCENDING)], unique=True)
    db.runs.create_index("id", unique=True)
    db.runs.create_index("case_id")
    db.timeline_events.create_index("case_id")
    db.gaps.create_index("case_id")
    db.drafts.create_index([("case_id", ASCENDING), ("v", ASCENDING)], unique=True)
    db.bns_decisions.create_index("case_id")
    db.referrals.create_index("case_id")
    db.exports.create_index([("case_id", ASCENDING), ("v", ASCENDING)], unique=True)
    db.sessions.create_index("sid", unique=True)
