"""Timeline Agent. docs/HACKATHON_PLAN.md §6.3.

Order of reliability, most reliable first:
1. Rule parsers (app.agents.parsers): WhatsApp exports (.txt or the .zip the app
   produces), bank alerts (SMS text, SMS backup CSV), statements (PDF, Excel,
   CSV), call logs, OCR'd payment/SMS screenshots, and EXIF capture times of
   photographs. Every event cites its file and line.
2. Narration: the LLM (JSON-schema output) reads the English segments and must
   cite the segment each fact came from; facts with no valid citation are
   dropped, and amounts/names must literally appear in the cited segment.
   If the LLM is unavailable, a rule-based reader of the same segments is used.
3. Merge: narration facts attach to the evidence events they describe; the same
   payment seen in two sources (same amount and payee, within 5 minutes, or the
   same day when one side has no time) becomes one event listing all sources.

Statements and SMS backups often span months. When other evidence or the
narration dates the incident, their transactions are kept only within that
window (±2 days); the step's note says how many rows were left out.
"""
import re
from datetime import timedelta

from app import custody
from app.agents import dates, extract, parsers
from app.agents.llm_client import LlmError, generate_json
from app.db import get_db
from app.schemas import TimelineEvent, checked
from app.util import IST, money, now_iso, parse_iso

KIND_RULES = {
    "call": re.compile(r"\bcall(ed|ing|s)?\b|\bphon(e|ed)\b", re.IGNORECASE),
    "link": re.compile(r"\blinks?\b|\burl\b", re.IGNORECASE),
    "otp": re.compile(r"\botp\b|one[- ]time|password|verification code", re.IGNORECASE),
    "debit": re.compile(r"debited|taken|deducted|withdrawn|gone from|went from|lost from|money .*(several|many) times", re.IGNORECASE),
    "payment": re.compile(r"\b(sent|send|transferred|paid|pay|gave)\b", re.IGNORECASE),
    "total": re.compile(r"\b(in total|total|altogether|in all)\b", re.IGNORECASE),
}
NAME_PATTERNS = [re.compile(r"\bnamed\s+([A-Z][a-z]{2,})"), re.compile(r"\b([A-Z][a-z]{2,})\s+(?:called|phoned|asked)")]
NOT_NAMES = {"October", "September", "November", "December", "January", "February", "March", "April", "May", "June",
             "July", "August", "Bank", "KYC", "WhatsApp", "That", "The", "Then", "He", "She", "They", "In", "On", "After",
             "Before", "When", "Someone", "Somebody", "One", "Sir", "Madam"}
WINDOW_DAYS = 2

PROMPT_VERSION = "narration-facts-v1"
NARRATION_PROMPT = """You read numbered segments of a complainant's statement to the police (English translation).
For EACH segment, report only facts literally stated in that segment.
Return JSON {{"facts": [{{"segment_id": int, "date": "D Month" or null, "amount": number or null,
"kinds": [one or more of "call","link","otp","debit","payment","total"], "person": name or null}}]}}.
kinds: call = a phone call; link = a link was sent; otp = an OTP/password was shared; debit = money was
taken from the account; payment = the complainant sent/paid money; total = a stated total loss.
person = a named person other than the complainant. Do not guess. Use null when not stated.
Segments:
{segments}"""
NARRATION_SCHEMA = {
    "type": "object",
    "properties": {"facts": {"type": "array", "items": {"type": "object", "properties": {
        "segment_id": {"type": "integer"}, "date": {"type": ["string", "null"]}, "amount": {"type": ["number", "null"]},
        "kinds": {"type": "array", "items": {"type": "string"}}, "person": {"type": ["string", "null"]}},
        "required": ["segment_id", "kinds"]}}},
    "required": ["facts"],
}


