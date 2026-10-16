"""Shared Pydantic models — the de facto schema for every MongoDB document shape.

Both G (platform/deterministic agents) and V (model-touching agents) import
these instead of writing ad hoc dicts, so the two sides of the pipeline can't
drift apart on field names. Matches the collections in app/db.py and the
contracts in contracts/*.json.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Case(BaseModel):
    id: str
    complainant_name: str
    complainant_contact: str | None = None
    consent_given: bool
    location: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: Literal["intake", "analyzing", "review", "approved", "exported"] = "intake"


class FileRecord(BaseModel):
    id: str
    case_id: str
    name: str
    sha256: str
    mime_type: str
    size_bytes: int
    status: Literal["accepted", "rejected"]
    reason: str | None = None
    kind: Literal[
        "financial_record", "conversation", "media", "call_log", "audio", "other"
    ] | None = None
    is_duplicate_of: str | None = None  # file id of the canonical copy, if deduped
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class AuditEntry(BaseModel):
    """One block in the append-only custody chain. Ordered by insertion."""

    id: str
    case_id: str
    entry_type: Literal["FILE_RECEIVED", "ARTIFACT_DERIVED", "OFFICER_ACTION"]
    payload: dict
    prev_hash: str | None
    entry_hash: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RunStep(BaseModel):
    name: Literal["triage", "metadata", "asr", "timeline", "gaps", "draft", "bns"]
    state: Literal["waiting", "running", "done", "failed", "skipped"] = "waiting"
    note: str | None = None


class Run(BaseModel):
    id: str
    case_id: str
    state: Literal["queued", "running", "done", "failed"] = "queued"
    steps: list[RunStep]
    created_at: datetime = Field(default_factory=datetime.utcnow)


class TimelineEvent(BaseModel):
    id: str
    case_id: str
    timestamp: str  # ISO string; precision noted separately
    timestamp_precision: Literal["exact", "date_only", "approximate"]
    summary: str
    amount: float | None = None
    account: str | None = None
    source_file_ids: list[str]
    source_refs: list[dict] = Field(default_factory=list)  # [{file_id, line/segment}]


class Gap(BaseModel):
    id: str
    case_id: str
    rule: Literal["G-01", "G-02", "G-03", "G-05", "G-07", "G-09"]
    question: str  # rendered from the fixed neutral template
    status: Literal["open", "answered", "dismissed"] = "open"
    answer: str | None = None
    dismiss_reason: str | None = None
    related_event_ids: list[str] = Field(default_factory=list)


class DraftSentence(BaseModel):
    sentence: str
    event_ids: list[str] = Field(default_factory=list)
    supported: bool  # false => rendered as "Unsupported — needs officer review"


class Draft(BaseModel):
    id: str
    case_id: str
    version: int
    sentences: list[DraftSentence]
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BnsSuggestion(BaseModel):
    id: str
    case_id: str
    section: str
    title: str
    ingredients: list[str]
    matched_event_ids: list[str]
    decision: Literal["pending", "accepted", "rejected"] = "pending"
    source: Literal["fixture", "live"] = "fixture"
