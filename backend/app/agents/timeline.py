"""Timeline Agent — owned by V. docs/HACKATHON_PLAN.md §6.3.

Order of reliability, most reliable first: rule parsers (WhatsApp export, bank
SMS, call-log CSV) are deterministic and run before the LLM. The LLM only
extracts events from the English ASR segments and the draft narrative, always
with JSON-schema output, and every event/sentence must cite its source or it
is dropped (events) / flagged unsupported (draft sentences) — never silently
kept. See app.agents.asr for why ASR is a subprocess, not an import here.
"""


def parse_whatsapp_export(text_path: str) -> list[dict]:
    """Both `dd/mm/yy, hh:mm -` and `[dd/mm/yy hh:mm]` formats. Each event carries {file_id, line}."""
    raise NotImplementedError


def parse_bank_sms(text_path: str) -> list[dict]:
    """Regex for amount, account, UPI ID, IMPS/NEFT, time."""
    raise NotImplementedError


def parse_call_log(csv_path: str) -> list[dict]:
    raise NotImplementedError


def extract_events_from_narration(english_segments: list[dict]) -> list[dict]:
    """Ollama call, JSON schema output. Each event must cite segment IDs; drop
    any event with no valid citation."""
    raise NotImplementedError


def merge_events(events: list[dict]) -> list[dict]:
    """Events within 5 minutes with the same amount+account merge into one,
    listing all sources. Times in IST; precision: exact | date_only | approximate."""
    raise NotImplementedError


def draft_narrative(events: list[dict]) -> list[dict]:
    """Ollama call -> [{"sentence": str, "event_ids": [...]}]. A sentence with
    no event_ids, or with IDs that don't exist, is marked supported=False and
    kept (never dropped silently) — see Trace-QnA.docx §3."""
    raise NotImplementedError


def run(case_id: str) -> None:
    """Entry point called from app.worker._run_stage for both 'asr' and 'timeline'."""
    raise NotImplementedError