def media_events(files: list[dict]) -> list[dict]:
    events = []
    for f in files:
        meta = f.get("meta") or {}
        if f.get("kind") != "media" or not meta.get("capture_time") or (f.get("dup") and not f["dup"]["canonical"]):
            continue
        place = (meta.get("geo") or "").split(" (")[0] or None
        device = meta.get("device")
        events.append(parsers.ev(at=meta["capture_time"], type="Media", actor="Complainant",
                                 action=f"Photograph taken ({f['name']}{', ' + device if device else ''})",
                                 place=place if place and not place.startswith("Outside") else None,
                                 src=[{"f": f["ev_id"], "l": 0}], source_kinds=["media"], kinds=["media"], conf=0.9))
    return events


def file_events(f: dict, complainant: str, year: int) -> tuple[list[dict], bool]:
    """Events from one file, and whether they're 'bulk' (statement / backup that
    may span far more than the incident)."""
    kind = f.get("kind")
    lines = parsers.text_lines(f)
    if not lines:
        return [], False
    if f.get("ocr") is not None:
        return parsers.parse_ocr(f, lines, year), False
    if kind == "conversation":
        return parsers.parse_whatsapp(f, lines, complainant, year), False
    if kind == "call_log":
        return parsers.parse_call_log(f, lines, year), False
    if kind == "financial_record":
        if f["ext"] in (".pdf", ".xlsx") or parsers.looks_like_statement(lines):
            return parsers.parse_statement(f, lines, year), True
        if f["ext"] == ".csv":
            reader, col = parsers.csv_rows(lines)
            if col["body"]:
                return parsers.parse_sms_csv(f, lines, year), True
        return parsers.parse_alert_lines(f, lines, year), len(lines) > 40
    return [], False


# ---------------------------------------------------------------- narration


def _seg_day(text: str | None, year: int):
    d = dates.find_date(text or "", year)
    return (d[2], d[1]) if d else None


def _person(text: str, complainant: str) -> str | None:
    for pat in NAME_PATTERNS:
        m = pat.search(text)
        if m and m.group(1) not in NOT_NAMES and m.group(1).lower() not in complainant.lower():
            return m.group(1)
    try:
        from app.agents.nlp import person_names
        for name in person_names(text):
            if name not in NOT_NAMES and name.lower() not in complainant.lower():
                return name
    except Exception:  # noqa: BLE001 - spaCy is an optional helper here
        pass
    return None


def rule_facts(segments: list[dict], complainant: str) -> list[dict]:
    facts = []
    for s in segments:
        text = s.get("en") or ""
        kinds = [k for k, rx in KIND_RULES.items() if rx.search(text)]
        amounts = extract.extract_amounts(text)
        if "total" in kinds and not amounts:
            kinds.remove("total")
        if "payment" in kinds and not amounts:
            kinds.remove("payment")
        d = dates.find_date(text, 2000)
        facts.append({"segment_id": s["id"], "date": f"{d[2]} {list(dates.MONTHS)[d[1] - 1]}" if d else None,
                      "amount": amounts[-1] if amounts else None, "kinds": kinds, "person": _person(text, complainant)})
    return facts


def llm_facts(segments: list[dict], complainant: str) -> tuple[list[dict], str]:
    lines = "\n".join(f"[{s['id']}] {s['en']}" for s in segments if s.get("en"))
    result, model = generate_json(NARRATION_PROMPT.format(segments=lines), NARRATION_SCHEMA)
    by_id = {s["id"]: s for s in segments}
    rules = {f["segment_id"]: f for f in rule_facts(segments, complainant)}
    facts = []
    for raw in result.get("facts", []):
        seg = by_id.get(raw.get("segment_id"))
        if not seg:
            continue  # no valid citation: dropped (§6.3)
        text = seg["en"]
        rule = rules[seg["id"]]
        amount = raw.get("amount")
        if amount is not None and amount not in extract.extract_amounts(text):
            amount = None  # not literally in the cited segment
        person = raw.get("person")
        if person and person not in text:
            person = None
        date = raw.get("date") if raw.get("date") and _seg_day(raw["date"], 2000) else None
        kinds = [k for k in raw.get("kinds", []) if k in KIND_RULES]
        facts.append({"segment_id": seg["id"], "date": date or rule["date"],
                      "amount": amount if amount is not None else rule["amount"],
                      "kinds": sorted(set(kinds) | set(rule["kinds"])), "person": person or rule["person"]})
    if not facts:
        raise LlmError("LLM returned no cited facts")
    return facts, model


