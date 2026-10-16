"""Timeline Agent — owned by V. docs/HACKATHON_PLAN.md §6.3.

Order of reliability, most reliable first: rule parsers (WhatsApp export, bank
SMS, call-log CSV) are deterministic and run before the LLM. The LLM only
extracts events from the English ASR segments and the draft narrative, always
with JSON-schema output, and every event/sentence must cite its source or it
is dropped (events) / flagged unsupported (draft sentences) — never silently
kept. See app.agents.asr for why ASR is a subprocess, not an import here.

NOTE: the exact WhatsApp/bank-SMS/call-log formats here follow the plan's
description (§6.3). There is no sample file yet under golden/ — re-check these
regexes against the real golden bundle once it exists.
"""
import csv
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone

from app.agents import extract
from app.agents.llm_client import LlmError, generate_json
from app.config import settings
from app.custody import append_entry
from app.db import get_db

IST = timezone(timedelta(hours=5, minutes=30))

WHATSAPP_RE_DASH = re.compile(r"^(\d{1,2}/\d{1,2}/\d{2}), (\d{1,2}:\d{2}) - ([^:]+): (.*)$")
WHATSAPP_RE_BRACKET = re.compile(r"^\[(\d{1,2}/\d{1,2}/\d{2}) (\d{1,2}:\d{2})\] ([^:]+): (.*)$")
BANK_DATE_RE = re.compile(r"\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b")
BANK_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2}(?::\d{2})?)\b")
BANK_TYPE_RE = re.compile(r"\b(debited|credited)\b", re.IGNORECASE)
BANK_METHOD_RE = re.compile(r"\b(IMPS|NEFT|UPI|RTGS)\b", re.IGNORECASE)


def _parse_whatsapp_datetime(date_str: str, time_str: str) -> str:
    dt = datetime.strptime(f"{date_str} {time_str}", "%d/%m/%y %H:%M").replace(tzinfo=IST)
    return dt.isoformat()


def parse_whatsapp_export(text_path: str) -> list[dict]:
    """Both `dd/mm/yy, hh:mm - Sender: message` and `[dd/mm/yy hh:mm] Sender: message`.
    Each event carries {file_id, line}; file_id is attached by the caller."""
    events = []
    with open(text_path, "r", encoding="utf-8", errors="ignore") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.rstrip("\n")
            match = WHATSAPP_RE_DASH.match(line) or WHATSAPP_RE_BRACKET.match(line)
            if not match:
                continue
            date_str, time_str, sender, message = match.groups()
            try:
                timestamp = _parse_whatsapp_datetime(date_str, time_str)
            except ValueError:
                continue
            events.append({
                "line": line_no,
                "timestamp": timestamp,
                "timestamp_precision": "exact",
                "summary": f"{sender.strip()}: {message.strip()}",
                "amount": extract.extract_amount(message),
                "account": (extract.extract_accounts(message) or [None])[0],
            })
    return events


def parse_bank_sms(text_path: str) -> list[dict]:
    """Regex for amount, account, UPI ID, IMPS/NEFT, time."""
    events = []
    with open(text_path, "r", encoding="utf-8", errors="ignore") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            amount = extract.extract_amount(line)
            if amount is None:
                continue

            date_match = BANK_DATE_RE.search(line)
            time_match = BANK_TIME_RE.search(line)
            timestamp, precision = None, "approximate"
            if date_match and time_match:
                timestamp, precision = _parse_bank_datetime(date_match.group(1), time_match.group(1)), "exact"
            elif date_match:
                timestamp, precision = _parse_bank_date_only(date_match.group(1)), "date_only"

            type_match = BANK_TYPE_RE.search(line)
            method_match = BANK_METHOD_RE.search(line)
            accounts = extract.extract_accounts(line)
            upi_ids = extract.extract_upi_ids(line)

            events.append({
                "line": line_no,
                "timestamp": timestamp,
                "timestamp_precision": precision,
                "summary": line,
                "amount": amount,
                "account": accounts[0] if accounts else None,
                "transaction_type": type_match.group(1).lower() if type_match else None,
                "method": method_match.group(1).upper() if method_match else None,
                "upi_id": upi_ids[0] if upi_ids else None,
            })
    return events


