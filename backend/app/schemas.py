"""Shared Pydantic models — the de facto schema for MongoDB documents
(docs/HACKATHON_PLAN.md §5). Write sites call `checked(Model, doc)` so a shape
drift between agents fails loudly at the write, not silently in the UI."""
from typing import Literal

from pydantic import BaseModel, ConfigDict


class _Doc(BaseModel):
    model_config = ConfigDict(extra="allow")


class Complainant(_Doc):
    name: str
    contact: str = ""
    address: str = ""
    language: str
    consent_at: str | None
    consent_version: str | None


class Case(_Doc):
    id: str
    ref: str
    status: Literal["draft", "analysing", "review", "approved", "exported"]
    created_by: str
    created_at: str
    complainant: Complainant
    analysis: dict
    approval: dict


class FileRecord(_Doc):
    id: str
    case_id: str
    name: str
    ext: str
    size: int
    sha256: str
    status: Literal["accepted", "rejected"]
    ev_id: str | None
    uploaded_at: str
    uploaded_by: str


class Source(_Doc):
    f: str | None = None
    l: int | None = None  # noqa: E741 - matches the UI's {f, l} / {n} source refs
    n: int | None = None


class TimelineEvent(_Doc):
    id: str
    case_id: str
    at: str
    prec: Literal["exact", "day", "approx"]
    type: Literal["Call", "Message", "Transaction", "Media"]
    actor: str
    action: str
    amount: float | None
    conf: float
    src: list[Source]
    source_kinds: list[str]


class Gap(_Doc):
    id: str
    case_id: str
    rule: Literal["G-01", "G-02", "G-03", "G-05", "G-07", "G-09"]
    key: str
    sev: Literal["High", "Medium", "Low"]
    q: str
    src: list[Source]
    status: Literal["open", "answered", "dismissed"]


class Sentence(_Doc):
    t: str
    event_ids: list[str]
    src: list[Source]
    supported: bool | None


class DraftVersion(_Doc):
    case_id: str
    v: int
    by: str
    at: str
    edited: bool
    fields: dict
    narrative: str
    sentences: list[Sentence]


class Run(_Doc):
    id: str
    case_id: str
    state: Literal["queued", "running", "done", "failed"]
    steps: list[dict]


def checked(model: type[BaseModel], doc: dict) -> dict:
    model.model_validate(doc)
    return doc