def link_narration(facts: list[dict], events: list[dict], year: int) -> tuple[list[dict], float | None, list[str]]:
    stated_total, persons = None, []
    current_day = None
    new_events = []
    for fact in sorted(facts, key=lambda x: x["segment_id"]):
        d = _seg_day(fact.get("date"), year)
        if d:
            current_day = d
        day = current_day
        kinds, amount, person = set(fact["kinds"]), fact.get("amount"), fact.get("person")
        if person and person not in persons:
            persons.append(person)
        src = {"n": fact["segment_id"]}

        def on_day(e):
            dt = parse_iso(e["at"]).astimezone(IST)
            return day is None or (dt.day, dt.month) == day

        if "total" in kinds and amount:
            stated_total = amount
            continue
        linked = False
        if "call" in kinds and not person:
            for e in events:
                if e["type"] == "Call" and on_day(e) and e.get("direction", "incoming").startswith("in"):
                    e["src"].append(src)
                    linked = True
                    break
        if "link" in kinds or "otp" in kinds:
            for e in events:
                if e["type"] == "Message" and on_day(e) and (("link" in kinds and "link" in e["kinds"]) or ("otp" in kinds and "otp" in e["kinds"])):
                    e["src"].append(src)
                    linked = True
        if "debit" in kinds and not amount:
            for e in events:
                if e["type"] == "Transaction" and on_day(e) and "debit" in e["kinds"] and e["source_kinds"] != ["narration"]:
                    e["src"].append(src)
                    linked = True
        if amount and ("payment" in kinds or "debit" in kinds):
            match = next((e for e in events if e["type"] == "Transaction" and e.get("amount") == amount and on_day(e)
                          and "credit" not in e["kinds"]), None)
            if match:
                match["src"].append(src)
                linked = True
            else:
                at = dates.iso(year, day[1], day[0]) if day else None
                who = f" to {person}" if person else ""
                action = (f"Called and asked for {money(amount)} more; the complainant says it was sent"
                          if person and "call" in kinds else f"Payment of {money(amount)}{who} stated in the narration")
                new_events.append(parsers.ev(at=at, prec="day" if day else "approx", type="Transaction",
                                             actor=person or "Complainant", action=action, amount=amount, person=person,
                                             src=[src], source_kinds=["narration"], kinds=["payment"], conf=0.62))
                linked = True
        if not linked and person and "call" in kinds:
            at = dates.iso(year, day[1], day[0]) if day else None
            new_events.append(parsers.ev(at=at, prec="day" if day else "approx", type="Call", actor=person,
                                         action="Called the complainant (stated in the narration)", person=person,
                                         src=[src], source_kinds=["narration"], kinds=["call"], conf=0.6))
    for e in new_events:
        if e["at"] is None:
            e["at"] = max((x["at"] for x in events), default=now_iso())
    return new_events, stated_total, persons


# -------------------------------------------------------------------- merge


def _same_payment(a: dict, b: dict) -> bool:
    if a["type"] != "Transaction" or b["type"] != "Transaction" or a.get("amount") != b.get("amount"):
        return False
    if set(a["kinds"]) & {"debit", "credit"} != set(b["kinds"]) & {"debit", "credit"}:
        return False
    for k in ("to_account", "upi"):
        if a.get(k) and b.get(k) and a[k] != b[k]:
            return False
    if {s.get("f") for s in a["src"]} & {s.get("f") for s in b["src"]}:
        return False  # two rows of the same file are two payments
    ta, tb = parse_iso(a["at"]), parse_iso(b["at"])
    if a["prec"] == "exact" and b["prec"] == "exact":
        return abs((ta - tb).total_seconds()) <= 300
    return ta.astimezone(IST).date() == tb.astimezone(IST).date()