def _parse_bank_datetime(date_str: str, time_str: str) -> str | None:
    sep = "-" if "-" in date_str else "/"
    parts = date_str.split(sep)
    year_fmt = "%y" if len(parts[2]) == 2 else "%Y"
    for date_fmt in (f"%d{sep}%m{sep}{year_fmt}", f"%d{sep}%m{sep}{year_fmt[1:]}"):
        try:
            time_fmt = "%H:%M:%S" if time_str.count(":") == 2 else "%H:%M"
            dt = datetime.strptime(f"{date_str} {time_str}", f"{date_fmt} {time_fmt}")
            return dt.replace(tzinfo=IST).isoformat()
        except ValueError:
            continue
    return None


def _parse_bank_date_only(date_str: str) -> str | None:
    sep = "-" if "-" in date_str else "/"
    parts = date_str.split(sep)
    year_fmt = "%y" if len(parts[2]) == 2 else "%Y"
    try:
        dt = datetime.strptime(date_str, f"%d{sep}%m{sep}{year_fmt}")
        return dt.replace(tzinfo=IST).isoformat()
    except ValueError:
        return None


def parse_call_log(csv_path: str) -> list[dict]:
    events = []
    with open(csv_path, "r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        normalized_fields = {name.strip().lower(): name for name in (reader.fieldnames or [])}
        for line_no, row in enumerate(reader, start=2):
            number = row.get(normalized_fields.get("number", ""), "")
            call_type = row.get(normalized_fields.get("type", ""), "")
            raw_ts = row.get(normalized_fields.get("timestamp", ""), "")
            duration = row.get(normalized_fields.get("duration", ""), "")

            timestamp, precision = None, "approximate"
            try:
                timestamp = datetime.fromisoformat(raw_ts).isoformat()
                precision = "exact"
            except (ValueError, TypeError):
                pass

            events.append({
                "line": line_no,
                "timestamp": timestamp,
                "timestamp_precision": precision,
                "summary": f"Call {call_type or 'logged'} with {number or 'unknown number'}".strip(),
                "amount": None,
                "account": None,
                "phone": extract.normalize_phone(number) if number else None,
                "duration_seconds": duration or None,
            })
    return events


NARRATION_EVENT_PROMPT = """You extract factual events from an English transcript of a crime complaint.
Return ONLY JSON: {{"events": [{{"summary": "...", "amount": number|null, "account": "..."|null, "timestamp_precision": "exact"|"date_only"|"approximate", "segment_ids": [int, ...]}}]}}
Every event MUST cite the segment_ids (from the list below) it was derived from. Never invent an event with no segment_ids.
Segments:
{segments}
"""


def extract_events_from_narration(english_segments: list[dict]) -> list[dict]:
    """Ollama call, JSON schema output. Each event must cite segment IDs; drop
    any event with no valid citation."""
    if not english_segments:
        return []
    valid_ids = {seg["id"] for seg in english_segments}
    segment_lines = "\n".join(f"[{seg['id']}] {seg['text']}" for seg in english_segments)
    prompt = NARRATION_EVENT_PROMPT.format(segments=segment_lines)

    try:
        result = generate_json(prompt)
    except LlmError:
        return []

    events = []
    for raw_event in result.get("events", []):
        segment_ids = [sid for sid in raw_event.get("segment_ids", []) if sid in valid_ids]
        if not segment_ids:
            continue
        events.append({
            "timestamp": None,
            "timestamp_precision": raw_event.get("timestamp_precision", "approximate"),
            "summary": raw_event.get("summary", ""),
            "amount": raw_event.get("amount"),
            "account": raw_event.get("account"),
            "segment_ids": segment_ids,
        })
    return events


def merge_events(events: list[dict]) -> list[dict]:
    """Events within 5 minutes with the same amount+account merge into one,
    listing all sources. Times in IST; precision: exact | date_only | approximate."""
    def _sort_key(event):
        ts = event.get("timestamp")
        try:
            return datetime.fromisoformat(ts) if ts else datetime.max.replace(tzinfo=IST)
        except ValueError:
            return datetime.max.replace(tzinfo=IST)

    ordered = sorted(events, key=_sort_key)
    merged: list[dict] = []

    for event in ordered:
        match = None
        if event.get("timestamp") and event.get("amount") is not None:
            event_time = _sort_key(event)
            for candidate in merged:
                if candidate.get("amount") != event.get("amount"):
                    continue
                if candidate.get("account") != event.get("account"):
                    continue
                if not candidate.get("timestamp"):
                    continue
                if abs((event_time - _sort_key(candidate)).total_seconds()) <= 300:
                    match = candidate
                    break
        if match:
            match["source_file_ids"] = sorted(set(match["source_file_ids"]) | set(event["source_file_ids"]))
            match["source_refs"].extend(event["source_refs"])
            match["source_kinds"] = sorted(set(match["source_kinds"]) | {event.get("source_kind")})
        else:
            merged.append({
                **event,
                "source_file_ids": list(event["source_file_ids"]),
                "source_refs": list(event["source_refs"]),
                "source_kinds": [event.get("source_kind")],
            })

    return merged


DRAFT_PROMPT = """You write a chronological FIR narrative in plain, neutral English using ONLY the events below.
Return ONLY JSON: {{"sentences": [{{"sentence": "...", "event_ids": ["...", ...]}}]}}
Every sentence must cite the event_ids (from the list below) it is based on. Do not add facts not present in these events.
Events (ordered):
{events}
"""


def draft_narrative(events: list[dict]) -> list[dict]:
    """Ollama call -> [{"sentence": str, "event_ids": [...]}]. A sentence with
    no event_ids, or with IDs that don't exist, is marked supported=False and
    kept (never dropped silently) — see Trace-QnA.docx §3."""
    if not events:
        return []
    valid_ids = {event["id"] for event in events}
    event_lines = "\n".join(
        f"- id={event['id']} time={event.get('timestamp') or 'unknown'} summary={event['summary']}"
        for event in events
    )
    prompt = DRAFT_PROMPT.format(events=event_lines)

    try:
        result = generate_json(prompt, unload_after=True)
        sentences = result.get("sentences", [])
    except LlmError:
        sentences = [{"sentence": event["summary"], "event_ids": [event["id"]]} for event in events]

    output = []
    for raw in sentences:
        event_ids = [eid for eid in raw.get("event_ids", []) if eid in valid_ids]
        output.append({
            "sentence": raw.get("sentence", ""),
            "event_ids": event_ids,
            "supported": bool(event_ids),
        })
    return output


def run_asr(case_id: str) -> None:
    """Runs faster-whisper as a subprocess for every unprocessed audio file
    in the case, storing both passes in db.narrations."""
    db = get_db()
    audio_files = list(db.files.find({"case_id": case_id, "kind": "audio"}))
    existing = {n["file_id"] for n in db.narrations.find({"case_id": case_id}, {"file_id": 1})}

    for file_record in audio_files:
        if file_record["id"] in existing:
            continue
        audio_path = os.path.join(settings.evidence_dir, file_record["sha256"])
        if not os.path.exists(audio_path):
            continue

        proc = subprocess.run(
            [sys.executable, "-m", "app.agents.asr", audio_path, settings.asr_model_size, settings.asr_device],
            capture_output=True, text=True, timeout=600,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"ASR subprocess failed for file {file_record['id']}: {proc.stderr[-2000:]}")

        import json
        result = json.loads(proc.stdout)
        narration = {
            "id": str(uuid.uuid4()),
            "case_id": case_id,
            "file_id": file_record["id"],
            "malayalam_text": result["malayalam"]["text"],
            "malayalam_segments": result["malayalam"]["segments"],
            "english_text": result["english"]["text"],
            "english_segments": result["english"]["segments"],
        }
        db.narrations.insert_one(dict(narration))
        append_entry(case_id, "ARTIFACT_DERIVED", {"artifact": "narration", "file_id": file_record["id"]})


def run_timeline(case_id: str) -> None:
    """Entry point called from app.worker._run_stage('timeline', case_id).
    Runs the deterministic parsers over text/CSV evidence, extracts narration
    events via the LLM, merges everything, and writes db.timeline_events.
    """
    db = get_db()
    raw_events: list[dict] = []

    text_files = list(db.files.find({"case_id": case_id, "kind": {"$in": ["conversation", "financial_record"]}}))
    for file_record in text_files:
        file_path = os.path.join(settings.evidence_dir, file_record["sha256"])
        if not os.path.exists(file_path) or not file_path.lower().endswith((".txt",)):
            continue
        parsed = parse_whatsapp_export(file_path) if file_record["kind"] == "conversation" else parse_bank_sms(file_path)
        for event in parsed:
            event["source_file_ids"] = [file_record["id"]]
            event["source_refs"] = [{"file_id": file_record["id"], "line": event.pop("line")}]
            # Gap Hunter's G-01 (unbacked payment) only counts a "financial_record"
            # file as a real financial record — a WhatsApp message that merely
            # mentions an amount must never count as backing evidence for itself.
            event["source_kind"] = file_record["kind"]
            raw_events.append(event)

    call_log_files = list(db.files.find({"case_id": case_id, "kind": "call_log"}))
    for file_record in call_log_files:
        file_path = os.path.join(settings.evidence_dir, file_record["sha256"])
        if not os.path.exists(file_path):
            continue
        for event in parse_call_log(file_path):
            event["source_file_ids"] = [file_record["id"]]
            event["source_refs"] = [{"file_id": file_record["id"], "line": event.pop("line")}]
            event["source_kind"] = "call_log"
            raw_events.append(event)

    for narration in db.narrations.find({"case_id": case_id}):
        narration_events = extract_events_from_narration(narration["english_segments"])
        for event in narration_events:
            event["source_file_ids"] = [narration["file_id"]]
            event["source_refs"] = [
                {"file_id": narration["file_id"], "segment": seg_id} for seg_id in event.pop("segment_ids")
            ]
            event["source_kind"] = "narration"
            raw_events.append(event)

    merged = merge_events(raw_events)
    db.timeline_events.delete_many({"case_id": case_id})
    stored_events = []
    for event in merged:
        stored = {
            "id": str(uuid.uuid4()),
            "case_id": case_id,
            "timestamp": event.get("timestamp") or datetime.utcnow().isoformat(),
            "timestamp_precision": event.get("timestamp_precision", "approximate"),
            "summary": event["summary"],
            "amount": event.get("amount"),
            "account": event.get("account"),
            "source_file_ids": event["source_file_ids"],
            "source_refs": event["source_refs"],
            "source_kinds": event.get("source_kinds", []),
        }
        stored_events.append(stored)
    if stored_events:
        db.timeline_events.insert_many([dict(e) for e in stored_events])
    append_entry(case_id, "ARTIFACT_DERIVED", {"artifact": "timeline", "event_count": len(stored_events)})


def run_draft(case_id: str) -> None:
    """Entry point called from app.worker._run_stage('draft', case_id)."""
    db = get_db()
    events = list(db.timeline_events.find({"case_id": case_id}, {"_id": 0}).sort("timestamp", 1))
    sentences = draft_narrative(events)

    last = db.drafts.find_one({"case_id": case_id}, sort=[("version", -1)])
    next_version = (last["version"] + 1) if last else 1
    draft = {
        "id": f"{case_id}-v{next_version}",
        "case_id": case_id,
        "version": next_version,
        "sentences": sentences,
        "created_at": datetime.utcnow(),
    }
    db.drafts.insert_one(dict(draft))
    append_entry(case_id, "ARTIFACT_DERIVED", {"artifact": "draft", "version": next_version})