def merge(events: list[dict]) -> list[dict]:
    out: list[dict] = []
    for e in sorted(events, key=lambda x: (x["prec"] != "exact", x["at"])):
        twin = next((o for o in out if _same_payment(o, e)), None)
        if twin:
            twin["src"] += [s for s in e["src"] if s not in twin["src"]]
            twin["source_kinds"] = sorted(set(twin["source_kinds"]) | set(e["source_kinds"]))
            for k in ("to_account", "upi", "ifsc", "account"):
                twin[k] = twin.get(k) or e.get(k)
            twin["conf"] = max(twin["conf"], e["conf"])
        else:
            out.append(e)
    return out


def _window(events: list[dict], facts: list[dict], year: int):
    days = [parse_iso(e["at"]).astimezone(IST).date() for e in events]
    for f in facts:
        d = dates.find_date(f.get("date") or "", year)
        if d:
            days.append(parse_iso(dates.iso(*d)).date())
    if not days:
        return None
    return min(days) - timedelta(days=WINDOW_DAYS), max(days) + timedelta(days=WINDOW_DAYS)


def build(case_id: str, *, use_llm: bool = True) -> str:
    db = get_db()
    case = db.cases.find_one({"id": case_id}) or {}
    complainant = case.get("complainant", {}).get("name", "")
    year = parse_iso(case.get("created_at") or now_iso()).astimezone(IST).year
    files = list(db.files.find({"case_id": case_id, "status": "accepted"}).sort("uploaded_at", 1))
    focused, bulk = [], []
    for f in files:
        if f.get("narration") or (f.get("dup") and not f["dup"]["canonical"]):
            continue
        evs, is_bulk = file_events(f, complainant, year)
        (bulk if is_bulk else focused).extend(evs)
    focused += media_events(files)

    narration = db.narrations.find_one({"case_id": case_id}) or {}
    segments = narration.get("segments") or []
    note_src = "no narration"
    facts: list[dict] = []
    if segments:
        cached = case.get("analysis", {}).get("narration_facts")
        if not use_llm and cached is not None:
            facts, note_src = cached, case["analysis"].get("narration_model", "rules")
        else:
            try:
                facts, model = llm_facts(segments, complainant)
                note_src = f"narration read by {model}"
            except LlmError:
                facts, note_src = rule_facts(segments, complainant), "narration read by rules (LLM unavailable)"

    left_out = 0
    win = _window(focused, facts, year)
    if win and bulk:
        kept = [e for e in bulk if win[0] <= parse_iso(e["at"]).astimezone(IST).date() <= win[1]]
        left_out = len(bulk) - len(kept)
        bulk = kept
    events = merge(focused + bulk)
    new_events, stated_total, persons = link_narration(facts, events, year)
    events = sorted(events + new_events, key=lambda x: x["at"])
    for i, e in enumerate(events, start=1):
        e["id"], e["case_id"] = f"E{i}", case_id
    db.timeline_events.delete_many({"case_id": case_id})
    if events:
        db.timeline_events.insert_many([dict(checked(TimelineEvent, e)) for e in events])
    db.cases.update_one({"id": case_id}, {"$set": {
        "analysis.stated_total": stated_total, "analysis.persons": persons,
        "analysis.narration_facts": facts, "analysis.narration_model": note_src}})
    custody.derived(case_id, "timeline", [{k: v for k, v in e.items() if k != "_id"} for e in events],
                    model=note_src, prompt=PROMPT_VERSION if segments else "none")
    sources = {s.get("f") or "N" for e in events for s in e["src"]}
    note = f"{len(events)} events from {len(sources)} sources; {note_src}"
    if left_out:
        note += f"; {left_out} statement/backup rows outside the incident dates left out"
    unread = [f["ev_id"] for f in files if not f.get("narration") and f.get("kind") in ("financial_record", "conversation", "call_log")
              and not any(s.get("f") == f["ev_id"] for e in events for s in e["src"])]
    if unread:
        note += f"; no events found in {', '.join(unread)} (check the file under Manifest)"
    return note


def events_for(case_id: str) -> list[dict]:
    return list(get_db().timeline_events.find({"case_id": case_id}, {"_id": 0}).sort("at", 1))
